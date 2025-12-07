"""Health check routes."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Health check endpoint - simple and fast, no blocking operations."""
    return {
        "status": "healthy",
        "service": "personal-assistant",
        "message": "Backend is running"
    }
