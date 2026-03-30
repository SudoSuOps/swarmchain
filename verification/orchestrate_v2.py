#!/usr/bin/env python3
"""
SwarmChain Validation Orchestrator v2 — Parallel Pipeline
==========================================================
4B inspectors + 9B judges + Katniss recorder
4 judges in parallel = 10x throughput

Resumes from where v1 left off (appends to existing output files).
"""
import asyncio
import json
import time
import argparse
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("orchestrator-v2")

RAILS = os.environ.get("SWARM_RAILS_HOST", "localhost")
WHALE = os.environ.get("SWARM_WHALE_HOST", "192.168.0.99")
API_URL = os.environ.get("SWARM_API_URL", f"http://{RAILS}:8080")
API_KEY = os.environ.get("SWARM_API_KEY", "")

# Fleet — round-robin across multiple instances
INSPECTORS = [f'http://{RAILS}:8210', f'http://{RAILS}:8211', f'http://{RAILS}:8212']
JUDGES = [f'http://{RAILS}:8201', f'http://{RAILS}:8202', f'http://{RAILS}:8203', f'http://{RAILS}:8204', f'http://{RAILS}:8205', f'http://{RAILS}:8206', f'http://{RAILS}:8207', f'http://{RAILS}:8208', f'http://{RAILS}:8209']
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
  propolis (0-39): Low quality, inaccurate, or too generic to be useful

Be decisive. Be brief. No extra commentary."""

RECORDER_SYSTEM = """You are the SwarmChain Recorder — Katniss.
The judge decided the verdict. You decide how history will read it.

Output a structured title deed:

