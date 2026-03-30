#!/usr/bin/env python3
"""SwarmChain Training Data Exporter — exports sealed blocks as JSONL for SwarmRefinery v1.

Fetches all sealed blocks (solved + exhausted) from the API, enriches each with
attempts, lineage, artifacts, and reward data, then writes a JSONL file plus a
summary JSON.

Usage:
    python export_training_data.py --api-url http://localhost:8080
    python export_training_data.py --api-url http://localhost:8080 --output my_dataset.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [export] %(message)s",
)
log = logging.getLogger("export")


class TrainingDataExporter:
    """Exports sealed SwarmChain blocks as JSONL for training."""

    def __init__(self, api_url: str, output: str, api_key: str | None):
        self.api_url = api_url.rstrip("/")
        self.output = output
        self.api_key = api_key

        # Summary aggregates
        self.total_blocks = 0
        self.solved_count = 0
        self.exhausted_count = 0
        self.total_attempts = 0
        self.total_energy = 0.0
        self.strategy_global: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "total_score": 0.0, "max_score": 0.0, "solves": 0}
        )
        self.grid_sizes: dict[str, int] = defaultdict(int)
        self.easiest_tasks: list[dict] = []
        self.hardest_tasks: list[dict] = []

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict | None:
        url = f"{self.api_url}{path}"
        try:
            resp = await client.get(url, params=params, headers=self._headers(), timeout=60.0)
            if resp.status_code >= 400:
                log.warning("GET %s -> %d: %s", path, resp.status_code, resp.text[:200])
                return None
            return resp.json()
        except httpx.HTTPError as exc:
            log.error("GET %s error: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Fetch all sealed blocks with pagination
    # ------------------------------------------------------------------

    async def fetch_sealed_blocks(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch all sealed blocks (solved + exhausted) via paginated GET."""
        all_blocks: list[dict] = []

        for status in ("solved", "exhausted"):
            offset = 0
            page_size = 50
            while True:
                data = await self._get(client, "/blocks", {
                    "status": status,
                    "limit": page_size,
                    "offset": offset,
                })
                if not data or not data.get("blocks"):
                    break
                blocks = data["blocks"]
                all_blocks.extend(blocks)
                if len(blocks) < page_size:
                    break
                offset += page_size

        log.info("Fetched %d sealed blocks total", len(all_blocks))
        return all_blocks

    # ------------------------------------------------------------------
    # Fetch enrichment data for a single block
    # ------------------------------------------------------------------

    async def fetch_attempts(self, client: httpx.AsyncClient, block_id: str) -> list[dict]:
        """Fetch all attempts for a block, paginated."""
        all_attempts: list[dict] = []
        offset = 0
        page_size = 100
        while True:
            data = await self._get(client, f"/attempts/block/{block_id}", {
                "limit": page_size,
                "offset": offset,
            })
            if not data or not data.get("attempts"):
                break
            attempts = data["attempts"]
            all_attempts.extend(attempts)
            if len(attempts) < page_size:
                break
            offset += page_size
        return all_attempts

    async def fetch_lineage(self, client: httpx.AsyncClient, block_id: str) -> list[dict]:
        """Fetch lineage edges for a block."""
        data = await self._get(client, f"/attempts/block/{block_id}/lineage")
        if data:
            return data.get("edges", [])
        return []

    async def fetch_artifacts(self, client: httpx.AsyncClient, block_id: str) -> list[dict]:
        """Fetch sealed artifacts for a block."""
        data = await self._get(client, f"/blocks/{block_id}/artifacts")
        if isinstance(data, list):
            return data
        return []

    async def fetch_rewards(self, client: httpx.AsyncClient, block_id: str) -> dict | None:
        """Fetch reward breakdown for a block."""
        return await self._get(client, f"/blocks/{block_id}/rewards")

    # ------------------------------------------------------------------
    # Process a single block into a training record
    # ------------------------------------------------------------------

    async def process_block(self, client: httpx.AsyncClient, block: dict) -> dict:
        """Enrich a block with attempts, lineage, artifacts, rewards."""
        block_id = block["block_id"]
        task_id = block.get("task_id", "")
        status = block.get("status", "unknown")
        task_payload = block.get("task_payload", {})

        # Fetch enrichment data concurrently
        attempts_task = self.fetch_attempts(client, block_id)
        lineage_task = self.fetch_lineage(client, block_id)
        artifacts_task = self.fetch_artifacts(client, block_id)
        rewards_task = self.fetch_rewards(client, block_id)

        attempts, lineage, artifacts, rewards_data = await asyncio.gather(
            attempts_task, lineage_task, artifacts_task, rewards_task,
            return_exceptions=True,
        )

        # Handle any exceptions from gather
        if isinstance(attempts, Exception):
            log.warning("Error fetching attempts for %s: %s", block_id, attempts)
            attempts = []
        if isinstance(lineage, Exception):
            lineage = []
        if isinstance(artifacts, Exception):
            artifacts = []
        if isinstance(rewards_data, Exception):
            rewards_data = None

        # Build strategy stats for this block
        strategy_stats: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "avg_score": 0.0, "max_score": 0.0, "total_score": 0.0, "solved": False}
        )
        for att in attempts:
            strat = att.get("strategy_family", "unknown")
            score = att.get("score", 0.0)
            ss = strategy_stats[strat]
            ss["count"] += 1
            ss["total_score"] += score
            if score > ss["max_score"]:
                ss["max_score"] = score
            if score == 1.0:
                ss["solved"] = True

            # Also update global strategy stats
            gs = self.strategy_global[strat]
            gs["count"] += 1
            gs["total_score"] += score
            if score > gs["max_score"]:
                gs["max_score"] = score
            if score == 1.0:
                gs["solves"] += 1

        # Compute avg_score in strategy_stats
        for ss in strategy_stats.values():
            if ss["count"] > 0:
                ss["avg_score"] = ss["total_score"] / ss["count"]
            del ss["total_score"]  # not needed in output

        # Build attempt list for output (simplified)
        attempt_records = []
        for att in attempts:
            attempt_records.append({
                "attempt_id": att.get("attempt_id"),
                "node_id": att.get("node_id"),
                "strategy": att.get("strategy_family"),
                "score": att.get("score", 0.0),
                "output_grid": att.get("output_json", {}).get("grid"),
                "parent_attempt_id": att.get("parent_attempt_id"),
                "promoted": att.get("promoted", False),
                "pruned": att.get("pruned", False),
                "energy_cost": att.get("energy_cost", 0.0),
                "latency_ms": att.get("latency_ms", 0),
            })

        # Find winning attempt
        winning_attempt_id = block.get("winning_attempt_id")
        winning_lineage_chain: list[str] = []
        if winning_attempt_id and lineage:
            # Trace lineage chain backwards from winner
            parent_map: dict[str, str] = {}
            for edge in lineage:
                child = edge.get("child_attempt_id")
                parent = edge.get("parent_attempt_id")
                if child and parent:
                    parent_map[child] = parent

            current = winning_attempt_id
            chain = [current]
            visited = {current}
            while current in parent_map:
                parent = parent_map[current]
                if parent in visited:
                    break
                chain.append(parent)
                visited.add(parent)
                current = parent
            winning_lineage_chain = list(reversed(chain))

        # Build elimination summary
        total_att = len(attempts)
        pruned = sum(1 for a in attempts if a.get("pruned", False))
        promoted = sum(1 for a in attempts if a.get("promoted", False))
        avg_score = sum(a.get("score", 0.0) for a in attempts) / max(total_att, 1)

        elimination_summary = {
            "total_attempts": total_att,
            "pruned": pruned,
            "promoted": promoted,
            "avg_score": round(avg_score, 4),
        }

        # Update global counters
        self.total_blocks += 1
        self.total_attempts += total_att
        self.total_energy += block.get("total_energy", 0.0)
        if status == "solved":
            self.solved_count += 1
        else:
            self.exhausted_count += 1

        # Track grid sizes
        input_grid = task_payload.get("input_grid", [])
        if input_grid:
            rows = len(input_grid)
            cols = len(input_grid[0]) if rows > 0 else 0
            self.grid_sizes[f"{rows}x{cols}"] += 1

        # Build the JSONL record
        record = {
            "block_id": block_id,
            "task_id": task_id,
            "task_description": task_payload.get("description", ""),
            "input_grid": task_payload.get("input_grid"),
            "expected_output": task_payload.get("expected_output"),
            "status": status,
            "final_score": block.get("final_score"),
            "attempt_count": total_att,
            "attempts": attempt_records,
            "winning_attempt_id": winning_attempt_id,
            "winning_lineage": winning_lineage_chain,
            "strategy_stats": dict(strategy_stats),
            "elimination_summary": elimination_summary,
        }

        return record

    # ------------------------------------------------------------------
    # Summary generation
    # ------------------------------------------------------------------

    def build_summary(self, all_records: list[dict]) -> dict:
        """Build the summary JSON from all exported records."""
        # Strategy effectiveness ranking
        strategy_ranking = []
        for name, gs in self.strategy_global.items():
            avg = gs["total_score"] / max(gs["count"], 1)
            strategy_ranking.append({
                "strategy": name,
                "total_attempts": gs["count"],
                "avg_score": round(avg, 4),
                "max_score": gs["max_score"],
                "total_solves": gs["solves"],
                "solve_rate": round(gs["solves"] / max(gs["count"], 1), 4),
            })
        strategy_ranking.sort(key=lambda x: x["solve_rate"], reverse=True)

        # Best/worst tasks by solve difficulty
        task_difficulty = []
        for rec in all_records:
            task_difficulty.append({
                "task_id": rec["task_id"],
                "status": rec["status"],
                "attempt_count": rec["attempt_count"],
                "final_score": rec.get("final_score"),
                "avg_score": rec["elimination_summary"]["avg_score"],
            })

        # Easiest: solved with fewest attempts
        solved_tasks = [t for t in task_difficulty if t["status"] == "solved"]
        solved_tasks.sort(key=lambda x: x["attempt_count"])
        easiest = solved_tasks[:10]

        # Hardest: exhausted or solved with most attempts
        task_difficulty.sort(key=lambda x: x["attempt_count"], reverse=True)
        hardest = task_difficulty[:10]

        summary = {
            "export_metadata": {
                "exporter": "SwarmChain Training Data Exporter v1",
                "format": "jsonl",
                "output_file": self.output,
            },
            "totals": {
                "total_blocks": self.total_blocks,
                "solved": self.solved_count,
                "exhausted": self.exhausted_count,
                "solve_rate": round(self.solved_count / max(self.total_blocks, 1), 4),
                "total_attempts": self.total_attempts,
                "total_energy": round(self.total_energy, 2),
            },
            "strategy_effectiveness": strategy_ranking,
            "grid_size_distribution": dict(sorted(self.grid_sizes.items())),
            "easiest_tasks": easiest,
            "hardest_tasks": hardest,
        }

        return summary

    # ------------------------------------------------------------------
    # Main export loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Execute the full export pipeline."""
        t0 = time.time()

        async with httpx.AsyncClient() as client:
            # Check API
            root = await self._get(client, "/")
            if not root:
                log.error("Cannot reach API at %s", self.api_url)
                return
            log.info("API alive: %s v%s", root.get("service"), root.get("version"))

            # Fetch all sealed blocks
            blocks = await self.fetch_sealed_blocks(client)
            if not blocks:
                log.error("No sealed blocks found. Nothing to export.")
                return

            log.info("Processing %d blocks...", len(blocks))

            # Process blocks with concurrency limit
            sem = asyncio.Semaphore(10)
            all_records: list[dict] = []

            async def _process(block: dict) -> dict:
                async with sem:
                    return await self.process_block(client, block)

            # Process in batches for progress reporting
            batch_size = 50
            for i in range(0, len(blocks), batch_size):
                batch = blocks[i:i + batch_size]
                results = await asyncio.gather(
                    *[_process(b) for b in batch],
                    return_exceptions=True,
                )
                for r in results:
                    if isinstance(r, dict):
                        all_records.append(r)
                    elif isinstance(r, Exception):
                        log.warning("Error processing block: %s", r)

                exported = len(all_records)
                total = len(blocks)
                log.info("%d/%d blocks exported...", exported, total)

        # Write JSONL
        jsonl_path = self.output
        with open(jsonl_path, "w") as f:
            for record in all_records:
                f.write(json.dumps(record, default=str) + "\n")
        log.info("JSONL written: %s (%d records)", jsonl_path, len(all_records))

        # Write summary
        summary = self.build_summary(all_records)
        summary_path = jsonl_path.replace(".jsonl", "_summary.json")
        if summary_path == jsonl_path:
            summary_path = jsonl_path + "_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        log.info("Summary written: %s", summary_path)

        elapsed = time.time() - t0
        file_size_mb = os.path.getsize(jsonl_path) / (1024 * 1024)

        # Print final report
        print("\n" + "=" * 60)
        print("  EXPORT COMPLETE")
        print("=" * 60)
        print(f"  Blocks exported:  {len(all_records)}")
        print(f"  Solved:           {self.solved_count}")
        print(f"  Exhausted:        {self.exhausted_count}")
        print(f"  Total attempts:   {self.total_attempts:,}")
        print(f"  Total energy:     {self.total_energy:,.1f}")
        print(f"  JSONL file:       {jsonl_path} ({file_size_mb:.1f} MB)")
        print(f"  Summary file:     {summary_path}")
        print(f"  Runtime:          {elapsed:.1f}s")
        print()
        print("  Strategy effectiveness (top 10):")
        for s in summary["strategy_effectiveness"][:10]:
            print(f"    {s['strategy']:<22} solve_rate={s['solve_rate']:.2%}  "
                  f"avg={s['avg_score']:.3f}  attempts={s['total_attempts']}")
        print()
        print("  Grid size distribution:")
        for size, count in sorted(summary["grid_size_distribution"].items()):
            print(f"    {size:<6} {count:>5} blocks")
        print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SwarmChain Training Data Exporter -- export sealed blocks as JSONL",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080",
        help="SwarmChain API base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--output",
        default="swarmchain_training_v1.jsonl",
        help="Output JSONL file path (default: swarmchain_training_v1.jsonl)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional API key for authenticated endpoints",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exporter = TrainingDataExporter(
        api_url=args.api_url,
        output=args.output,
        api_key=args.api_key,
    )
    asyncio.run(exporter.run())


if __name__ == "__main__":
    main()
