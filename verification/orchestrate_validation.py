#!/usr/bin/env python3
"""
SwarmChain Validation Orchestrator
====================================
Runs on Xeon CPU. Loads pairs from NVMe. Submits to the chain.
Each pair = one block. Full protocol:

  1. Pair enters SwarmChain (block opens with full Q&A)
  2. 9B base LOOKS (RTX 4500) — structure, completeness
  3. 27B base JUDGES (RTX 6000) — verdict, reasoning, score
  4. Katniss RECORDS (Whale 3090 Ti) — writes ledger entry, seals
  5. Block seals with full record — timestamp, verdict, proof

"We don't have 1 real defendable pair until they go through SwarmChain."

Usage:
  python3 orchestrate_validation.py \
    --domain failure \
    --input /data1/swarm-honey/failure/failure_intelligence.jsonl \
    --limit 10 \
    --session epoch-1-validation-failure
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("orchestrator")

# ── Network Config ──────────────────────────────────────────
RAILS = os.environ.get("SWARM_RAILS_HOST", "localhost")
WHALE = os.environ.get("SWARM_WHALE_HOST", "192.168.0.99")

API_URL = os.environ.get("SWARM_API_URL", f"http://{RAILS}:8080")
API_KEY = os.environ.get("SWARM_API_KEY", "")

# Model endpoints — each model has ONE job
LOOK_URL = f"http://{RAILS}:8096/v1/chat/completions"       # 9B base — THE LOOK
JUDGE_URL = f"http://{RAILS}:8095/v1/chat/completions"      # 27B base — THE JUDGE
RECORDER_URL = f"http://{WHALE}:8097/v1/chat/completions"   # Katniss — THE RECORDER

# ── Prompts ─────────────────────────────────────────────────

LOOK_SYSTEM = """You are a quality assessor. You receive a Q&A pair from a domain dataset.
Your job: assess the STRUCTURE and COMPLETENESS of the answer.

Evaluate:
1. Does the answer address the question directly?
2. Is the answer well-structured (reasoning, steps, actionable)?
3. Is the response length appropriate (not too short, not bloated)?
4. Does it contain specific details (not generic filler)?

Output a brief assessment (3-5 sentences) and a structure score 0-100."""

JUDGE_SYSTEM = """You are the final quality judge for AI training pairs.
You receive a Q&A pair and a preliminary assessment.
Your job: deliver the VERDICT.

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

You receive a verified pair with its assessment, verdict, and cost data.
Your job: write the PERMANENT LEDGER RECORD with CLOSING SHEET.

This is a title deed for an AI data pair. It must be complete, defensible,
and readable by a human 5 years from now.

Output EXACTLY this format:

═══ SWARMCHAIN TITLE DEED ═══

PAIR_ID: <pair index>
DOMAIN: <domain>
SKILL: <skill category>
RECORDED_AT: <timestamp>

PROPERTY DESCRIPTION:
<one sentence — what this Q&A pair covers, the subject matter>

INSPECTION REPORT:
VALIDATOR_ASSESSMENT: <what the 9B found — structure, completeness, coherence>
JUDGE_VERDICT: <PASS or FAIL>
JUDGE_SCORE: <0-100>
CLASSIFICATION: <honey or jelly or propolis>
JUDGE_REASONING: <the 27B's stated reasoning>

TITLE OPINION:
WHY_SEALED: <2-3 sentences — why this pair was classified this way. What made it pass or fail. What a buyer needs to know about this pair's quality.>
DEFECTS_NOTED: <any quality issues, gaps, or concerns — or NONE if clean>
BUYER_CONFIDENCE: <HIGH / MEDIUM / LOW — would you put this in a client dataset?>

CLOSING SHEET:
LOOK_COST: <9B energy>
JUDGE_COST: <27B energy>
RECORD_COST: <recorder energy>
TOTAL_VALIDATION_COST: <sum>
ANCHOR_FEE: PENDING (Hedera batch anchor per 50 blocks)

