"""Ticker lookup API routes."""
from __future__ import annotations

import logging

import requests
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/ticker/search")
async def ticker_search(q: str = ""):
    """Proxy Yahoo Finance autocomplete; returns matching tickers for a name or symbol."""
    query = q.strip()
    if not query:
        return []
    try:
        response = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": 7, "newsCount": 0, "enableFuzzyQuery": True},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        data = response.json()
        results = []
        for item in data.get("quotes", []):
            if item.get("quoteType") not in ("EQUITY", "ETF"):
                continue
            results.append(
                {
                    "symbol": item.get("symbol", ""),
                    "name": item.get("longname") or item.get("shortname", ""),
                    "exchange": item.get("exchDisp", ""),
                    "type": item.get("quoteType", ""),
                }
            )
        return results[:7]
    except Exception as exc:
        logger.warning("Ticker search failed: %s", exc)
        return []
