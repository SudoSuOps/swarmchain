"""Lineage tracking — every attempt is traceable, every path is recorded.

Search becomes data. The lineage graph captures the elimination history,
showing how the swarm converged from noise to signal.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.models import LineageEdge, Attempt


class LineageService:
    """Manages the parent-child attempt graph within a block."""

    @staticmethod
    async def record_edge(
        db: AsyncSession,
        block_id: str,
        parent_attempt_id: str,
        child_attempt_id: str,
        delta_score: float,
    ) -> LineageEdge:
        """Record a parent → child derivation link."""
        edge = LineageEdge(
            block_id=block_id,
            parent_attempt_id=parent_attempt_id,
            child_attempt_id=child_attempt_id,
            delta_score=delta_score,
        )
        db.add(edge)
        await db.flush()
        return edge

    @staticmethod
    async def get_ancestry(db: AsyncSession, block_id: str, attempt_id: str) -> list[str]:
        """Trace backward from an attempt to its root — the full search lineage."""
        ancestry = []
        current = attempt_id
        seen = set()

        while current and current not in seen:
            seen.add(current)
            ancestry.append(current)
            result = await db.execute(
                select(LineageEdge.parent_attempt_id)
                .where(LineageEdge.block_id == block_id)
                .where(LineageEdge.child_attempt_id == current)
            )
            parent = result.scalar_one_or_none()
            current = parent

        return list(reversed(ancestry))

    @staticmethod
    async def get_descendants(db: AsyncSession, block_id: str, attempt_id: str) -> list[str]:
        """Get all children derived from an attempt."""
        result = await db.execute(
            select(LineageEdge.child_attempt_id)
            .where(LineageEdge.block_id == block_id)
            .where(LineageEdge.parent_attempt_id == attempt_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_block_edges(db: AsyncSession, block_id: str) -> list[dict]:
        """Get the full lineage graph for a block."""
        result = await db.execute(
            select(LineageEdge)
            .where(LineageEdge.block_id == block_id)
            .order_by(LineageEdge.created_at)
        )
        edges = result.scalars().all()
        return [
            {
                "parent": e.parent_attempt_id,
                "child": e.child_attempt_id,
                "delta_score": e.delta_score,
            }
            for e in edges
        ]

    @staticmethod
    async def get_winning_lineage(db: AsyncSession, block_id: str, winning_attempt_id: str) -> list[dict]:
        """Get the winning path — the chain from root to solution."""
        ancestry_ids = await LineageService.get_ancestry(db, block_id, winning_attempt_id)

        if not ancestry_ids:
            return []

        result = await db.execute(
            select(Attempt)
            .where(Attempt.block_id == block_id)
            .where(Attempt.attempt_id.in_(ancestry_ids))
        )
        attempts_map = {a.attempt_id: a for a in result.scalars().all()}

        lineage = []
        for aid in ancestry_ids:
            a = attempts_map.get(aid)
            if a:
                lineage.append({
                    "attempt_id": a.attempt_id,
                    "node_id": a.node_id,
                    "score": a.score,
                    "method": a.method,
                    "strategy_family": a.strategy_family,
                })
        return lineage