CERTIFICATION:
This pair has been inspected, judged, and recorded through the SwarmChain
Validation Protocol. This record is sealed and immutable.

RECORD_STATUS: SEALED
NOTARIZED_BY: katniss-recorder (SwarmRefinery 9B)

═══ END OF DEED ═══"""


# ── Model Calls ─────────────────────────────────────────────

async def call_model(client: httpx.AsyncClient, url: str, system: str, user_content: str, max_tokens: int = 1024, enable_thinking: bool = False) -> dict | None:
    """Call a model and return response + metrics.

    enable_thinking=False for structured output (Look, Judge)
    enable_thinking=True for thoughtful records (Recorder/Katniss)
    """
    try:
        start = time.monotonic()
        payload = {
            "model": "default",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1,
        }
        # Ensure enough tokens for thinking to complete before content
        # Qwen 3.5 thinks by default — content appears after thinking
        # Just need enough max_tokens (4096+) for both thinking + output

        resp = await client.post(url, json=payload, timeout=120)
        latency = time.monotonic() - start

        if resp.status_code != 200:
            log.warning("Model %s returned %d", url.split(":")[2][:4], resp.status_code)
            return None

        data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content", "") or ""

        # If thinking was on and content is empty, check reasoning_content
        if not content.strip() and msg.get("reasoning_content"):
            content = msg["reasoning_content"]

        # Strip any <think> tags that leaked through
        if "<think>" in content:
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

        return {
            "content": content,
            "latency_ms": round(latency * 1000),
            "tokens": data.get("usage", {}).get("total_tokens", 0),
        }
    except Exception as e:
        log.error("Model call failed (%s): %s", url.split(":")[2][:4], e)
        return None


# ── API Calls ───────────────────────────────────────────────

async def api_request(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> dict | None:
    """Make an authenticated API request."""
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    try:
        resp = await client.request(method, f"{API_URL}{path}", headers=headers, timeout=30, **kwargs)
        if resp.status_code == 200:
            return resp.json()
        log.warning("API %s %s: %d", method, path, resp.status_code)
        return None
    except Exception as e:
        log.error("API error: %s", e)
        return None


# ── Validation Protocol ─────────────────────────────────────

async def validate_pair(
    client: httpx.AsyncClient,
    pair: dict,
    pair_index: int,
    domain: str,
    session_id: str,
) -> dict:
    """Run one pair through the full validation protocol.

    Step 1: Open block with full pair data
    Step 2: 9B LOOKS at it
    Step 3: 27B JUDGES it
    Step 4: Katniss RECORDS it
    Step 5: Block seals
    """
    # Extract the Q&A
    messages = pair.get("messages", [])
    user_prompt = ""
    original_answer = ""
    system_prompt = ""

    for m in messages:
        if m.get("role") == "system":
            system_prompt = m.get("content", "")
        elif m.get("role") == "user":
            user_prompt = m.get("content", "")
        elif m.get("role") == "assistant":
            original_answer = m.get("content", "")

    if not user_prompt or not original_answer:
        return {"pair_index": pair_index, "status": "skip", "reason": "missing Q or A"}

    # ── STEP 1: Open block with full pair ──
    block_resp = await api_request(client, "POST", "/blocks/open", json={
        "task_id": f"validate-{domain}-{pair_index:06d}",
        "domain": domain,
        "reward_pool": 100.0,
        "max_attempts": 10,
        "time_limit_sec": 3600,
        "task_payload": {
            "validation_type": "domain_pair_verification",
            "domain": domain,
            "pair_index": pair_index,
            "skill": pair.get("skill", ""),
            "task_type": pair.get("task_type", ""),
            "cell_id": pair.get("cell_id", ""),
            "fingerprint": pair.get("fingerprint", ""),
            "original_grade": pair.get("grade", ""),
            "user_prompt": user_prompt[:2000],
            "original_answer": original_answer[:3000],
            "system_prompt": system_prompt[:500],
        },
        "metadata": {
            "session_id": session_id,
            "sequence_number": pair_index + 1,
            "tier": 1,
            "difficulty_band": "validation",
            "attempt_cap": 10,
        },
    })

    if not block_resp:
        return {"pair_index": pair_index, "status": "error", "reason": "failed to open block"}

    block_id = block_resp["block_id"]
    log.debug("[%d] Block opened: %s", pair_index, block_id[:12])

    # ── STEP 2: 9B LOOKS ──
    look_input = f"""DOMAIN: {domain}
