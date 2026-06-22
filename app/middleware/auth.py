from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime
from app.models.database import APIKey, get_db

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> APIKey:
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Add X-API-Key header. Get your free key at /v1/auth/generate-key"
        )

    result = await db.execute(select(APIKey).where(APIKey.key == api_key))
    key_obj = result.scalar_one_or_none()

    if not key_obj:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not key_obj.is_active:
        raise HTTPException(status_code=403, detail="API key is disabled")

    if key_obj.requests_today >= key_obj.daily_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {key_obj.daily_limit} requests reached. Resets at midnight UTC."
        )

    # Update usage stats
    await db.execute(
        update(APIKey)
        .where(APIKey.key == api_key)
        .values(
            requests_today=APIKey.requests_today + 1,
            total_requests=APIKey.total_requests + 1,
            last_used=datetime.utcnow()
        )
    )
    await db.commit()

    return key_obj
