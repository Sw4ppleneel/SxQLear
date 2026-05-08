from fastapi import APIRouter

from api.connections import router as connections_router
from api.projects import router as projects_router
from api.inference import router as inference_router
from api.validation import router as validation_router
from api.memory import router as memory_router
from api.datasets import router as datasets_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(connections_router)
api_router.include_router(projects_router)
api_router.include_router(inference_router)
api_router.include_router(validation_router)
api_router.include_router(memory_router)
api_router.include_router(datasets_router)
