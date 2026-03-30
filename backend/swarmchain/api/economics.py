"""Economics API — dataset sales, reputation leaderboard, economic stats."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from swarmchain.db.engine import get_db
from swarmchain.db.models import Block, Node, Reward, DatasetSale
from swarmchain.services.economics import EconomicsEngine
from swarmchain.services.reputation import ReputationService
from swarmchain.services.discord_notify import DiscordNotifier
from swarmchain.api.auth import require_api_key

router = APIRouter()
economics = EconomicsEngine()
reputation = ReputationService()
discord = DiscordNotifier()


class DatasetSaleRequest(BaseModel):
    block_id: str
    buyer: str
    sale_price: float
    platform_fee_pct: float = 0.10


@router.post("/economics/dataset-sale", dependencies=[Depends(require_api_key)])
async def execute_dataset_sale(req: DatasetSaleRequest, db: AsyncSession = Depends(get_db)):
    """Execute a dataset sale event — distributes payouts to all contributors.

    Applies reputation gating, anti-spam penalties, and diminishing returns.
    """
    try:
        sale = await economics.execute_dataset_sale(
            db, req.block_id, req.buyer, req.sale_price, req.platform_fee_pct
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "sale_id": sale.sale_id,
        "block_id": sale.block_id,
        "buyer": sale.buyer,
        "sale_price": sale.sale_price,
        "platform_fee": sale.platform_fee,
        "distributable": sale.distributable,
        "payout_count": sale.payout_count,
        "status": sale.status,
        "payout_summary": sale.payout_summary,
    }


@router.get("/economics/sales")
async def list_dataset_sales(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """List dataset sale history."""
    return await economics.get_sale_history(db, limit)


@router.get("/economics/leaderboard")
async def get_leaderboard(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Get nodes ranked by reputation score."""
    return await reputation.get_leaderboard(db, limit)


@router.get("/economics/stats")
async def get_economic_stats(db: AsyncSession = Depends(get_db)):
    """System-wide economic overview."""
    # Total rewards distributed
    total_rewards = (await db.execute(
        select(func.sum(Reward.reward_amount))
    )).scalar() or 0

    # Rewards by type
    result = await db.execute(
        select(Reward.reward_type, func.sum(Reward.reward_amount))
        .group_by(Reward.reward_type)
    )
    rewards_by_type = {row[0]: round(float(row[1]), 4) for row in result.all()}

    # Dataset sales
    total_sales = (await db.execute(
        select(func.count(DatasetSale.id)).where(DatasetSale.status == "completed")
    )).scalar() or 0

    total_sale_revenue = (await db.execute(
        select(func.sum(DatasetSale.sale_price)).where(DatasetSale.status == "completed")
    )).scalar() or 0

    total_platform_fees = (await db.execute(
        select(func.sum(DatasetSale.platform_fee)).where(DatasetSale.status == "completed")
    )).scalar() or 0

    # Node stats
    active_nodes = (await db.execute(
        select(func.count(Node.id)).where(Node.active == True)
    )).scalar() or 0

    avg_reputation = (await db.execute(
        select(func.avg(Node.reputation_score)).where(Node.active == True)
    )).scalar() or 0

    return {
        "total_rewards_distributed": round(float(total_rewards), 4),
        "rewards_by_type": rewards_by_type,
        "dataset_sales": {
            "total_sales": total_sales,
            "total_revenue": round(float(total_sale_revenue), 4),
            "total_platform_fees": round(float(total_platform_fees), 4),
        },
        "nodes": {
            "active": active_nodes,
            "avg_reputation": round(float(avg_reputation), 4),
        },
    }


@router.post("/economics/energy-report", dependencies=[Depends(require_api_key)])
async def send_energy_report(db: AsyncSession = Depends(get_db)):
    """Push an energy report to Discord."""
    # Gather stats
    total_blocks = (await db.execute(select(func.count(Block.id)))).scalar() or 0
    solved_blocks = (await db.execute(
        select(func.count(Block.id)).where(Block.status == "solved")
    )).scalar() or 0

    total_attempts = (await db.execute(
        select(func.count()).select_from(Reward)
    )).scalar() or 0

    total_energy = (await db.execute(
        select(func.sum(Block.total_energy))
    )).scalar() or 0

    active_nodes = (await db.execute(
        select(func.count(Node.id)).where(Node.active == True)
    )).scalar() or 0

    solve_rate = solved_blocks / max(total_blocks, 1)

    top_nodes = await reputation.get_leaderboard(db, limit=5)

    sent = await discord.energy_report(
        total_blocks=total_blocks,
        solved_blocks=solved_blocks,
        total_attempts=total_attempts,
        total_energy=float(total_energy),
        active_nodes=active_nodes,
        solve_rate=solve_rate,
        top_nodes=top_nodes,
    )
    return {"sent": sent, "total_blocks": total_blocks, "solved_blocks": solved_blocks}
