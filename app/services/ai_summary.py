import httpx
import logging
from typing import List
from app.config import settings

logger = logging.getLogger(__name__)


class AISummaryService:

    async def summarize(self, query: str, results: list) -> str:
        context = self._build_context(query, results)
        summary = await self._call_ollama(query, context)
        return summary

    def _build_context(self, query: str, results: list) -> str:
        lines = []
        for i, r in enumerate(results[:5], 1):
            title = getattr(r, "title", "")
            desc = getattr(r, "description", "")
            lines.append(f"{i}. {title}: {desc}")
        return "\n".join(lines)

    async def _call_ollama(self, query: str, context: str) -> str:
        prompt = f"""You are a helpful search assistant for MyAISpace.in.
Based on the following search results for the query "{query}", provide a concise and informative summary in 3-4 sentences.

Search Results:
{context}

Summary:"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": settings.OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 200
                        }
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response", "").strip()
                else:
                    return self._fallback_summary(query, context)

        except Exception as e:
            logger.warning(f"Ollama not available: {e}. Using fallback summary.")
            return self._fallback_summary(query, context)

    def _fallback_summary(self, query: str, context: str) -> str:
        lines = [l for l in context.split("\n") if l.strip()]
        if not lines:
            return f"Search results for: {query}"
        first = lines[0].split(":", 1)[-1].strip() if ":" in lines[0] else lines[0]
        return f"Here are the top results for '{query}'. {first[:300]}..."


ai_summary_service = AISummaryService()
