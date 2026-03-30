#!/usr/bin/env python3
"""
SwarmChain Domain Verification Pipeline
=========================================
Takes raw domain pairs and runs them through the chain.
Each pair becomes a verification block:
  - Bees attempt to reproduce the assistant's answer
  - Deterministic scoring compares bee output to original
  - Honey/jelly/propolis classification with full receipt
  - SwarmRefinery (Katniss 9B) audits the results

This is the refinery doing real work.
"A pair is not a pair if it's not defendable and bankable."

Usage:
  python3 verify_domain.py \
    --domain failure \
    --input /data1/swarm-honey/failure/failure_intelligence.jsonl \
    --limit 100 \
    --output /data1/swarm-honey/failure/verified/ \
    --api-url http://localhost:8080
"""

import asyncio
import json
import time
import hashlib
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
log = logging.getLogger("domain-verify")

# ── Config ──────────────────────────────────────────────────
RAILS_HOST = os.environ.get("SWARM_RAILS_HOST", "localhost")

# Models to use for verification (ordered by escalation)
MODELS = [
    {"name": "bee-3b",     "url": f"http://{RAILS_HOST}:9100/v1/chat/completions", "tier": "cpu"},
    {"name": "bee-3b-2",   "url": f"http://{RAILS_HOST}:9101/v1/chat/completions", "tier": "cpu"},
    {"name": "bee-3b-3",   "url": f"http://{RAILS_HOST}:9102/v1/chat/completions", "tier": "cpu"},
    {"name": "gpu-4b",     "url": f"http://{RAILS_HOST}:8094/v1/chat/completions", "tier": "gpu"},
    {"name": "katniss-9b", "url": f"http://{RAILS_HOST}:8090/v1/chat/completions", "tier": "gpu"},
]

# Scoring thresholds
HONEY_THRESHOLD = 0.85   # verified reproducible
JELLY_THRESHOLD = 0.40   # partially reproducible
# below jelly = propolis (not reproducible)

# ── Scoring ─────────────────────────────────────────────────

def score_response(original: str, candidate: str) -> dict:
    """Score a candidate response against the original.

    Multi-dimensional scoring:
    1. Length ratio — is the response similar length?
    2. Key phrase overlap — do they share important terms?
    3. Structure match — similar formatting (bullets, headers)?
    4. Content hash similarity — character-level overlap

    Returns dict with component scores and final score.
    """
    if not original or not candidate:
        return {"final_score": 0.0, "reason": "empty response"}

    orig_lower = original.lower().strip()
    cand_lower = candidate.lower().strip()

    # 1. Length ratio (0-1): penalize if way too short or too long
    len_ratio = min(len(cand_lower), len(orig_lower)) / max(len(cand_lower), len(orig_lower), 1)
    length_score = len_ratio if len_ratio > 0.3 else len_ratio * 0.5

    # 2. Key phrase overlap: extract significant words (>4 chars), compute Jaccard
    def extract_words(text):
        return set(w for w in text.split() if len(w) > 4 and w.isalpha())

    orig_words = extract_words(orig_lower)
    cand_words = extract_words(cand_lower)
    if orig_words and cand_words:
        intersection = orig_words & cand_words
        union = orig_words | cand_words
        word_overlap = len(intersection) / len(union) if union else 0
    else:
        word_overlap = 0.0

    # 3. Structure match: check for similar formatting markers
    def structure_features(text):
        features = set()
        if '\n-' in text or '\n*' in text: features.add('bullets')
        if '\n#' in text or '**' in text: features.add('headers')
        if '```' in text: features.add('code')
        if '|' in text and '-|-' in text.replace(' ', ''): features.add('table')
        if '<reasoning>' in text or '<think>' in text: features.add('reasoning')
        lines = text.strip().split('\n')
        if len(lines) > 5: features.add('multiline')
        if len(lines) > 20: features.add('long')
        return features

    orig_struct = structure_features(orig_lower)
    cand_struct = structure_features(cand_lower)
    if orig_struct or cand_struct:
        struct_overlap = len(orig_struct & cand_struct) / len(orig_struct | cand_struct) if (orig_struct | cand_struct) else 0
    else:
        struct_overlap = 1.0  # both plain text = match

    # 4. N-gram overlap (trigrams for content similarity)
    def trigrams(text):
        words = text.split()
        return set(tuple(words[i:i+3]) for i in range(len(words)-2))

    orig_tri = trigrams(orig_lower)
    cand_tri = trigrams(cand_lower)
    if orig_tri and cand_tri:
        tri_overlap = len(orig_tri & cand_tri) / len(orig_tri) if orig_tri else 0
    else:
        tri_overlap = 0.0

    # Final weighted score
    final = (
        length_score * 0.15 +
        word_overlap * 0.35 +
        struct_overlap * 0.15 +
        tri_overlap * 0.35
    )

    return {
        "final_score": round(final, 4),
        "length_score": round(length_score, 4),
        "word_overlap": round(word_overlap, 4),
        "struct_overlap": round(struct_overlap, 4),
        "trigram_overlap": round(tri_overlap, 4),
    }


