from fastapi import APIRouter
from .blocks import router as blocks_router
from .attempts import router as attempts_router
from .nodes import router as nodes_router
from .rewards import router as rewards_router
from .validators import router as validators_router
from .economics import router as economics_router
from .events import router as events_router
from .health import router as health_router
from .tasks import router as tasks_router
from .anchors import router as anchors_router
from .epochs import router as epochs_router
from .energy import router as energy_router

api_router = APIRouter()
api_router.include_router(blocks_router, prefix="/blocks", tags=["blocks"])
api_router.include_router(attempts_router, prefix="/attempts", tags=["attempts"])
api_router.include_router(nodes_router, prefix="/nodes", tags=["nodes"])
api_router.include_router(rewards_router, tags=["rewards"])
api_router.include_router(validators_router, tags=["validators"])
api_router.include_router(economics_router, tags=["economics"])
api_router.include_router(events_router, tags=["events"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(anchors_router, prefix="/anchors", tags=["anchors"])
api_router.include_router(epochs_router, prefix="/epochs", tags=["epochs"])
api_router.include_router(energy_router, prefix="/energy", tags=["energy"])
