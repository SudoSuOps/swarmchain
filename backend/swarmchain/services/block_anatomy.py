"""Block anatomy — every sealed block is a hive. We extract everything.

Taxonomy (maps to Royal Jelly Protocol):
- Honey:    score >= 0.95 — the solved pair, the dataset asset
- Jelly:    score 0.30-0.95 — partial solutions, refinement signal
- Propolis: score < 0.30 — failed attempts, elimination signal

Everything has value:
- Honey trains "what's correct"
- Jelly trains "what's almost right"
- Propolis trains "what doesn't work"
- Lineage trains "how to search"
- Convergence ratio measures efficiency

The math: if a block has 100 propolis, 15 jelly, 1 honey, the
convergence ratio is 100:15:1. SwarmRefinery v2 should push
this toward 50:10:1 → 20:5:1 as the model learns to search better.
"""
from dataclasses import dataclass
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.models import Block, Attempt, Reward, LineageEdge

HONEY_THRESHOLD = 0.95
JELLY_THRESHOLD = 0.30


@dataclass
class BlockAnatomy:
    """Full breakdown of what's inside a sealed block."""
    block_id: str
    status: str

    # Counts
    total_attempts: int
    honey_count: int       # score >= 0.95
    jelly_count: int       # score 0.30-0.95
    propolis_count: int    # score < 0.30
    invalid_count: int     # valid=False

    # The solved pair (if honey exists)
    winning_pair: dict | None    # {input, output, score, node_id, strategy, attempt_id}

    # Energy
    total_energy: float
    energy_per_honey: float      # total_energy / honey_count
    energy_per_solve: float      # total_energy (if solved)

    # Convergence math
    propolis_to_honey_ratio: float   # propolis_count / max(honey_count, 1)
    jelly_to_honey_ratio: float      # jelly_count / max(honey_count, 1)
    convergence_efficiency: float    # honey_count / total_attempts

    # Lineage depth
    max_lineage_depth: int
    lineage_edge_count: int

    # Rewards
    total_rewards: float
    reward_node_count: int

    # Strategy effectiveness
    strategy_stats: dict     # {strategy: {count, avg_score, honey_count, best_score}}

    # Top jelly (almost-solved, most valuable for training)
    top_jelly: list[dict]    # top 5 jelly attempts

    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "status": self.status,
            "taxonomy": {
                "honey": self.honey_count,
                "jelly": self.jelly_count,
                "propolis": self.propolis_count,
                "invalid": self.invalid_count,
                "total": self.total_attempts,
            },
            "winning_pair": self.winning_pair,
            "energy": {
                "total": round(self.total_energy, 4),
                "per_honey": round(self.energy_per_honey, 4),
                "per_solve": round(self.energy_per_solve, 4),
            },
            "convergence": {
                "propolis_to_honey": f"{self.propolis_to_honey_ratio:.0f}:1",
                "jelly_to_honey": f"{self.jelly_to_honey_ratio:.0f}:1",
                "efficiency": round(self.convergence_efficiency, 4),
                "attempts_per_solve": round(1 / max(self.convergence_efficiency, 0.001)),
            },
            "lineage": {
                "max_depth": self.max_lineage_depth,
                "edges": self.lineage_edge_count,
            },
            "rewards": {
                "total": round(self.total_rewards, 4),
                "contributing_nodes": self.reward_node_count,
            },
            "strategy_stats": self.strategy_stats,
            "top_jelly": self.top_jelly,
        }


