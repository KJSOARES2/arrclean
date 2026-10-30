"""Aggregated API router for ArrClean v1."""

from fastapi import APIRouter

from app.api.connections import router as connections_router
from app.api.dashboard import router as dashboard_router
from app.api.duplicates import router as duplicates_router
from app.api.seed_watch import router as seed_watch_router
from app.api.settings import router as settings_router
from app.api.websocket import router as ws_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(dashboard_router)
api_router.include_router(duplicates_router)
api_router.include_router(seed_watch_router)
api_router.include_router(settings_router)
api_router.include_router(connections_router)
api_router.include_router(ws_router)

__all__ = ["api_router"]
