#!/usr/bin/env python3
"""
SwarmChain Validation Orchestrator v5 — Direct Judge
=====================================================
No inspector. 9B judges read the pair directly. Katniss records.
Two steps per block. Maximum efficiency. One GPU.

"The 4B inspector was a passthrough. The 9B does all the work."
"""
import asyncio
import json
import time
import argparse
import logging
import os
import re
from pathlib import Path
from datetime import datetime, timezone
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("orchestrator-v5")

RAILS = os.environ.get("SWARM_RAILS_HOST", "localhost")
API_URL = os.environ.get("SWARM_API_URL", f"http://{RAILS}:8080")
API_KEY = os.environ.get("SWARM_API_KEY", "")

JUDGE_PORTS = [8201, 8202, 8203, 8204, 8205, 8206, 8207, 8208, 8209, 8220, 8221, 8222]
RECORDER_PORT = 8097

JUDGE_SYSTEM = """You are the final quality judge for AI training pairs.
Output EXACTLY this format — nothing else:

VERDICT: PASS or FAIL
TOTAL_SCORE: <number 0-100>
CLASSIFICATION: propolis or jelly or honey
REASONING: <1-2 sentences max>

Scoring guide:
  honey (80-100): High quality, accurate, actionable, well-structured
  jelly (40-79): Partial quality, some gaps, usable with improvement
  propolis (0-39): Low quality, inaccurate, or too generic

Be decisive. Be brief. No extra commentary."""

RECORDER_SYSTEM = """You are the SwarmChain Recorder — Katniss.
Write a brief title deed:

PAIR_ID: <id>
DOMAIN: <domain>
PAIR_SUMMARY: <one sentence>
VERDICT: <PASS/FAIL>
SCORE: <0-100>
CLASSIFICATION: <honey/jelly/propolis>
WHY_SEALED: <2 sentences>
RECORD_STATUS: SEALED"""

_judge_idx = 0
_lock = asyncio.Lock()

async def next_judge():
    global _judge_idx
    async with _lock:
        port = JUDGE_PORTS[_judge_idx % len(JUDGE_PORTS)]
        _judge_idx += 1
        return port


async def call_model(client, port, system, user_content, max_tokens=4096):
    try:
        start = time.monotonic()
        resp = await client.post(f"http://{RAILS}:{port}/v1/chat/completions", json={
            "model": "default",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
            "max_tokens": max_tokens, "temperature": 0.1,
        }, timeout=180)
        latency = time.monotonic() - start
        if resp.status_code != 200: return "", 0
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content", "") or ""
        if "<think>" in content:
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        if not content.strip() and msg.get("reasoning_content"):
            content = msg["reasoning_content"]
        return content, round(latency * 1000)
    except:
        return "", 0


async def api_req(client, method, path, **kwargs):
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        resp = await client.request(method, f"{API_URL}{path}", headers=headers, timeout=30, **kwargs)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None


def parse_verdict(text):
    score, classification, verdict = 0.0, "propolis", "FAIL"
    for line in text.split("\n"):
        ll = line.strip().lower()
        if ll.startswith("verdict:"): verdict = "PASS" if "pass" in ll else "FAIL"
        if "total_score:" in ll or "total score:" in ll:
            nums = re.findall(r'\d+', line)
            if nums: score = min(int(nums[0]), 100) / 100.0
        if ll.startswith("classification:"):
            if "propolis" in ll: classification = "propolis"
            elif "jelly" in ll: classification = "jelly"
            elif "honey" in ll: classification = "honey"
        if ll.startswith("score:") and score == 0.0:
            nums = re.findall(r'\d+', line)
            if nums: score = min(int(nums[0]), 100) / 100.0
    if score > 0 and classification == "propolis":
        if score >= 0.80: classification = "honey"
        elif score >= 0.40: classification = "jelly"
    # No guessing — if score can't be parsed, stays 0.0/propolis
    return verdict, score, classification


