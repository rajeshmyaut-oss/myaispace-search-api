import sqlite3
import secrets
import time
import json
import httpx
from datetime import datetime, date
from functools import wraps
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

load_dotenv()

# ── Groq client (cloud AI — used when GROQ_API_KEY is set) ───────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
groq_client  = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception:
        groq_client = None

app = Flask(__name__)

# ── CORS — allow myaispace.in ─────────────────────────────────────────────────
CORS(app, resources={
    r"/v1/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-API-Key"]
    }
})

DB_PATH = "myaispace_search.db"
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:32b")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
DAILY_LIMIT = int(os.getenv("RATE_LIMIT_PER_DAY", "500"))

# ── Simple in-memory search cache (avoids redundant requests) ────────────────
_search_cache = {}
CACHE_TTL = 300  # 5 minutes


def _cache_get(key):
    entry = _search_cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key, data):
    _search_cache[key] = {"data": data, "ts": time.time()}


# ── DuckDuckGo Lite HTML scraper (no rate limits) ─────────────────────────────
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def ddg_lite_search(query: str, count: int = 10) -> list:
    """Scrape DuckDuckGo Lite — no JS, no rate limits."""
    results = []
    try:
        resp = requests.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": query, "kl": "in-en"},
            headers=_HEADERS,
            timeout=15
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        rows = soup.select("table tr")
        title, url, desc = None, None, None

        for row in rows:
            a_tag = row.select_one("a.result-link")
            snippet = row.select_one("td.result-snippet")

            if a_tag:
                title = a_tag.get_text(strip=True)
                url = a_tag.get("href", "")
            elif snippet and title and url:
                desc = snippet.get_text(strip=True)
                if url.startswith("http"):
                    results.append({
                        "title": title,
                        "url": url,
                        "description": desc,
                        "published": None,
                        "source": extract_domain(url)
                    })
                    title, url, desc = None, None, None
                if len(results) >= count:
                    break
    except Exception as e:
        raise RuntimeError(f"DDG Lite scrape failed: {e}")
    return results


def ddg_lite_news(query: str, count: int = 10) -> list:
    """Fetch news via DuckDuckGo Lite with !news bang."""
    return ddg_lite_search(f"{query} site:news.google.com OR site:bbc.com OR site:reuters.com", count)


def wikipedia_search(query: str, count: int = 10) -> list:
    """Wikipedia OpenSearch API — always free, never rate-limited."""
    results = []
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": count,
                "format": "json",
                "srinfo": "totalhits",
                "srprop": "snippet|titlesnippet"
            },
            headers=_HEADERS,
            timeout=10
        )
        data = resp.json()
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = BeautifulSoup(item.get("snippet", ""), "html.parser").get_text()
            url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            results.append({
                "title": title,
                "url": url,
                "description": snippet,
                "published": None,
                "source": "wikipedia.org"
            })
    except Exception as e:
        raise RuntimeError(f"Wikipedia search failed: {e}")
    return results


def ddg_image_search(query: str, count: int = 10) -> list:
    """Image search via DDGS with fallback."""
    results = []
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.images(keywords=query, safesearch="moderate", max_results=count))
            for item in raw:
                results.append({
                    "title": item.get("title", ""),
                    "image_url": item.get("image", ""),
                    "source_url": item.get("url", ""),
                    "thumbnail": item.get("thumbnail"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "source": extract_domain(item.get("url", ""))
                })
    except Exception:
        pass
    return results


# ── In-memory rate limiter (per minute) ──────────────────────────────────────
_rate_store = {}


def check_rate_limit(api_key: str) -> bool:
    now = time.time()
    window = 60
    if api_key not in _rate_store:
        _rate_store[api_key] = []
    _rate_store[api_key] = [t for t in _rate_store[api_key] if now - t < window]
    if len(_rate_store[api_key]) >= RATE_LIMIT:
        return False
    _rate_store[api_key].append(now)
    return True


# ── Database Setup ────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 1,
            daily_limit INTEGER DEFAULT 500,
            requests_today INTEGER DEFAULT 0,
            total_requests INTEGER DEFAULT 0,
            last_reset_date TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            last_used TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS search_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT,
            query TEXT,
            search_type TEXT DEFAULT 'web',
            results_count INTEGER DEFAULT 0,
            response_time_ms INTEGER DEFAULT 0,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Auth Decorator ────────────────────────────────────────────────────────────
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return jsonify({
                "error": "Unauthorized",
                "message": "API key required. Add X-API-Key header. Get your free key at POST /v1/auth/generate-key",
                "status_code": 401
            }), 401

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key = ?", (api_key,)
        ).fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Invalid API key", "status_code": 401}), 401

        if not row["is_active"]:
            conn.close()
            return jsonify({"error": "API key is disabled", "status_code": 403}), 403

        # Reset daily count if new day
        today = date.today().isoformat()
        if row["last_reset_date"] != today:
            conn.execute(
                "UPDATE api_keys SET requests_today = 0, last_reset_date = ? WHERE key = ?",
                (today, api_key)
            )
            conn.commit()
            requests_today = 0
        else:
            requests_today = row["requests_today"]

        if requests_today >= row["daily_limit"]:
            conn.close()
            return jsonify({
                "error": "Daily limit reached",
                "message": f"Daily limit of {row['daily_limit']} requests reached. Resets at midnight.",
                "status_code": 429
            }), 429

        if not check_rate_limit(api_key):
            conn.close()
            return jsonify({
                "error": "Rate limit exceeded",
                "message": f"Max {RATE_LIMIT} requests per minute.",
                "status_code": 429
            }), 429

        # Update counters
        conn.execute(
            "UPDATE api_keys SET requests_today = requests_today + 1, total_requests = total_requests + 1, last_used = ? WHERE key = ?",
            (datetime.utcnow().isoformat(), api_key)
        )
        conn.commit()
        conn.close()

        request.api_key = api_key
        return f(*args, **kwargs)
    return decorated


