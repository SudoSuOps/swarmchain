#!/usr/bin/env python3
"""
SwarmChain Validation Orchestrator v4 — Queue Pipeline
=======================================================
CONSTANT GPU LOAD. No round-robin idle. No power cycling.

Architecture:
  - Xeon pre-loads pairs into asyncio queues
  - Inspector workers pull from input queue, push to judge queue
  - Judge workers pull from judge queue, push to recorder queue
  - Recorder workers pull and seal
  - Each worker has a DEDICATED model — no sharing, no idle

  GPU stays at constant power. Steady state. Like a mining rig.
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
log = logging.getLogger("orchestrator-v4")

RAILS = os.environ.get("SWARM_RAILS_HOST", "localhost")
WHALE = os.environ.get("SWARM_WHALE_HOST", "192.168.0.99")
API_URL = os.environ.get("SWARM_API_URL", f"http://{RAILS}:8080")
API_KEY = os.environ.get("SWARM_API_KEY", "")

# Each worker gets a DEDICATED endpoint — no sharing
INSPECTOR_PORTS = [8210, 8211, 8212, 8213, 8214]
JUDGE_PORTS = [8201, 8202, 8203, 8204, 8205, 8206, 8207, 8208]
RECORDER_PORTS = [8097]  # Local on RTX 4500

LOOK_SYSTEM = """You are a quality inspector for AI training pairs.
Assess structure and completeness. 3-5 sentences. Brief and direct."""

JUDGE_SYSTEM = """You are the final quality judge for AI training pairs.
Output EXACTLY:

VERDICT: PASS or FAIL
TOTAL_SCORE: <0-100>
CLASSIFICATION: propolis or jelly or honey
REASONING: <1-2 sentences>

