"""API v2 router."""

from fastapi import APIRouter

from app.api.v2 import generation

api_v2_router = APIRouter()
api_v2_router.include_router(generation.router)
