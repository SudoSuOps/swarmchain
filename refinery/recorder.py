"""Refinery Recorder — writes deeds from judged verdicts.

Uses base 2B model (Qwen3.5-2B-Q4) with /no_think.
You don't hire a lawyer to fill out the deed at the courthouse.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

log = logging.getLogger("refinery.recorder")

RECORDER_SYSTEM_PROMPT = """/no_think
You are the SwarmChain Deed Recorder.
Write EXACTLY this format — nothing else:

PAIR_ID: <id>
DOMAIN: <domain>
PAIR_SUMMARY: <one sentence>
VERDICT: <PASS/FAIL>
SCORE: <0-100>
CLASSIFICATION: <royal-jelly/honey/propolis>
WHY_SEALED: <2 sentences>
RECORD_STATUS: SEALED"""


class Recorder:
    def __init__(self, domain: str, ports: list[int], api_url: str = "http://localhost:8080"):
        self.domain = domain
        self.ports = ports
        self.api_url = api_url

    async def run(self, bin_file: Path, output_dir: Path, existing: int = 0) -> dict:
        stats = {"recorded": 0, "r_honey": 0, "r_jelly": 0, "r_propolis": 0}
        work_q: asyncio.Queue = asyncio.Queue(maxsize=len(self.ports) * 2)
        write_lock = asyncio.Lock()
        start_time = time.monotonic()

        async with httpx.AsyncClient() as client:
            workers = [
                asyncio.create_task(
                    self._worker(i, self.ports[i], work_q, output_dir, write_lock, stats, client)
                )
                for i in range(len(self.ports))
            ]

            cursor = 0
            idle = 0
            while True:
                if bin_file.exists():
                    lines = open(bin_file).readlines()
                    new = []
                    for i in range(cursor, len(lines)):
                        try:
                            new.append(json.loads(lines[i]))
                        except Exception:
                            pass
                    if new:
                        idle = 0
                        for entry in new:
                            await work_q.put(entry)
                        cursor = len(lines)
                    else:
                        idle += 1
                else:
                    idle += 1

                receipts = output_dir / "receipts.jsonl"
                recorded = sum(1 for _ in open(receipts)) if receipts.exists() else 0
                if idle > 60 and recorded >= cursor + existing:
                    break
                await asyncio.sleep(5)

            for _ in range(len(self.ports)):
                await work_q.put(None)
            await asyncio.gather(*workers)

        wall = time.monotonic() - start_time
        stats["wall_sec"] = round(wall, 1)
        stats["rate"] = round(stats["recorded"] / (wall / 60), 1) if wall > 0 else 0
        return stats

    async def _worker(self, wid, port, q, output_dir, lock, stats, client):
        receipts_file = output_dir / "receipts.jsonl"
        while True:
            item = await q.get()
            if item is None:
                break
            entry = item
            c = entry["classification"]

            result = {
                "pair_index": entry["pair_index"],
                "domain": entry["domain"],
                "status": "verified",
                "verdict": entry["verdict"],
                "score": entry["score"],
                "classification": c,
                "sealed_at": datetime.now(timezone.utc).isoformat(),
            }

            async with lock:
                with open(receipts_file, "a") as f:
                    f.write(json.dumps(result) + "\n")
                with open(output_dir / f"{c}.jsonl", "a") as f:
                    f.write(json.dumps({**entry.get("pair", {}), "swarmchain_validation": result}) + "\n")
                stats["recorded"] += 1
                if c == "honey":
                    stats["r_honey"] += 1
                elif c == "jelly":
                    stats["r_jelly"] += 1
                else:
                    stats["r_propolis"] += 1
            q.task_done()
