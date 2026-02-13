"""API v1 路由汇总"""

from fastapi import APIRouter

from app.api.v1 import chat, export, sessions, settings, skills, sources, templates, tts, workspace_sources

api_router = APIRouter()
api_router.include_router(export.router, tags=["export"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(skills.router, tags=["skills"])
api_router.include_router(sources.router, tags=["sources"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(templates.router, tags=["templates"])
api_router.include_router(workspace_sources.router, tags=["workspace-sources"])
api_router.include_router(settings.router)
api_router.include_router(tts.router)
