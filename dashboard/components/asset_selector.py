"""Asset selector sidebar component."""

import streamlit as st
import yaml
from typing import Dict, List, Any


def load_assets_config(config_path: str = "config/assets.yaml") -> Dict[str, Any]:
    try:
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def get_asset_list(config: Dict[str, Any]) -> List[Dict[str, str]]:
    assets = []
    assets_cfg = config.get("assets", {})
    for category_assets in assets_cfg.values():
        if isinstance(category_assets, dict):
            for key, info in category_assets.items():
                if isinstance(info, dict) and "ticker" in info:
                    assets.append({
                        "ticker": info["ticker"],
                        "name": info.get("name", key),
                        "category": info.get("category", "unknown"),
                    })
    return assets


def render_asset_selector() -> str:
    """Render asset selector in sidebar. Returns selected ticker."""
    config = load_assets_config()
    assets = get_asset_list(config)

    if not assets:
        st.sidebar.warning("No assets configured.")
        return ""

    st.sidebar.header("Assets")

    # Group by category
    categories = {}
    for a in assets:
        cat = a["category"].title()
        categories.setdefault(cat, []).append(a)

    # Build display labels
    labels = []
    ticker_map = {}
    for cat, items in categories.items():
        for a in items:
            label = f"{a['name']} ({a['ticker']})"
            labels.append(label)
            ticker_map[label] = a["ticker"]

    selected_label = st.sidebar.selectbox("Select asset", labels, index=0)
    selected_ticker = ticker_map.get(selected_label, "")

    # Quick-add ticker
    st.sidebar.divider()
    new_ticker = st.sidebar.text_input("Quick lookup ticker", placeholder="e.g. TSLA")
    if new_ticker and new_ticker.strip():
        selected_ticker = new_ticker.strip().upper()
        st.sidebar.info(f"Viewing: {selected_ticker}")

    return selected_ticker
