"""Stock chart API routes backed by Financial Modeling Prep."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests
from fastapi import APIRouter, HTTPException

from backend.config import CHART_PERIOD_DAYS
from backend.http_client import fetch_json

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stock-chart"])


@router.get("/stock-chart/compare")
async def get_stock_chart_compare(tickers: str, period: str = "1M"):
    """
    Fetch stock chart data for multiple tickers for comparison.

    Args:
        tickers: Comma-separated ticker symbols (max 2), e.g. "AAPL,MSFT"
        period: Time period (1M, 6M, YTD, 1Y, 5Y, MAX)

    Returns:
        JSON with tickers list, quotes dict, and historical dict
    """
    try:
        fmp_key = os.getenv("FMP_API_KEY")
        if not fmp_key:
            raise HTTPException(status_code=500, detail="FMP_API_KEY not configured")

        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        if len(ticker_list) == 0 or len(ticker_list) > 2:
            raise HTTPException(status_code=400, detail="Provide 1-2 comma-separated tickers")

        quote_url = "https://financialmodelingprep.com/stable/quote"
        hist_url = "https://financialmodelingprep.com/stable/historical-price-eod/full"

        async def load_compare_ticker(tkr: str) -> tuple[str, dict, List[Dict]]:
            quote_data_list, hist_result = await asyncio.gather(
                fetch_json(quote_url, params={"symbol": tkr, "apikey": fmp_key}),
                fetch_json(hist_url, params={"symbol": tkr, "apikey": fmp_key}),
                return_exceptions=True,
            )

            if isinstance(quote_data_list, Exception):
                logger.error("Failed to fetch compare chart data for %s: %s", tkr, quote_data_list)
                raise HTTPException(status_code=404, detail=f"Could not fetch data for ticker {tkr}")

            if not quote_data_list:
                raise HTTPException(status_code=404, detail=f"No quote data found for {tkr}")

            if isinstance(hist_result, Exception):
                logger.warning("Historical compare chart fetch failed for %s: %s", tkr, hist_result)
                hist_data = []
            else:
                hist_data = hist_result

            qd = quote_data_list[0]
            quote_payload = {
                "symbol": qd.get("symbol", tkr),
                "name": qd.get("name", ""),
                "exchange": qd.get("exchange", ""),
                "price": qd.get("price", 0),
                "changesPercentage": qd.get("changesPercentage", 0),
                "change": qd.get("change", 0),
                "dayHigh": qd.get("dayHigh", 0),
                "dayLow": qd.get("dayLow", 0),
                "volume": qd.get("volume", 0),
                "marketCap": qd.get("marketCap", 0),
                "open": qd.get("open", 0),
                "previousClose": qd.get("previousClose", 0),
                "yearHigh": qd.get("yearHigh", 0),
                "yearLow": qd.get("yearLow", 0),
                "avgVolume": qd.get("avgVolume", 0),
                "pe": qd.get("pe", None),
                "eps": qd.get("eps", None),
                "beta": qd.get("beta", None),
            }
            return tkr, quote_payload, filter_chart_data_by_period(hist_data, period)

        results = await asyncio.gather(*(load_compare_ticker(tkr) for tkr in ticker_list))
        quotes = {ticker: quote for ticker, quote, _ in results}
        historical = {ticker: history for ticker, _, history in results}

        return {
            "tickers": ticker_list,
            "quotes": quotes,
            "historical": historical,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def filter_chart_data_by_period(data: Any, period: str) -> List[Dict]:
    """Filter historical chart data by time period."""
    if period == "1D":
        return data if isinstance(data, list) else []

    if period == "YTD":
        cutoff_date = datetime(datetime.now().year, 1, 1)
    else:
        days = CHART_PERIOD_DAYS.get(period, CHART_PERIOD_DAYS["1M"])
        cutoff_date = datetime.now() - timedelta(days=days)

    historical = data.get("historical", data) if isinstance(data, dict) else data

    if not isinstance(historical, list):
        return []

    filtered = []
    for item in historical:
        try:
            item_date_str = item.get("date", "").split(" ")[0]
            item_date = datetime.strptime(item_date_str, "%Y-%m-%d")

            if item_date >= cutoff_date:
                filtered.append(item)
        except (ValueError, AttributeError):
            continue

    return filtered


@router.get("/stock-chart/{ticker}")
async def get_stock_chart(ticker: str, period: str = "1M"):
    """
    Fetch stock chart data from FMP API.

    Args:
        ticker: Stock ticker symbol (e.g., AAPL, MSFT)
        period: Time period (1D, 1W, 1M, 3M, 1Y, ALL)

    Returns:
        JSON with quote data and historical price data
    """
    try:
        fmp_key = os.getenv("FMP_API_KEY")
        if not fmp_key:
            raise HTTPException(status_code=500, detail="FMP_API_KEY not configured")

        ticker = ticker.upper()

        quote_url = "https://financialmodelingprep.com/stable/quote"
        if period == "1D":
            hist_url = "https://financialmodelingprep.com/stable/historical-chart/5min"
        else:
            hist_url = "https://financialmodelingprep.com/stable/historical-price-eod/full"

        quote_data_list, hist_result = await asyncio.gather(
            fetch_json(quote_url, params={"symbol": ticker, "apikey": fmp_key}),
            fetch_json(hist_url, params={"symbol": ticker, "apikey": fmp_key}),
            return_exceptions=True,
        )

        if isinstance(quote_data_list, Exception):
            logger.error("Failed to fetch quote for %s: %s", ticker, quote_data_list)
            raise HTTPException(status_code=404, detail=f"Could not fetch data for ticker {ticker}")

        if not quote_data_list or len(quote_data_list) == 0:
            logger.error("Empty quote response for %s", ticker)
            raise HTTPException(status_code=404, detail=f"No quote data found for {ticker}")

        quote_data = quote_data_list[0]
        logger.debug("FMP quote response for %s: %s", ticker, quote_data)

        if isinstance(hist_result, Exception):
            logger.error("Failed to fetch historical data for %s: %s", ticker, hist_result)
            hist_data = []
        else:
            hist_data = hist_result

        quote_data = {
            "symbol": quote_data.get("symbol", ticker),
            "name": quote_data.get("name", ""),
            "exchange": quote_data.get("exchange", ""),
            "price": quote_data.get("price", 0),
            "changesPercentage": quote_data.get("changesPercentage", 0),
            "change": quote_data.get("change", 0),
            "dayHigh": quote_data.get("dayHigh", 0),
            "dayLow": quote_data.get("dayLow", 0),
            "volume": quote_data.get("volume", 0),
            "marketCap": quote_data.get("marketCap", 0),
            "open": quote_data.get("open", 0),
            "previousClose": quote_data.get("previousClose", 0),
            "yearHigh": quote_data.get("yearHigh", 0),
            "yearLow": quote_data.get("yearLow", 0),
            "avgVolume": quote_data.get("avgVolume", 0),
            "pe": quote_data.get("pe", None),
            "eps": quote_data.get("eps", None),
            "beta": quote_data.get("beta", None),
        }

        if isinstance(hist_data, list) and len(hist_data) > 0:
            logger.debug("FMP historical response sample for %s: %s", ticker, hist_data[0])
        elif isinstance(hist_data, dict) and "historical" in hist_data:
            sample = hist_data["historical"][0] if hist_data["historical"] else "empty"
            logger.debug("FMP historical response sample for %s: %s", ticker, sample)

        filtered_data = filter_chart_data_by_period(hist_data, period)

        return {
            "ticker": ticker,
            "quote": quote_data,
            "historical": filtered_data,
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"FMP API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
