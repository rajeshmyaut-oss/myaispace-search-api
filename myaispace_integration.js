/**
 * MyAISpace Search API — Frontend Integration
 * Add this to your myaispace.in website
 *
 * Usage:
 *   const api = new MyAISpaceSearch("mss_your_api_key_here");
 *   const results = await api.webSearch("SAP CPI tutorial");
 */

class MyAISpaceSearch {
  constructor(apiKey, baseUrl = "http://localhost:8000") {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
    this.headers = {
      "X-API-Key": apiKey,
      "Content-Type": "application/json",
    };
  }

  // ── Web Search ────────────────────────────────────────────────────────────
  async webSearch(query, options = {}) {
    const params = new URLSearchParams({
      q: query,
      count: options.count || 10,
      region: options.region || "in-en",
      summary: options.summary || false,
    });

    const res = await fetch(`${this.baseUrl}/v1/search/web?${params}`, {
      headers: this.headers,
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Search failed");
    }

    return res.json();
  }

  // ── Image Search ──────────────────────────────────────────────────────────
  async imageSearch(query, options = {}) {
    const params = new URLSearchParams({
      q: query,
      count: options.count || 10,
      region: options.region || "in-en",
    });

    const res = await fetch(`${this.baseUrl}/v1/search/images?${params}`, {
      headers: this.headers,
    });

    if (!res.ok) throw new Error("Image search failed");
    return res.json();
  }

  // ── News Search ───────────────────────────────────────────────────────────
  async newsSearch(query, options = {}) {
    const params = new URLSearchParams({
      q: query,
      count: options.count || 10,
      region: options.region || "in-en",
    });

    const res = await fetch(`${this.baseUrl}/v1/search/news?${params}`, {
      headers: this.headers,
    });

    if (!res.ok) throw new Error("News search failed");
    return res.json();
  }

  // ── AI Summary ────────────────────────────────────────────────────────────
  async aiSummarize(query) {
    const res = await fetch(
      `${this.baseUrl}/v1/search/summarize?q=${encodeURIComponent(query)}`,
      { headers: this.headers }
    );

    if (!res.ok) throw new Error("Summary failed");
    return res.json();
  }

  // ── Generate API Key (one time) ───────────────────────────────────────────
  static async generateKey(name, email, baseUrl = "http://localhost:8000") {
    const res = await fetch(`${baseUrl}/v1/auth/generate-key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Key generation failed");
    }

    return res.json();
  }
}


// ── Example Usage on myaispace.in ────────────────────────────────────────────

async function runSearchExample() {
  const API_KEY = "mss_your_api_key_here"; // Replace with your key
  const api = new MyAISpaceSearch(API_KEY, "http://localhost:8000");

  try {
    // 1. Web Search
    console.log("=== Web Search ===");
    const webResults = await api.webSearch("SAP CPI tutorial", { count: 5 });
    console.log(`Found ${webResults.total_results} results in ${webResults.response_time_ms}ms`);
    webResults.results.forEach((r, i) => {
      console.log(`${i + 1}. ${r.title}`);
      console.log(`   ${r.url}`);
      console.log(`   ${r.description}`);
    });

    // 2. News Search
    console.log("\n=== News Search ===");
    const news = await api.newsSearch("India tech news", { count: 3 });
    news.results.forEach((n) => console.log(`• ${n.title} — ${n.source}`));

    // 3. AI Summary
    console.log("\n=== AI Summary ===");
    const summary = await api.aiSummarize("What is SAP CPI?");
    console.log(summary.summary);

  } catch (err) {
    console.error("Error:", err.message);
  }
}

// Uncomment to test:
// runSearchExample();

// Export for use in modules
if (typeof module !== "undefined") module.exports = MyAISpaceSearch;