def classify(score: float) -> str:
    """Honey/jelly/propolis classification."""
    if score >= HONEY_THRESHOLD:
        return "honey"
    elif score >= JELLY_THRESHOLD:
        return "jelly"
    return "propolis"


# ── Model Dispatch ──────────────────────────────────────────

async def call_model(client: httpx.AsyncClient, model: dict, messages: list, max_tokens: int = 2048) -> dict | None:
    """Call a model endpoint and return the response."""
    try:
        start = time.monotonic()
        resp = await client.post(
            model["url"],
            json={
                "model": model["name"],
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
            timeout=60,
        )
        latency = time.monotonic() - start

        if resp.status_code != 200:
            return None

        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        return {
            "content": content,
            "model": model["name"],
            "tier": model["tier"],
            "latency_ms": round(latency * 1000),
            "tokens": data.get("usage", {}).get("total_tokens", 0),
        }
    except Exception as e:
        log.debug("Model %s failed: %s", model["name"], e)
        return None


# ── Verification Pipeline ───────────────────────────────────

async def verify_pair(
    client: httpx.AsyncClient,
    pair: dict,
    pair_index: int,
    models: list[dict],
) -> dict:
    """Verify a single pair through the tribunal.

    1. Extract user prompt + original assistant answer
    2. Send user prompt to multiple bees
    3. Score each bee's response against the original
    4. Best score = the pair's verification score
    5. Classify and receipt
    """
    messages = pair.get("messages", [])
    user_msg = None
    system_msg = None
    original_answer = None

    for m in messages:
        if m.get("role") == "system":
            system_msg = m.get("content", "")
        elif m.get("role") == "user":
            user_msg = m.get("content", "")
        elif m.get("role") == "assistant":
            original_answer = m.get("content", "")

    if not user_msg or not original_answer:
        return {
            "pair_index": pair_index,
            "status": "skip",
            "reason": "missing user or assistant message",
        }

    # Build the prompt for bees (system + user, no assistant)
    bee_messages = []
    if system_msg:
        bee_messages.append({"role": "system", "content": system_msg})
    bee_messages.append({"role": "user", "content": user_msg})

    # Dispatch to models — escalation: bees first, then GPU, then Katniss
    attempts = []
    best_score = 0.0
    best_attempt = None

    for model in models:
        result = await call_model(client, model, bee_messages)
        if result is None:
            continue

        # Score against original
        scoring = score_response(original_answer, result["content"])
        score = scoring["final_score"]

        attempt = {
            "model": result["model"],
            "tier": result["tier"],
            "score": score,
            "scoring_detail": scoring,
            "latency_ms": result["latency_ms"],
            "tokens": result["tokens"],
            "response_length": len(result["content"]),
        }
        attempts.append(attempt)

        if score > best_score:
            best_score = score
            best_attempt = attempt

        # Early exit if honey — no need to escalate further
        if score >= HONEY_THRESHOLD:
            break

    classification = classify(best_score)

    # Build the verification receipt
    receipt = {
        "pair_index": pair_index,
        "cell_id": pair.get("cell_id", ""),
        "fingerprint": pair.get("fingerprint", ""),
        "domain": pair.get("domain", ""),
        "skill": pair.get("skill", ""),
        "task_type": pair.get("task_type", ""),
        "original_grade": pair.get("grade", ""),
        "original_verification_score": pair.get("verification_score"),
        "status": "verified",
        "classification": classification,
        "best_score": best_score,
        "best_model": best_attempt["model"] if best_attempt else None,
        "best_tier": best_attempt["tier"] if best_attempt else None,
        "attempts": len(attempts),
        "attempt_details": attempts,
        "total_energy": sum(a.get("latency_ms", 0) for a in attempts),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "user_prompt_length": len(user_msg),
        "original_answer_length": len(original_answer),
    }

    return receipt


# ── Main ────────────────────────────────────────────────────

async def run_verification(args):
    """Run the full domain verification pipeline."""
    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load pairs
    log.info("Loading %s...", input_path)
    pairs = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))

    total = len(pairs)
    if args.limit:
        pairs = pairs[:args.limit]
    log.info("Loaded %d pairs (limit: %s)", len(pairs), args.limit or "none")

    # Output files
    honey_file = output_dir / "honey.jsonl"
    jelly_file = output_dir / "jelly.jsonl"
    propolis_file = output_dir / "propolis.jsonl"
    receipts_file = output_dir / "receipts.jsonl"
    report_file = output_dir / "verification_report.json"

    # Filter active models (health check)
    active_models = []
    async with httpx.AsyncClient() as client:
        for m in MODELS:
            try:
                health_url = m["url"].replace("/v1/chat/completions", "/health")
                resp = await client.get(health_url, timeout=3)
                if resp.status_code == 200:
                    active_models.append(m)
                    log.info("  ✅ %s (%s)", m["name"], m["tier"])
            except:
                log.info("  ❌ %s — offline", m["name"])

    if not active_models:
        log.error("No models available. Start the fleet first.")
        return

    log.info("Active models: %d", len(active_models))

    # Run verification
    honey_count = 0
    jelly_count = 0
    propolis_count = 0
    skip_count = 0
    total_energy = 0
    start_time = time.monotonic()

    async with httpx.AsyncClient() as client:
        for i, pair in enumerate(pairs):
            receipt = await verify_pair(client, pair, i, active_models)

            # Write receipt
            with open(receipts_file, "a") as f:
                f.write(json.dumps(receipt) + "\n")

            if receipt["status"] == "skip":
                skip_count += 1
                continue

            # Write to classification file
            classified_pair = {
                **pair,
                "swarmchain_verification": {
                    "classification": receipt["classification"],
                    "score": receipt["best_score"],
                    "model": receipt["best_model"],
                    "attempts": receipt["attempts"],
                    "verified_at": receipt["verified_at"],
                }
            }

            if receipt["classification"] == "honey":
                honey_count += 1
                with open(honey_file, "a") as f:
                    f.write(json.dumps(classified_pair) + "\n")
            elif receipt["classification"] == "jelly":
                jelly_count += 1
                with open(jelly_file, "a") as f:
                    f.write(json.dumps(classified_pair) + "\n")
            else:
                propolis_count += 1
                with open(propolis_file, "a") as f:
                    f.write(json.dumps(classified_pair) + "\n")

            total_energy += receipt.get("total_energy", 0)

            # Progress
            if (i + 1) % 10 == 0 or i == len(pairs) - 1:
                elapsed = time.monotonic() - start_time
                rate = (i + 1) / elapsed
                eta = (len(pairs) - i - 1) / rate if rate > 0 else 0
                log.info(
                    "[%d/%d] honey=%d jelly=%d propolis=%d skip=%d (%.1f pairs/min, ETA %.0fs)",
                    i + 1, len(pairs), honey_count, jelly_count, propolis_count, skip_count,
                    rate * 60, eta,
                )

    # Final report
    wall_time = time.monotonic() - start_time
    verified = honey_count + jelly_count + propolis_count
    report = {
        "domain": args.domain,
        "input_file": str(input_path),
        "total_pairs": total,
        "verified": verified,
        "skipped": skip_count,
        "honey": honey_count,
        "jelly": jelly_count,
        "propolis": propolis_count,
        "honey_rate": round(honey_count / max(verified, 1), 4),
        "jelly_rate": round(jelly_count / max(verified, 1), 4),
        "propolis_rate": round(propolis_count / max(verified, 1), 4),
        "total_energy_ms": total_energy,
        "wall_time_sec": round(wall_time, 1),
        "pairs_per_minute": round(verified / (wall_time / 60), 1),
        "models_used": [m["name"] for m in active_models],
        "scoring_thresholds": {
            "honey": HONEY_THRESHOLD,
            "jelly": JELLY_THRESHOLD,
        },
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    log.info("")
    log.info("═══════════════════════════════════════")
    log.info("  DOMAIN VERIFICATION COMPLETE")
    log.info("═══════════════════════════════════════")
    log.info("  Domain:    %s", args.domain)
    log.info("  Verified:  %d pairs", verified)
    log.info("  Honey:     %d (%.1f%%)", honey_count, honey_count / max(verified, 1) * 100)
    log.info("  Jelly:     %d (%.1f%%)", jelly_count, jelly_count / max(verified, 1) * 100)
    log.info("  Propolis:  %d (%.1f%%)", propolis_count, propolis_count / max(verified, 1) * 100)
    log.info("  Time:      %.1f seconds (%.1f pairs/min)", wall_time, verified / (wall_time / 60))
    log.info("  Output:    %s", output_dir)
    log.info("═══════════════════════════════════════")


def main():
    parser = argparse.ArgumentParser(description="SwarmChain Domain Verification")
    parser.add_argument("--domain", required=True, help="Domain name (e.g., failure)")
    parser.add_argument("--input", required=True, help="Input JSONL file")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--limit", type=int, default=None, help="Limit pairs to verify")
    parser.add_argument("--api-url", default="http://localhost:8080", help="SwarmChain API URL")
    args = parser.parse_args()

    asyncio.run(run_verification(args))


if __name__ == "__main__":
    main()
