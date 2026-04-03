"""
Arena Sentiment Analyst Agent

Purpose-built sentiment analyst for the Finance Agent Arena.
Answers: is human conviction in this stock building or eroding?

Pillars:
  1. News Flow & Media Sentiment  (news cycle, catalysts, volume)
  2. Analyst Sentiment Momentum   (upgrades/downgrades, price targets)
  3. Earnings Call Tone           (guidance, management tone, buybacks)
  4. Insider & Institutional      (insider filings, 13F trends, short interest)

All sentiment data is Tavily-sourced with search_depth="advanced".
FinancialDataFetcher used only to fetch company name and sector context.

Uses claude-haiku-4-5-20251001 for ALL LLM calls.
Never crashes the arena — all errors produce a fallback neutral signal.
"""
from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from arena.state import AgentSignal, ThesisState
from data.financial_data import FinancialDataFetcher
from data.sec_edgar import SECEdgarClient
from shared.tavily_client import get_tavily_client

logger = logging.getLogger(__name__)

VALID_VIEWS = {"bullish", "bearish", "neutral", "cautious"}
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Level 3: the agent this one questions when uncertain
QUESTION_TARGET = "risk"


# ---------------------------------------------------------------------------
# Section 1 — Data fetching helpers
# ---------------------------------------------------------------------------

def fetch_company_context(ticker: str) -> dict:
    """
    Fetch only company name, sector, and market_cap from FinancialDataFetcher.
    This is the only FinancialDataFetcher call in this agent.
    Never raises.
    """
    result = {
        "ticker": ticker,
        "company_name": ticker,
        "sector": "Unknown",
        "market_cap": None,
    }

    try:
        fetcher = FinancialDataFetcher()
        stock_info = fetcher.get_stock_info(ticker)
        if stock_info:
            result["company_name"] = stock_info.get("name") or stock_info.get("company_name") or ticker
            result["sector"] = stock_info.get("sector") or "Unknown"
            result["market_cap"] = stock_info.get("market_cap")
    except Exception as e:
        print(f"[Sentiment] fetch_company_context failed for {ticker}: {e}")

    return result


def fetch_insider_data_from_sec(ticker: str) -> dict:
    """
    Fetch Form 4 insider transaction data directly from SEC EDGAR.
    Parses non-derivative transactions for the last 90 days.
    Returns structured data overriding Tavily's weaker insider signal.
    Never raises — falls back to empty result on any error.
    """
    import xml.etree.ElementTree as ET
    from datetime import datetime, timedelta

    empty: dict = {
        "insider_activity": None,          # None = no SEC data, do not override
        "insider_buying_amount_usd": None,
        "insider_transaction_count_90d": 0,
        "notable_insider_transactions": None,
    }

    try:
        sec = SECEdgarClient()
        filings = sec.get_recent_filings(ticker, filing_type="4", limit=30)
        if not filings:
            return empty

        cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        recent = [f for f in filings if f.get("filing_date", "") >= cutoff]

        if not recent:
            return empty

        total_bought_usd = 0.0
        total_sold_usd = 0.0
        transaction_count = 0
        notable: list = []

        for filing in recent[:15]:
            doc_url = filing.get("document_url", "")
            if not doc_url:
                continue

            # SEC primaryDocument sometimes points to the XSL-styled display
            # version under xslF345X05/; strip that prefix to get raw XML.
            doc_url = doc_url.replace("/xslF345X05/", "/")

            xml_text = sec._get_text(doc_url)
            if not xml_text:
                continue

            try:
                root = ET.fromstring(xml_text)
            except ET.ParseError:
                # Some Form 4s are HTML-wrapped; skip gracefully
                continue

            # Form 4 XML structure:
            #   transactionCode  → direct text (no <value> wrapper)
            #   transactionShares/value, transactionPricePerShare/value → <value> wrapper
            for txn in root.iter("nonDerivativeTransaction"):
                code_el = txn.find("transactionCoding/transactionCode")
                if code_el is None:
                    continue
                code = (code_el.text or "").strip()
                if code not in ("P", "S"):
                    continue

                shares_el = txn.find("transactionAmounts/transactionShares/value")
                price_el  = txn.find("transactionAmounts/transactionPricePerShare/value")

                try:
                    shares = float(shares_el.text) if shares_el is not None and shares_el.text else 0.0
                    price  = float(price_el.text)  if price_el  is not None and price_el.text  else 0.0
                    amount = shares * price
                except (TypeError, ValueError):
                    continue

                transaction_count += 1
                if code == "P":
                    total_bought_usd += amount
                    if amount >= 100_000:
                        notable.append(f"Purchase ${amount:,.0f}")
                elif code == "S":
                    total_sold_usd += amount
                    if amount >= 500_000:
                        notable.append(f"Sale ${amount:,.0f}")

        if transaction_count == 0:
            # Filings found but contained no reportable transactions
            return empty

        # Determine net activity
        if total_bought_usd > total_sold_usd * 2:
            activity = "buying"
        elif total_sold_usd > total_bought_usd * 2:
            activity = "selling"
        elif total_bought_usd > 0 and total_sold_usd > 0:
            activity = "mixed"
        elif total_bought_usd > 0:
            activity = "buying"
        elif total_sold_usd > 0:
            activity = "selling"
        else:
            activity = "none"

        notable_str: str | None = None
        if notable:
            notable_str = "; ".join(notable[:3])

        return {
            "insider_activity": activity,
            "insider_buying_amount_usd": total_bought_usd if total_bought_usd > 0 else None,
            "insider_transaction_count_90d": transaction_count,
            "notable_insider_transactions": notable_str,
        }

    except Exception as e:
        print(f"[Sentiment/SEC] fetch_insider_data_from_sec failed for {ticker}: {e}")
        return empty


