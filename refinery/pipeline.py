"""End-to-end refinery pipeline — orchestrates judge → classify → record.

Usage:
    from refinery.pipeline import RefineryPipeline
    pipeline = RefineryPipeline(domain="finance")
    results = await pipeline.run(pairs, judge_ports=[8201], recorder_ports=[8097])
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from .judge import Judge
from .recorder import Recorder
from .classifier import classify_verdict

log = logging.getLogger("refinery.pipeline")


class RefineryPipeline:
    """Orchestrates the full validation pipeline for a domain."""

    def __init__(self, domain: str, output_dir: Path | None = None):
        self.domain = domain
        self.output_dir = output_dir or Path(f"/data1/swarm-honey/{domain}/validated")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        pairs: list[dict],
        judge_ports: list[int],
        recorder_ports: list[int],
        resume_from: int = 0,
    ) -> dict:
        """Run full pipeline: judge all pairs, then record all verdicts."""
        bin_file = self.output_dir / "judged.jsonl"

        # Phase 1: Judge
        log.info("JUDGE PHASE: %d pairs on %d judges", len(pairs), len(judge_ports))
        judge = Judge(self.domain, judge_ports)
        judge_stats = await judge.run(pairs[resume_from:], bin_file, start_idx=resume_from)
        log.info("Judged: %d (%.1f/min)", judge_stats["judged"], judge_stats["rate"])

        # Phase 2: Record
        log.info("RECORD PHASE: draining bin on %d recorders", len(recorder_ports))
        recorder = Recorder(self.domain, recorder_ports)
        record_stats = await recorder.run(bin_file, self.output_dir)
        log.info("Recorded: %d (%.1f/min)", record_stats["recorded"], record_stats["rate"])

        return {
            "domain": self.domain,
            "input_pairs": len(pairs),
            "judged": judge_stats["judged"],
            "recorded": record_stats["recorded"],
            "honey": judge_stats["honey"],
            "jelly": judge_stats["jelly"],
            "propolis": judge_stats["propolis"],
            "judge_rate": judge_stats["rate"],
            "recorder_rate": record_stats["rate"],
            "output_dir": str(self.output_dir),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
