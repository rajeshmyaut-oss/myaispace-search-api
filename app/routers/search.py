from fastapi import APIRouter, Depends, Query, HTTPException
from app.models.schemas import (
    WebSearchResponse, ImageSearchResponse,
    NewsSearchResponse, SummaryResponse
)
from app.models.database import APIKey
from app.middleware.auth import verify_api_key
from app.services.search_service import search_service
from app.services.ai_summary import ai_summary_service
from app.config import settings
import time

router = APIRouter(prefix="/v1/search", tags=["Search"])


@router.get("/web", response_model=WebSearchResponse)
async def web_search(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    count: int = Query(10, ge=1, le=20, description="Number of results (max 20)"),
    region: str = Query("in-en", description="Region code e.g. in-en, us-en, uk-en"),
    summary: bool = Query(False, description="Include AI-powered summary (requires Ollama)"),
    key_obj: APIKey = Depends(verify_api_key)
):
    """Search the web. Returns titles, URLs, and descriptions."""
    start = time.time()

    results = search_service.web_search(query=q, count=count, region=region)

    if not results:
        raise HTTPException(status_code=404, detail="No results found for this query")

    ai_summary = None
    if summary:
        ai_summary = await ai_summary_service.summarize(q, results)

    elapsed = int((time.time() - start) * 1000)

    return WebSearchResponse(
        query=q,
        total_results=len(results),
        results=results,
        ai_summary=ai_summary,
        response_time_ms=elapsed
    )


@router.get("/images", response_model=ImageSearchResponse)
async def image_search(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    count: int = Query(10, ge=1, le=20, description="Number of results (max 20)"),
    region: str = Query("in-en", description="Region code"),
    key_obj: APIKey = Depends(verify_api_key)
):
    """Search for images. Returns image URLs, thumbnails, and source links."""
    start = time.time()

    results = search_service.image_search(query=q, count=count, region=region)

    if not results:
        raise HTTPException(status_code=404, detail="No image results found")

    elapsed = int((time.time() - start) * 1000)

    return ImageSearchResponse(
        query=q,
        total_results=len(results),
        results=results,
        response_time_ms=elapsed
    )


@router.get("/news", response_model=NewsSearchResponse)
async def news_search(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    count: int = Query(10, ge=1, le=20, description="Number of results (max 20)"),
    region: str = Query("in-en", description="Region code"),
    key_obj: APIKey = Depends(verify_api_key)
):
    """Search for latest news articles."""
    start = time.time()

    results = search_service.news_search(query=q, count=count, region=region)

    if not results:
        raise HTTPException(status_code=404, detail="No news results found")

    elapsed = int((time.time() - start) * 1000)

    return NewsSearchResponse(
        query=q,
        total_results=len(results),
        results=results,
        response_time_ms=elapsed
    )


@router.get("/summarize", response_model=SummaryResponse)
async def ai_summarize(
    q: str = Query(..., min_length=1, max_length=500, description="Search query to summarize"),
    key_obj: APIKey = Depends(verify_api_key)
):
    """Get an AI-powered summary of search results using your local Ollama model."""
    start = time.time()

    web_results = search_service.web_search(query=q, count=5)
    if not web_results:
        raise HTTPException(status_code=404, detail="No results found to summarize")

    summary = await ai_summary_service.summarize(q, web_results)
    sources = [r.url for r in web_results]
    elapsed = int((time.time() - start) * 1000)

    return SummaryResponse(
        query=q,
        summary=summary,
        sources=sources,
        model_used=settings.OLLAMA_MODEL,
        response_time_ms=elapsed
    )