SKILL: {pair.get('skill', 'unknown')}
TASK TYPE: {pair.get('task_type', 'unknown')}

QUESTION:
{user_prompt[:1500]}

ANSWER:
{original_answer[:2000]}"""

    look_result = await call_model(client, LOOK_URL, LOOK_SYSTEM, look_input, max_tokens=4096)
    look_text = look_result["content"] if look_result else "9B Look unavailable"
    look_latency = look_result["latency_ms"] if look_result else 0

    # Submit 9B look as attempt
    await api_request(client, "POST", "/attempts", json={
        "block_id": block_id,
        "node_id": "9b-base-look",
        "strategy": "structure_assessment",
        "method": "llm_inference",
        "output_json": {"assessment": look_text},
        "score": 0.0,
        "energy_cost": look_latency / 1000,
        "latency_ms": look_latency,
    })

    # ── STEP 3: 27B JUDGES ──
    judge_input = f"""DOMAIN: {domain}
SKILL: {pair.get('skill', 'unknown')}

QUESTION:
{user_prompt[:1500]}

ANSWER:
{original_answer[:2000]}

PRELIMINARY ASSESSMENT (9B):
{look_text[:800]}"""

    judge_result = await call_model(client, JUDGE_URL, JUDGE_SYSTEM, judge_input, max_tokens=4096)
    judge_text = judge_result["content"] if judge_result else "27B Judge unavailable"
    judge_latency = judge_result["latency_ms"] if judge_result else 0

    # Parse score from judge output — expects structured format:
    # VERDICT: PASS or FAIL
    # TOTAL_SCORE: 55
    # CLASSIFICATION: jelly
    score = 0.0
    classification = "propolis"
    verdict = "FAIL"
    try:
        for line in judge_text.split("\n"):
            line_clean = line.strip()
            line_lower = line_clean.lower()

            # VERDICT
            if line_lower.startswith("verdict:"):
                verdict = "PASS" if "pass" in line_lower else "FAIL"

            # TOTAL_SCORE or TOTAL SCORE
            if "total_score:" in line_lower or "total score:" in line_lower:
                import re
                nums = re.findall(r'\d+', line_clean)
                if nums:
                    raw = int(nums[0])
                    score = min(raw, 100) / 100.0

            # CLASSIFICATION
            if line_lower.startswith("classification:"):
                if "propolis" in line_lower:
                    classification = "propolis"
                elif "near-honey" in line_lower or "near honey" in line_lower:
                    classification = "honey"
                elif "jelly" in line_lower:
                    classification = "jelly"
                elif "honey" in line_lower:
                    classification = "honey"

            # Also catch "SCORE:" standalone
            if line_lower.startswith("score:") and score == 0.0:
                import re
                nums = re.findall(r'\d+', line_clean)
                if nums:
                    raw = int(nums[0])
                    score = min(raw, 100) / 100.0
    except:
        pass

    # Fallback: derive classification from score if parser missed it
    if score > 0 and classification == "propolis":
        if score >= 0.80:
            classification = "honey"
        elif score >= 0.40:
            classification = "jelly"

    # Fallback: if PASS in text but score is 0
    if score == 0.0 and "PASS" in judge_text.upper():
        score = 0.80
        classification = "honey"

    log.debug("Parsed: verdict=%s score=%.2f class=%s", verdict, score, classification)

    # Submit 27B verdict as attempt (this is the SCORING attempt)
    await api_request(client, "POST", "/attempts", json={
        "block_id": block_id,
        "node_id": "27b-base-judge",
        "strategy": "quality_verdict",
        "method": "llm_inference",
        "output_json": {
            "verdict": verdict,
            "score": score,
            "classification": classification,
            "reasoning": judge_text,
        },
        "score": score,
        "energy_cost": judge_latency / 1000,
        "latency_ms": judge_latency,
    })

    # ── STEP 4: KATNISS RECORDS ──
    record_input = f"""WRITE THE TITLE DEED FOR THIS PAIR:

