"""Aggregate routers for the ``/api`` and versioned ``/api/v1`` surfaces.

Legacy unversioned investigation and catalog aliases stay available for local
development but are hidden from the OpenAPI document. New clients should use
``/api/v1``.
"""

from fastapi import APIRouter

from backend.api.routes import catalog, health, investigations

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(investigations.router, include_in_schema=False)
api_router.include_router(catalog.router, include_in_schema=False)

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(health.router)
v1_router.include_router(investigations.router)
v1_router.include_router(catalog.router)

api_router.include_router(v1_router)
