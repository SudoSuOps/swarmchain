"""Finality service — finality creates value.

A block reaches finality when:
- solved: a verified attempt reaches score 1.0
- exhausted: max_attempts reached or time limit exceeded without solve
- (future) inconclusive: domain validator cannot determine resolution

Sealed blocks are immutable datasets — reproducible from stored data.
"""
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.models import Block, Attempt, BlockArtifact
from swarmchain.services.lineage import LineageService


class FinalityService:
    """Determines and executes block finality."""

    @staticmethod
    async def check_solved(db: AsyncSession, block: Block) -> bool:
        """Check if any attempt achieved a perfect score."""
        result = await db.execute(
            select(Attempt)
            .where(Attempt.block_id == block.block_id)
            .where(Attempt.valid == True)
            .where(Attempt.score >= 1.0)
            .order_by(Attempt.created_at)
            .limit(1)
        )
        winner = result.scalar_one_or_none()
        if winner:
            block.status = "solved"
            block.winning_attempt_id = winner.attempt_id
            block.winning_node_id = winner.node_id
            block.final_score = winner.score
            block.end_time = datetime.now(timezone.utc)
            return True
        return False

    @staticmethod
    async def check_exhausted(db: AsyncSession, block: Block) -> bool:
        """Check if the block has hit its limits."""
        now = datetime.now(timezone.utc)

        # Time limit
        elapsed = (now - block.start_time).total_seconds()
        if elapsed >= block.time_limit_sec:
            await FinalityService._mark_exhausted(db, block)
            return True

        # Attempt limit
        if block.attempt_count >= block.max_attempts:
            await FinalityService._mark_exhausted(db, block)
            return True

        return False

    @staticmethod
    async def _mark_exhausted(db: AsyncSession, block: Block) -> None:
        """Mark block as exhausted — set best attempt as winner."""
        block.status = "exhausted"
        block.end_time = datetime.now(timezone.utc)

        # Find best attempt
        result = await db.execute(
            select(Attempt)
            .where(Attempt.block_id == block.block_id)
            .where(Attempt.valid == True)
            .order_by(Attempt.score.desc())
            .limit(1)
        )
        best = result.scalar_one_or_none()
        if best:
            block.winning_attempt_id = best.attempt_id
            block.winning_node_id = best.node_id
            block.final_score = best.score

    @staticmethod
    async def seal_block(db: AsyncSession, block: Block) -> BlockArtifact:
        """Generate the sealed artifact for a finalized block.

        Every sealed block is reproducible from its stored data.
        """
        # Gather elimination summary
        result = await db.execute(
            select(
                func.count(Attempt.id).label("total"),
                func.sum(Attempt.energy_cost).label("total_energy"),
                func.avg(Attempt.score).label("avg_score"),
                func.max(Attempt.score).label("max_score"),
                func.count(Attempt.id).filter(Attempt.pruned == True).label("pruned_count"),
                func.count(Attempt.id).filter(Attempt.promoted == True).label("promoted_count"),
            )
            .where(Attempt.block_id == block.block_id)
        )
        stats = result.one()

        elimination_summary = {
            "total_attempts": stats.total or 0,
            "total_energy": float(stats.total_energy or 0),
            "avg_score": float(stats.avg_score or 0),
            "max_score": float(stats.max_score or 0),
            "pruned_count": stats.pruned_count or 0,
            "promoted_count": stats.promoted_count or 0,
        }
        block.elimination_summary = elimination_summary

        # Get winning lineage
        winning_lineage = []
        if block.winning_attempt_id:
            winning_lineage = await LineageService.get_winning_lineage(
                db, block.block_id, block.winning_attempt_id
            )

        # Get all unique contributing nodes
        result = await db.execute(
            select(Attempt.node_id).where(Attempt.block_id == block.block_id).distinct()
        )
        contributing_nodes = list(result.scalars().all())

        # Build sealed artifact
        artifact_data = {
            "block_id": block.block_id,
            "task_id": block.task_id,
            "domain": block.domain,
            "status": block.status,
            "final_score": block.final_score,
            "winning_attempt_id": block.winning_attempt_id,
            "winning_node_id": block.winning_node_id,
            "elimination_summary": elimination_summary,
            "winning_lineage": winning_lineage,
            "contributing_nodes": contributing_nodes,
            "task_payload": block.task_payload,
            "sealed_at": datetime.now(timezone.utc).isoformat(),
        }

        artifact = BlockArtifact(
            block_id=block.block_id,
            artifact_type="sealed_block",
            artifact_json=artifact_data,
        )
        db.add(artifact)
        await db.flush()
        return artifact
