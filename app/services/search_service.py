from duckduckgo_search import DDGS
from typing import List, Optional
from app.models.schemas import WebResult, ImageResult, NewsResult
import logging

logger = logging.getLogger(__name__)


class SearchService:

    # ── Web Search ────────────────────────────────────────────────────────────
    def web_search(self, query: str, count: int = 10, region: str = "in-en") -> List[WebResult]:
        results = []
        try:
            with DDGS() as ddgs:
                raw = ddgs.text(
                    keywords=query,
                    region=region,
                    safesearch="moderate",
                    max_results=count
                )
                for item in raw:
                    results.append(WebResult(
                        title=item.get("title", ""),
                        url=item.get("href", ""),
                        description=item.get("body", ""),
                        published=item.get("published", None),
                        source=self._extract_domain(item.get("href", ""))
                    ))
        except Exception as e:
            logger.error(f"Web search error: {e}")
        return results

    # ── Image Search ──────────────────────────────────────────────────────────
    def image_search(self, query: str, count: int = 10, region: str = "in-en") -> List[ImageResult]:
        results = []
        try:
            with DDGS() as ddgs:
                raw = ddgs.images(
                    keywords=query,
                    region=region,
                    safesearch="moderate",
                    max_results=count
                )
                for item in raw:
                    results.append(ImageResult(
                        title=item.get("title", ""),
                        image_url=item.get("image", ""),
                        source_url=item.get("url", ""),
                        thumbnail=item.get("thumbnail", None),
                        width=item.get("width", None),
                        height=item.get("height", None),
                        source=self._extract_domain(item.get("url", ""))
                    ))
        except Exception as e:
            logger.error(f"Image search error: {e}")
        return results

    # ── News Search ───────────────────────────────────────────────────────────
    def news_search(self, query: str, count: int = 10, region: str = "in-en") -> List[NewsResult]:
        results = []
        try:
            with DDGS() as ddgs:
                raw = ddgs.news(
                    keywords=query,
                    region=region,
                    safesearch="moderate",
                    max_results=count
                )
                for item in raw:
                    results.append(NewsResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        description=item.get("body", ""),
                        published=item.get("date", None),
                        source=item.get("source", self._extract_domain(item.get("url", ""))),
                        image_url=item.get("image", None)
                    ))
        except Exception as e:
            logger.error(f"News search error: {e}")
        return results

    def _extract_domain(self, url: str) -> str:
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.replace("www.", "")
        except Exception:
            return ""


search_service = SearchService()