honey (80-100), jelly (40-79), propolis (0-39). Be decisive."""

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


async def call_model(client, port, system, user_content, host="localhost", max_tokens=4096):
    url = f"http://{host}:{port}/v1/chat/completions"
    try:
        start = time.monotonic()
        resp = await client.post(url, json={
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


def parse_verdict(judge_text):
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
    # No guessing — if score can't be parsed, stays 0.0/propolis
    return verdict, score, classification


# ── Queue-based workers ─────────────────────────────────

async def inspector_worker(worker_id, port, input_q, judge_q, client):
    """Dedicated inspector — pulls pairs, inspects, pushes to judge queue. Never idle."""
    while True:
        item = await input_q.get()
        if item is None:
            await judge_q.put(None)
            break

        idx, pair, domain = item
        msgs = pair.get("messages", [])
        user_prompt = next((m["content"] for m in msgs if m.get("role") == "user"), "")
        original_answer = next((m["content"] for m in msgs if m.get("role") == "assistant"), "")

        if not user_prompt or not original_answer:
            input_q.task_done()
            continue

        look_input = f"DOMAIN: {domain}\nSKILL: {pair.get('skill','')}\n\nQ:\n{user_prompt[:1500]}\n\nA:\n{original_answer[:2000]}"
        look_text, look_ms = await call_model(client, port, LOOK_SYSTEM, look_input, max_tokens=512)

        await judge_q.put((idx, pair, domain, user_prompt, original_answer, look_text, look_ms))
        input_q.task_done()


async def judge_worker(worker_id, port, judge_q, record_q, client):
    """Dedicated judge — pulls inspected pairs, judges, pushes to recorder. Never idle."""
    while True:
        item = await judge_q.get()
        if item is None:
            await record_q.put(None)
            break

        idx, pair, domain, user_prompt, original_answer, look_text, look_ms = item

        judge_input = f"DOMAIN: {domain}\nSKILL: {pair.get('skill','')}\n\nQ:\n{user_prompt[:1500]}\n\nA:\n{original_answer[:2000]}\n\nINSPECTOR:\n{look_text[:500]}"
        judge_text, judge_ms = await call_model(client, port, JUDGE_SYSTEM, judge_input)
        verdict, score, classification = parse_verdict(judge_text)

        await record_q.put((idx, pair, domain, user_prompt, original_answer, look_text, look_ms, judge_text, judge_ms, verdict, score, classification))
        judge_q.task_done()


async def recorder_worker(worker_id, port, record_q, output_q, client, host="192.168.0.99"):
    """Dedicated recorder — pulls judged pairs, writes deeds, seals blocks."""
    while True:
        item = await record_q.get()
        if item is None:
            await output_q.put(None)
            break

        idx, pair, domain, user_prompt, original_answer, look_text, look_ms, judge_text, judge_ms, verdict, score, classification = item

        # Open block
        block = await api_req(client, "POST", "/blocks/open", json={
            "task_id": f"validate-{domain}-{idx:06d}", "domain": domain,
            "reward_pool": 100, "max_attempts": 10, "time_limit_sec": 3600,
            "task_payload": {
                "validation_type": "domain_pair_verification", "domain": domain,
                "pair_index": idx, "skill": pair.get("skill", ""),
                "user_prompt": user_prompt[:2000], "original_answer": original_answer[:3000],
            },
            "metadata": {"session_id": "epoch-1-validation", "sequence_number": idx + 1},
        })

        block_id = block["block_id"] if block else "unknown"

        # Submit inspector attempt
        await api_req(client, "POST", "/attempts", json={
            "block_id": block_id, "node_id": "4b-inspector", "strategy": "structure_look",
            "method": "llm_inference", "output_json": {"assessment": look_text},
            "score": 0.0, "energy_cost": look_ms/1000, "latency_ms": look_ms,
        })

        # Submit judge attempt
        await api_req(client, "POST", "/attempts", json={
            "block_id": block_id, "node_id": "9b-base-judge", "strategy": "quality_verdict",
            "method": "llm_inference", "output_json": {"verdict": verdict, "score": score, "classification": classification, "reasoning": judge_text},
            "score": score, "energy_cost": judge_ms/1000, "latency_ms": judge_ms,
        })

        # Record deed
        record_input = f"PAIR_ID: {idx}\nDOMAIN: {domain}\nSKILL: {pair.get('skill','')}\nVERDICT: {verdict}\nSCORE: {score:.2f}\nCLASS: {classification}\nQ:\n{user_prompt[:500]}\nA:\n{original_answer[:800]}\nJUDGE:\n{judge_text[:400]}"
        record_text, record_ms = await call_model(client, port, RECORDER_SYSTEM, record_input, host=host)

        # Submit recorder attempt
        await api_req(client, "POST", "/attempts", json={
            "block_id": block_id, "node_id": "katniss-recorder", "strategy": "ledger_record",
            "method": "llm_inference", "output_json": {"ledger_entry": record_text, "classification": classification, "score": score},
            "score": score, "energy_cost": record_ms/1000, "latency_ms": record_ms,
        })

        # Seal
        await api_req(client, "POST", f"/blocks/{block_id}/finalize", json={"force": True, "reason": f"Validated: {classification} ({score:.2f})"})

        result = {
            "pair_index": idx, "block_id": block_id, "domain": domain,
            "skill": pair.get("skill", ""), "task_type": pair.get("task_type", ""),
            "status": "verified", "verdict": verdict, "score": score,
            "classification": classification,
            "look_summary": look_text[:200], "judge_reasoning": judge_text[:300],
            "ledger_record": record_text[:300],
            "energy_ms": look_ms + judge_ms + record_ms,
            "sealed_at": datetime.now(timezone.utc).isoformat(),
        }

        await output_q.put((idx, pair, result))
        record_q.task_done()


async def run(args):
    output_dir = Path(f"/data1/swarm-honey/{args.domain}/validated")
    output_dir.mkdir(parents=True, exist_ok=True)

    pairs = [json.loads(l) for l in open(args.input) if l.strip()]
    total = len(pairs)

    receipts_file = output_dir / "receipts.jsonl"
    existing = sum(1 for _ in open(receipts_file)) if receipts_file.exists() else 0
    if existing > 0:
        log.info("Resuming from pair %d", existing)
        pairs = pairs[existing:]
    if args.limit: pairs = pairs[:args.limit]

    # Determine worker counts based on available endpoints
    n_inspectors = len(INSPECTOR_PORTS)
    n_judges = len(JUDGE_PORTS)
    n_recorders = len(RECORDER_PORTS)

    log.info("Pipeline: %d inspectors → %d judges → %d recorders | %d pairs from %d",
        n_inspectors, n_judges, n_recorders, len(pairs), existing)

    # Register nodes
    async with httpx.AsyncClient() as client:
        for node in ["4b-inspector", "9b-base-judge", "katniss-recorder"]:
            await api_req(client, "POST", "/nodes/register", json={"node_id": node, "hardware": "validation", "model": node})

    # Queues — buffered to keep workers fed
    input_q = asyncio.Queue(maxsize=50)     # pairs waiting for inspection
    judge_q = asyncio.Queue(maxsize=50)     # inspected, waiting for judge
    record_q = asyncio.Queue(maxsize=50)    # judged, waiting for recorder
    output_q = asyncio.Queue()              # completed deeds

    honey, jelly, propolis, skipped = 0, 0, 0, 0
    start_time = time.monotonic()
    write_lock = asyncio.Lock()

    async with httpx.AsyncClient() as client:
        # Start workers — each gets a DEDICATED port
        inspector_tasks = [
            asyncio.create_task(inspector_worker(i, INSPECTOR_PORTS[i], input_q, judge_q, client))
            for i in range(n_inspectors)
        ]
        judge_tasks = [
            asyncio.create_task(judge_worker(i, JUDGE_PORTS[i], judge_q, record_q, client))
            for i in range(n_judges)
        ]
        recorder_tasks = [
            asyncio.create_task(recorder_worker(i, RECORDER_PORTS[i], record_q, output_q, client, host="localhost"))
            for i in range(n_recorders)
        ]

        # Feed the input queue — Xeon pre-loads from DDR5
        async def feeder():
            for i, pair in enumerate(pairs):
                await input_q.put((existing + i, pair, args.domain))
            # Poison pills to stop workers
            for _ in range(n_inspectors):
                await input_q.put(None)

        # Drain the output queue — write results
        async def drainer():
            nonlocal honey, jelly, propolis
            done = 0
            none_count = 0
            while none_count < n_recorders:
                item = await output_q.get()
                if item is None:
                    none_count += 1
                    continue

                idx, pair, result = item
                done += 1

                async with write_lock:
                    with open(receipts_file, "a") as f:
                        f.write(json.dumps(result) + "\n")

                    cls = result["classification"]
                    entry = {**pair, "swarmchain_validation": result}
                    with open(output_dir / f"{cls}.jsonl", "a") as f:
                        f.write(json.dumps(entry) + "\n")

                    if cls == "honey": honey += 1
                    elif cls == "jelly": jelly += 1
                    else: propolis += 1

                if done % 10 == 0:
                    elapsed = time.monotonic() - start_time
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (len(pairs) - done) / rate if rate > 0 else 0
                    log.info("[%d/%d] H:%d J:%d P:%d | %.1f/min ETA:%.0fs",
                        done, len(pairs), honey, jelly, propolis, rate * 60, eta)

        # Run all concurrently
        await asyncio.gather(feeder(), drainer(), *inspector_tasks, *judge_tasks, *recorder_tasks)

    wall = time.monotonic() - start_time
    verified = honey + jelly + propolis
    report = {
        "epoch": "epoch-1-validation", "domain": args.domain,
        "total_pairs": total, "verified": verified + existing,
        "honey": honey, "jelly": jelly, "propolis": propolis,
        "honey_rate": round(honey / max(verified, 1), 4),
        "wall_time_sec": round(wall, 1),
        "pairs_per_minute": round(verified / (wall / 60), 2) if wall > 0 else 0,
        "pipeline": {"inspectors": n_inspectors, "judges": n_judges, "recorders": n_recorders},
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(output_dir / "epoch_report.json", "w") as f:
        json.dump(report, f, indent=2)

    log.info("═══ COMPLETE — %d verified | H:%d J:%d P:%d | %.1f/min ═══",
        verified, honey, jelly, propolis, verified/(wall/60) if wall > 0 else 0)


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
