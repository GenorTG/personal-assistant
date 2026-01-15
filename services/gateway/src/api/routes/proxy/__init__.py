"""Proxy routes for LLM service."""
from fastapi import APIRouter
from .health import router as health_router
from .llm_proxy import router as llm_proxy_router

# Combine all proxy routers
router = APIRouter(tags=["proxy"])
router.include_router(health_router)
router.include_router(llm_proxy_router)

__all__ = ["router", "health_router", "llm_proxy_router"]

