"""Financial News Tool — fetches news from RSS feeds and optional API providers."""

import os
import re
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import feedparser
from tools.base import BaseTool

# RSS feeds that work without API keys
RSS_FEEDS = {
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "google_finance": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en",
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "investing_com": "https://www.investing.com/rss/news.rss",
    "cnbc": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
}

# Query-specific Google News RSS (financial context)
_GOOGLE_NEWS_SEARCH = "https://news.google.com/rss/search?q={query}+stock+market&hl=en-US&gl=US&ceid=US:en"


class FinancialNewsTool(BaseTool):

    def get_name(self) -> str:
        return "financial_news"

    def get_description(self) -> str:
        return "Fetch recent financial news articles for a given asset, ticker, or topic."

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Asset name, ticker symbol, or search topic (e.g. 'AAPL', 'gold', 'S&P 500').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of articles to return (default 10).",
                },
                "source": {
                    "type": "string",
                    "description": "Specific RSS source key, or 'all' for all feeds (default 'all').",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        max_results: int = 10,
        source: str = "all",
        **kwargs,
    ) -> Dict[str, Any]:
        query = query.strip()
        if not query:
            return {"error": "Query is required.", "articles": []}

        articles: List[Dict[str, Any]] = []

        # 1. Try optional API providers first (if keys configured)
        articles.extend(_fetch_finnhub(query, max_results))
        articles.extend(_fetch_newsapi(query, max_results))

        # 2. RSS: query-specific Google News search
        articles.extend(_fetch_rss(_GOOGLE_NEWS_SEARCH.format(query=query), "google_news_search"))

        # 3. General RSS feeds
        if source == "all":
            for name, url in RSS_FEEDS.items():
                articles.extend(_fetch_rss(url, name))
        elif source in RSS_FEEDS:
            articles.extend(_fetch_rss(RSS_FEEDS[source], source))

        # Filter by relevance to query
        articles = _filter_relevant(articles, query)

        # Deduplicate by title similarity
        articles = _deduplicate(articles)

        # Sort by date (newest first) and limit
        articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)
        articles = articles[:max_results]

        return {
            "query": query,
            "count": len(articles),
            "articles": articles,
        }


# ---------------------------------------------------------------------------
# RSS fetching
# ---------------------------------------------------------------------------

def _fetch_rss(url: str, source_name: str) -> List[Dict[str, Any]]:
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries[:20]:  # cap per-feed
            published = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
                except Exception:
                    published = getattr(entry, "published", "")
            elif hasattr(entry, "published"):
                published = entry.published

            summary = _clean_html(getattr(entry, "summary", ""))
            articles.append({
                "title": getattr(entry, "title", ""),
                "summary": summary[:500],
                "source": source_name,
                "url": getattr(entry, "link", ""),
                "published_at": published,
                "sentiment_hint": None,
            })
        return articles
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Optional API providers (graceful no-ops when keys absent)
# ---------------------------------------------------------------------------

def _fetch_finnhub(query: str, max_results: int) -> List[Dict[str, Any]]:
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return []
    try:
        import finnhub
        client = finnhub.Client(api_key=api_key)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        news = client.company_news(query.upper(), _from=today, to=today)
        articles = []
        for item in (news or [])[:max_results]:
            articles.append({
                "title": item.get("headline", ""),
                "summary": (item.get("summary", "") or "")[:500],
                "source": f"finnhub:{item.get('source', '')}",
                "url": item.get("url", ""),
                "published_at": datetime.fromtimestamp(
                    item.get("datetime", 0), tz=timezone.utc
                ).isoformat() if item.get("datetime") else "",
                "sentiment_hint": None,
            })
        return articles
    except Exception:
        return []


def _fetch_newsapi(query: str, max_results: int) -> List[Dict[str, Any]]:
    api_key = os.environ.get("NEWSAPI_KEY", "")
    if not api_key:
        return []
    try:
        from newsapi import NewsApiClient
        client = NewsApiClient(api_key=api_key)
        resp = client.get_everything(q=query, language="en", sort_by="publishedAt", page_size=max_results)
        articles = []
        for item in (resp.get("articles") or []):
            articles.append({
                "title": item.get("title", ""),
                "summary": (item.get("description", "") or "")[:500],
                "source": f"newsapi:{item.get('source', {}).get('name', '')}",
                "url": item.get("url", ""),
                "published_at": item.get("publishedAt", ""),
                "sentiment_hint": None,
            })
        return articles
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _filter_relevant(articles: List[Dict], query: str) -> List[Dict]:
    query_terms = set(query.lower().split())
    scored = []
    for a in articles:
        text = f"{a['title']} {a['summary']}".lower()
        hits = sum(1 for t in query_terms if t in text)
        if hits > 0:
            scored.append((hits, a))
    # If very few matches, return all (the general feeds may still be useful)
    if len(scored) < 3:
        return articles
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored]


def _deduplicate(articles: List[Dict]) -> List[Dict]:
    seen: set = set()
    unique = []
    for a in articles:
        key = _title_hash(a["title"])
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def _title_hash(title: str) -> str:
    normalized = re.sub(r"\W+", " ", title.lower()).strip()
    return hashlib.md5(normalized.encode()).hexdigest()[:12]
