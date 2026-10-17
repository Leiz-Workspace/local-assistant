
from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter(tags=["System"])


@router.get("/health")
async def health():
    return {
        "service": "shldd-backend",
        "status": "ok",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
