#!/usr/bin/env python3
"""
SwarmChain Validation Orchestrator v3 — Parallel Pipeline
==========================================================
Runs N pairs concurrently. On the block, off the block.
5 inspectors + 9 judges + 1 recorder = full assembly line.
Blocks in the queue. Maximum throughput at quality.
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
log = logging.getLogger("orchestrator-v3")

RAILS = os.environ.get("SWARM_RAILS_HOST", "localhost")
WHALE = os.environ.get("SWARM_WHALE_HOST", "192.168.0.99")
API_URL = os.environ.get("SWARM_API_URL", f"http://{RAILS}:8080")
API_KEY = os.environ.get("SWARM_API_KEY", "")
PARALLEL = int(os.environ.get("SWARM_PARALLEL", "3"))

INSPECTORS = [f"http://{RAILS}:{p}" for p in [8210, 8211, 8212, 8213, 8214]]
JUDGES = [f"http://{RAILS}:{p}" for p in [8201, 8202, 8203, 8204, 8205, 8206, 8207, 8208, 8209]]
RECORDER = f"http://{WHALE}:8097"

LOOK_SYSTEM = """You are a quality inspector for AI training pairs.
Assess the structure and completeness of this Q&A pair.
Output 3-5 sentences: Is it well-structured? Complete? Specific? Actionable?
Be brief and direct."""

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

Be decisive. Be brief."""

RECORDER_SYSTEM = """You are the SwarmChain Recorder — Katniss.
Write a brief title deed record:

PAIR_ID: <id>
DOMAIN: <domain>
PAIR_SUMMARY: <one sentence>
VERDICT: <PASS/FAIL>
SCORE: <0-100>
CLASSIFICATION: <honey/jelly/propolis>
WHY_SEALED: <2 sentences>
BUYER_CONFIDENCE: <HIGH/MEDIUM/LOW>
RECORD_STATUS: SEALED"""

# Round-robin counters
_insp_idx = 0
_judge_idx = 0
_lock = asyncio.Lock()


async def next_inspector():
    global _insp_idx
    async with _lock:
        url = INSPECTORS[_insp_idx % len(INSPECTORS)]
        _insp_idx += 1
        return url

async def next_judge():
    global _judge_idx
    async with _lock:
        url = JUDGES[_judge_idx % len(JUDGES)]
        _judge_idx += 1
        return url


async def call_model(client, url, system, user_content, max_tokens=4096):
    try:
        start = time.monotonic()
        resp = await client.post(f"{url}/v1/chat/completions", json={
            "model": "default",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
            "max_tokens": max_tokens, "temperature": 0.1,
        }, timeout=180)
        latency = time.monotonic() - start
        if resp.status_code != 200: return None
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content", "") or ""
        if "<think>" in content:
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        if not content.strip() and msg.get("reasoning_content"):
            content = msg["reasoning_content"]
        return {"content": content, "latency_ms": round(latency * 1000)}
    except:
        return None


async def api_req(client, method, path, **kwargs):
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        resp = await client.request(method, f"{API_URL}{path}", headers=headers, timeout=30, **kwargs)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None


async def validate_one(client, pair, idx, domain, session):
    """Validate one pair — gets its own inspector + judge from the pool."""
    msgs = pair.get("messages", [])
    user_prompt = next((m["content"] for m in msgs if m.get("role") == "user"), "")
    original_answer = next((m["content"] for m in msgs if m.get("role") == "assistant"), "")

    if not user_prompt or not original_answer:
        return {"pair_index": idx, "status": "skip", "reason": "missing Q or A"}

    # Get dedicated inspector + judge for this pair
    insp_url = await next_inspector()
    judge_url = await next_judge()

    # Open block
    block = await api_req(client, "POST", "/blocks/open", json={
        "task_id": f"validate-{domain}-{idx:06d}", "domain": domain,
        "reward_pool": 100, "max_attempts": 10, "time_limit_sec": 3600,
        "task_payload": {
            "validation_type": "domain_pair_verification", "domain": domain,
            "pair_index": idx, "skill": pair.get("skill", ""),
            "task_type": pair.get("task_type", ""),
            "user_prompt": user_prompt[:2000], "original_answer": original_answer[:3000],
        },
        "metadata": {"session_id": session, "sequence_number": idx + 1},
    })
    if not block: return {"pair_index": idx, "status": "error", "reason": "block open failed"}
    block_id = block["block_id"]

    # INSPECTOR
    look_input = f"DOMAIN: {domain}\nSKILL: {pair.get('skill','')}\n\nQUESTION:\n{user_prompt[:1500]}\n\nANSWER:\n{original_answer[:2000]}"
    look = await call_model(client, insp_url, LOOK_SYSTEM, look_input, max_tokens=512)
    look_text = look["content"] if look else "unavailable"
    look_ms = look["latency_ms"] if look else 0

    await api_req(client, "POST", "/attempts", json={
        "block_id": block_id, "node_id": "4b-inspector", "strategy": "structure_look",
        "method": "llm_inference", "output_json": {"assessment": look_text},
        "score": 0.0, "energy_cost": look_ms/1000, "latency_ms": look_ms,
    })

    # JUDGE
    judge_input = f"DOMAIN: {domain}\nSKILL: {pair.get('skill','')}\n\nQUESTION:\n{user_prompt[:1500]}\n\nANSWER:\n{original_answer[:2000]}\n\nINSPECTOR:\n{look_text[:500]}"
    judge = await call_model(client, judge_url, JUDGE_SYSTEM, judge_input, max_tokens=4096)
    judge_text = judge["content"] if judge else "unavailable"
    judge_ms = judge["latency_ms"] if judge else 0

    # Parse
    score, classification, verdict = 0.0, "propolis", "FAIL"
    for line in judge_text.split("\n"):
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
    # No guessing — if score cant be parsed, stays 0.0/propolis

    await api_req(client, "POST", "/attempts", json={
        "block_id": block_id, "node_id": "9b-base-judge", "strategy": "quality_verdict",
        "method": "llm_inference", "output_json": {"verdict": verdict, "score": score, "classification": classification, "reasoning": judge_text},
        "score": score, "energy_cost": judge_ms/1000, "latency_ms": judge_ms,
    })

    # RECORDER
    record_input = f"PAIR_ID: {idx}\nDOMAIN: {domain}\nSKILL: {pair.get('skill','')}\nVERDICT: {verdict}\nSCORE: {score:.2f}\nCLASS: {classification}\nQUESTION:\n{user_prompt[:500]}\nANSWER:\n{original_answer[:800]}\nINSPECTOR:\n{look_text[:300]}\nJUDGE:\n{judge_text[:400]}\nCOSTS: look={look_ms}ms judge={judge_ms}ms\n\nWrite the title deed."
    record = await call_model(client, RECORDER, RECORDER_SYSTEM, record_input, max_tokens=4096)
    record_text = record["content"] if record else "unavailable"
    record_ms = record["latency_ms"] if record else 0

    await api_req(client, "POST", "/attempts", json={
        "block_id": block_id, "node_id": "katniss-recorder", "strategy": "ledger_record",
        "method": "llm_inference", "output_json": {"ledger_entry": record_text, "classification": classification, "score": score},
        "score": score, "energy_cost": record_ms/1000, "latency_ms": record_ms,
    })

    await api_req(client, "POST", f"/blocks/{block_id}/finalize", json={"force": True, "reason": f"Validated: {classification} ({score:.2f})"})

    return {
        "pair_index": idx, "block_id": block_id, "domain": domain,
        "skill": pair.get("skill", ""), "task_type": pair.get("task_type", ""),
        "status": "verified", "verdict": verdict, "score": score,
        "classification": classification,
        "look_summary": look_text[:200], "judge_reasoning": judge_text[:300],
        "ledger_record": record_text[:300],
        "energy_ms": look_ms + judge_ms + record_ms,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
    }