async def validate_one(client, pair, idx, domain, session):
    """Two steps: judge reads pair directly → Katniss records."""
    msgs = pair.get("messages", [])
    user_prompt = next((m["content"] for m in msgs if m.get("role") == "user"), "")
    original_answer = next((m["content"] for m in msgs if m.get("role") == "assistant"), "")
    if not user_prompt or not original_answer:
        return {"pair_index": idx, "status": "skip"}

    judge_port = await next_judge()

    # Open block
    block = await api_req(client, "POST", "/blocks/open", json={
        "task_id": f"validate-{domain}-{idx:06d}", "domain": domain,
        "reward_pool": 100, "max_attempts": 5, "time_limit_sec": 3600,
        "task_payload": {
            "validation_type": "direct_judge",
            "domain": domain, "pair_index": idx,
            "skill": pair.get("skill", pair.get("metadata", {}).get("skill", "")),
            "user_prompt": user_prompt[:2000],
            "original_answer": original_answer[:3000],
        },
        "metadata": {"session_id": session, "sequence_number": idx + 1},
    })
    if not block: return {"pair_index": idx, "status": "error", "reason": "block open failed"}
    block_id = block["block_id"]

    # JUDGE — reads pair directly
    judge_input = f"DOMAIN: {domain}\n\nQUESTION:\n{user_prompt[:1500]}\n\nANSWER:\n{original_answer[:2000]}"
    judge_text, judge_ms = await call_model(client, judge_port, JUDGE_SYSTEM, judge_input)
    verdict, score, classification = parse_verdict(judge_text)

    await api_req(client, "POST", "/attempts", json={
        "block_id": block_id, "node_id": "9b-base-judge",
        "strategy": "direct_verdict", "method": "llm_inference",
        "output_json": {"verdict": verdict, "score": score, "classification": classification, "reasoning": judge_text},
        "score": score, "energy_cost": judge_ms/1000, "latency_ms": judge_ms,
    })

    # KATNISS RECORDS
    record_input = f"PAIR_ID: {idx}\nDOMAIN: {domain}\nVERDICT: {verdict}\nSCORE: {score:.2f}\nCLASS: {classification}\nQ:\n{user_prompt[:500]}\nA:\n{original_answer[:800]}\nJUDGE:\n{judge_text[:400]}"
    record_text, record_ms = await call_model(client, RECORDER_PORT, RECORDER_SYSTEM, record_input)

    await api_req(client, "POST", "/attempts", json={
        "block_id": block_id, "node_id": "katniss-recorder",
        "strategy": "ledger_record", "method": "llm_inference",
        "output_json": {"ledger_entry": record_text, "classification": classification, "score": score},
        "score": score, "energy_cost": record_ms/1000, "latency_ms": record_ms,
    })

    await api_req(client, "POST", f"/blocks/{block_id}/finalize", json={"force": True})

    return {
        "pair_index": idx, "block_id": block_id, "domain": domain,
        "status": "verified", "verdict": verdict, "score": score,
        "classification": classification,
        "judge_reasoning": judge_text[:300], "ledger_record": record_text[:300],
        "energy_ms": judge_ms + record_ms,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
    }


async def run(args):
    output_dir = Path(f"/data1/swarm-honey/{args.domain}/validated")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all JSONL files in domain
    domain_dir = Path(f"/data1/swarm-honey/{args.domain}")
    input_files = sorted(domain_dir.glob("*.jsonl"))
    input_files = [f for f in input_files if "validated" not in str(f)]

    pairs = []
    for f in input_files:
        for line in open(f):
            if line.strip():
                pairs.append(json.loads(line))
    total = len(pairs)

    receipts_file = output_dir / "receipts.jsonl"
    existing = sum(1 for _ in open(receipts_file)) if receipts_file.exists() else 0
    if existing > 0:
        log.info("Resuming from pair %d", existing)
        pairs = pairs[existing:]
    if args.limit: pairs = pairs[:args.limit]
    log.info("Epoch 2: %s | %d pairs | %d judges | direct mode", args.domain, len(pairs), len(JUDGE_PORTS))

    async with httpx.AsyncClient() as client:
        for node in ["9b-base-judge", "katniss-recorder"]:
            await api_req(client, "POST", "/nodes/register", json={"node_id": node, "hardware": "validation", "model": node})

    honey, jelly, propolis, skipped = 0, 0, 0, 0
    start_time = time.monotonic()
    write_lock = asyncio.Lock()

    async def process(client, pair, idx):
        nonlocal honey, jelly, propolis, skipped
        result = await validate_one(client, pair, idx, args.domain, args.session)
        async with write_lock:
            with open(receipts_file, "a") as f:
                f.write(json.dumps(result) + "\n")
            if result.get("status") == "skip":
                skipped += 1; return
            cls = result["classification"]
            with open(output_dir / f"{cls}.jsonl", "a") as f:
                f.write(json.dumps({**pair, "swarmchain_validation": result}) + "\n")
            if cls == "honey": honey += 1
            elif cls == "jelly": jelly += 1
            else: propolis += 1

    async with httpx.AsyncClient() as client:
        BATCH = min(len(JUDGE_PORTS), 10)  # process 5 at a time
        for batch_start in range(0, len(pairs), BATCH):
            batch = pairs[batch_start:batch_start + BATCH]
            tasks = [process(client, p, existing + batch_start + i) for i, p in enumerate(batch)]
            await asyncio.gather(*tasks)

            done = batch_start + len(batch)
            if done % 10 == 0 or done == len(pairs):
                elapsed = time.monotonic() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(pairs) - done) / rate if rate > 0 else 0
                log.info("[%d/%d] H:%d J:%d P:%d | %.1f/min ETA:%.0fs",
                    done, len(pairs), honey, jelly, propolis, rate * 60, eta)

    wall = time.monotonic() - start_time
    verified = honey + jelly + propolis
    report = {
        "epoch": "epoch-2-validation", "domain": args.domain,
        "total_pairs": total, "verified": verified + existing,
        "honey": honey, "jelly": jelly, "propolis": propolis,
        "honey_rate": round(honey / max(verified, 1), 4),
        "wall_time_sec": round(wall, 1),
        "pairs_per_minute": round(verified / (wall / 60), 2) if wall > 0 else 0,
        "config": "direct_judge_v5", "judges": len(JUDGE_PORTS), "inspector": "none",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(output_dir / "epoch_report.json", "w") as f:
        json.dump(report, f, indent=2)
    log.info("═══ EPOCH 2 COMPLETE — %d verified | H:%d J:%d P:%d | %.1f/min ═══",
        verified, honey, jelly, propolis, verified/(wall/60) if wall > 0 else 0)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--input", default=None)
    parser.add_argument("--session", default="epoch-2-validation")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(args))

if __name__ == "__main__":
    main()