def fetch_sentiment_data(ticker: str) -> dict:
    """
    Four Tavily searches split across two topics:
      - topic="news"    for Pillar 1 (news flow) — recency-optimised
      - topic="finance" for Pillars 2-4 (analyst, management, insider) — data-optimised

    Two focused Haiku extraction calls (10 fields each) instead of one 20-field call.
    Returns structured sentiment indicators — never invented.
    Falls back to safe defaults if extraction fails.
    """
    defaults = {
        "news_sentiment_overall": "neutral",
        "major_catalyst": None,
        "catalyst_type": None,
        "news_volume": "normal",
        "days_since_major_news": None,
        "analyst_consensus": "hold",
        "upgrades_60d": None,
        "downgrades_60d": None,
        "price_target_trend": "stable",
        "avg_price_target": None,
        "current_price_vs_target": "at",
        "guidance_direction": "unknown",
        "management_tone": "neutral",
        "buyback_announced": False,
        "dividend_change": "unknown",
        "management_credibility_note": None,
        "insider_activity": "none",
        "insider_buying_amount_usd": None,
        "institutional_trend": "stable",
        "short_interest_pct": None,
        "short_interest_trend": "stable",
        "notable_institutional_moves": None,
    }

    try:
        tavily = get_tavily_client()
        client = Anthropic()

        def _search(query: str, topic: str = "finance") -> str:
            try:
                result = tavily.search(
                    query=query,
                    topic=topic,
                    search_depth="advanced",
                    max_results=7,
                )
                parts = []
                if result.get("answer"):
                    parts.append(result["answer"])
                for r in result.get("results", [])[:5]:
                    if r.get("content"):
                        parts.append(r["content"][:600])
                return "\n\n".join(parts)
            except Exception as e:
                print(f"[Sentiment] Tavily search failed ({topic}): {e}")
                return ""

        def _parse_json(text: str) -> dict:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())

        # ── Pillar 1: News flow — topic="news" for recency ────────────────────
        news_text = _search(
            f"{ticker} stock news recent weeks major catalyst product launch "
            "lawsuit regulatory issue earnings miss beat analyst reaction",
            topic="news",
        )

        # ── Pillar 2: Analyst sentiment — topic="finance" for ratings data ────
        analyst_text = _search(
            f"{ticker} analyst price target consensus rating buy sell hold "
            "upgrades downgrades 2024 2025 Wall Street forecast",
            topic="finance",
        )

        # ── Extraction call A: news + analyst (10 fields) ─────────────────────
        news_analyst_context = (
            "=== NEWS FLOW ===\n" + news_text[:1500]
            + "\n\n=== ANALYST RATINGS ===\n" + analyst_text[:1500]
        )

        prompt_a = (
            f"Extract these 10 fields for {ticker} from the search results. "
            f"Use only what is explicitly stated — do not guess. "
            f"Respond ONLY with a JSON object, no preamble.\n\n"
            f"{{\n"
            f'  "news_sentiment_overall": "very_positive"|"positive"|"neutral"|"negative"|"very_negative",\n'
            f'  "major_catalyst": "one-sentence description of the biggest recent news, or null",\n'
            f'  "catalyst_type": "positive"|"negative"|"neutral"|null,\n'
            f'  "news_volume": "high"|"normal"|"low",\n'
            f'  "days_since_major_news": integer or null,\n'
            f'  "analyst_consensus": "strong_buy"|"buy"|"hold"|"sell"|"strong_sell",\n'
            f'  "upgrades_60d": integer or null,\n'
            f'  "downgrades_60d": integer or null,\n'
            f'  "price_target_trend": "rising"|"falling"|"stable",\n'
            f'  "avg_price_target": number (USD) or null\n'
            f"}}\n\n"
            f"Rules:\n"
            f"- news_volume: 'high' if multiple major stories, 'low' if quiet\n"
            f"- analyst_consensus: map 'outperform'→buy, 'underperform'→sell, 'market perform'→hold\n"
            f"- If you cannot find a value, use null — never fabricate\n\n"
            f"Search results:\n{news_analyst_context}"
        )

        resp_a = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt_a}],
        )
        parsed_a = _parse_json(resp_a.content[0].text)

        # ── Pillar 3: Management signals — topic="finance" ────────────────────
        mgmt_text = _search(
            f"{ticker} earnings call guidance raised lowered maintained CEO CFO "
            "outlook forward guidance buyback share repurchase dividend 2024 2025",
            topic="finance",
        )

        # ── Pillar 4: Insider & institutional — topic="finance" ───────────────
        insider_text = _search(
            f"{ticker} insider buying selling Form 4 SEC filing institutional "
            "holdings 13F short interest float hedge fund position 2024 2025",
            topic="finance",
        )

        # ── Extraction call B: management + insider (10 fields) ───────────────
        mgmt_insider_context = (
            "=== EARNINGS CALL & MANAGEMENT ===\n" + mgmt_text[:1500]
            + "\n\n=== INSIDER & INSTITUTIONAL ===\n" + insider_text[:1500]
        )

        # Also pass the analyst consensus so Haiku can compute current_price_vs_target
        avg_pt = parsed_a.get("avg_price_target")
        pt_hint = f"Average analyst price target: ${avg_pt}" if avg_pt else ""

        prompt_b = (
            f"Extract these 10 fields for {ticker} from the search results. "
            f"Use only what is explicitly stated — do not guess. "
            f"Respond ONLY with a JSON object, no preamble.\n\n"
            f"{pt_hint}\n\n"
            f"{{\n"
            f'  "current_price_vs_target": "below"|"at"|"above",\n'
            f'  "guidance_direction": "raised"|"maintained"|"lowered"|"withdrawn"|"unknown",\n'
            f'  "management_tone": "confident"|"cautious"|"defensive"|"neutral",\n'
            f'  "buyback_announced": true or false,\n'
            f'  "dividend_change": "raised"|"maintained"|"cut"|"none"|"unknown",\n'
            f'  "management_credibility_note": "one sentence on guidance reliability, or null",\n'
            f'  "insider_activity": "buying"|"selling"|"mixed"|"none",\n'
            f'  "insider_buying_amount_usd": total dollar amount of insider purchases, or null,\n'
            f'  "institutional_trend": "increasing"|"decreasing"|"stable",\n'
            f'  "short_interest_pct": percentage of float sold short as a number, or null,\n'
            f'  "short_interest_trend": "rising"|"falling"|"stable",\n'
            f'  "notable_institutional_moves": "one sentence on the most notable fund activity, or null"\n'
            f"}}\n\n"
            f"Rules:\n"
            f"- buyback_announced: true only if a specific repurchase program was announced\n"
            f"- insider_activity: 'buying' if net purchases, 'selling' if net sales, 'mixed' if both\n"
            f"- current_price_vs_target: compare current price to avg_price_target if known\n"
            f"- If you cannot find a value, use null or 'unknown' — never fabricate\n\n"
            f"Search results:\n{mgmt_insider_context}"
        )

        resp_b = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt_b}],
        )
        parsed_b = _parse_json(resp_b.content[0].text)

        # ── Merge both extraction results ─────────────────────────────────────
        def _str(val, default, valid_set=None):
            if val is None:
                return default
            s = str(val).lower().strip()
            if valid_set and s not in valid_set:
                return default
            return s

        def _int(val):
            try:
                return int(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        def _float(val):
            try:
                return float(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        result = {
            # From extraction A
            "news_sentiment_overall": _str(
                parsed_a.get("news_sentiment_overall"), "neutral",
                {"very_positive", "positive", "neutral", "negative", "very_negative"}
            ),
            "major_catalyst": str(parsed_a.get("major_catalyst") or "") or None,
            "catalyst_type": _str(
                parsed_a.get("catalyst_type"), None,
                {"positive", "negative", "neutral"}
            ),
            "news_volume": _str(parsed_a.get("news_volume"), "normal", {"high", "normal", "low"}),
            "days_since_major_news": _int(parsed_a.get("days_since_major_news")),
            "analyst_consensus": _str(
                parsed_a.get("analyst_consensus"), "hold",
                {"strong_buy", "buy", "hold", "sell", "strong_sell"}
            ),
            "upgrades_60d": _int(parsed_a.get("upgrades_60d")),
            "downgrades_60d": _int(parsed_a.get("downgrades_60d")),
            "price_target_trend": _str(
                parsed_a.get("price_target_trend"), "stable",
                {"rising", "falling", "stable"}
            ),
            "avg_price_target": _float(parsed_a.get("avg_price_target")),
            # From extraction B
            "current_price_vs_target": _str(
                parsed_b.get("current_price_vs_target"), "at",
                {"below", "at", "above"}
            ),
            "guidance_direction": _str(
                parsed_b.get("guidance_direction"), "unknown",
                {"raised", "maintained", "lowered", "withdrawn", "unknown"}
            ),
            "management_tone": _str(
                parsed_b.get("management_tone"), "neutral",
                {"confident", "cautious", "defensive", "neutral"}
            ),
            "buyback_announced": bool(parsed_b.get("buyback_announced", False)),
            "dividend_change": _str(
                parsed_b.get("dividend_change"), "unknown",
                {"raised", "maintained", "cut", "none", "unknown"}
            ),
            "management_credibility_note": str(parsed_b.get("management_credibility_note") or "") or None,
            "insider_activity": _str(
                parsed_b.get("insider_activity"), "none",
                {"buying", "selling", "mixed", "none"}
            ),
            "insider_buying_amount_usd": _float(parsed_b.get("insider_buying_amount_usd")),
            "institutional_trend": _str(
                parsed_b.get("institutional_trend"), "stable",
                {"increasing", "decreasing", "stable"}
            ),
            "short_interest_pct": _float(parsed_b.get("short_interest_pct")),
            "short_interest_trend": _str(
                parsed_b.get("short_interest_trend"), "stable",
                {"rising", "falling", "stable"}
            ),
            "notable_institutional_moves": str(parsed_b.get("notable_institutional_moves") or "") or None,
        }

        # ── SEC EDGAR Form 4 override for insider pillar ──────────────────────
        # Tavily rarely surfaces Form 4 data reliably; SEC EDGAR is authoritative.
        # Only override when SEC returns a real activity value (not None).
        sec_insider = fetch_insider_data_from_sec(ticker)
        if sec_insider.get("insider_activity") is not None:
            result["insider_activity"] = sec_insider["insider_activity"]
            if sec_insider.get("insider_buying_amount_usd") is not None:
                result["insider_buying_amount_usd"] = sec_insider["insider_buying_amount_usd"]
            if sec_insider.get("notable_insider_transactions"):
                existing = result.get("notable_institutional_moves")
                sec_note = f"SEC Form 4 (90d): {sec_insider['notable_insider_transactions']}"
                result["notable_institutional_moves"] = (
                    f"{existing}; {sec_note}" if existing else sec_note
                )
            print(
                f"[Sentiment/SEC] {ticker}: insider={sec_insider['insider_activity']} "
                f"bought=${sec_insider.get('insider_buying_amount_usd') or 0:,.0f} "
                f"txns={sec_insider.get('insider_transaction_count_90d', 0)}"
            )

        return result

    except Exception as e:
        print(f"[Sentiment] fetch_sentiment_data failed for {ticker}: {e}")
        return defaults


# ---------------------------------------------------------------------------
# Section 2 — Pillar scoring helpers
# ---------------------------------------------------------------------------

def score_news_pillar(sentiment_data: dict) -> dict:
    """Pillar 1: News flow and media sentiment signal."""
    overall = sentiment_data.get("news_sentiment_overall", "neutral")
    volume = sentiment_data.get("news_volume", "normal")
    catalyst_type = sentiment_data.get("catalyst_type")

    if overall == "very_positive":
        news_signal = "bullish"
    elif overall == "positive":
        news_signal = "bullish" if volume in ("high", "normal") else "neutral"
    elif overall == "negative":
        # Legal/regulatory negatives are harder bearish
        if catalyst_type == "negative" and volume == "high":
            news_signal = "bearish"
        else:
            news_signal = "cautious"
    elif overall == "very_negative":
        news_signal = "bearish"
    else:
        news_signal = "neutral"

    return {
        "news_signal": news_signal,
        "news_sentiment_overall": overall,
        "news_volume": volume,
        "major_catalyst": sentiment_data.get("major_catalyst"),
        "catalyst_type": catalyst_type,
    }


def score_analyst_pillar(sentiment_data: dict) -> dict:
    """Pillar 2: Analyst sentiment momentum signal."""
    consensus = sentiment_data.get("analyst_consensus", "hold")
    upgrades = sentiment_data.get("upgrades_60d") or 0
    downgrades = sentiment_data.get("downgrades_60d") or 0
    target_trend = sentiment_data.get("price_target_trend", "stable")
    vs_target = sentiment_data.get("current_price_vs_target", "at")

    net_upgrades = upgrades - downgrades

    if consensus in ("strong_buy", "buy") and target_trend == "rising" and vs_target == "below":
        analyst_signal = "bullish"
    elif consensus in ("strong_buy", "buy") and net_upgrades > 0:
        analyst_signal = "bullish"
    elif consensus in ("sell", "strong_sell") or (target_trend == "falling" and net_upgrades < 0):
        analyst_signal = "bearish"
    elif vs_target == "above" and target_trend != "rising":
        # Stock already above consensus target — limited upside priced in
        analyst_signal = "cautious"
    elif consensus == "hold" and target_trend == "stable":
        analyst_signal = "neutral"
    elif net_upgrades > 2:
        analyst_signal = "bullish"
    elif net_upgrades < -2:
        analyst_signal = "bearish"
    else:
        analyst_signal = "neutral"

    upgrade_ratio = None
    if upgrades + downgrades > 0:
        upgrade_ratio = round(upgrades / (upgrades + downgrades), 2)

    return {
        "analyst_signal": analyst_signal,
        "analyst_consensus": consensus,
        "upgrades_60d": upgrades,
        "downgrades_60d": downgrades,
        "upgrade_ratio": upgrade_ratio,
        "price_target_trend": target_trend,
        "current_price_vs_target": vs_target,
        "avg_price_target": sentiment_data.get("avg_price_target"),
    }


def score_management_pillar(sentiment_data: dict) -> dict:
    """Pillar 3: Earnings call tone and management signals."""
    guidance = sentiment_data.get("guidance_direction", "unknown")
    tone = sentiment_data.get("management_tone", "neutral")
    buyback = sentiment_data.get("buyback_announced", False)
    dividend = sentiment_data.get("dividend_change", "unknown")

    # Guidance is the primary signal — it is management committing to numbers
    if guidance in ("lowered", "withdrawn"):
        management_signal = "bearish"
    elif guidance == "raised" and tone in ("confident", "neutral"):
        management_signal = "bullish"
        if buyback:
            management_signal = "bullish"  # double confirmation
    elif guidance == "raised" and tone == "defensive":
        # Raised but defensive — cautious
        management_signal = "cautious"
    elif guidance == "maintained":
        if tone == "confident" and buyback:
            management_signal = "bullish"
        elif tone == "defensive":
            management_signal = "cautious"
        else:
            management_signal = "neutral"
    else:
        # guidance == "unknown"
        if tone == "confident" and buyback:
            management_signal = "bullish"
        elif tone == "defensive" or dividend == "cut":
            management_signal = "bearish"
        elif tone == "cautious":
            management_signal = "cautious"
        else:
            management_signal = "neutral"

    # Dividend cut is a hard bearish override unless guidance was raised
    if dividend == "cut" and management_signal not in ("bearish",):
        management_signal = "cautious"

    return {
        "management_signal": management_signal,
        "guidance_direction": guidance,
        "management_tone": tone,
        "buyback_announced": buyback,
        "dividend_change": dividend,
        "management_credibility_note": sentiment_data.get("management_credibility_note"),
    }


def score_insider_pillar(sentiment_data: dict) -> dict:
    """Pillar 4: Insider and institutional activity signal."""
    insider = sentiment_data.get("insider_activity", "none")
    buying_amount = sentiment_data.get("insider_buying_amount_usd") or 0
    inst_trend = sentiment_data.get("institutional_trend", "stable")
    short_pct = sentiment_data.get("short_interest_pct")
    short_trend = sentiment_data.get("short_interest_trend", "stable")

    # Insider activity is the most credible signal (skin in the game)
    if insider == "buying" and buying_amount >= 500_000:
        # Meaningful insider buying — strong bullish
        insider_signal = "bullish"
    elif insider == "buying" and buying_amount > 0:
        insider_signal = "bullish"
    elif insider == "buying":
        # Buying reported but amount unknown — mild bullish
        insider_signal = "bullish"
    elif insider == "selling":
        insider_signal = "cautious"  # not automatically bearish — could be diversification
    elif insider == "mixed":
        insider_signal = "neutral"
    else:
        insider_signal = "neutral"

    # Institutional trend modifier
    if inst_trend == "increasing" and insider_signal == "bullish":
        pass  # holds bullish
    elif inst_trend == "decreasing" and insider_signal in ("neutral", "cautious"):
        insider_signal = "cautious"
    elif inst_trend == "increasing" and insider_signal == "neutral":
        insider_signal = "bullish"

    # Short interest modifier
    if short_pct is not None:
        if short_pct > 15 and short_trend == "rising":
            # Heavy and growing short interest — market actively betting against
            if insider_signal == "bullish":
                insider_signal = "cautious"   # conflict — reduce to cautious
            elif insider_signal == "neutral":
                insider_signal = "cautious"
        elif short_pct > 15 and short_trend == "falling":
            # High short interest unwinding — potential short squeeze tailwind
            if insider_signal in ("neutral", "cautious"):
                insider_signal = "bullish"

    return {
        "insider_signal": insider_signal,
        "insider_activity": insider,
        "insider_buying_amount_usd": buying_amount if buying_amount else None,
        "institutional_trend": inst_trend,
        "short_interest_pct": short_pct,
        "short_interest_trend": short_trend,
        "notable_institutional_moves": sentiment_data.get("notable_institutional_moves"),
    }


def score_pillars(sentiment_data: dict) -> dict:
    """
    Evaluate all 4 sentiment pillars and compute overall_signal + data_quality.
    Weighted vote:
      management (2x) + insider (1.5x → 3 votes of 2) + analyst (1x) + news (1x)
    Total = 6 votes. Rounds to nearest: management=2, insider=2, analyst=1, news=1.
    """
    news = score_news_pillar(sentiment_data)
    analyst = score_analyst_pillar(sentiment_data)
    management = score_management_pillar(sentiment_data)
    insider = score_insider_pillar(sentiment_data)

    news_signal = news["news_signal"]
    analyst_signal = analyst["analyst_signal"]
    management_signal = management["management_signal"]
    insider_signal = insider["insider_signal"]

    # Weighted vote: management 2x, insider 2x (rounds 1.5x up), analyst 1x, news 1x
    weighted_signals = [
        management_signal, management_signal,   # 2x weight
        insider_signal, insider_signal,          # 2x weight (closest to 1.5x with integers)
        analyst_signal,                          # 1x weight
        news_signal,                             # 1x weight
    ]

    counts: dict[str, int] = {}
    for s in weighted_signals:
        counts[s] = counts.get(s, 0) + 1

    max_count = max(counts.values())
    majority_candidates = [s for s, c in counts.items() if c == max_count]

    if len(majority_candidates) == 1:
        overall_signal = majority_candidates[0]
    elif "neutral" in majority_candidates:
        overall_signal = "neutral"
    else:
        overall_signal = majority_candidates[0]

    # Hard overrides for the most credible signals
    guidance = sentiment_data.get("guidance_direction")
    insider_buying = sentiment_data.get("insider_buying_amount_usd") or 0

    # Lowered/withdrawn guidance is a near-certain bearish signal
    if guidance in ("lowered", "withdrawn") and overall_signal == "bullish":
        overall_signal = "cautious"

    # Large insider buying (> $1M) is a near-certain bullish signal
    if insider_buying >= 1_000_000 and overall_signal in ("bearish",):
        overall_signal = "cautious"  # at least cautious, not outright bearish

    # Data quality
    indicators = [
        sentiment_data.get("news_sentiment_overall") not in (None, "neutral"),
        sentiment_data.get("analyst_consensus") not in (None, "hold"),
        sentiment_data.get("upgrades_60d") is not None,
        sentiment_data.get("guidance_direction") not in (None, "unknown"),
        sentiment_data.get("management_tone") not in (None, "neutral"),
        sentiment_data.get("insider_activity") not in (None, "none"),
        sentiment_data.get("institutional_trend") not in (None, "stable"),
        sentiment_data.get("short_interest_pct") is not None,
    ]
    data_points_available = sum(1 for v in indicators if v)
    data_quality = round(data_points_available / len(indicators), 2)

    return {
        # Signals
        "news_signal": news_signal,
        "analyst_signal": analyst_signal,
        "management_signal": management_signal,
        "insider_signal": insider_signal,
        "overall_signal": overall_signal,
        # News details
        "news_sentiment_overall": news["news_sentiment_overall"],
        "news_volume": news["news_volume"],
        "major_catalyst": news["major_catalyst"],
        "catalyst_type": news["catalyst_type"],
        # Analyst details
        "analyst_consensus": analyst["analyst_consensus"],
        "upgrades_60d": analyst["upgrades_60d"],
        "downgrades_60d": analyst["downgrades_60d"],
        "upgrade_ratio": analyst["upgrade_ratio"],
        "price_target_trend": analyst["price_target_trend"],
        "current_price_vs_target": analyst["current_price_vs_target"],
        "avg_price_target": analyst["avg_price_target"],
        # Management details
        "guidance_direction": management["guidance_direction"],
        "management_tone": management["management_tone"],
        "buyback_announced": management["buyback_announced"],
        "dividend_change": management["dividend_change"],
        "management_credibility_note": management["management_credibility_note"],
        # Insider details
        "insider_activity": insider["insider_activity"],
        "insider_buying_amount_usd": insider["insider_buying_amount_usd"],
        "institutional_trend": insider["institutional_trend"],
        "short_interest_pct": insider["short_interest_pct"],
        "short_interest_trend": insider["short_interest_trend"],
        "notable_institutional_moves": insider["notable_institutional_moves"],
        "data_quality": data_quality,
    }


# ---------------------------------------------------------------------------
# Section 3 — LLM reasoning
# ---------------------------------------------------------------------------

def _build_peer_context(state: ThesisState) -> str:
    """
    Reads what other agents have already written to the whiteboard.
    Prioritises raw_outputs (full findings) over agent_signals (structured only).
    Sentiment stays in its lane — never comment on P/E, DCF, leverage, or momentum.
    """
    raw_outputs = state.get("raw_outputs", {})
    agent_signals = state.get("agent_signals", {})

    if not raw_outputs and not agent_signals:
        return ""

    lines = []

    for agent_name, findings_text in raw_outputs.items():
        if agent_name == "sentiment":
            continue
        lines.append(f"[{agent_name.upper()} — full findings]\n{findings_text}\n")

    for agent_name, signal in agent_signals.items():
        if agent_name == "sentiment":
            continue
        if agent_name in raw_outputs:
            continue
        lines.append(
            f"[{agent_name.upper()} — signal only] "
            f"{signal['view']} ({signal['confidence']:.0%}) — {signal['reasoning']}"
        )

    if not lines:
        return ""

    return (
        "Other analysts have already written their findings on the whiteboard:\n\n"
        + "\n".join(lines)
        + "\nIMPORTANT: Your view is about HUMAN CONVICTION — news, analyst opinion, "
        "management signals, and insider behaviour. Do not comment on P/E, DCF, "
        "leverage, or momentum — those belong to other agents. "
        "Use peer context to assess whether sentiment supports or contradicts "
        "the committee's emerging thesis. "
        "If fundamental sees value but insiders are selling, flag that conflict explicitly. "
        "If quant sees positive momentum and you see analyst upgrades, note the corroboration."
    )


def run_llm_reasoning(
    ticker: str,
    pillar_scores: dict,
    sentiment_data: dict,
    conflicts: list,
    state: ThesisState,
) -> AgentSignal:
    """
    Single Haiku call to reason over sentiment pillar results and produce AgentSignal.
    Falls back to pillar majority on any error.
    """
    conflict_context = ""
    if conflicts:
        desc_list = [c.get("description", "") for c in conflicts if "sentiment" in c.get("agents", [])]
        if desc_list:
            conflict_context = (
                "\nThe investment committee has flagged these conflicts:\n"
                + "\n".join(f"- {d}" for d in desc_list)
                + "\nFactor this into your confidence."
            )

    peer_context = _build_peer_context(state)

    def _fmtv(val, suffix="", fallback="N/A"):
        if val is None or val == "":
            return fallback
        try:
            if isinstance(val, float):
                return f"{val:,.0f}{suffix}" if abs(val) >= 1000 else f"{val:.1f}{suffix}"
            return f"{val}{suffix}"
        except (TypeError, ValueError):
            return fallback

    upgrades = pillar_scores.get("upgrades_60d") or 0
    downgrades = pillar_scores.get("downgrades_60d") or 0
    buying_usd = pillar_scores.get("insider_buying_amount_usd")
    buying_str = f"${buying_usd:,.0f}" if buying_usd else "N/A"
    short_pct = pillar_scores.get("short_interest_pct")
    short_str = f"{short_pct:.1f}%" if short_pct is not None else "N/A"

    prompt = f"""You are a Sentiment Analyst at a hedge fund investment committee.
Your job is to read the human narrative around {ticker} —
news flow, analyst opinion, management signals, and insider behaviour.
You capture what financials and price charts cannot: conviction.
Never comment on P/E, DCF, leverage, or price momentum.

4-pillar sentiment analysis:

- News flow:              {pillar_scores['news_signal']}
  (Overall: {pillar_scores.get('news_sentiment_overall', 'N/A')}, Volume: {pillar_scores.get('news_volume', 'N/A')})
  Major catalyst: {pillar_scores.get('major_catalyst') or 'None identified'}

- Analyst sentiment:      {pillar_scores['analyst_signal']}
  (Consensus: {pillar_scores.get('analyst_consensus', 'N/A')}, Upgrades/Downgrades 60d: {upgrades}/{downgrades},
   Price target trend: {pillar_scores.get('price_target_trend', 'N/A')}, Stock vs avg target: {pillar_scores.get('current_price_vs_target', 'N/A')})

- Management signals:     {pillar_scores['management_signal']}
  (Guidance: {pillar_scores.get('guidance_direction', 'N/A')}, Tone: {pillar_scores.get('management_tone', 'N/A')},
   Buyback: {pillar_scores.get('buyback_announced', False)}, Dividend: {pillar_scores.get('dividend_change', 'N/A')})

- Insider & institutional: {pillar_scores['insider_signal']}
  (Insider activity: {pillar_scores.get('insider_activity', 'N/A')}, Amount: {buying_str},
   Institutional trend: {pillar_scores.get('institutional_trend', 'N/A')},
   Short interest: {short_str} — {pillar_scores.get('short_interest_trend', 'N/A')})
  Notable: {pillar_scores.get('notable_institutional_moves') or 'None'}

Data quality: {pillar_scores['data_quality']:.0%} of sentiment indicators available.
{peer_context}
{conflict_context}

Key principle: your view is about HUMAN CONVICTION, not intrinsic value.
Insider buying at scale is the single most credible bullish signal.
Management lowering guidance is the single most credible bearish signal.
Treat these as near-overrides unless other pillars strongly disagree.

Respond with ONLY a JSON object — no preamble, no markdown:
{{
  "view": "bullish" | "bearish" | "neutral" | "cautious",
  "reasoning": "one sentence citing the most credible sentiment signal with specifics",
  "confidence": 0.0 to 1.0
}}

Confidence calibration:
- 3 or 4 pillars agree AND fresh data → 0.72–0.90
- 2 pillars agree → 0.50–0.71
- Pillars conflict → 0.35–0.50
- Insider buying > $1M is a confidence floor 0.70 for bullish view
- Guidance lowered is a confidence floor 0.68 for bearish/cautious view
- Stale or unavailable data → cap confidence at 0.55
- Always cite the single most decisive data point in your reasoning"""

    try:
        client = Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)
        view = str(parsed.get("view", "")).lower().strip()
        if view not in VALID_VIEWS:
            view = pillar_scores["overall_signal"]

        confidence = float(parsed.get("confidence", 0.5))
        confidence = round(min(max(confidence, 0.0), 1.0), 2)

        # Enforce confidence floors for the most credible signals
        buying_amt = sentiment_data.get("insider_buying_amount_usd") or 0
        guidance = sentiment_data.get("guidance_direction", "unknown")
        if buying_amt >= 1_000_000 and view == "bullish":
            confidence = max(confidence, 0.70)
        if guidance in ("lowered", "withdrawn") and view in ("bearish", "cautious"):
            confidence = max(confidence, 0.68)
        if pillar_scores.get("data_quality", 1.0) < 0.4:
            confidence = min(confidence, 0.55)

        return {
            "view": view,
            "reasoning": str(parsed.get("reasoning", "Sentiment analysis complete.")),
            "confidence": confidence,
        }

    except Exception as e:
        print(f"[Sentiment] run_llm_reasoning failed: {e}")
        return {
            "view": pillar_scores["overall_signal"],
            "reasoning": f"LLM parse failed — pillar majority: {pillar_scores['overall_signal']}",
            "confidence": 0.45,
        }


# ---------------------------------------------------------------------------
# Section 4 — Level 3: Agent-to-agent Q&A helpers
# ---------------------------------------------------------------------------

def _read_questions(agent_name: str, state: ThesisState) -> dict:
    """Returns {asking_agent: question_text} for questions addressed to agent_name."""
    all_questions = state.get("agent_questions", {})
    return {
        asker: targets[agent_name]
        for asker, targets in all_questions.items()
        if agent_name in targets
    }


def _build_answer_context(questions: dict) -> str:
    """Formats incoming questions for injection into the LLM prompt. Returns '' if none."""
    if not questions:
        return ""
    lines = ["DIRECT QUESTIONS FROM COMMITTEE MEMBERS — answer these in your reasoning:"]
    for asker, question in questions.items():
        lines.append(f"  [{asker.upper()} asks]: {question}")
    return "\n".join(lines)


def _extract_answers(
    agent_name: str,
    questions: dict,
    signal: AgentSignal,
    pillar_scores: dict,
    state: ThesisState,
) -> dict:
    """
    For each incoming question, makes a Haiku call to produce a grounded answer.
    Returns the full updated agent_answers dict (carry-forward pattern).
    """
    existing_answers = dict(state.get("agent_answers", {}))
    if not questions:
        return existing_answers

    answers_for_this_agent = {}
    client = Anthropic()

    for asking_agent, question in questions.items():
        prompt = (
            f"You are the {agent_name} analyst. A colleague ({asking_agent}) asked:\n"
            f'"{question}"\n\n'
            f"Your signal: {signal['view']} ({signal['confidence']:.0%} confidence)\n"
            f"Your findings: {json.dumps(pillar_scores, default=str)}\n\n"
            f"Answer in 1-2 sentences using specific numbers. Be direct."
        )
        try:
            response = client.messages.create(
                model=HAIKU_MODEL, max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            answers_for_this_agent[asking_agent] = response.content[0].text.strip()
        except Exception as e:
            print(f"[{agent_name.capitalize()}] _extract_answers error: {e}")
            answers_for_this_agent[asking_agent] = "Answer unavailable — see full findings."

    existing_answers[agent_name] = answers_for_this_agent
    return existing_answers


def _generate_question(
    agent_name: str,
    pillar_scores: dict,
    signal: AgentSignal,
    state: ThesisState,
) -> dict:
    """
    If confidence < 0.70 and conditions allow, asks QUESTION_TARGET one question.
    Returns the full updated agent_questions dict (carry-forward pattern).

    Guards (all must pass):
      1. confidence < 0.70
      2. agent_name not already in agent_questions (no repeat questions)
      3. QUESTION_TARGET has produced raw_outputs
    """
    existing_questions = dict(state.get("agent_questions", {}))

    if signal.get("confidence", 1.0) >= 0.70:
        return existing_questions
    if agent_name in existing_questions:
        return existing_questions
    if QUESTION_TARGET not in state.get("raw_outputs", {}):
        return existing_questions

    prompt = (
        f"You are the {agent_name} analyst with a {signal['view']} view at "
        f"{signal['confidence']:.0%} confidence — below your comfort threshold.\n"
        f"Write ONE specific question (1 sentence) for the {QUESTION_TARGET} analyst "
        f"that would most reduce your uncertainty. Cite exact metrics you need.\n"
        f"Your findings: {json.dumps(pillar_scores, default=str)}\n\n"
        f"If you have no genuinely useful question, respond exactly: NO_QUESTION"
    )
    try:
        client = Anthropic()
        response = client.messages.create(
            model=HAIKU_MODEL, max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        question_text = response.content[0].text.strip()
        if question_text != "NO_QUESTION" and len(question_text) >= 10:
            existing_questions[agent_name] = {QUESTION_TARGET: question_text}
    except Exception as e:
        print(f"[{agent_name.capitalize()}] _generate_question error: {e}")

    return existing_questions


# ---------------------------------------------------------------------------
# Section 5 — Main entry point
# ---------------------------------------------------------------------------

def run_sentiment_agent(state: ThesisState) -> dict:
    """
    Main entry point called by arena/agents.py.
    Fetches sentiment data, runs 4-pillar analysis, returns AgentSignal.
    Always returns — never crashes the arena.
    """
    ticker = state.get("ticker", "")
    conflicts = state.get("conflicts", [])

    print(f"[Sentiment] Starting analysis for {ticker}")

    from arena.progress import emit_arena_event as _emit
    _emit({"type": "arena_agent_start", "agent": "sentiment", "round": state.get("round", 0) + 1})

    try:
        company_info = fetch_company_context(ticker)

        print(f"[Sentiment] Fetching sentiment data for {ticker}")
        sentiment_data = fetch_sentiment_data(ticker)

        pillar_scores = score_pillars(sentiment_data)

        print(
            f"[Sentiment] Pillars: news={pillar_scores['news_signal']} "
            f"analyst={pillar_scores['analyst_signal']} "
            f"management={pillar_scores['management_signal']} "
            f"insider={pillar_scores['insider_signal']} "
            f"→ overall={pillar_scores['overall_signal']} "
            f"data_quality={pillar_scores['data_quality']:.0%}"
        )

        signal: AgentSignal = run_llm_reasoning(
            ticker, pillar_scores, sentiment_data, conflicts, state
        )

        # Level 3: Q&A
        incoming_questions = _read_questions("sentiment", state)
        updated_questions = _generate_question("sentiment", pillar_scores, signal, state)
        updated_answers = _extract_answers("sentiment", incoming_questions, signal, pillar_scores, state)

        buying_usd = sentiment_data.get("insider_buying_amount_usd")
        buying_str = f"${buying_usd:,.0f}" if buying_usd else "N/A"
        short_pct = sentiment_data.get("short_interest_pct")
        short_str = f"{short_pct:.1f}%" if short_pct is not None else "N/A"

        raw_findings = (
            f"SENTIMENT ANALYSIS — {ticker}\n"
            f"News: {pillar_scores.get('news_signal')} | "
            f"Overall={sentiment_data.get('news_sentiment_overall', 'N/A')} | "
            f"Volume={sentiment_data.get('news_volume', 'N/A')}\n"
            f"Catalyst: {sentiment_data.get('major_catalyst') or 'None'}\n"
            f"Analysts: {pillar_scores.get('analyst_signal')} | "
            f"Consensus={sentiment_data.get('analyst_consensus', 'N/A')} | "
            f"Upgrades/Downgrades={sentiment_data.get('upgrades_60d', 'N/A')}/"
            f"{sentiment_data.get('downgrades_60d', 'N/A')} | "
            f"Target trend={sentiment_data.get('price_target_trend', 'N/A')} | "
            f"vs target={sentiment_data.get('current_price_vs_target', 'N/A')}\n"
            f"Management: {pillar_scores.get('management_signal')} | "
            f"Guidance={sentiment_data.get('guidance_direction', 'N/A')} | "
            f"Tone={sentiment_data.get('management_tone', 'N/A')} | "
            f"Buyback={sentiment_data.get('buyback_announced', False)} | "
            f"Dividend={sentiment_data.get('dividend_change', 'N/A')}\n"
            f"Insider: {pillar_scores.get('insider_signal')} | "
            f"Activity={sentiment_data.get('insider_activity', 'N/A')} | "
            f"Amount={buying_str} | "
            f"Institutional={sentiment_data.get('institutional_trend', 'N/A')} | "
            f"Short interest={short_str} ({sentiment_data.get('short_interest_trend', 'N/A')})\n"
            f"Notable: {sentiment_data.get('notable_institutional_moves') or 'None'}\n"
            f"Final view: {signal['view']} ({signal['confidence']:.0%} confidence)\n"
            f"Reasoning: {signal['reasoning']}"
        )

        if incoming_questions:
            qa_lines = ["\nQUESTIONS ANSWERED:"]
            my_answers = updated_answers.get("sentiment", {})
            for asker, q in incoming_questions.items():
                qa_lines.append(f"  [{asker.upper()} asked]: {q}")
                qa_lines.append(f"  [Answer]: {my_answers.get(asker, 'No answer generated.')}")
            raw_findings += "\n".join(qa_lines)

        if "sentiment" in updated_questions:
            tgt = list(updated_questions["sentiment"].keys())[0]
            raw_findings += f"\nOPEN QUESTION TO {tgt.upper()}: {updated_questions['sentiment'][tgt]}"

    except Exception as e:
        print(f"[Sentiment] Unhandled error for {ticker}: {e}")
        signal = {
            "view": "neutral",
            "reasoning": f"Analysis incomplete — data error: {str(e)[:80]}",
            "confidence": 0.30,
        }
        raw_findings = f"SENTIMENT ANALYSIS — {ticker}\nError: {str(e)[:120]}"
        updated_questions = dict(state.get("agent_questions", {}))
        updated_answers = dict(state.get("agent_answers", {}))

    print(f"[Sentiment] Signal: view={signal['view']} confidence={signal['confidence']}")

    from arena.progress import emit_arena_event
    emit_arena_event({
        "type": "arena_agent_done",
        "agent": "sentiment",
        "view": signal["view"],
        "confidence": signal["confidence"],
        "reasoning": signal["reasoning"],
    })

    existing_raw = dict(state.get("raw_outputs", {}))
    existing_raw["sentiment"] = raw_findings

    return {
        "agent_signals":   {"sentiment": signal},
        "raw_outputs":     existing_raw,
        "agent_questions": updated_questions,
        "agent_answers":   updated_answers,
    }
