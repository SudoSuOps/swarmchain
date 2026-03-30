"""SwarmOS Calibration — 50-pair test run with real measurements.

Runs a small sample through the pipeline to measure:
- Actual latency per judge and recorder call
- Actual GPU power draw under load
- Actual honey rate for this domain
- Compares measured vs flight sheet estimates
"""
from __future__ import annotations

import asyncio
import json
import re
import statistics
import time
from pathlib import Path

import httpx

from . import config
from .hardware.power import read_gpu_power
from .models import CalibrationReport, FlightSheet


JUDGE_SYS = config.JUDGE_SYSTEM_PROMPT
RECORDER_SYS = config.RECORDER_SYSTEM_PROMPT


async def _call_model(client: httpx.AsyncClient, port: int, system: str, user: str, max_tokens: int = 4096):
    try:
        start = time.monotonic()
        resp = await client.post(
            f"http://{config.API_HOST}:{port}/v1/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens, "temperature": 0.1,
            },
            timeout=180,
        )
        latency = time.monotonic() - start
        if resp.status_code != 200:
            return "", round(latency * 1000)
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content", "") or ""
        if "<think>" in content:
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if not content.strip() and msg.get("reasoning_content"):
            content = msg["reasoning_content"]
        return content, round(latency * 1000)
    except Exception:
        return "", 0


def _parse_verdict(text: str):
    """Parse judge output. Score-only classification. 3-tier: royal-jelly / honey / wax."""
    score, verdict = 0.0, "FAIL"
    for line in text.split("\n"):
        ll = line.strip().lower()
        if ll.startswith("verdict:"):
            verdict = "PASS" if "pass" in ll else "FAIL"
        if "total_score:" in ll or "total score:" in ll:
            nums = re.findall(r"\d+", line)
            if nums:
                score = min(int(nums[0]), 100) / 100.0
    # Score-only classification — no verdict gating, no guessing
    if score >= 0.75:
        classification = "royal-jelly"
    elif score >= 0.50:
        classification = "honey"
    else:
        classification = "propolis"
    return verdict, score, classification


async def _run_calibration(
    pairs: list[dict],
    judge_port: int,
    recorder_port: int,
    domain: str,
) -> dict:
    """Run calibration sample and collect measurements."""
    judge_latencies = []
    recorder_latencies = []
    royal_jelly = honey = wax = 0

    async with httpx.AsyncClient() as client:
        for pair in pairs:
            msgs = pair.get("messages", [])
            user_prompt = next((m["content"] for m in msgs if m.get("role") == "user"), "")
            answer = next((m["content"] for m in msgs if m.get("role") == "assistant"), "")
            if not user_prompt or not answer:
                continue

            # Judge
            judge_input = f"DOMAIN: {domain}\n\nQUESTION:\n{user_prompt[:1500]}\n\nANSWER:\n{answer[:2000]}"
            judge_text, judge_ms = await _call_model(client, judge_port, JUDGE_SYS, judge_input)
            if judge_ms > 0:
                judge_latencies.append(judge_ms)

            verdict, score, cls = _parse_verdict(judge_text)

            # Recorder
            rec_input = f"PAIR_ID: cal\nDOMAIN: {domain}\nVERDICT: {verdict}\nSCORE: {score:.2f}\nCLASS: {cls}\nQ:\n{user_prompt[:500]}\nA:\n{answer[:800]}\nJUDGE:\n{judge_text[:400]}"
            rec_text, rec_ms = await _call_model(client, recorder_port, RECORDER_SYS, rec_input, max_tokens=512)
            if rec_ms > 0:
                recorder_latencies.append(rec_ms)

            if cls == "royal-jelly": royal_jelly += 1
            elif cls == "honey": honey += 1
            else: wax += 1
            else: propolis += 1

    total = honey + jelly + propolis
    return {
        "judge_latencies": judge_latencies,
        "recorder_latencies": recorder_latencies,
        "royal_jelly": royal_jelly, "honey": honey, "propolis": wax,
        "total": total,
        "royal_jelly_rate": royal_jelly / max(total, 1),
    }


