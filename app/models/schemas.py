from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime


# ── Search Result Schemas ─────────────────────────────────────────────────────

class WebResult(BaseModel):
    title: str
    url: str
    description: str
    published: Optional[str] = None
    source: Optional[str] = None


class ImageResult(BaseModel):
    title: str
    image_url: str
    source_url: str
    thumbnail: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    source: Optional[str] = None


class NewsResult(BaseModel):
    title: str
    url: str
    description: str
    published: Optional[str] = None
    source: Optional[str] = None
    image_url: Optional[str] = None


class WebSearchResponse(BaseModel):
    query: str
    total_results: int
    search_type: str = "web"
    results: List[WebResult]
    ai_summary: Optional[str] = None
    response_time_ms: int


class ImageSearchResponse(BaseModel):
    query: str
    total_results: int
    search_type: str = "images"
    results: List[ImageResult]
    response_time_ms: int


class NewsSearchResponse(BaseModel):
    query: str
    total_results: int
    search_type: str = "news"
    results: List[NewsResult]
    response_time_ms: int


class SummaryResponse(BaseModel):
    query: str
    summary: str
    sources: List[str]
    model_used: str
    response_time_ms: int


# ── Auth Schemas ──────────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    name: str
    email: str


class APIKeyResponse(BaseModel):
    key: str
    name: str
    email: str
    daily_limit: int
    created_at: datetime
    message: str


class APIKeyStats(BaseModel):
    key_preview: str
    name: str
    email: str
    is_active: bool
    daily_limit: int
    requests_today: int
    total_requests: int
    created_at: datetime
    last_used: Optional[datetime] = None


# ── Error Schema ──────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    message: str
    status_code: int