def log_search(api_key, query, search_type, count, elapsed_ms):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO search_logs (api_key, query, search_type, results_count, response_time_ms, timestamp) VALUES (?,?,?,?,?,?)",
            (api_key, query, search_type, count, elapsed_ms, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── AI Summary ────────────────────────────────────────────────────────────────
def get_ai_summary(query: str, results: list) -> str:
    context_lines = []
    for i, r in enumerate(results[:5], 1):
        context_lines.append(f"{i}. {r['title']}: {r['description'][:200]}")
    context = "\n".join(context_lines)

    prompt = f"""/no_think
You are a helpful search assistant for MyAISpace.in.
Based on the following search results for the query "{query}", provide a concise summary in 3 sentences only. No preamble.

Search Results:
{context}

Summary:"""

    # Use Groq if available, else Ollama
    if groq_client:
        try:
            resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
                stream=False
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            pass
    else:
        try:
            response = httpx.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                      "think": False, "options": {"temperature": 0.3, "num_predict": 512}},
                timeout=60.0
            )
            if response.status_code == 200:
                data = response.json()
                text = data.get("response", "").strip()
                if not text:
                    text = data.get("thinking", "").strip()
                    if text:
                        text = text.split("\n\n")[-1].strip()[:400]
                return text
        except Exception:
            pass

    # Fallback summary (no Ollama needed)
    if results:
        return f"Top result for '{query}': {results[0]['title']}. {results[0]['description'][:300]}"
    return f"No summary available for '{query}'."


# ── Helper ────────────────────────────────────────────────────────────────────
def extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# ════════════════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return jsonify({
        "name": "MyAISpace Search API",
        "version": "1.0.0",
        "website": "https://myaispace.in",
        "docs": "See /v1/docs for endpoint list",
        "endpoints": {
            "web_search":   "GET /v1/search/web?q=query&count=10",
            "image_search": "GET /v1/search/images?q=query&count=10",
            "news_search":  "GET /v1/search/news?q=query&count=10",
            "ai_summary":   "GET /v1/search/summarize?q=query",
            "generate_key": "POST /v1/auth/generate-key",
            "key_stats":    "GET /v1/auth/stats"
        },
        "authentication": "Add X-API-Key header to all search requests",
        "free": True
    })


@app.get("/health")
def health():
    return jsonify({"status": "healthy", "service": "MyAISpace Search API"})


# ── Web Search ────────────────────────────────────────────────────────────────
@app.get("/v1/search/web")
@require_api_key
def web_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    count = min(int(request.args.get("count", 10)), 20)
    region = request.args.get("region", "in-en")
    include_summary = request.args.get("summary", "false").lower() == "true"

    start = time.time()

    cache_key = f"web:{q}:{count}:{region}"
    results = _cache_get(cache_key)

    if not results:
        # Try DDG Lite first
        try:
            results = ddg_lite_search(q, count)
        except Exception:
            results = []

        # Fallback to Wikipedia (always works, never rate-limited)
        if not results:
            try:
                results = wikipedia_search(q, count)
            except Exception as e:
                return jsonify({"error": "Search failed", "message": str(e)}), 500

        if results:
            _cache_set(cache_key, results)

    ai_summary = None
    if include_summary and results:
        ai_summary = get_ai_summary(q, results)

    elapsed = int((time.time() - start) * 1000)
    log_search(request.api_key, q, "web", len(results), elapsed)

    return jsonify({
        "query": q,
        "total_results": len(results),
        "search_type": "web",
        "results": results,
        "ai_summary": ai_summary,
        "response_time_ms": elapsed
    })


