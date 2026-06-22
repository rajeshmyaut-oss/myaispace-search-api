from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, date
from app.models.database import APIKey, get_db, generate_api_key
from app.models.schemas import APIKeyCreate, APIKeyResponse, APIKeyStats
from app.middleware.auth import verify_api_key

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


@router.post("/generate-key", response_model=APIKeyResponse)
async def generate_key(payload: APIKeyCreate, db: AsyncSession = Depends(get_db)):
    """Generate a free API key to use MyAISpace Search API."""

    # Check if email already has a key
    result = await db.execute(select(APIKey).where(APIKey.email == payload.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"An API key already exists for {payload.email}. Use /v1/auth/stats to view it."
        )

    new_key = APIKey(
        key=generate_api_key(),
        name=payload.name,
        email=payload.email,
        daily_limit=500,
        created_at=datetime.utcnow()
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    return APIKeyResponse(
        key=new_key.key,
        name=new_key.name,
        email=new_key.email,
        daily_limit=new_key.daily_limit,
        created_at=new_key.created_at,
        message="Your free API key has been generated! Add X-API-Key header to all requests."
    )


@router.get("/stats", response_model=APIKeyStats)
async def get_key_stats(key_obj: APIKey = Depends(verify_api_key)):
    """View your API key usage statistics."""
    return APIKeyStats(
        key_preview=key_obj.key[:12] + "..." + key_obj.key[-4:],
        name=key_obj.name,
        email=key_obj.email,
        is_active=key_obj.is_active,
        daily_limit=key_obj.daily_limit,
        requests_today=key_obj.requests_today,
        total_requests=key_obj.total_requests,
        created_at=key_obj.created_at,
        last_used=key_obj.last_used
    )


@router.post("/reset-daily", response_model=dict)
async def reset_daily_counts(db: AsyncSession = Depends(get_db)):
    """Reset daily request counts for all keys (run this daily via cron)."""
    await db.execute(update(APIKey).values(requests_today=0))
    await db.commit()
    return {"message": "Daily counts reset successfully", "timestamp": datetime.utcnow()}
