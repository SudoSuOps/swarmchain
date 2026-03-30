#!/usr/bin/env python3
"""SwarmChain Real Worker — connects to actual model endpoints, measures real energy.

This is NOT simulation. This calls real LLM inference and submits real attempts
with real energy measurements. Deploy on any machine in the swarm.

Usage:
  # CPU worker calling local llama-server (BitNet/SwarmJelly)
  python real_worker.py --api-url http://165.227.109.67/api \
    --model-url http://localhost:8085/v1/completions \
    --node-type cpu-bitnet --hardware-class xeon-72t \
    --api-key <key>

  # GPU worker calling vLLM (Capital 9B)
  python real_worker.py --api-url http://165.227.109.67/api \
    --model-url http://localhost:8081/v1/completions \
    --node-type gpu-mid --hardware-class rtx3090 \
    --api-key <key>

  # Edge worker on Jetson
  python real_worker.py --api-url http://165.227.109.67/api \
    --model-url http://localhost:8085/v1/completions \
    --node-type edge-jetson --hardware-class jetson-orin-8gb \
    --api-key <key>
"""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import platform
import signal
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("swarm-worker")

# ─── Energy Metering ──────────────────────────────────────────────────────────

class EnergyMeter:
    """Measures real compute energy per inference call.

    CPU: tracks process CPU time (seconds) → converts to energy units
    GPU: reads nvidia-smi power draw if available
    """

    def __init__(self, hardware_class: str):
        self.hardware_class = hardware_class
        self.has_gpu = self._check_gpu()

    @staticmethod
    def _check_gpu() -> bool:
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def start(self) -> dict:
        """Start an energy measurement window."""
        state = {
            "wall_start": time.monotonic(),
            "cpu_start": time.process_time(),
        }
        if self.has_gpu:
            state["gpu_power_start"] = self._read_gpu_power()
        return state

    def stop(self, state: dict) -> dict:
        """Stop measurement, compute energy consumed.

        Returns:
            {energy_cost: float, wall_ms: int, cpu_ms: int, gpu_watt_sec: float | None}
        """
        wall_elapsed = time.monotonic() - state["wall_start"]
        cpu_elapsed = time.process_time() - state["cpu_start"]

        result = {
            "wall_ms": int(wall_elapsed * 1000),
            "cpu_ms": int(cpu_elapsed * 1000),
        }

        if self.has_gpu and "gpu_power_start" in state:
            gpu_power = self._read_gpu_power()
            # Average power (watts) × time (seconds) = watt-seconds (joules)
            avg_power = (state["gpu_power_start"] + gpu_power) / 2
            result["gpu_watt_sec"] = round(avg_power * wall_elapsed, 4)
            # Energy cost = GPU watt-seconds (dominant cost for GPU workers)
            result["energy_cost"] = result["gpu_watt_sec"]
        else:
            # CPU-only: energy = CPU seconds (normalized)
            # 1 CPU-second ≈ 0.1 energy units (calibrated for Xeon ~150W TDP)
            result["gpu_watt_sec"] = None
            result["energy_cost"] = round(cpu_elapsed * 0.1, 4)

        return result

    @staticmethod
    def _read_gpu_power() -> float:
        """Read current GPU power draw in watts."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            return float(result.stdout.strip().split("\n")[0])
        except Exception:
            return 0.0


# ─── Model Client ─────────────────────────────────────────────────────────────

class ModelClient:
    """Calls a real LLM endpoint (OpenAI-compatible /v1/completions or /v1/chat/completions)."""

    def __init__(self, model_url: str, model_name: str = "default", max_tokens: int = 512):
        self.model_url = model_url.rstrip("/")
        self.model_name = model_name
        self.max_tokens = max_tokens
        # Detect endpoint type
        self.is_chat = "/chat/" in model_url

    async def generate(self, client: httpx.AsyncClient, prompt: str) -> str:
        """Send a prompt to the model and return the response text."""
        if self.is_chat:
            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.max_tokens,
                "temperature": 0.7,
            }
        else:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "max_tokens": self.max_tokens,
                "temperature": 0.7,
            }

        try:
            resp = await client.post(self.model_url, json=payload, timeout=120.0)
            if resp.status_code != 200:
                log.warning("Model returned %d: %s", resp.status_code, resp.text[:200])
                return ""

            data = resp.json()
            if self.is_chat:
                return data["choices"][0]["message"]["content"]
            else:
                return data["choices"][0]["text"]

        except Exception as e:
            log.error("Model call failed: %s", e)
            return ""


# ─── Prompt Builder ───────────────────────────────────────────────────────────

def build_arc_prompt(task_payload: dict) -> str:
    """Build a prompt for an ARC grid task."""
    desc = task_payload.get("description", "Transform the grid")
    input_grid = task_payload.get("input_grid", [])

    return (
        f"You are solving an ARC grid transformation task.\n\n"
        f"Task: {desc}\n\n"
        f"Input grid:\n{json.dumps(input_grid)}\n\n"
        f"Output ONLY the transformed grid as a JSON array of arrays. "
        f"No explanation, no markdown, just the grid.\n\n"
        f"Output grid:"
    )


def parse_grid_response(response: str) -> list[list[int]] | None:
    """Parse a model response into a grid. Handles various formats."""
    text = response.strip()

    # Try direct JSON parse
    try:
        grid = json.loads(text)
        if isinstance(grid, list) and all(isinstance(row, list) for row in grid):
            return [[int(c) for c in row] for row in grid]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Try extracting JSON from markdown code blocks
    for marker in ["```json", "```"]:
        if marker in text:
            start = text.index(marker) + len(marker)
            end = text.index("```", start) if "```" in text[start:] else len(text)
            try:
                grid = json.loads(text[start:end].strip())
                if isinstance(grid, list):
                    return [[int(c) for c in row] for row in grid]
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    # Try finding array pattern
    import re
    match = re.search(r'\[\s*\[.*?\]\s*\]', text, re.DOTALL)
    if match:
        try:
            grid = json.loads(match.group())
            if isinstance(grid, list):
                return [[int(c) for c in row] for row in grid]
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    return None


# ─── Real Worker ──────────────────────────────────────────────────────────────

class RealWorker:
    """A real SwarmChain worker that calls actual model inference.

    This is not simulation. Real compute. Real energy. Real data.
    """

    def __init__(
        self,
        api_url: str,
        model_url: str,
        node_id: str,
        node_type: str,
        hardware_class: str,
        api_key: str = "",
        model_name: str = "default",
        max_concurrent: int = 1,
    ):
        self.api_url = api_url.rstrip("/")
        self.node_id = node_id
        self.node_type = node_type
        self.hardware_class = hardware_class
        self.api_key = api_key
        self.model_client = ModelClient(model_url, model_name)
        self.energy_meter = EnergyMeter(hardware_class)
        self.max_concurrent = max_concurrent
        self._running = True

        # Stats
        self.total_attempts = 0
        self.total_solves = 0
        self.total_energy = 0.0

    async def run(self):
        """Main worker loop — register, then mine forever."""
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        async with httpx.AsyncClient(headers=headers, timeout=120.0) as client:
            # Register
            resp = await client.post(f"{self.api_url}/nodes/register", json={
                "node_id": self.node_id,
                "node_type": self.node_type,
                "hardware_class": self.hardware_class,
                "metadata": {
                    "platform": platform.platform(),
                    "cpu_count": os.cpu_count(),
                    "worker_version": "real-worker-v1",
                },
            })
            if resp.status_code != 200:
                log.error("Failed to register: %s", resp.text[:200])
                return
            log.info("Registered as %s (%s/%s)", self.node_id, self.node_type, self.hardware_class)

            # Mine loop
            while self._running:
                try:
                    await self._mine_cycle(client)
                except Exception as e:
                    log.error("Mine cycle error: %s", e)

                await asyncio.sleep(1.0)

    async def _mine_cycle(self, client: httpx.AsyncClient):
        """One mining cycle: find open block, generate attempt, submit."""
        # Find open blocks
        resp = await client.get(f"{self.api_url}/blocks", params={"status": "open"})
        if resp.status_code != 200:
            log.debug("No blocks response: %s", resp.status_code)
            await asyncio.sleep(5.0)
            return

        data = resp.json()
        blocks = data.get("blocks", [])
        if not blocks:
            log.debug("No open blocks, waiting...")
            await asyncio.sleep(5.0)
            return

        # Pick a block (random for diversity)
        import random
        block = random.choice(blocks)
        block_id = block["block_id"]
        task_payload = block.get("task_payload", {})

        # Build prompt
        prompt = build_arc_prompt(task_payload)

        # Call model with energy metering
        meter_state = self.energy_meter.start()
        response_text = await self.model_client.generate(client, prompt)
        energy_data = self.energy_meter.stop(meter_state)

        # Parse response into grid
        grid = parse_grid_response(response_text)
        if grid is None:
            log.warning("Failed to parse model response for block %s", block_id[:8])
            # Submit anyway — let the verifier score it as 0.0
            grid = []

        # Submit attempt
        attempt_data = {
            "node_id": self.node_id,
            "block_id": block_id,
            "method": "llm_inference",
            "strategy_family": f"model:{self.model_client.model_name}",
            "output_json": {"grid": grid, "raw_response": response_text[:500]},
            "energy_cost": energy_data["energy_cost"],
            "latency_ms": energy_data["wall_ms"],
        }

        resp = await client.post(f"{self.api_url}/attempts", json=attempt_data)
        if resp.status_code == 200:
            result = resp.json()
            score = result.get("score", 0)
            self.total_attempts += 1
            self.total_energy += energy_data["energy_cost"]

            status = ""
            if score >= 0.95:
                self.total_solves += 1
                status = " HONEY!"
            elif score >= 0.30:
                status = " jelly"

            log.info(
                "[%s] block=%s score=%.3f energy=%.4f wall=%dms%s",
                self.node_id[:12], block_id[:8], score,
                energy_data["energy_cost"], energy_data["wall_ms"], status,
            )
        else:
            log.warning("Submit failed: %s %s", resp.status_code, resp.text[:200])

    def stop(self):
        self._running = False
        log.info(
            "Worker %s stopping — %d attempts, %d solves, %.2f energy",
            self.node_id, self.total_attempts, self.total_solves, self.total_energy,
        )


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="SwarmChain Real Worker — real models, real energy")
    parser.add_argument("--api-url", required=True, help="SwarmChain API URL")
    parser.add_argument("--model-url", required=True, help="Model endpoint (OpenAI-compatible)")
    parser.add_argument("--node-id", default=None, help="Node ID (auto-generated if not set)")
    parser.add_argument("--node-type", default="cpu-worker", help="Node type")
    parser.add_argument("--hardware-class", default="cpu", help="Hardware class")
    parser.add_argument("--api-key", default="", help="SwarmChain API key")
    parser.add_argument("--model-name", default="default", help="Model name for the endpoint")
    return parser.parse_args()


def main():
    args = parse_args()
    node_id = args.node_id or f"real-{args.node_type}-{uuid.uuid4().hex[:8]}"

    worker = RealWorker(
        api_url=args.api_url,
        model_url=args.model_url,
        node_id=node_id,
        node_type=args.node_type,
        hardware_class=args.hardware_class,
        api_key=args.api_key,
        model_name=args.model_name,
    )

    # Graceful shutdown
    def handle_signal(sig, frame):
        worker.stop()
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log.info("Starting real worker: %s (%s)", node_id, args.hardware_class)
    log.info("API: %s", args.api_url)
    log.info("Model: %s", args.model_url)
    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