def run_calibration(
    job_id: str,
    flight_sheet: FlightSheet,
    input_path: str,
    sample_size: int = 50,
) -> CalibrationReport:
    """Run calibration and produce a CalibrationReport."""
    # Load sample pairs
    pairs = []
    p = Path(input_path)
    if p.exists():
        with open(p) as f:
            for i, line in enumerate(f):
                if line.strip():
                    pairs.append(json.loads(line))
                if len(pairs) >= sample_size:
                    break

    if not pairs:
        return CalibrationReport(
            job_id=job_id,
            flight_sheet_id=flight_sheet.sheet_id,
            warnings=["No pairs found for calibration"],
        )

    # Pick first available judge and recorder port
    judge_port = None
    recorder_port = None
    for ga in flight_sheet.gpu_assignments:
        if ga.role == "judge" and ga.ports:
            judge_port = ga.ports[0]
        elif ga.role == "recorder" and ga.ports:
            recorder_port = ga.ports[0]
    for ca in flight_sheet.cpu_assignments:
        if ca.role == "recorder" and ca.ports and not recorder_port:
            recorder_port = ca.ports[0]

    if not judge_port or not recorder_port:
        return CalibrationReport(
            job_id=job_id,
            flight_sheet_id=flight_sheet.sheet_id,
            warnings=["No judge or recorder port available"],
        )

    # Measure GPU power before
    power_before = read_gpu_power()

    # Run the calibration
    results = asyncio.run(_run_calibration(pairs, judge_port, recorder_port, flight_sheet.domain))

    # Measure GPU power after (under load, last reading)
    power_after = read_gpu_power()

    # Compute statistics
    jl = results["judge_latencies"]
    rl = results["recorder_latencies"]

    judge_mean = statistics.mean(jl) if jl else 0
    judge_p95 = sorted(jl)[int(len(jl) * 0.95)] if len(jl) >= 2 else judge_mean
    rec_mean = statistics.mean(rl) if rl else 0
    rec_p95 = sorted(rl)[int(len(rl) * 0.95)] if len(rl) >= 2 else rec_mean

    # Hashrate from latencies (single instance)
    judge_hashrate = 60000 / judge_mean if judge_mean > 0 else 0  # per minute from ms
    recorder_hashrate = 60000 / rec_mean if rec_mean > 0 else 0

    # Scale by instance count from flight sheet
    total_judge_instances = sum(a.instance_count for a in flight_sheet.gpu_assignments if a.role == "judge")
    total_recorder_instances = (
        sum(a.instance_count for a in flight_sheet.gpu_assignments if a.role == "recorder")
        + sum(a.instance_count for a in flight_sheet.cpu_assignments if a.role == "recorder")
    )
    scaled_judge = judge_hashrate * total_judge_instances
    scaled_recorder = recorder_hashrate * total_recorder_instances

    # Warnings
    warnings = []
    est_hashrate = flight_sheet.totals.total_estimated_hashrate
    measured_bottleneck = min(scaled_judge, scaled_recorder) if scaled_judge > 0 and scaled_recorder > 0 else 0
    if est_hashrate > 0 and measured_bottleneck > 0:
        variance = abs(measured_bottleneck - est_hashrate) / est_hashrate
        if variance > 0.20:
            warnings.append(f"Hashrate variance {variance:.0%} — measured {measured_bottleneck:.1f} vs estimated {est_hashrate:.1f}")

    return CalibrationReport(
        job_id=job_id,
        flight_sheet_id=flight_sheet.sheet_id,
        sample_size=len(pairs),
        judge_latency_mean_ms=round(judge_mean, 1),
        judge_latency_p95_ms=round(judge_p95, 1),
        recorder_latency_mean_ms=round(rec_mean, 1),
        recorder_latency_p95_ms=round(rec_p95, 1),
        measured_judge_hashrate=round(scaled_judge, 1),
        measured_recorder_hashrate=round(scaled_recorder, 1),
        gpu_power_mean_w=power_after,
        cpu_load_mean=0,  # Would need /proc/loadavg
        sample_honey_rate=results["royal_jelly_rate"],
        sample_honey=results["royal_jelly"],
        sample_jelly=results["honey"],
        sample_propolis=results["propolis"],
        warnings=warnings,
    )


def format_calibration(report: CalibrationReport) -> str:
    """Human-readable calibration output."""
    lines = [
        f"═══ CALIBRATION REPORT ═══",
        f"Job:     {report.job_id}",
        f"Sheet:   {report.flight_sheet_id}",
        f"Sample:  {report.sample_size} pairs",
        "",
        "LATENCY:",
        f"  Judge:     {report.judge_latency_mean_ms:.0f}ms mean / {report.judge_latency_p95_ms:.0f}ms p95",
        f"  Recorder:  {report.recorder_latency_mean_ms:.0f}ms mean / {report.recorder_latency_p95_ms:.0f}ms p95",
        "",
        "THROUGHPUT (scaled to fleet):",
        f"  Judge:     {report.measured_judge_hashrate:.1f} verdicts/min",
        f"  Recorder:  {report.measured_recorder_hashrate:.1f} deeds/min",
        "",
        "QUALITY (sample):",
        f"  Royal Jelly: {report.sample_honey} ({report.sample_honey_rate:.1%})",
        f"  Honey:       {report.sample_jelly}",
        f"  Wax:         {report.sample_propolis}",
        "",
        "GPU POWER:",
    ]
    for idx, watts in sorted(report.gpu_power_mean_w.items()):
        lines.append(f"  GPU {idx}: {watts:.1f}W")

    if report.warnings:
        lines.append("\nWARNINGS:")
        for w in report.warnings:
            lines.append(f"  ! {w}")

    return "\n".join(lines)
