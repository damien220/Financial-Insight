"""News feed component."""

import streamlit as st
from typing import Any, Dict, List


def render_news_feed(news_data: Dict[str, Any]) -> None:
    """Render scrollable news feed."""
    st.subheader("Recent News")

    articles = news_data.get("articles", [])
    if not articles:
        st.info("No news articles available.")
        return

    # Source filter
    sources = sorted(set(a.get("source", "unknown") for a in articles))
    if len(sources) > 1:
        selected_sources = st.multiselect(
            "Filter by source",
            sources,
            default=sources,
            key="news_source_filter",
        )
        articles = [a for a in articles if a.get("source") in selected_sources]

    st.caption(f"Showing {len(articles)} articles")

    for article in articles:
        _render_article(article)


def _render_article(article: Dict[str, Any]) -> None:
    source = article.get("source", "Unknown")
    title = article.get("title", "Untitled")
    summary = article.get("summary", "")
    url = article.get("url", "")
    published = article.get("published_at", "")

    # Header line
    time_str = published[:16] if published else ""
    header = f"**{title}**"
    if url:
        header = f"[{title}]({url})"

    meta_parts = []
    if source:
        meta_parts.append(f"`{source}`")
    if time_str:
        meta_parts.append(time_str)
    meta = " · ".join(meta_parts)

    st.markdown(f"{header}")
    if meta:
        st.caption(meta)
    if summary:
        with st.expander("Summary", expanded=False):
            st.write(summary)
    st.divider()
