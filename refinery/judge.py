"""Refinery Judge — renders quality verdicts on pairs.

Uses base 9B model (Qwen3.5-9B-Q4). No fine-tuned models in the validation chain.
The judge thinks. The recorder writes. Separation of concerns.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .classifier import classify_verdict

log = logging.getLogger("refinery.judge")

JUDGE_SYSTEM_PROMPT = """You are the final quality judge for AI training pairs.
Output EXACTLY this format — nothing else:

VERDICT: PASS or FAIL
TOTAL_SCORE: <number 0-100>
CLASSIFICATION: royal-jelly or honey or propolis
REASONING: <1-2 sentences max>

Scoring guide:
  royal-jelly (75-100): High quality, accurate, actionable, well-structured
  honey (50-74): Partial quality, some gaps, usable with improvement
  propolis (0-49): Low quality, inaccurate, or too generic

Be decisive. Be brief. No extra commentary."""


class Judge:
    def __init__(self, domain: str, ports: list[int]):
        self.domain = domain
        self.ports = ports

    async def run(self, pairs: list[dict], bin_file: Path, start_idx: int = 0) -> dict:
        stats = {"judged": 0, "honey": 0, "royal_jelly": 0, "propolis": 0, "skipped": 0}
        input_q: asyncio.Queue = asyncio.Queue(maxsize=100)
        write_lock = asyncio.Lock()
        start_time = time.monotonic()

        async with httpx.AsyncClient() as client:
            workers = [
                asyncio.create_task(
                    self._worker(i, self.ports[i % len(self.ports)],
                                 input_q, bin_file, write_lock, stats, client)
                )
                for i in range(len(self.ports))
            ]
            for i, pair in enumerate(pairs):
                await input_q.put((start_idx + i, pair, self.domain))
            for _ in range(len(self.ports)):
                await input_q.put(None)
            await asyncio.gather(*workers)

        wall = time.monotonic() - start_time
        stats["wall_sec"] = round(wall, 1)
        stats["rate"] = round(stats["judged"] / (wall / 60), 1) if wall > 0 else 0
        return stats

    async def _worker(self, wid, port, q, bin_file, lock, stats, client):
        while True:
            item = await q.get()
            if item is None:
                break
            idx, pair, domain = item
            msgs = pair.get("messages", [])
            up = next((m["content"] for m in msgs if m.get("role") == "user"), "")
            oa = next((m["content"] for m in msgs if m.get("role") == "assistant"), "")
            if not up or not oa:
                async with lock:
                    stats["skipped"] += 1
                q.task_done()
                continue

            text, ms = await self._call(client, port,
                                        f"DOMAIN: {domain}\n\nQUESTION:\n{up[:1500]}\n\nANSWER:\n{oa[:2000]}")
            verdict, score, classification = classify_verdict(text)

            entry = {
                "pair_index": idx, "domain": domain, "verdict": verdict,
                "score": score, "classification": classification,
                "judge_reasoning": text[:500], "judge_ms": ms,
                "judge_port": port, "user_prompt": up, "original_answer": oa,
                "pair": pair, "judged_at": datetime.now(timezone.utc).isoformat(),
            }
            async with lock:
                with open(bin_file, "a") as f:
                    f.write(json.dumps(entry) + "\n")
                stats["judged"] += 1
                if classification == "honey":
                    stats["honey"] += 1
                elif classification == "royal-jelly":
                    stats["royal_jelly"] += 1
                else:
                    stats["propolis"] += 1
            q.task_done()

    async def _call(self, client, port, user_msg):
        try:
            start = time.monotonic()
            resp = await client.post(
                f"http://localhost:{port}/v1/chat/completions",
                json={
                    "model": "default",
                    "messages": [
                        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 4096,
                    "temperature": 0.1,
                },
                timeout=180,
            )
            ms = round((time.monotonic() - start) * 1000)
            if resp.status_code != 200:
                return "", 0
            content = resp.json()["choices"][0]["message"].get("content", "")
            if "<think>" in content:
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return content, ms
        except Exception:
            return "", 0
