"""Aggregate router for the ``/api`` prefix."""

from fastapi import APIRouter

from backend.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
