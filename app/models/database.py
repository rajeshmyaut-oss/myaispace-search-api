from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from datetime import datetime
import secrets
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    email = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    daily_limit = Column(Integer, default=500)
    requests_today = Column(Integer, default=0)
    total_requests = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, nullable=True)


class SearchLog(Base):
    __tablename__ = "search_logs"

    id = Column(Integer, primary_key=True, index=True)
    api_key = Column(String(64), index=True)
    query = Column(Text, nullable=False)
    search_type = Column(String(20), default="web")
    results_count = Column(Integer, default=0)
    response_time_ms = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def generate_api_key() -> str:
    return "mss_" + secrets.token_urlsafe(40)