PAIR_ID: <id>
DOMAIN: <domain>
PAIR_SUMMARY: <one sentence>
VERDICT: <PASS/FAIL>
SCORE: <0-100>
CLASSIFICATION: <honey/jelly/propolis>
WHY_SEALED: <2 sentences — why this classification>
BUYER_CONFIDENCE: <HIGH/MEDIUM/LOW>
RECORD_STATUS: SEALED"""


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
            import re; content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        if not content.strip() and msg.get("reasoning_content"):
            content = msg["reasoning_content"]
        return {"content": content, "latency_ms": round(latency * 1000)}
    except Exception as e:
        log.debug("Model error: %s", e)
        return None


async def api_req(client, method, path, **kwargs):
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        resp = await client.request(method, f"{API_URL}{path}", headers=headers, timeout=30, **kwargs)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None


async def validate_one(client, pair, idx, domain, session, inspector_url, judge_url):
    """Validate one pair — inspector + judge + recorder."""
    msgs = pair.get("messages", [])
    user_prompt = next((m["content"] for m in msgs if m.get("role") == "user"), "")
    original_answer = next((m["content"] for m in msgs if m.get("role") == "assistant"), "")
    system_prompt = next((m.get("content", "") for m in msgs if m.get("role") == "system"), "")

    if not user_prompt or not original_answer:
        return {"pair_index": idx, "status": "skip", "reason": "missing Q or A"}

    # Open block
    block = await api_req(client, "POST", "/blocks/open", json={
        "task_id": f"validate-{domain}-{idx:06d}",
        "domain": domain, "reward_pool": 100, "max_attempts": 10, "time_limit_sec": 3600,
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

    # 4B INSPECTOR — quick look
    look_input = f"DOMAIN: {domain}\nSKILL: {pair.get('skill','')}\n\nQUESTION:\n{user_prompt[:1500]}\n\nANSWER:\n{original_answer[:2000]}"
    look = await call_model(client, inspector_url, LOOK_SYSTEM, look_input, max_tokens=512)
    look_text = look["content"] if look else "Inspector unavailable"
    look_ms = look["latency_ms"] if look else 0

    await api_req(client, "POST", "/attempts", json={
        "block_id": block_id, "node_id": "4b-inspector", "strategy": "structure_look",
        "method": "llm_inference", "output_json": {"assessment": look_text},
        "score": 0.0, "energy_cost": look_ms/1000, "latency_ms": look_ms,
    })

    # 9B JUDGE — verdict
    judge_input = f"DOMAIN: {domain}\nSKILL: {pair.get('skill','')}\n\nQUESTION:\n{user_prompt[:1500]}\n\nANSWER:\n{original_answer[:2000]}\n\nINSPECTOR NOTE:\n{look_text[:500]}"
    judge = await call_model(client, judge_url, JUDGE_SYSTEM, judge_input, max_tokens=4096)
    judge_text = judge["content"] if judge else "Judge unavailable"
    judge_ms = judge["latency_ms"] if judge else 0

    # Parse verdict
    score, classification, verdict = 0.0, "propolis", "FAIL"
    for line in judge_text.split("\n"):
        ll = line.strip().lower()
        if ll.startswith("verdict:"): verdict = "PASS" if "pass" in ll else "FAIL"
        if "total_score:" in ll or "total score:" in ll:
            import re; nums = re.findall(r'\d+', line);
            if nums: score = min(int(nums[0]), 100) / 100.0
        if ll.startswith("classification:"):
            if "propolis" in ll: classification = "propolis"
            elif "jelly" in ll: classification = "jelly"
            elif "honey" in ll: classification = "honey"
        if ll.startswith("score:") and score == 0.0:
            import re; nums = re.findall(r'\d+', line)
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

    # KATNISS RECORDS
    record_input = f"PAIR_ID: {idx}\nDOMAIN: {domain}\nSKILL: {pair.get('skill','')}\nQUESTION:\n{user_prompt[:800]}\nANSWER:\n{original_answer[:1200]}\n\n9B ASSESSMENT:\n{look_text[:400]}\n\n27B VERDICT: {verdict}\nSCORE: {score:.2f}\nCLASSIFICATION: {classification}\nREASONING:\n{judge_text[:600]}\n\nLOOK_COST: {look_ms}ms\nJUDGE_COST: {judge_ms}ms\n\nWrite the title deed."
    record = await call_model(client, RECORDER, RECORDER_SYSTEM, record_input, max_tokens=4096)
    record_text = record["content"] if record else "Recorder unavailable"
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

    # Resume: skip already processed
    existing = 0
    receipts_file = output_dir / "receipts.jsonl"
    if receipts_file.exists():
        existing = sum(1 for _ in open(receipts_file))
    if existing > 0:
        log.info("Resuming from pair %d (skipping %d already processed)", existing, existing)
        pairs = pairs[existing:]

    if args.limit:
        pairs = pairs[:args.limit]
    log.info("Processing %d pairs (starting at %d)", len(pairs), existing)

    # Register nodes
    async with httpx.AsyncClient() as client:
        for node in ["4b-inspector", "9b-base-judge", "katniss-recorder"]:
            await api_req(client, "POST", "/nodes/register", json={"node_id": node, "hardware": "validation", "model": node})

    honey, jelly, propolis, skipped = 0, 0, 0, 0
    start_time = time.monotonic()
    judge_idx = 0
    inspector_idx = 0

    async with httpx.AsyncClient() as client:
        for i, pair in enumerate(pairs):
            pair_idx = existing + i

            # Round-robin inspectors and judges
            insp_url = INSPECTORS[inspector_idx % len(INSPECTORS)]
            judge_url = JUDGES[judge_idx % len(JUDGES)]
            inspector_idx += 1
            judge_idx += 1

            result = await validate_one(client, pair, pair_idx, args.domain, args.session, insp_url, judge_url)

            with open(receipts_file, "a") as f:
                f.write(json.dumps(result) + "\n")

            if result["status"] == "skip":
                skipped += 1; continue

            entry = {**pair, "swarmchain_validation": result}
            cls = result["classification"]
            cls_file = output_dir / f"{cls}.jsonl"
            with open(cls_file, "a") as f:
                f.write(json.dumps(entry) + "\n")

            if cls == "honey": honey += 1
            elif cls == "jelly": jelly += 1
            else: propolis += 1

            elapsed = time.monotonic() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(pairs) - i - 1) / rate if rate > 0 else 0

            log.info("[%d/%d] %s %s score=%.2f | H:%d J:%d P:%d | %.1f/min ETA:%.0fs",
                i + 1, len(pairs), cls.upper(), result.get("verdict", "?"),
                result.get("score", 0), honey, jelly, propolis, rate * 60, eta)

    wall = time.monotonic() - start_time
    verified = honey + jelly + propolis
    report = {
        "epoch": "epoch-1-validation", "domain": args.domain, "session": args.session,
        "total_pairs": total, "verified": verified + existing, "skipped": skipped,
        "honey": honey, "jelly": jelly, "propolis": propolis,
        "honey_rate": round(honey / max(verified, 1), 4),
        "wall_time_sec": round(wall, 1),
        "pairs_per_minute": round(verified / (wall / 60), 2) if wall > 0 else 0,
        "protocol": {"inspectors": "4B base ×2", "judges": "9B base ×4", "recorder": "Katniss 9B"},
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(output_dir / "epoch_report.json", "w") as f:
        json.dump(report, f, indent=2)

    log.info("═══ COMPLETE — %d verified | H:%d J:%d P:%d | %.1f/min ═══", verified, honey, jelly, propolis, verified/(wall/60) if wall > 0 else 0)


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
