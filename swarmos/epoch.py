"""SwarmOS Epoch Runner — execute validation from a signed POJ.

Decoupled architecture:
  Phase 1: Judges dump verdicts to bin (JSONL) at GPU speed
  Phase 2: Recorder polls bin, records deeds at refinery speed
  No coupling. No blocking. Miners mine, refinery refines.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import config, state
from .models import EpochProgress, FlightSheet, POJ

log = logging.getLogger("swarmos.epoch")


# ── Model server management ───────────────────────────────


def _launch_server(gguf: str, port: int, gpu_index: int | None, threads: int, ctx_size: int = 4096) -> subprocess.Popen:
    """Launch a llama-server instance."""
    cmd = [
        str(config.LLAMA_SERVER),
        "-m", gguf,
        "--host", "0.0.0.0",
        "--port", str(port),
        "--ctx-size", str(ctx_size),
        "--parallel", "1",
        "--threads", str(threads),
    ]
    if gpu_index is not None:
        cmd.extend(["--n-gpu-layers", "99"])
    else:
        cmd.extend(["--n-gpu-layers", "0"])

    env = os.environ.copy()
    if gpu_index is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
    else:
        env["CUDA_VISIBLE_DEVICES"] = ""

    logfile = open(f"/tmp/swarmos-server-{port}.log", "w")
    proc = subprocess.Popen(cmd, stdout=logfile, stderr=logfile, env=env)
    log.info("Launched server on :%d (PID %d, GPU=%s)", port, proc.pid, gpu_index)
    return proc


async def _wait_healthy(ports: list[int], timeout: int = 120):
    """Wait for all model servers to report healthy."""
    async with httpx.AsyncClient() as client:
        deadline = time.monotonic() + timeout
        for port in ports:
            while time.monotonic() < deadline:
                try:
                    resp = await client.get(f"http://localhost:{port}/health", timeout=3)
                    if resp.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(2)
            else:
                log.warning("Server on :%d did not become healthy in %ds", port, timeout)


# ── Inference helpers ──────────────────────────────────────


async def _call_model(client: httpx.AsyncClient, port: int, system: str, user: str, max_tokens: int = 4096):
    try:
        start = time.monotonic()
        resp = await client.post(
            f"http://localhost:{port}/v1/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens, "temperature": 0.1,
            },
            timeout=180,
        )
        latency = time.monotonic() - start
        if resp.status_code != 200:
            return "", 0
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content", "") or ""
        if "<think>" in content:
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if not content.strip() and msg.get("reasoning_content"):
            content = msg["reasoning_content"]
        return content, round(latency * 1000)
    except Exception:
        return "", 0


async def _api_req(client: httpx.AsyncClient, method: str, path: str, **kwargs):
    headers = {"X-API-Key": config.API_KEY}
    try:
        resp = await client.request(method, f"{config.API_URL}{path}", headers=headers, timeout=30, **kwargs)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None


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


# ── Judge phase ────────────────────────────────────────────


async def _judge_worker(worker_id, port, input_q, bin_file, write_lock, stats, client):
    """Dedicated judge — pulls pairs, renders verdict, dumps to bin."""
    while True:
        item = await input_q.get()
        if item is None:
            break
        idx, pair, domain = item
        msgs = pair.get("messages", [])
        up = next((m["content"] for m in msgs if m.get("role") == "user"), "")
        oa = next((m["content"] for m in msgs if m.get("role") == "assistant"), "")
        if not up or not oa:
            async with write_lock:
                stats["skipped"] += 1
            input_q.task_done()
            continue

        jt, jms = await _call_model(client, port, config.JUDGE_SYSTEM_PROMPT,
                                     f"DOMAIN: {domain}\n\nQUESTION:\n{up[:1500]}\n\nANSWER:\n{oa[:2000]}")
        v, s, c = _parse_verdict(jt)

        entry = {
            "pair_index": idx, "domain": domain, "verdict": v, "score": s,
            "classification": c, "judge_reasoning": jt[:500], "judge_ms": jms,
            "judge_port": port, "user_prompt": up, "original_answer": oa,
            "skill": pair.get("skill", pair.get("metadata", {}).get("skill", "")),
            "pair": pair, "judged_at": datetime.now(timezone.utc).isoformat(),
        }
        async with write_lock:
            with open(bin_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
            stats["judged"] += 1
            if c == "honey": stats["honey"] += 1
            elif c == "jelly": stats["jelly"] += 1
            else: stats["propolis"] += 1
        input_q.task_done()


async def run_judge_phase(
    pairs: list[dict], domain: str, judge_ports: list[int],
    bin_file: Path, start_idx: int = 0,
) -> dict:
    """Run all judges, dump verdicts to bin. Returns stats."""
    stats = {"judged": 0, "honey": 0, "jelly": 0, "propolis": 0, "skipped": 0}
    input_q = asyncio.Queue(maxsize=100)
    write_lock = asyncio.Lock()
    start_time = time.monotonic()

    async with httpx.AsyncClient() as client:
        workers = [
            asyncio.create_task(_judge_worker(i, judge_ports[i % len(judge_ports)], input_q, bin_file, write_lock, stats, client))
            for i in range(len(judge_ports))
        ]

        # Feed
        for i, pair in enumerate(pairs):
            await input_q.put((start_idx + i, pair, domain))
        for _ in range(len(judge_ports)):
            await input_q.put(None)

        await asyncio.gather(*workers)

    stats["wall_sec"] = round(time.monotonic() - start_time, 1)
    stats["rate"] = round(stats["judged"] / (stats["wall_sec"] / 60), 1) if stats["wall_sec"] > 0 else 0
    return stats


# ── Record phase ───────────────────────────────────────────


async def _record_worker(worker_id, port, work_q, output_dir, write_lock, stats, client):
    """Recorder worker — pulls judged entries, writes deeds, seals blocks."""
    receipts_file = output_dir / "receipts.jsonl"
    while True:
        item = await work_q.get()
        if item is None:
            break
        entry = item
        idx = entry["pair_index"]
        domain = entry["domain"]
        v, s, c = entry["verdict"], entry["score"], entry["classification"]
        jt, jms = entry["judge_reasoning"], entry["judge_ms"]
        up, oa = entry["user_prompt"], entry["original_answer"]
        pair = entry["pair"]

        ri = f"PAIR_ID: {idx}\nDOMAIN: {domain}\nVERDICT: {v}\nSCORE: {s:.2f}\nCLASS: {c}\nQ:\n{up[:500]}\nA:\n{oa[:800]}\nJUDGE:\n{jt[:400]}"
        rt, rms = await _call_model(client, port, config.RECORDER_SYSTEM_PROMPT, ri, max_tokens=512)

        bl = await _api_req(client, "POST", "/blocks/open", json={
            "task_id": f"validate-{domain}-{idx:06d}", "domain": domain,
            "reward_pool": 100, "max_attempts": 5, "time_limit_sec": 3600,
            "task_payload": {"pair_index": idx, "user_prompt": up[:2000], "original_answer": oa[:3000]},
            "metadata": {"session_id": f"swarmos-{domain}", "sequence_number": idx + 1},
        })
        bid = bl["block_id"] if bl else "?"

        await _api_req(client, "POST", "/attempts", json={
            "block_id": bid, "node_id": "9b-base-judge", "strategy": "direct_verdict",
            "method": "llm_inference", "output_json": {"verdict": v, "score": s, "classification": c},
            "score": s, "energy_cost": jms / 1000, "latency_ms": jms,
        })
        await _api_req(client, "POST", "/attempts", json={
            "block_id": bid, "node_id": "deed-recorder", "strategy": "ledger_record",
            "method": "llm_inference", "output_json": {"ledger_entry": rt, "classification": c, "score": s},
            "score": s, "energy_cost": rms / 1000, "latency_ms": rms,
        })
        await _api_req(client, "POST", f"/blocks/{bid}/finalize", json={"force": True})

        result = {
            "pair_index": idx, "block_id": bid, "domain": domain, "status": "verified",
            "verdict": v, "score": s, "classification": c,
            "judge_reasoning": jt[:300], "ledger_record": rt[:300],
            "energy_ms": jms + rms, "sealed_at": datetime.now(timezone.utc).isoformat(),
        }
        async with write_lock:
            with open(receipts_file, "a") as f:
                f.write(json.dumps(result) + "\n")
            with open(output_dir / f"{c}.jsonl", "a") as f:
                f.write(json.dumps({**pair, "swarmchain_validation": result}) + "\n")
            stats["recorded"] += 1
            if c == "honey": stats["r_honey"] += 1
            elif c == "jelly": stats["r_jelly"] += 1
            else: stats["r_propolis"] += 1
        work_q.task_done()


async def run_record_phase(
    bin_file: Path, output_dir: Path, recorder_ports: list[int],
    existing_receipts: int = 0,
) -> dict:
    """Run Recorder recorders, polling the bin. Returns stats."""
    stats = {"recorded": 0, "r_honey": 0, "r_jelly": 0, "r_propolis": 0}
    work_q = asyncio.Queue(maxsize=len(recorder_ports) * 2)
    write_lock = asyncio.Lock()
    start_time = time.monotonic()

    # Register nodes
    async with httpx.AsyncClient() as client:
        for node in ["9b-base-judge", "deed-recorder"]:
            await _api_req(client, "POST", "/nodes/register",
                          json={"node_id": node, "hardware": "validation", "model": node})

    async with httpx.AsyncClient() as client:
        workers = [
            asyncio.create_task(_record_worker(i, recorder_ports[i], work_q, output_dir, write_lock, stats, client))
            for i in range(len(recorder_ports))
        ]

        # Poll bin for entries
        cursor = 0
        idle_rounds = 0
        while True:
            if bin_file.exists():
                bin_lines = open(bin_file).readlines()
                new_entries = []
                for i in range(cursor, len(bin_lines)):
                    try:
                        new_entries.append(json.loads(bin_lines[i]))
                    except Exception:
                        pass
                if new_entries:
                    idle_rounds = 0
                    for entry in new_entries:
                        await work_q.put(entry)
                    cursor = len(bin_lines)
                else:
                    idle_rounds += 1
            else:
                idle_rounds += 1

            receipts_file = output_dir / "receipts.jsonl"
            recorded = sum(1 for _ in open(receipts_file)) if receipts_file.exists() else 0
            if idle_rounds > 60:  # 5 min idle
                if recorded >= cursor + existing_receipts:
                    break
            await asyncio.sleep(5)

        for _ in range(len(recorder_ports)):
            await work_q.put(None)
        await asyncio.gather(*workers)

    stats["wall_sec"] = round(time.monotonic() - start_time, 1)
    stats["rate"] = round(stats["recorded"] / (stats["wall_sec"] / 60), 1) if stats["wall_sec"] > 0 else 0
    return stats


# ── Full epoch execution ──────────────────────────────────


def run_epoch(job_id: str, resume: bool = False):
    """Execute a full epoch from a signed POJ.

    This launches both judge and record phases as background processes,
    then monitors progress. REQUIRES a valid permit.
    """
    from .permit import verify_permit

    # ── PERMIT GATE — mandatory, no exceptions ──────────────
    valid, reason = verify_permit(job_id)
    if not valid:
        raise ValueError(
            f"No permit issued. Review the flight sheet and issue a permit first.\n"
            f"Detail: {reason}\n"
            f"Run: swarmos permit issue {job_id}"
        )
    log.info("Permit verified for job %s", job_id)

    poj = state.load_poj(job_id)
    fs = state.load_flightsheet(job_id)
    if not poj or not fs:
        raise ValueError(f"Job {job_id}: missing POJ or flight sheet")
    if not poj.signed:
        raise ValueError(f"Job {job_id}: POJ not signed")
    if not fs.locked:
        raise ValueError(f"Job {job_id}: flight sheet not locked")

    domain = poj.domain
    output_dir = config.HONEY_DIR / domain / "validated"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load pairs
    pairs = []
    input_path = fs.input_path
    if not input_path:
        domain_dir = config.HONEY_DIR / domain
        for f in sorted(domain_dir.glob("*.jsonl")):
            if "validated" not in str(f):
                input_path = str(f)
                break

    if input_path and Path(input_path).exists():
        with open(input_path) as f:
            for line in f:
                if line.strip():
                    pairs.append(json.loads(line))

    if not pairs:
        raise ValueError(f"No pairs found at {input_path}")

    # Resume support
    bin_file = output_dir / "judged.jsonl"
    receipts_file = output_dir / "receipts.jsonl"
    existing_receipts = sum(1 for _ in open(receipts_file)) if receipts_file.exists() else 0
    existing_judged = sum(1 for _ in open(bin_file)) if bin_file.exists() else 0

    skip = max(existing_judged, existing_receipts)
    if resume and skip > 0:
        log.info("Resuming from pair %d (judged=%d, receipts=%d)", skip, existing_judged, existing_receipts)
        pairs = pairs[skip:]

    # Collect all ports from flight sheet
    judge_ports = []
    recorder_ports = []
    for ga in fs.gpu_assignments:
        if ga.role == "judge":
            judge_ports.extend(ga.ports)
        elif ga.role == "recorder":
            recorder_ports.extend(ga.ports)
    for ca in fs.cpu_assignments:
        if ca.role == "recorder":
            recorder_ports.extend(ca.ports)

    log.info("EPOCH START: %s | %d pairs | %d judges | %d recorders",
             domain, len(pairs), len(judge_ports), len(recorder_ports))

    # Save initial progress
    progress = EpochProgress(job_id=job_id, domain=domain, pair_count=poj.pair_count)
    state.save_progress(job_id, progress)

    # Run judge phase (blocking — fills the bin)
    log.info("=== JUDGE PHASE ===")
    judge_stats = asyncio.run(run_judge_phase(pairs, domain, judge_ports, bin_file, start_idx=skip))
    log.info("Judges done: %d verdicts in %.1fs (%.1f/min)",
             judge_stats["judged"], judge_stats["wall_sec"], judge_stats["rate"])

    # Run record phase (blocking — drains the bin)
    log.info("=== RECORD PHASE ===")
    record_stats = asyncio.run(run_record_phase(bin_file, output_dir, recorder_ports, existing_receipts))
    log.info("Recorders done: %d deeds in %.1fs (%.1f/min)",
             record_stats["recorded"], record_stats["wall_sec"], record_stats["rate"])

    # Update progress
    progress.judged = judge_stats["judged"] + existing_judged
    progress.recorded = record_stats["recorded"] + existing_receipts
    progress.honey = judge_stats["honey"]
    progress.jelly = judge_stats["jelly"]
    progress.propolis = judge_stats["propolis"]
    progress.judge_rate = judge_stats["rate"]
    progress.recorder_rate = record_stats["rate"]
    progress.elapsed_sec = judge_stats["wall_sec"] + record_stats["wall_sec"]
    state.save_progress(job_id, progress)

    log.info("═══ EPOCH COMPLETE — %d deeds | H:%d J:%d P:%d ═══",
             progress.recorded, progress.honey, progress.jelly, progress.propolis)

    return progress