async def run(args):
    input_path = Path(args.input)
    output_dir = Path(f"/data1/swarm-honey/{args.domain}/validated")
    output_dir.mkdir(parents=True, exist_ok=True)

    pairs = [json.loads(l) for l in open(input_path) if l.strip()]
    total = len(pairs)

    receipts_file = output_dir / "receipts.jsonl"
    existing = sum(1 for _ in open(receipts_file)) if receipts_file.exists() else 0
    if existing > 0:
        log.info("Resuming from pair %d", existing)
        pairs = pairs[existing:]
    if args.limit: pairs = pairs[:args.limit]
    log.info("Processing %d pairs (%d parallel) starting at %d", len(pairs), PARALLEL, existing)

    async with httpx.AsyncClient() as client:
        for node in ["4b-inspector", "9b-base-judge", "katniss-recorder"]:
            await api_req(client, "POST", "/nodes/register", json={"node_id": node, "hardware": "validation", "model": node})

    honey, jelly, propolis, skipped = 0, 0, 0, 0
    start_time = time.monotonic()
    write_lock = asyncio.Lock()

    async def process_and_write(client, pair, idx):
        nonlocal honey, jelly, propolis, skipped
        result = await validate_one(client, pair, idx, args.domain, args.session)

        async with write_lock:
            with open(receipts_file, "a") as f:
                f.write(json.dumps(result) + "\n")

            if result["status"] == "skip":
                skipped += 1
                return

            entry = {**pair, "swarmchain_validation": result}
            cls = result["classification"]
            with open(output_dir / f"{cls}.jsonl", "a") as f:
                f.write(json.dumps(entry) + "\n")

            if cls == "honey": honey += 1
            elif cls == "jelly": jelly += 1
            else: propolis += 1

    async with httpx.AsyncClient() as client:
        # Process in batches of PARALLEL
        for batch_start in range(0, len(pairs), PARALLEL):
            batch = pairs[batch_start:batch_start + PARALLEL]
            tasks = []
            for i, pair in enumerate(batch):
                idx = existing + batch_start + i
                tasks.append(process_and_write(client, pair, idx))

            await asyncio.gather(*tasks)

            # Progress
            done = batch_start + len(batch)
            elapsed = time.monotonic() - start_time
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(pairs) - done) / rate if rate > 0 else 0
            total_done = existing + done
            log.info("[%d/%d] H:%d J:%d P:%d | %.1f/min ETA:%.0fs | total:%d",
                done, len(pairs), honey, jelly, propolis, rate * 60, eta, total_done)

    wall = time.monotonic() - start_time
    verified = honey + jelly + propolis
    report = {
        "epoch": "epoch-1-validation", "domain": args.domain,
        "total_pairs": total, "verified": verified + existing,
        "honey": honey, "jelly": jelly, "propolis": propolis,
        "honey_rate": round(honey / max(verified, 1), 4),
        "wall_time_sec": round(wall, 1),
        "pairs_per_minute": round(verified / (wall / 60), 2) if wall > 0 else 0,
        "parallel": PARALLEL,
        "fleet": {"inspectors": len(INSPECTORS), "judges": len(JUDGES), "recorder": 1},
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(output_dir / "epoch_report.json", "w") as f:
        json.dump(report, f, indent=2)

    log.info("═══ COMPLETE — %d verified | H:%d J:%d P:%d | %.1f/min | %dx parallel ═══",
        verified, honey, jelly, propolis, verified/(wall/60) if wall > 0 else 0, PARALLEL)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--session", default="epoch-1-validation")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(args))

if __name__ == "__main__":
    main()
