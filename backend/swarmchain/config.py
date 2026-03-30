"""Centralized configuration for SwarmChain backend."""
import logging
from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache

logger = logging.getLogger("swarmchain.config")


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://swarmchain:swarmchain@localhost:5432/swarmchain"
    database_url_sync: str = "postgresql://swarmchain:swarmchain@localhost:5432/swarmchain"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Controller
    controller_enabled: bool = False  # False = external controller (Zima-2) manages blocks
    controller_loop_interval_sec: float = 5.0
    beam_width: int = 10
    prune_threshold: float = 0.05
    min_contribution_score: float = 0.01

    # Reward engine
    solver_reward_pct: float = 0.40
    lineage_reward_pct: float = 0.30
    exploration_reward_pct: float = 0.20
    efficiency_reward_pct: float = 0.10

    # Economics
    spam_score_threshold: float = 0.02
    spam_penalty_multiplier: float = 0.1
    duplicate_decay_rate: float = 0.5
    reputation_solve_boost: float = 0.05
    reputation_spam_penalty: float = 0.1
    reputation_decay_rate: float = 0.001
    min_reputation_for_rewards: float = 0.1

    # Cost tracking
    electricity_rate_per_kwh: float = 0.10  # $/kWh default
    orchestration_cost_per_block: float = 0.001  # $ overhead per block
    convergence_window_size: int = 20  # blocks per convergence window

    # Hedera HCS anchoring
    hedera_operator_id: str = ""  # empty = anchoring disabled
    hedera_operator_key: str = ""
    hedera_topic_id: str = "0.0.10291838"
    hedera_anchor_interval: int = 50  # anchor every N sealed blocks

    # Discord
    discord_webhook_url: str = ""  # empty = notifications disabled

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = ""  # empty = no auth required (dev mode)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://swarmchain.eth.limo",
        "https://block.swarmchain.eth.limo",
    ]

    model_config = {"env_prefix": "SWARMCHAIN_", "env_file": ".env"}

    @model_validator(mode="after")
    def validate_reward_percentages(self):
        total = self.solver_reward_pct + self.lineage_reward_pct + self.exploration_reward_pct + self.efficiency_reward_pct
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Reward percentages must sum to 1.0, got {total}")
        if not self.api_key:
            logger.warning("SWARMCHAIN_API_KEY is empty — all mutation endpoints are UNPROTECTED")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
