"""Discord webhook notifications for SwarmChain events.

Pushes real-time events to a Discord channel:
- Block solved (honey found)
- Block exhausted (no solve)
- Energy reports (periodic stats)
- Mining milestones (100, 500, 1000 blocks)
- Node achievements (first solve, reputation milestones)
"""
import logging
from datetime import datetime, timezone
import httpx
from swarmchain.config import get_settings

logger = logging.getLogger("swarmchain.discord")


class DiscordNotifier:
    """Posts SwarmChain events to Discord via webhook."""

    def __init__(self, webhook_url: str | None = None):
        s = get_settings()
        self.webhook_url = webhook_url or s.discord_webhook_url
        self.enabled = bool(self.webhook_url)

    async def _post(self, payload: dict) -> bool:
        """Send a webhook payload to Discord."""
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json=payload, timeout=10.0)
                if resp.status_code in (200, 204):
                    return True
                logger.warning("Discord webhook %d: %s", resp.status_code, resp.text[:200])
                return False
        except Exception as e:
            logger.error("Discord webhook error: %s", e)
            return False

    async def block_solved(
        self,
        block_id: str,
        task_id: str,
        solver_node: str,
        strategy: str,
        score: float,
        attempt_count: int,
        total_energy: float,
        honey: int,
        jelly: int,
        propolis: int,
    ) -> bool:
        """Notify when a block reaches finality with a perfect solve."""
        return await self._post({
            "embeds": [{
                "title": "BLOCK SOLVED",
                "color": 0x00FF88,  # green
                "fields": [
                    {"name": "Block", "value": f"`{block_id[:12]}`", "inline": True},
                    {"name": "Task", "value": task_id, "inline": True},
                    {"name": "Score", "value": f"**{score:.3f}**", "inline": True},
                    {"name": "Solver", "value": f"`{solver_node}`", "inline": True},
                    {"name": "Strategy", "value": strategy, "inline": True},
                    {"name": "Attempts", "value": str(attempt_count), "inline": True},
                    {"name": "Anatomy", "value": f"Honey: {honey} | Jelly: {jelly} | Propolis: {propolis}", "inline": False},
                    {"name": "Energy", "value": f"{total_energy:.2f} units", "inline": True},
                ],
                "footer": {"text": "SwarmChain | Search becomes data"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        })

    async def block_exhausted(
        self,
        block_id: str,
        task_id: str,
        best_score: float,
        attempt_count: int,
        total_energy: float,
    ) -> bool:
        """Notify when a block exhausts without solving."""
        return await self._post({
            "embeds": [{
                "title": "BLOCK EXHAUSTED",
                "color": 0xFFA500,  # amber
                "fields": [
                    {"name": "Block", "value": f"`{block_id[:12]}`", "inline": True},
                    {"name": "Task", "value": task_id, "inline": True},
                    {"name": "Best Score", "value": f"{best_score:.3f}", "inline": True},
                    {"name": "Attempts", "value": str(attempt_count), "inline": True},
                    {"name": "Energy", "value": f"{total_energy:.2f}", "inline": True},
                ],
                "footer": {"text": "SwarmChain | Elimination becomes integrity"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        })

    async def energy_report(
        self,
        total_blocks: int,
        solved_blocks: int,
        total_attempts: int,
        total_energy: float,
        active_nodes: int,
        solve_rate: float,
        top_nodes: list[dict],
    ) -> bool:
        """Periodic energy and mining status report."""
        node_lines = "\n".join(
            f"`{n['node_id'][:15]}` — {n['total_rewards']:.1f} earned, rep {n['reputation_score']:.3f}"
            for n in top_nodes[:5]
        )

        return await self._post({
            "embeds": [{
                "title": "ENERGY REPORT",
                "color": 0x5865F2,  # blurple
                "fields": [
                    {"name": "Blocks", "value": f"{solved_blocks}/{total_blocks} solved ({solve_rate:.0%})", "inline": True},
                    {"name": "Attempts", "value": f"{total_attempts:,}", "inline": True},
                    {"name": "Energy", "value": f"{total_energy:,.1f} units", "inline": True},
                    {"name": "Active Nodes", "value": str(active_nodes), "inline": True},
                    {"name": "Top Nodes", "value": node_lines or "None yet", "inline": False},
                ],
                "footer": {"text": "SwarmChain | Finality creates value"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        })

    async def mining_milestone(self, blocks_sealed: int, target: int) -> bool:
        """Notify on mining milestones (100, 250, 500, 1000)."""
        pct = blocks_sealed / target * 100
        return await self._post({
            "embeds": [{
                "title": f"MILESTONE: {blocks_sealed} BLOCKS SEALED",
                "description": f"**{pct:.0f}%** of {target} target reached.",
                "color": 0xFFD700,  # gold
                "footer": {"text": "SwarmChain | The refinery is running"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        })

    async def custom(self, title: str, message: str, color: int = 0x5865F2) -> bool:
        """Send a custom notification."""
        return await self._post({
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
                "footer": {"text": "SwarmChain"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        })