PAIR INDEX: {pair_index}
DOMAIN: {domain}
SKILL: {pair.get('skill', 'unknown')}
TASK TYPE: {pair.get('task_type', 'unknown')}
TIMESTAMP: {datetime.now(timezone.utc).isoformat()}

QUESTION:
{user_prompt[:1000]}

ORIGINAL ANSWER:
{original_answer[:1500]}

9B ASSESSMENT:
{look_text[:500]}

27B VERDICT: {verdict}
SCORE: {score:.2f} / 1.00
CLASSIFICATION: {classification}
27B REASONING:
{judge_text[:800]}

CLOSING COSTS:
LOOK_COST: {look_latency}ms energy
JUDGE_COST: {judge_latency}ms energy
RECORD_COST: recording now

Write the complete title deed with closing sheet now."""

    record_result = await call_model(client, RECORDER_URL, RECORDER_SYSTEM, record_input, max_tokens=4096)
    record_text = record_result["content"] if record_result else "Recorder unavailable"
    record_latency = record_result["latency_ms"] if record_result else 0

    # Submit record as final attempt
    await api_request(client, "POST", "/attempts", json={
        "block_id": block_id,
        "node_id": "katniss-recorder",
        "strategy": "ledger_record",
        "method": "llm_inference",
        "output_json": {
            "ledger_entry": record_text,
            "classification": classification,
            "score": score,
            "verdict": verdict,
        },
        "score": score,
        "energy_cost": record_latency / 1000,
        "latency_ms": record_latency,
    })

    # ── STEP 5: SEAL THE BLOCK ──
    await api_request(client, "POST", f"/blocks/{block_id}/finalize", json={
        "force": True,
        "reason": f"Validation complete: {classification} ({score:.2f})",
    })

    total_energy = look_latency + judge_latency + record_latency

    result = {
        "pair_index": pair_index,
        "block_id": block_id,
        "domain": domain,
        "skill": pair.get("skill", ""),
        "task_type": pair.get("task_type", ""),
        "status": "verified",
        "verdict": verdict,
        "score": score,
        "classification": classification,
        "look_summary": look_text[:200],
        "judge_reasoning": judge_text[:300],
        "ledger_record": record_text[:300],
        "energy_ms": total_energy,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
    }

    return result


# ── Main Loop ───────────────────────────────────────────────

async def run(args):
    """Run the validation epoch."""
    input_path = Path(args.input)
    output_dir = Path(f"/data1/swarm-honey/{args.domain}/validated")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load pairs
    log.info("Loading %s...", input_path)
    pairs = []
    with open(input_path) as f:
        for line in f:
            if line.strip():
                pairs.append(json.loads(line))

    total = len(pairs)
    if args.limit:
        pairs = pairs[:args.limit]
    log.info("Loaded %d pairs (limit: %s)", len(pairs), args.limit or "all")

    # Output files
    honey_file = output_dir / "honey.jsonl"
    jelly_file = output_dir / "jelly.jsonl"
    propolis_file = output_dir / "propolis.jsonl"
    receipts_file = output_dir / "receipts.jsonl"
    report_file = output_dir / "epoch_report.json"

    # Verify all models are online
    log.info("Checking models...")
    async with httpx.AsyncClient() as client:
        for name, url in [("9B Look", LOOK_URL), ("27B Judge", JUDGE_URL), ("Recorder", RECORDER_URL)]:
            health = url.replace("/v1/chat/completions", "/health")
            try:
                r = await client.get(health, timeout=5)
                log.info("  %s: %s", name, "✅" if r.status_code == 200 else "❌")
            except:
                log.error("  %s: ❌ OFFLINE", name)
                return

        api_health = await client.get(f"{API_URL}/health", timeout=5)
        log.info("  API: %s", "✅" if api_health.status_code == 200 else "❌")

    # Run validation
    honey = 0
    jelly = 0
    propolis = 0
    skipped = 0
    start_time = time.monotonic()

    async with httpx.AsyncClient() as client:
        for i, pair in enumerate(pairs):
            result = await validate_pair(client, pair, i, args.domain, args.session)

            # Write receipt
            with open(receipts_file, "a") as f:
                f.write(json.dumps(result) + "\n")

            if result["status"] == "skip":
                skipped += 1
                continue

            # Write to classification file with full pair
            entry = {**pair, "swarmchain_validation": result}

            if result["classification"] == "honey":
                honey += 1
                with open(honey_file, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            elif result["classification"] == "jelly":
                jelly += 1
                with open(jelly_file, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            else:
                propolis += 1
                with open(propolis_file, "a") as f:
                    f.write(json.dumps(entry) + "\n")

            # Progress
            elapsed = time.monotonic() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(pairs) - i - 1) / rate if rate > 0 else 0

            log.info(
                "[%d/%d] %s %s score=%.2f | H:%d J:%d P:%d | %.1f/min ETA:%.0fs",
                i + 1, len(pairs),
                result["classification"].upper(),
                result.get("verdict", "?"),
                result.get("score", 0),
                honey, jelly, propolis,
                rate * 60, eta,
            )

    # Final report
    wall = time.monotonic() - start_time
    verified = honey + jelly + propolis
    report = {
        "epoch": "epoch-1-validation",
        "domain": args.domain,
        "session": args.session,
        "input_file": str(input_path),
        "total_pairs": total,
        "limit": args.limit,
        "verified": verified,
        "skipped": skipped,
        "honey": honey,
        "jelly": jelly,
        "propolis": propolis,
        "honey_rate": round(honey / max(verified, 1), 4),
        "wall_time_sec": round(wall, 1),
        "pairs_per_minute": round(verified / (wall / 60), 2) if wall > 0 else 0,
        "protocol": {
            "look": "9B base (RTX 4500)",
            "judge": "27B base Q8 (RTX 6000)",
            "recorder": "Katniss SwarmRefinery 9B (RTX 3090 Ti)",
            "orchestrator": "Xeon w9-3475X",
        },
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    log.info("")
    log.info("═══════════════════════════════════════")
    log.info("  EPOCH 1 VALIDATION — %s — COMPLETE", args.domain.upper())
    log.info("═══════════════════════════════════════")
    log.info("  Verified:  %d pairs", verified)
    log.info("  Honey:     %d (%.1f%%)", honey, honey / max(verified, 1) * 100)
    log.info("  Jelly:     %d (%.1f%%)", jelly, jelly / max(verified, 1) * 100)
    log.info("  Propolis:  %d (%.1f%%)", propolis, propolis / max(verified, 1) * 100)
    log.info("  Time:      %.1fs (%.1f pairs/min)", wall, verified / (wall / 60) if wall > 0 else 0)
    log.info("  Output:    %s", output_dir)
    log.info("  Report:    %s", report_file)
    log.info("═══════════════════════════════════════")


def main():
    parser = argparse.ArgumentParser(description="SwarmChain Validation Orchestrator")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--session", default="epoch-1-validation")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