# ── Image Search ──────────────────────────────────────────────────────────────
@app.get("/v1/search/images")
@require_api_key
def image_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    count = min(int(request.args.get("count", 10)), 20)
    region = request.args.get("region", "in-en")

    start = time.time()

    cache_key = f"img:{q}:{count}"
    results = _cache_get(cache_key)

    if not results:
        results = ddg_image_search(q, count)
        if results:
            _cache_set(cache_key, results)

    if not results:
        return jsonify({"error": "No image results found", "message": "Try a different query"}), 404

    elapsed = int((time.time() - start) * 1000)
    log_search(request.api_key, q, "images", len(results), elapsed)

    return jsonify({
        "query": q,
        "total_results": len(results),
        "search_type": "images",
        "results": results,
        "response_time_ms": elapsed
    })


# ── News Search ───────────────────────────────────────────────────────────────
@app.get("/v1/search/news")
@require_api_key
def news_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    count = min(int(request.args.get("count", 10)), 20)
    region = request.args.get("region", "in-en")

    start = time.time()

    cache_key = f"news:{q}:{count}"
    results = _cache_get(cache_key)

    if not results:
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.news(keywords=q, region=region, safesearch="moderate", max_results=count))
                results = [{
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("body", ""),
                    "published": item.get("date"),
                    "source": item.get("source", extract_domain(item.get("url", ""))),
                    "image_url": item.get("image")
                } for item in raw]
        except Exception:
            # Fallback: use lite search with news keywords
            web_results = ddg_lite_search(f"{q} news latest", count)
            results = [{
                "title": r["title"], "url": r["url"],
                "description": r["description"], "published": None,
                "source": r["source"], "image_url": None
            } for r in web_results]

        if results:
            _cache_set(cache_key, results)

    elapsed = int((time.time() - start) * 1000)
    log_search(request.api_key, q, "news", len(results), elapsed)

    return jsonify({
        "query": q,
        "total_results": len(results),
        "search_type": "news",
        "results": results,
        "response_time_ms": elapsed
    })


# ── AI Summary ────────────────────────────────────────────────────────────────
@app.get("/v1/search/summarize")
@require_api_key
def summarize():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    start = time.time()

    cache_key = f"web:{q}:5:in-en"
    raw_results = _cache_get(cache_key)
    if not raw_results:
        try:
            raw_results = ddg_lite_search(q, 5)
        except Exception:
            raw_results = []
        if not raw_results:
            raw_results = wikipedia_search(q, 5)
    results = [{"title": r["title"], "url": r["url"], "description": r["description"]} for r in raw_results]

    if not results:
        return jsonify({"error": "No results found to summarize"}), 404

    summary = get_ai_summary(q, results)
    sources = [r["url"] for r in results]
    elapsed = int((time.time() - start) * 1000)

    return jsonify({
        "query": q,
        "summary": summary,
        "sources": sources,
        "model_used": OLLAMA_MODEL,
        "response_time_ms": elapsed
    })


# ── Auth: Generate Key ────────────────────────────────────────────────────────
@app.post("/v1/auth/generate-key")
def generate_key():
    data = request.get_json()
    if not data or not data.get("name") or not data.get("email"):
        return jsonify({"error": "name and email are required"}), 400

    name = data["name"].strip()
    email = data["email"].strip().lower()

    conn = get_db()
    existing = conn.execute(
        "SELECT key FROM api_keys WHERE email = ?", (email,)
    ).fetchone()

    if existing:
        conn.close()
        return jsonify({
            "error": f"API key already exists for {email}. Use GET /v1/auth/stats to view usage."
        }), 400

    new_key = "mss_" + secrets.token_urlsafe(40)
    now = datetime.utcnow().isoformat()

    conn.execute(
        "INSERT INTO api_keys (key, name, email, daily_limit, created_at, last_reset_date) VALUES (?,?,?,?,?,?)",
        (new_key, name, email, DAILY_LIMIT, now, date.today().isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({
        "key": new_key,
        "name": name,
        "email": email,
        "daily_limit": DAILY_LIMIT,
        "created_at": now,
        "message": "Your free API key is ready! Add X-API-Key header to all search requests.",
        "example": f"curl http://localhost:8000/v1/search/web?q=hello -H 'X-API-Key: {new_key}'"
    }), 201


# ── Auth: Stats ───────────────────────────────────────────────────────────────
@app.get("/v1/auth/stats")
@require_api_key
def key_stats():
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM api_keys WHERE key = ?", (request.api_key,)
    ).fetchone()
    conn.close()

    key = row["key"]
    return jsonify({
        "key_preview": key[:12] + "..." + key[-4:],
        "name": row["name"],
        "email": row["email"],
        "is_active": bool(row["is_active"]),
        "daily_limit": row["daily_limit"],
        "requests_today": row["requests_today"],
        "total_requests": row["total_requests"],
        "created_at": row["created_at"],
        "last_used": row["last_used"]
    })


# ── Serve Frontend Page ───────────────────────────────────────────────────────
@app.get("/chat")
def serve_chat():
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "..", "static"),
        "index.html"
    )