class BlockAnatomyService:
    """Dissects a sealed block into its full anatomy."""

    @staticmethod
    async def analyze(db: AsyncSession, block_id: str) -> BlockAnatomy:
        """Full anatomical analysis of a sealed block."""
        # Get block
        result = await db.execute(select(Block).where(Block.block_id == block_id))
        block = result.scalar_one_or_none()
        if not block:
            raise ValueError(f"Block {block_id} not found")

        # Get all attempts
        result = await db.execute(
            select(Attempt)
            .where(Attempt.block_id == block_id)
            .order_by(Attempt.score.desc())
        )
        attempts = list(result.scalars().all())

        # Classify
        honey = [a for a in attempts if a.valid and a.score >= HONEY_THRESHOLD]
        jelly = [a for a in attempts if a.valid and JELLY_THRESHOLD <= a.score < HONEY_THRESHOLD]
        propolis = [a for a in attempts if a.valid and a.score < JELLY_THRESHOLD]
        invalid = [a for a in attempts if not a.valid]

        total_energy = sum(a.energy_cost for a in attempts)
        honey_count = len(honey)
        jelly_count = len(jelly)
        propolis_count = len(propolis)

        # Winning pair
        winning_pair = None
        if block.winning_attempt_id:
            winner = next((a for a in attempts if a.attempt_id == block.winning_attempt_id), None)
            if winner:
                winning_pair = {
                    "attempt_id": winner.attempt_id,
                    "node_id": winner.node_id,
                    "score": winner.score,
                    "strategy": winner.strategy_family,
                    "method": winner.method,
                    "input": block.task_payload.get("input_grid") if block.task_payload else None,
                    "output": winner.output_json.get("grid") if winner.output_json else None,
                    "task_description": block.task_payload.get("description") if block.task_payload else None,
                    "energy_cost": winner.energy_cost,
                }

        # Strategy stats
        strategy_map: dict[str, dict] = {}
        for a in attempts:
            if not a.valid:
                continue
            s = a.strategy_family
            if s not in strategy_map:
                strategy_map[s] = {"count": 0, "scores": [], "honey": 0}
            strategy_map[s]["count"] += 1
            strategy_map[s]["scores"].append(a.score)
            if a.score >= HONEY_THRESHOLD:
                strategy_map[s]["honey"] += 1

        strategy_stats = {}
        for s, data in strategy_map.items():
            scores = data["scores"]
            strategy_stats[s] = {
                "count": data["count"],
                "avg_score": round(sum(scores) / len(scores), 4) if scores else 0,
                "best_score": round(max(scores), 4) if scores else 0,
                "honey_count": data["honey"],
            }

        # Top jelly (most valuable partial solutions)
        top_jelly = [
            {
                "attempt_id": a.attempt_id,
                "node_id": a.node_id,
                "score": a.score,
                "strategy": a.strategy_family,
                "output": a.output_json.get("grid") if a.output_json else None,
            }
            for a in jelly[:5]
        ]

        # Lineage
        result = await db.execute(
            select(func.count(LineageEdge.id))
            .where(LineageEdge.block_id == block_id)
        )
        edge_count = result.scalar() or 0

        # Compute max lineage depth via ancestry of winner
        max_depth = 0
        if block.winning_attempt_id:
            from swarmchain.services.lineage import LineageService
            ancestry = await LineageService.get_ancestry(db, block_id, block.winning_attempt_id)
            max_depth = len(ancestry)

        # Rewards
        result = await db.execute(
            select(
                func.sum(Reward.reward_amount),
                func.count(func.distinct(Reward.node_id)),
            )
            .where(Reward.block_id == block_id)
        )
        reward_row = result.one()
        total_rewards = float(reward_row[0] or 0)
        reward_node_count = reward_row[1] or 0

        return BlockAnatomy(
            block_id=block_id,
            status=block.status,
            total_attempts=len(attempts),
            honey_count=honey_count,
            jelly_count=jelly_count,
            propolis_count=propolis_count,
            invalid_count=len(invalid),
            winning_pair=winning_pair,
            total_energy=total_energy,
            energy_per_honey=total_energy / max(honey_count, 1),
            energy_per_solve=total_energy if block.status == "solved" else 0,
            propolis_to_honey_ratio=propolis_count / max(honey_count, 1),
            jelly_to_honey_ratio=jelly_count / max(honey_count, 1),
            convergence_efficiency=honey_count / max(len(attempts), 1),
            max_lineage_depth=max_depth,
            lineage_edge_count=edge_count,
            total_rewards=total_rewards,
            reward_node_count=reward_node_count,
            strategy_stats=strategy_stats,
            top_jelly=top_jelly,
        )