@app.get("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "..", "static"),
        filename
    )


# ── School Tracker Web App ────────────────────────────────────────────────────
_TRACKER_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "school-tracker")

@app.get("/school-tracker")
@app.get("/school-tracker/")
def serve_tracker():
    return send_from_directory(_TRACKER_DIR, "index.html")

@app.get("/school-tracker/<path:filename>")
def serve_tracker_files(filename):
    file_path = os.path.join(_TRACKER_DIR, filename)
    if os.path.isfile(file_path):
        return send_from_directory(_TRACKER_DIR, filename)
    # All Flutter routes fall back to index.html (client-side routing)
    return send_from_directory(_TRACKER_DIR, "index.html")


# ── Streaming AI Chat Endpoint ────────────────────────────────────────────────
@app.post("/v1/ai/chat")
@require_api_key
def ai_chat():
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "message field is required"}), 400

    user_message = data["message"].strip()
    history = data.get("history", [])
    with_search = data.get("with_search", True)

    # Build context from web search
    search_context = ""
    search_results = []
    if with_search:
        try:
            web = ddg_lite_search(user_message, 4)
            if not web:
                web = wikipedia_search(user_message, 4)
            search_results = web
            lines = [f"{i+1}. {r['title']}: {r['description'][:200]}" for i, r in enumerate(web)]
            search_context = "\n".join(lines)
        except Exception:
            pass

    # Build system prompt
    system = (
        "You are MyAI, a helpful and knowledgeable AI assistant for MyAISpace.in. "
        "Answer clearly and concisely. Use the web context below if relevant. "
        "If the context is not relevant, answer from your own knowledge."
    )
    if search_context:
        system += f"\n\nWeb search context:\n{search_context}"

    # Build messages for Ollama (chat format)
    messages = [{"role": "system", "content": system}]
    for h in history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    def generate():
        # Emit search sources first
        if search_results:
            yield f"data: {json.dumps({'type': 'sources', 'sources': [{'title': r['title'], 'url': r['url'], 'source': r['source']} for r in search_results]})}\n\n"

        # ── Use Groq (cloud) if API key is set, else fall back to local Ollama ──
        if groq_client:
            try:
                stream = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1024,
                    stream=True
                )
                for chunk in stream:
                    token = chunk.choices[0].delta.content or ""
                    if token:
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        else:
            # Local Ollama fallback
            try:
                with requests.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={"model": OLLAMA_MODEL, "messages": messages, "stream": True,
                          "think": False, "options": {"temperature": 0.7, "num_predict": 1024}},
                    stream=True, timeout=120
                ) as resp:
                    for line in resp.iter_lines():
                        if line:
                            try:
                                chunk = json.loads(line)
                                token = chunk.get("message", {}).get("content", "")
                                if token:
                                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                                if chunk.get("done"):
                                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                                    break
                            except Exception:
                                continue
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': 'AI service unavailable: ' + str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── CompleteHealth AI — page + proxy ─────────────────────────────────────────
_CH_RAG_URL = os.getenv("COMPLETEHEALTH_RAG_URL", "http://localhost:8001")

@app.get("/completehealth-ai")
def serve_completehealth_ai():
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "..", "static"),
        "completehealth-ai.html"
    )

@app.post("/v1/completehealth/ask")
def completehealth_ask():
    data = request.get_json()
    if not data or not data.get("question"):
        return jsonify({"error": "question field is required"}), 400
    try:
        resp = requests.post(
            f"{_CH_RAG_URL}/ask",
            json={"question": data["question"], "top_k": data.get("top_k", 4)},
            timeout=120
        )
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "RAG service offline", "detail": "CompleteHealth AI is not running. Start it with: py -m uvicorn main:app --port 8001"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Boot ──────────────────────────────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  MyAISpace Search API")
    print("  http://localhost:8000")
    print("  Website: https://myaispace.in")
    print("="*50 + "\n")
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
