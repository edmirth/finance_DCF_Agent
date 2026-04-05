#!/usr/bin/env python3
"""
Finance Agent Data Monitor & Evaluator
=======================================
Terminal tool to inspect data sources, agent data flows, and live agent execution.

Modes:
  health          Check all API health, keys, quotas, and latency
  flow            Visualize data flow architecture for every agent
  eval  TICKER    Fetch real data from each source and show quality/structure
  monitor TICKER  Run an agent with live instrumentation showing every data call
  test  TICKER    Full earnings data integrity test — shows actual data content,
                  detects fallbacks, and scores completeness

Usage:
  python eval_monitor.py health
  python eval_monitor.py flow
  python eval_monitor.py eval AAPL
  python eval_monitor.py eval AAPL --agent analyst
  python eval_monitor.py monitor AAPL --agent analyst
  python eval_monitor.py monitor AAPL --agent earnings
  python eval_monitor.py test AAPL
  python eval_monitor.py test NVDA
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap
# ─────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

# Suppress noisy library logs during monitoring
for _noisy in ("httpx", "httpcore", "openai", "anthropic", "langchain", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.CRITICAL)
logging.getLogger().setLevel(logging.CRITICAL)

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskID,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
    from rich.tree import Tree
except ImportError:
    print("Missing dependency: pip install rich>=13.0.0")
    sys.exit(1)

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    """Result of a single health/eval check."""
    api: str
    status: str          # "ok" | "warning" | "error" | "skip"
    latency_ms: Optional[float]
    detail: str
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def icon(self) -> str:
        return {"ok": "[green]✓[/]", "warning": "[yellow]⚠[/]",
                "error": "[red]✗[/]", "skip": "[dim]─[/]"}.get(self.status, "?")

    @property
    def color(self) -> str:
        return {"ok": "green", "warning": "yellow", "error": "red", "skip": "dim"}.get(self.status, "white")


@dataclass
class CallRecord:
    """Records a single instrumented data-layer call during monitor mode."""
    ts: float
    tool: str
    api: str
    status: str          # "ok" | "error" | "cache"
    latency_ms: float
    detail: str


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_ms(ms: Optional[float]) -> str:
    if ms is None:
        return "N/A"
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms/1000:.2f}s"


def _fmt_num(n: Optional[float]) -> str:
    if n is None:
        return "N/A"
    if abs(n) >= 1e12:
        return f"${n/1e12:.2f}T"
    if abs(n) >= 1e9:
        return f"${n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"${n/1e6:.2f}M"
    return f"${n:,.0f}"


def _key_status(env_var: str) -> tuple[str, str]:
    """Returns (status, display_value) for an API key."""
    val = os.environ.get(env_var, "")
    if not val:
        return "missing", "[red]NOT SET[/]"
    masked = val[:6] + "…" + val[-3:] if len(val) > 12 else val[:4] + "…"
    return "ok", f"[green]{masked}[/]"


def _http_get(url: str, headers: Dict = None, params: Dict = None, timeout: int = 10) -> tuple[int, Optional[Dict]]:
    """Simple HTTP GET, returns (status_code, json_body_or_none)."""
    try:
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
        try:
            body = r.json()
        except Exception:
            body = None
        return r.status_code, body
    except requests.Timeout:
        return -1, None
    except requests.ConnectionError:
        return -2, None
    except Exception:
        return -3, None


# ─────────────────────────────────────────────────────────────────────────────
# 1.  HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────

class HealthChecker:
    """Check every external API used by the agent system."""

    def run_all(self) -> List[CheckResult]:
        checks = [
            self._check_financial_datasets,
            self._check_sec_edgar,
            self._check_fmp,
            self._check_tavily,
            self._check_fred,
            self._check_anthropic,
        ]
        results: List[CheckResult] = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("Checking APIs…", total=len(checks))
            for fn in checks:
                r = fn()
                results.append(r)
                progress.advance(task)
        return results

    # ── individual checks ────────────────────────────────────────────────────

    def _check_financial_datasets(self) -> CheckResult:
        api = "Financial Datasets AI"
        key = os.environ.get("FINANCIAL_DATASETS_API_KEY", "")
        if not key:
            return CheckResult(api, "skip", None, "FINANCIAL_DATASETS_API_KEY not set")

        t0 = time.time()
        code, body = _http_get(
            "https://api.financialdatasets.ai/company/facts",
            headers={"X-API-KEY": key},
            params={"ticker": "AAPL"},
        )
        lat = (time.time() - t0) * 1000

        if code == 200 and body:
            name = body.get("company_facts", {}).get("name", "Unknown")
            return CheckResult(api, "ok", lat, f"Authenticated · {name}", {"endpoint": "/company/facts"})
        if code == 401:
            return CheckResult(api, "error", lat, "Invalid API key (401)")
        if code == 402:
            return CheckResult(api, "warning", lat, "Quota exceeded (402)")
        if code == -1:
            return CheckResult(api, "error", None, "Request timed out (>10s)")
        if code == -2:
            return CheckResult(api, "error", None, "Connection failed")
        return CheckResult(api, "error", lat, f"HTTP {code}")

    def _check_sec_edgar(self) -> CheckResult:
        api = "SEC EDGAR"
        t0 = time.time()
        code, body = _http_get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "FinanceDCFAgent research@finance-agent.com"},
            timeout=15,
        )
        lat = (time.time() - t0) * 1000

        if code == 200 and body:
            count = len(body)
            return CheckResult(api, "ok", lat, f"No API key needed · {count:,} tickers in CIK map",
                               {"tickers": count})
        if code == 429:
            return CheckResult(api, "warning", lat, "Rate limited — 5 req/s max")
        if code == -1:
            return CheckResult(api, "error", None, "Request timed out (>15s)")
        return CheckResult(api, "error", lat, f"HTTP {code}")

    def _check_fmp(self) -> CheckResult:
        api = "FMP (Financial Modeling Prep)"
        key = os.environ.get("FMP_API_KEY", "")
        if not key:
            return CheckResult(api, "skip", None, "FMP_API_KEY not set — optional premium source")

        t0 = time.time()
        code, body = _http_get(
            "https://financialmodelingprep.com/stable/batch-quote",
            params={"symbols": "AAPL", "apikey": key},
        )
        lat = (time.time() - t0) * 1000

        if code == 200 and body:
            if isinstance(body, list) and body:
                price = body[0].get("price", "N/A")
                return CheckResult(api, "ok", lat, f"Authenticated · AAPL ${price}")
            return CheckResult(api, "warning", lat, "Auth OK but empty response")
        if code in (401, 403):
            return CheckResult(api, "error", lat, f"Invalid API key ({code})")
        if code == 402:
            return CheckResult(api, "warning", lat, "Premium subscription required for this endpoint")
        return CheckResult(api, "error", lat, f"HTTP {code}")

    def _check_tavily(self) -> CheckResult:
        api = "Tavily Search"
        key = os.environ.get("TAVILY_API_KEY", "")
        if not key:
            return CheckResult(api, "skip", None, "TAVILY_API_KEY not set — web search unavailable")

        try:
            from tavily import TavilyClient
            t0 = time.time()
            client = TavilyClient(api_key=key)
            result = client.search("Apple Inc stock beta 2025", max_results=1)
            lat = (time.time() - t0) * 1000
            if result:
                n = len(result.get("results", []))
                return CheckResult(api, "ok", lat, f"Search OK · {n} result(s) returned")
            return CheckResult(api, "warning", lat, "Auth OK but empty results")
        except Exception as e:
            msg = str(e)[:80]
            if "API key" in msg or "401" in msg or "unauthorized" in msg.lower():
                return CheckResult(api, "error", None, f"Invalid API key: {msg}")
            return CheckResult(api, "error", None, f"Error: {msg}")

    def _check_fred(self) -> CheckResult:
        api = "FRED (Federal Reserve)"
        key = os.environ.get("FRED_API_KEY", "")
        if not key:
            return CheckResult(api, "skip", None, "FRED_API_KEY not set — treasury rate fetching disabled")

        try:
            import fredapi
            t0 = time.time()
            fred = fredapi.Fred(api_key=key)
            series = fred.get_series("DGS10")
            lat = (time.time() - t0) * 1000
            latest = float(series.dropna().iloc[-1])
            return CheckResult(api, "ok", lat, f"10-Year Treasury (DGS10): {latest:.2f}%")
        except Exception as e:
            msg = str(e)[:80]
            if "api_key" in msg.lower() or "Bad Request" in msg:
                return CheckResult(api, "error", None, f"Invalid API key")
            return CheckResult(api, "warning", None, f"Error: {msg}")

    def _check_anthropic(self) -> CheckResult:
        api = "Anthropic (LLM backbone)"
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return CheckResult(api, "error", None, "ANTHROPIC_API_KEY not set — agents cannot run")
        # Don't make a real API call (cost); just verify key format
        if not key.startswith("sk-ant-"):
            return CheckResult(api, "warning", None, "Key set but unusual format — verify it")
        masked = key[:12] + "…"
        return CheckResult(api, "ok", None, f"Key present ({masked}) — format OK, not tested")


def show_health(results: List[CheckResult]) -> None:
    """Render health check results to the terminal."""
    console.print()
    console.rule("[bold cyan]API Health Check[/bold cyan]")
    console.print()

    # Config table
    cfg_table = Table(title="Environment Configuration", box=box.ROUNDED, border_style="cyan",
                      show_header=True, header_style="bold cyan")
    cfg_table.add_column("Variable", style="bold")
    cfg_table.add_column("Status")
    cfg_table.add_column("Value (masked)")

    env_vars = [
        ("FINANCIAL_DATASETS_API_KEY", "Financial Datasets AI"),
        ("FMP_API_KEY",                 "FMP (optional premium)"),
        ("TAVILY_API_KEY",              "Tavily Search"),
        ("FRED_API_KEY",                "FRED Treasury rates"),
        ("ANTHROPIC_API_KEY",           "Anthropic LLM"),
        ("OPENAI_API_KEY",              "OpenAI (optional)"),
    ]
    for var, label in env_vars:
        status, display = _key_status(var)
        icon = "[green]✓[/]" if status == "ok" else "[red]✗[/]"
        cfg_table.add_row(var, f"{icon} {label}", display)

    console.print(cfg_table)
    console.print()

    # Health results table
    h_table = Table(title="Live API Status", box=box.ROUNDED, border_style="cyan",
                    show_header=True, header_style="bold cyan")
    h_table.add_column("API", style="bold", min_width=30)
    h_table.add_column("Status", justify="center", min_width=12)
    h_table.add_column("Latency", justify="right", min_width=10)
    h_table.add_column("Details")

    for r in results:
        status_text = {
            "ok":      "[bold green]● ONLINE[/]",
            "warning": "[bold yellow]◐ DEGRADED[/]",
            "error":   "[bold red]○ FAILED[/]",
            "skip":    "[dim]– SKIPPED[/]",
        }.get(r.status, r.status)
        h_table.add_row(r.api, status_text, _fmt_ms(r.latency_ms), r.detail)

    console.print(h_table)
    console.print()

    # Summary
    ok  = sum(1 for r in results if r.status == "ok")
    warn = sum(1 for r in results if r.status == "warning")
    err  = sum(1 for r in results if r.status == "error")
    skip = sum(1 for r in results if r.status == "skip")
    console.print(
        f"  [green]✓ {ok} online[/]  [yellow]⚠ {warn} degraded[/]  "
        f"[red]✗ {err} failed[/]  [dim]─ {skip} skipped[/]"
    )
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# 2.  DATA FLOW VISUALIZATION
# ─────────────────────────────────────────────────────────────────────────────

# Static definition of each agent's data flow
AGENT_FLOWS = {
    "analyst": {
        "label": "Equity Analyst Agent (ReAct)",
        "description": "Comprehensive equity research report",
        "llm_calls": "8–12 (per ReAct iteration)",
        "steps": [
            ("get_stock_info",       "Financial Datasets AI",  "Company overview & business model"),
            ("analyze_industry",     "Tavily Search + LLM",    "TAM, Porter's 5 Forces, regulation"),
            ("analyze_competitors",  "Tavily Search + LLM",    "Top 3-5 rivals, market share"),
            ("analyze_moat",         "Tavily Search + LLM",    "Brand, network effects, switching costs"),
            ("get_financial_metrics","Financial Datasets AI",  "Full financial history"),
            ("search_web",           "Tavily Search",          "Management quality, recent news"),
            ("get_sec_filings",      "SEC EDGAR",              "10-K / 10-Q filings"),
            ("analyze_sec_filing",   "SEC EDGAR + LLM",        "Risk factors, MD&A highlights"),
        ],
        "fallbacks": ["SEC EDGAR → plain text fallback if XBRL unavailable"],
        "output": "Full equity research report with recommendation",
    },
    "earnings": {
        "label": "Earnings Agent (LangGraph 9-node)",
        "description": "Earnings trends, surprises, transcripts, and peer comparison",
        "llm_calls": 2,
        "steps": [
            ("fetch_company_info",   "Financial Datasets AI",  "Price, sector, market cap  [Node 1]"),
            ("fetch_earnings_history","Financial Datasets AI", "Revenue, EPS, margins (quarterly)  [Node 2 ‖]"),
            ("fetch_analyst_estimates","Financial Datasets AI","Forward EPS/revenue forecasts  [Node 3 ‖]"),
            ("fetch_surprises_and_insights","FMP → Tavily",     "Actual vs. estimates + call transcripts  [Node 4 ‖]"),
            ("fetch_sec_filings",    "SEC EDGAR",              "10-Q / 10-K summaries  [Node 5 ‖]"),
            ("aggregate",            "—",                      "Sync point — waits for all parallel nodes  [Node 6]"),
            ("analyze",              "Anthropic LLM",          "Trend & quality analysis  [Node 7]"),
            ("investment_thesis",    "Anthropic LLM",          "BUY/HOLD/SELL + price target  [Node 8]"),
            ("format_report",        "—",                      "Final formatted report  [Node 9]"),
        ],
        "fallbacks": [
            "Earnings transcripts: FMP → Tavily web search",
        ],
        "output": "Earnings analysis + BUY/HOLD/SELL rating + price target",
    },
    "graph": {
        "label": "LangGraph Equity Analyst (10-step)",
        "description": "Deterministic structured equity research workflow",
        "llm_calls": 10,
        "steps": [
            ("company_info",         "Financial Datasets AI",  "Facts, sector, price  [Step 1]"),
            ("financials",           "Financial Datasets AI",  "5Y financial history  [Step 2]"),
            ("industry",             "Tavily Search + LLM",    "Market size, competitive dynamics  [Step 3]"),
            ("competitors",          "Tavily Search + LLM",    "Peer analysis  [Step 4]"),
            ("moat",                 "Tavily Search + LLM",    "Competitive advantage assessment  [Step 5]"),
            ("management",           "Tavily Search + LLM",    "Leadership quality  [Step 6]"),
            ("thesis",               "Anthropic LLM",          "Investment thesis  [Step 7]"),
            ("recommendation",       "Anthropic LLM",          "Final rating + price target  [Step 8]"),
            ("report",               "—",                      "Format & output  [Step 9]"),
        ],
        "fallbacks": [],
        "output": "Structured equity research report (reproducible)",
    },
    "market": {
        "label": "Market Agent (ReAct)",
        "description": "Market conditions, regime, sentiment, sector rotation",
        "llm_calls": "2–4",
        "steps": [
            ("get_market_overview",  "FMP Market Data",        "Indices, VIX, breadth"),
            ("analyze_sector",       "FMP Market Data",        "Sector ETF performance"),
            ("classify_market_regime","Internal algorithm",    "BULL/BEAR/NEUTRAL scoring"),
            ("get_market_news",      "Tavily Search",          "Latest market-moving news"),
        ],
        "fallbacks": ["Massive.com → FMP fallback for market data"],
        "output": "Market regime + risk mode + sector allocation",
    },
    "portfolio": {
        "label": "Portfolio Agent (ReAct)",
        "description": "Portfolio performance, diversification, tax optimization",
        "llm_calls": "2–5",
        "steps": [
            ("calculate_portfolio_metrics","Financial Datasets AI","Total value, P&L, concentration risk"),
            ("analyze_diversification",    "Financial Datasets AI","Sector exposure, Herfindahl index"),
            ("identify_tax_loss_harvesting","Financial Datasets AI","Unrealized losses > $1,000 threshold"),
        ],
        "fallbacks": [],
        "output": "Portfolio report + tax harvest opportunities",
    },
}

DATA_SOURCES = {
    "Financial Datasets AI": {"color": "blue",   "note": "Primary financial data — API key req."},
    "Tavily Search":          {"color": "cyan",   "note": "Web search — API key req."},
    "SEC EDGAR":              {"color": "green",  "note": "Regulatory filings — no key needed"},
    "FMP → Tavily":           {"color": "magenta","note": "Earnings surprises + transcripts — FMP primary, Tavily fallback"},
    "FMP":                    {"color": "magenta","note": "Market quotes — optional"},
    "FRED":                   {"color": "white",  "note": "10-Year Treasury yield — API key req."},
    "Anthropic LLM":          {"color": "red",    "note": "LLM backbone for analysis nodes"},
    "Internal algorithm":     {"color": "dim",    "note": "Pure math — no network call"},
    "AV → FMP → Tavily":      {"color": "yellow", "note": "3-tier fallback cascade"},
    "FMP Market Data":        {"color": "magenta","note": "Indices, VIX, sector ETFs"},
    "—":                      {"color": "dim",    "note": "No external call"},
    "Tavily Search + LLM":    {"color": "cyan",   "note": "Web search synthesised by LLM"},
    "SEC EDGAR + LLM":        {"color": "green",  "note": "Filing text analysed by LLM"},
    "Internal Calculator":    {"color": "dim",    "note": "Pure math — no network call"},
    "FMP (optional)":         {"color": "magenta","note": "Optional cross-validation"},
}


def show_flow(filter_agent: Optional[str] = None) -> None:
    """Render data-flow trees for all (or one) agents."""
    console.print()
    console.rule("[bold cyan]Agent Data Flow Architecture[/bold cyan]")

    agents = AGENT_FLOWS if not filter_agent else {
        k: v for k, v in AGENT_FLOWS.items() if k == filter_agent
    }

    for agent_key, info in agents.items():
        console.print()
        title = f"[bold white]{info['label']}[/bold white]  [dim]{info['description']}[/dim]"
        console.print(Panel(title, border_style="blue", padding=(0, 2)))

        tree = Tree(
            f"[bold cyan]{info['label']}[/bold cyan] "
            f"[dim]({info['llm_calls']} LLM call(s))[/dim]"
        )

        for i, (tool, source, note) in enumerate(info["steps"], 1):
            src_info = DATA_SOURCES.get(source, {"color": "white"})
            color = src_info["color"]
            prefix = f"[dim]{i:2d}.[/dim] "
            branch = tree.add(
                f"{prefix}[bold]{tool}[/bold]  "
                f"[{color}]→ {source}[/{color}]"
            )
            branch.add(f"[dim]{note}[/dim]")

        if info.get("fallbacks"):
            fb_branch = tree.add("[yellow]Fallback Cascades[/yellow]")
            for fb in info["fallbacks"]:
                fb_branch.add(f"[dim yellow]{fb}[/dim yellow]")

        out_branch = tree.add("[green]Output[/green]")
        out_branch.add(f"[dim]{info['output']}[/dim]")

        console.print(tree)

    # Legend
    console.print()
    console.rule("[dim]Data Source Legend[/dim]")
    legend_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    legend_table.add_column("Source", style="bold")
    legend_table.add_column("Note")

    shown = set()
    for info in agents.values():
        for _, source, _ in info["steps"]:
            if source not in shown:
                shown.add(source)
                src_info = DATA_SOURCES.get(source, {"color": "white", "note": ""})
                color = src_info["color"]
                note = src_info.get("note", "")
                legend_table.add_row(f"[{color}]{source}[/{color}]", note)

    console.print(legend_table)
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# 3.  TICKER EVAL
# ─────────────────────────────────────────────────────────────────────────────

class TickerEvaluator:
    """Fetch real data from each source for a ticker and report quality/structure."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self.results: List[CheckResult] = []

    def run(self) -> None:
        console.print()
        console.rule(f"[bold cyan]Data Evaluation: {self.ticker}[/bold cyan]")
        console.print()

        checks = [
            ("Financial Datasets AI",    self._eval_financial_datasets),
            ("SEC EDGAR",                self._eval_sec_edgar),
            ("FMP Market Data",          self._eval_fmp),
            ("Tavily Search",            self._eval_tavily),
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task(f"Fetching data for {self.ticker}…", total=len(checks))
            for label, fn in checks:
                progress.update(task, description=f"Checking {label}…")
                result = fn()
                self.results.append(result)
                progress.advance(task)

        self._render()

    # ── individual evaluators ─────────────────────────────────────────────────

    def _eval_financial_datasets(self) -> CheckResult:
        key = os.environ.get("FINANCIAL_DATASETS_API_KEY", "")
        if not key:
            return CheckResult("Financial Datasets AI", "skip", None, "API key not set")

        headers = {"X-API-KEY": key}
        extra: Dict[str, Any] = {}

        # --- company facts ---
        t0 = time.time()
        code, body = _http_get(
            "https://api.financialdatasets.ai/company/facts",
            headers=headers,
            params={"ticker": self.ticker},
        )
        lat = (time.time() - t0) * 1000

        if code != 200 or not body:
            status_map = {401: "auth", 404: "not found", -1: "timeout", -2: "connection"}
            return CheckResult("Financial Datasets AI", "error", lat,
                               status_map.get(code, f"HTTP {code}"))

        facts = body.get("company_facts", {})
        extra["company_name"]  = facts.get("name", "N/A")
        extra["sector"]        = facts.get("sector", "N/A")
        extra["industry"]      = facts.get("industry", "N/A")
        extra["market_cap"]    = facts.get("market_cap")
        extra["shares"]        = facts.get("weighted_average_shares")

        # --- financials (income + cash flow) ---
        t1 = time.time()
        code2, body2 = _http_get(
            "https://api.financialdatasets.ai/financials",
            headers=headers,
            params={"ticker": self.ticker, "period": "annual", "limit": 5},
        )
        lat += (time.time() - t1) * 1000

        if code2 == 200 and body2:
            # Financials are nested: {"financials": {"income_statements": [], ...}}
            fin = body2.get("financials", body2)
            income = fin.get("income_statements", [])
            cf     = fin.get("cash_flow_statements", [])
            bs     = fin.get("balance_sheets", [])
            extra["income_years"] = len(income)
            extra["cf_years"]     = len(cf)
            extra["bs_years"]     = len(bs)
            if income:
                extra["revenues"] = [s.get("revenue") for s in income[:5]]
            if cf:
                extra["fcfs"] = [s.get("free_cash_flow") for s in cf[:5]]
            if income:
                extra["net_incomes"] = [s.get("net_income") for s in income[:5]]

        detail = (
            f"{extra.get('company_name')} · {extra.get('sector')} · "
            f"Cap {_fmt_num(extra.get('market_cap'))} · "
            f"{extra.get('income_years', 0)}Y financials"
        )
        return CheckResult("Financial Datasets AI", "ok", lat, detail, extra)

    def _eval_sec_edgar(self) -> CheckResult:
        try:
            from data.sec_edgar import SECEdgarClient
            client = SECEdgarClient()
        except Exception as e:
            return CheckResult("SEC EDGAR", "error", None, f"Could not load SECEdgarClient: {e}")

        # Step 1: resolve CIK (uses www.sec.gov/files/company_tickers.json internally)
        t0 = time.time()
        try:
            cik = client.get_cik(self.ticker)
        except Exception as e:
            lat = (time.time() - t0) * 1000
            return CheckResult("SEC EDGAR", "error", lat, f"CIK lookup failed: {e}")

        lat = (time.time() - t0) * 1000

        if not cik:
            return CheckResult("SEC EDGAR", "warning", lat,
                               f"{self.ticker} not found in SEC EDGAR CIK map")

        # Step 2: fetch recent filings via submissions API
        t1 = time.time()
        try:
            subs_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            subs = client._get_json(subs_url)
        except Exception as e:
            lat += (time.time() - t1) * 1000
            return CheckResult("SEC EDGAR", "warning", lat,
                               f"CIK {cik} found but could not load filings: {e}")

        lat += (time.time() - t1) * 1000

        if not subs:
            return CheckResult("SEC EDGAR", "warning", lat,
                               f"CIK {cik} found but submissions API returned empty")

        name = subs.get("name", self.ticker)
        filings = subs.get("filings", {}).get("recent", {})
        forms        = filings.get("form", [])
        dates        = filings.get("filingDate", [])
        descriptions = filings.get("primaryDocument", [])

        recent_10k = next(((d, f) for d, fo, f in zip(dates, forms, descriptions) if fo == "10-K"), None)
        recent_10q = next(((d, f) for d, fo, f in zip(dates, forms, descriptions) if fo == "10-Q"), None)
        recent_8k  = next(((d, f) for d, fo, f in zip(dates, forms, descriptions) if fo == "8-K"),  None)

        extra = {
            "cik":           cik,
            "entity_name":   name,
            "10k":           f"{recent_10k[0]} — {recent_10k[1]}" if recent_10k else "N/A",
            "10q":           f"{recent_10q[0]} — {recent_10q[1]}" if recent_10q else "N/A",
            "8k":            f"{recent_8k[0]}"  if recent_8k  else "N/A",
            "total_filings": len(forms),
        }
        detail = (
            f"CIK {cik} · {name} · "
            f"10-K: {extra['10k']} · "
            f"10-Q: {extra['10q']}"
        )
        return CheckResult("SEC EDGAR", "ok", lat, detail, extra)

    def _eval_fmp(self) -> CheckResult:
        key = os.environ.get("FMP_API_KEY", "")
        if not key:
            return CheckResult("FMP Market Data", "skip", None,
                               "FMP_API_KEY not set — market quotes via other sources")

        t0 = time.time()
        code, body = _http_get(
            "https://financialmodelingprep.com/stable/batch-quote",
            params={"symbols": self.ticker, "apikey": key},
        )
        lat = (time.time() - t0) * 1000

        if code == 200 and body and isinstance(body, list) and body:
            q = body[0]
            extra = {
                "price":     q.get("price"),
                "change":    q.get("changePercent"),
                "volume":    q.get("volume"),
                "mkt_cap":   q.get("marketCap"),
                "pe":        q.get("pe"),
                "eps":       q.get("eps"),
            }
            detail = (
                f"${extra['price']:.2f}  "
                f"({'+' if (extra['change'] or 0) >= 0 else ''}{(extra['change'] or 0):.2f}%)  "
                f"Vol {extra.get('volume', 0):,}  "
                f"PE {extra.get('pe') or 'N/A'}"
            )
            return CheckResult("FMP Market Data", "ok", lat, detail, extra)
        if code in (402, 403):
            return CheckResult("FMP Market Data", "warning", lat, "Premium subscription required")
        return CheckResult("FMP Market Data", "error", lat, f"HTTP {code}")

    def _eval_tavily(self) -> CheckResult:
        key = os.environ.get("TAVILY_API_KEY", "")
        if not key:
            return CheckResult("Tavily Search", "skip", None, "TAVILY_API_KEY not set — web search disabled")

        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=key)
            query = f"{self.ticker} stock beta analyst estimates 2025"
            t0 = time.time()
            result = client.search(query, max_results=3)
            lat = (time.time() - t0) * 1000

            results_list = result.get("results") or []
            answer = result.get("answer") or ""
            extra = {
                "query":         query,
                "num_results":   len(results_list),
                "answer_length": len(answer),
                "sources":       [r.get("url", "") for r in results_list[:3]],
            }
            if results_list:
                detail = (
                    f"{len(results_list)} result(s) · "
                    f"answer {len(answer)} chars · "
                    f"sample: {(results_list[0].get('title', ''))[:50]}…"
                )
            else:
                detail = "No results returned"
            return CheckResult("Tavily Search", "ok" if results_list else "warning", lat, detail, extra)
        except Exception as e:
            msg = str(e)[:80]
            return CheckResult("Tavily Search", "error", None, f"Error: {msg}")

    # ── render ────────────────────────────────────────────────────────────────

    def _render(self) -> None:
        for r in self.results:
            self._render_source(r)
        self._render_summary()

    def _render_source(self, r: CheckResult) -> None:
        status_line = {
            "ok":      f"[bold green]✓ ONLINE[/bold green]",
            "warning": f"[bold yellow]⚠ DEGRADED[/bold yellow]",
            "error":   f"[bold red]✗ FAILED[/bold red]",
            "skip":    f"[dim]─ SKIPPED[/dim]",
        }.get(r.status, r.status)

        lat_str = f"[dim]Latency: {_fmt_ms(r.latency_ms)}[/dim]" if r.latency_ms else ""

        header = f"{status_line}  {lat_str}  [dim]{r.detail}[/dim]"

        content_lines = [header]

        ex = r.extra
        if r.api == "Financial Datasets AI" and r.status == "ok":
            content_lines += [
                "",
                f"  [bold]Company Facts[/bold]",
                f"    Name:       {ex.get('company_name', 'N/A')}",
                f"    Sector:     {ex.get('sector', 'N/A')}",
                f"    Industry:   {ex.get('industry', 'N/A')}",
                f"    Market Cap: {_fmt_num(ex.get('market_cap'))}",
                f"    Shares Out: {_fmt_num(ex.get('shares'))}",
                "",
                f"  [bold]Financial History[/bold]",
                f"    Income Statements:   {ex.get('income_years', 0)} years",
                f"    Cash Flow Stmts:     {ex.get('cf_years', 0)} years",
                f"    Balance Sheets:      {ex.get('bs_years', 0)} years",
            ]
            if ex.get("revenues"):
                rev_str = "  →  ".join(_fmt_num(v) for v in ex["revenues"] if v)
                content_lines.append(f"    Revenue (newest first): {rev_str}")
            if ex.get("fcfs"):
                fcf_str = "  →  ".join(_fmt_num(v) for v in ex["fcfs"] if v)
                content_lines.append(f"    FCF    (newest first): {fcf_str}")

        elif r.api == "Alpha Vantage" and r.status == "ok":
            content_lines += [
                "",
                f"  [bold]Earnings Data[/bold]",
                f"    Quarterly Reports: {ex.get('quarterly_count', 0)} quarters",
                f"    Annual Reports:    {ex.get('annual_count', 0)} years",
                f"    Latest EPS:        {ex.get('latest_eps', 'N/A')} ({ex.get('latest_period', 'N/A')})",
            ]

        elif r.api == "SEC EDGAR" and r.status == "ok":
            content_lines += [
                "",
                f"  [bold]SEC Filing Index[/bold]",
                f"    CIK:           {ex.get('cik', 'N/A')}",
                f"    Entity Name:   {ex.get('entity_name', 'N/A')}",
                f"    Total Filings: {ex.get('total_filings', 0):,}",
                f"    Latest 10-K:   {ex.get('10k', 'N/A')}",
                f"    Latest 10-Q:   {ex.get('10q', 'N/A')}",
                f"    Latest 8-K:    {ex.get('8k', 'N/A')}",
            ]

        elif r.api == "FMP Market Data" and r.status == "ok":
            content_lines += [
                "",
                f"  [bold]Real-Time Quote[/bold]",
                f"    Price:      ${ex.get('price', 'N/A')}",
                f"    Change:     {ex.get('change', 'N/A'):.2f}%" if ex.get("change") is not None else "    Change:     N/A",
                f"    Volume:     {ex.get('volume', 0):,}",
                f"    Market Cap: {_fmt_num(ex.get('mkt_cap'))}",
                f"    P/E Ratio:  {ex.get('pe', 'N/A')}",
                f"    EPS (ttm):  {ex.get('eps', 'N/A')}",
            ]

        elif r.api == "Tavily Search" and r.status == "ok":
            content_lines += [
                "",
                f"  [bold]Web Search[/bold]",
                f"    Query:   {ex.get('query', 'N/A')}",
                f"    Results: {ex.get('num_results', 0)}",
                f"    Answer:  {ex.get('answer_length', 0)} chars generated",
            ]
            if ex.get("sources"):
                content_lines.append(f"    Sources:")
                for s in ex["sources"][:3]:
                    content_lines.append(f"      • {s}")

        body = "\n".join(content_lines)
        color_map = {"ok": "green", "warning": "yellow", "error": "red", "skip": "dim"}
        border = color_map.get(r.status, "white")
        console.print(Panel(body, title=f"[bold]{r.api}[/bold]",
                            border_style=border, padding=(0, 2)))
        console.print()

    def _render_summary(self) -> None:
        ok   = [r for r in self.results if r.status == "ok"]
        warn = [r for r in self.results if r.status == "warning"]
        err  = [r for r in self.results if r.status == "error"]
        skip = [r for r in self.results if r.status == "skip"]

        table = Table(title=f"Eval Summary — {self.ticker}", box=box.ROUNDED,
                      border_style="cyan", show_header=True, header_style="bold cyan")
        table.add_column("Source", style="bold")
        table.add_column("Status", justify="center")
        table.add_column("Latency", justify="right")
        table.add_column("Data Quality")

        quality_map = {
            "Financial Datasets AI": lambda r: (
                f"{r.extra.get('income_years', 0)}Y income · {r.extra.get('cf_years', 0)}Y CF"
                if r.extra else "—"
            ),
            "SEC EDGAR": lambda r: (
                f"{r.extra.get('total_filings', 0)} filings"
                if r.extra else "—"
            ),
            "FMP Market Data": lambda r: (
                f"${r.extra.get('price', 'N/A')}"
                if r.extra else "—"
            ),
            "Tavily Search": lambda r: (
                f"{r.extra.get('num_results', 0)} web results"
                if r.extra else "—"
            ),
        }

        status_icons = {"ok": "[green]✓[/]", "warning": "[yellow]⚠[/]",
                        "error": "[red]✗[/]", "skip": "[dim]─[/]"}

        for r in self.results:
            quality_fn = quality_map.get(r.api, lambda _: "—")
            quality = quality_fn(r) if r.status == "ok" else r.detail[:50]
            table.add_row(r.api, status_icons.get(r.status, "?"),
                          _fmt_ms(r.latency_ms), quality)

        console.print(table)
        console.print(
            f"\n  [green]✓ {len(ok)} available[/]  "
            f"[yellow]⚠ {len(warn)} degraded[/]  "
            f"[red]✗ {len(err)} failed[/]  "
            f"[dim]─ {len(skip)} skipped[/]\n"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4.  LIVE AGENT MONITOR
# ─────────────────────────────────────────────────────────────────────────────

class MonitorCallback:
    """LangChain callback that records tool invocations for the live monitor."""

    def __init__(self, call_log: List[CallRecord], live_table: Table):
        self.call_log = call_log
        self.live_table = live_table
        self._tool_start: Dict[str, float] = {}
        self._lock = threading.Lock()

    def on_tool_start(self, serialized: Dict, input_str: str, **kwargs: Any) -> None:
        name = serialized.get("name", "unknown_tool")
        with self._lock:
            self._tool_start[name] = time.time()

        # Determine data source from tool name
        source = self._infer_source(name)
        self._add_row(name, source, "running", None, f"Input: {str(input_str)[:60]}…")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        pass  # We handle timing in on_tool_error / deduce from logs

    def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        self._add_row("tool_error", "—", "error", None, str(error)[:80])

    def _infer_source(self, tool_name: str) -> str:
        mapping = {
            "get_stock_info":           "Financial Datasets AI",
            "get_financial_metrics":    "Financial Datasets AI",
            "get_company_context":      "Financial Datasets AI",
            "perform_multiples_valuation": "Financial Datasets AI",
            "search_web":               "Tavily Search",
            "analyze_industry":         "Tavily + LLM",
            "analyze_competitors":      "Tavily + LLM",
            "analyze_moat":             "Tavily + LLM",
            "get_market_overview":      "FMP Market Data",
            "analyze_sector":           "FMP Market Data",
            "get_market_news":          "Tavily Search",
            "classify_market_regime":   "Internal algorithm",
            "get_quarterly_earnings":   "Financial Datasets AI",
            "get_analyst_estimates":    "Financial Datasets AI",
            "get_earnings_surprises":   "FMP → Tavily",
            "get_earnings_call_insights": "FMP → Tavily",
            "compare_peer_earnings":    "Financial Datasets AI",
            "get_sec_filings":          "SEC EDGAR",
            "analyze_sec_filing":       "SEC EDGAR + LLM",
            "calculate_portfolio_metrics":    "Financial Datasets AI",
            "analyze_diversification":        "Financial Datasets AI",
            "identify_tax_loss_harvesting":   "Financial Datasets AI",
        }
        return mapping.get(tool_name, "Unknown")

    def _add_row(self, tool: str, source: str, status: str,
                 latency_ms: Optional[float], detail: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        status_icon = {
            "running": "[yellow]⟳ running[/]",
            "ok":      "[green]✓ ok[/]",
            "error":   "[red]✗ error[/]",
            "cache":   "[cyan]⚡ cache[/]",
        }.get(status, status)

        lat_str = _fmt_ms(latency_ms)
        with self._lock:
            self.live_table.add_row(ts, tool, source, status_icon, lat_str, detail[:70])

            rec = CallRecord(
                ts=time.time(), tool=tool, api=source,
                status=status, latency_ms=latency_ms or 0,
                detail=detail,
            )
            self.call_log.append(rec)


_URL_API_MAP = [
    ("api.financialdatasets.ai",     "Financial Datasets AI"),
    ("financialmodelingprep.com",    "FMP"),
    # Alpha Vantage removed
    ("data.sec.gov",                 "SEC EDGAR"),
    ("www.sec.gov",                  "SEC EDGAR"),
    ("api.tavily.com",               "Tavily Search"),
    ("api.perplexity.ai",            "Perplexity"),
    ("api.openai.com",               "OpenAI"),
    ("api.anthropic.com",            "Anthropic LLM"),
    ("api.fred.stlouisfed.org",      "FRED"),
    ("api.massive.com",              "Massive.com"),
]

_URL_TOOL_MAP = [
    ("/company/facts",               "get_stock_info"),
    ("/financials",                  "get_financial_metrics"),
    ("/earnings-call-transcript",    "get_earnings_call_insights"),
    ("/batch-quote",                 "market_quote"),
    ("/submissions/CIK",             "get_sec_filings"),
    ("/api/xbrl/",                   "get_sec_financials"),
    ("/files/company_tickers",       "sec_cik_lookup"),
    ("DGS10",                        "get_treasury_rate"),
]


def _infer_api_and_tool(url: str) -> tuple[str, str]:
    api = "Unknown"
    for fragment, name in _URL_API_MAP:
        if fragment in url:
            api = name
            break
    tool = "http_request"
    for fragment, name in _URL_TOOL_MAP:
        if fragment in url:
            tool = name
            break
    return api, tool


def _patch_http_for_monitoring(call_log: List[CallRecord], live_table: Table) -> Any:
    """
    Patch requests.Session.request to intercept every HTTP call made by the agents.
    This captures Financial Datasets, FMP, Alpha Vantage, SEC EDGAR, Tavily, FRED — all in one place.
    Returns the original method for cleanup.
    """
    import urllib.parse
    original_request = requests.Session.request
    table_lock = threading.Lock()

    def patched_request(self_session, method, url, **kwargs):
        t0 = time.time()
        status_code = -1
        try:
            response = original_request(self_session, method, url, **kwargs)
            status_code = response.status_code
            lat = (time.time() - t0) * 1000
            return response
        except Exception as exc:
            lat = (time.time() - t0) * 1000
            raise
        finally:
            lat = (time.time() - t0) * 1000
            api, tool = _infer_api_and_tool(url)

            # Shorten the URL for display
            parsed = urllib.parse.urlparse(url)
            path = parsed.path[:40] + ("…" if len(parsed.path) > 40 else "")
            qs_preview = ""
            if parsed.query:
                first_param = parsed.query.split("&")[0][:30]
                qs_preview = f"?{first_param}…"

            ok = 200 <= status_code < 300
            status_icon = "[green]✓ ok[/]" if ok else (
                "[yellow]⚠ cached[/]" if status_code == 304 else "[red]✗ error[/]"
            )
            rec_status = "ok" if ok else "error"
            ts = datetime.now().strftime("%H:%M:%S")

            with table_lock:
                live_table.add_row(
                    ts, tool, api, status_icon, _fmt_ms(lat),
                    f"HTTP {status_code}  {path}{qs_preview}"
                )
                call_log.append(CallRecord(
                    ts=time.time(), tool=tool, api=api,
                    status=rec_status, latency_ms=lat,
                    detail=f"HTTP {status_code} {path}",
                ))

    requests.Session.request = patched_request  # type: ignore[method-assign]
    return original_request


def run_monitor(ticker: str, agent_name: str) -> None:
    """Instrument and run an agent, showing live data call activity."""
    ticker = ticker.upper()
    agent_map = {
        "analyst":  "Equity Analyst Agent",
        "earnings": "Earnings Agent",
        "graph":    "LangGraph Equity Analyst",
        "market":   "Market Agent",
    }
    agent_label = agent_map.get(agent_name, agent_name)

    console.print()
    console.rule(f"[bold cyan]Live Monitor: {agent_label} — {ticker}[/bold cyan]")
    console.print(
        f"\n  Instrumenting all tools… every data call will appear in real-time.\n"
        f"  [dim]Press Ctrl+C to stop early.[/dim]\n"
    )

    call_log: List[CallRecord] = []

    # Build live table
    live_table = Table(
        title=f"Live Data Calls — {agent_label} / {ticker}",
        box=box.MINIMAL_DOUBLE_HEAD,
        border_style="cyan",
        show_header=True,
        header_style="bold cyan",
    )
    live_table.add_column("Time",    min_width=10)
    live_table.add_column("Tool",    min_width=28, style="bold")
    live_table.add_column("Source",  min_width=22)
    live_table.add_column("Status",  min_width=12)
    live_table.add_column("Latency", min_width=8, justify="right")
    live_table.add_column("Details", min_width=40)

    # Suppress LangChain's verbose stdout so the live table is the primary display
    try:
        from langchain.globals import set_verbose
        set_verbose(False)
    except Exception:
        pass
    os.environ["LANGCHAIN_VERBOSE"] = "false"

    # Patch requests.Session.request to intercept every HTTP call
    original_request = _patch_http_for_monitoring(call_log, live_table)

    # Run the agent inside a Live display
    result_holder: Dict[str, Any] = {}

    def _run_agent():
        try:
            if agent_name == "earnings":
                from agents.earnings_agent import EarningsAgent
                agent = EarningsAgent()
                result_holder["output"] = agent.analyze(ticker)

            elif agent_name == "market":
                from agents.market_agent import MarketAnalysisAgent
                agent = MarketAnalysisAgent()
                query = "Analyze current market conditions, sentiment, and sector rotation"
                result_holder["output"] = agent.analyze(query)

            else:
                result_holder["error"] = f"Unknown agent: {agent_name}"

        except KeyboardInterrupt:
            result_holder["cancelled"] = True
        except Exception as e:
            result_holder["error"] = str(e)

    agent_thread = threading.Thread(target=_run_agent, daemon=True)
    agent_thread.start()

    with Live(live_table, console=console, refresh_per_second=4) as live:
        try:
            while agent_thread.is_alive():
                live.update(live_table)
                time.sleep(0.25)
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠ Interrupted by user[/]")

    agent_thread.join(timeout=5)

    # Restore original requests method
    requests.Session.request = original_request  # type: ignore[method-assign]

    # Final summary
    console.print()
    console.rule("[bold cyan]Monitoring Summary[/bold cyan]")
    console.print()

    if call_log:
        summary = Table(box=box.ROUNDED, border_style="cyan",
                        title="Data Call Summary", show_header=True,
                        header_style="bold cyan")
        summary.add_column("Data Source", style="bold")
        summary.add_column("Calls", justify="right")
        summary.add_column("Errors", justify="right")
        summary.add_column("Total Latency", justify="right")

        from collections import Counter
        source_calls:   Counter = Counter()
        source_errors:  Counter = Counter()
        source_latency: Dict[str, float] = {}

        for rec in call_log:
            source_calls[rec.api] += 1
            if rec.status == "error":
                source_errors[rec.api] += 1
            source_latency[rec.api] = source_latency.get(rec.api, 0) + rec.latency_ms

        for src, count in source_calls.most_common():
            errs = source_errors.get(src, 0)
            total_lat = source_latency.get(src, 0)
            err_str = f"[red]{errs}[/]" if errs else "[green]0[/]"
            summary.add_row(src, str(count), err_str, _fmt_ms(total_lat))

        console.print(summary)
        console.print(
            f"\n  Total tool calls: [bold]{len(call_log)}[/bold]  "
            f"Errors: [red]{sum(source_errors.values())}[/red]  "
            f"Total API time: [bold]{_fmt_ms(sum(source_latency.values()))}[/bold]\n"
        )
    else:
        console.print("  [dim]No tool calls recorded.[/dim]\n")

    if "error" in result_holder:
        console.print(f"[red]Agent error:[/] {result_holder['error']}\n")
    elif "cancelled" in result_holder:
        console.print("[yellow]Agent run cancelled.[/]\n")
    elif "output" in result_holder:
        console.print("[green]Agent completed successfully.[/green]\n")


# ─────────────────────────────────────────────────────────────────────────────
# 5.  EARNINGS DATA INTEGRITY TEST
# ─────────────────────────────────────────────────────────────────────────────

# Node definitions matching EarningsAgent._build_graph()
_EARNINGS_NODES = [
    ("fetch_company_info",      "Company Info",            "Node 1   "),
    ("fetch_earnings_history",  "Earnings History",        "Node 2 ‖ "),
    ("fetch_analyst_estimates", "Analyst Estimates",       "Node 3 ‖ "),
    ("fetch_guidance_and_news", "Guidance, Calls & Peers", "Node 4 ‖ "),
    ("fetch_sec_filings",       "SEC Filings",             "Node 5 ‖ "),
    ("aggregate_data",          "Aggregate (sync)",        "Node 6   "),
    ("comprehensive_analysis",  "Analysis (LLM call 1)",   "Node 7   "),
    ("develop_thesis",          "Thesis  (LLM call 2)",    "Node 8   "),
    ("generate_report",         "Generate Report",         "Node 9   "),
]

# State fields to evaluate for completeness
_EARNINGS_FIELDS = [
    # (state_key,           display_label,         expected_source)
    ("company_name",        "Company Name",        "Financial Datasets AI"),
    ("sector",              "Sector",              "Financial Datasets AI"),
    ("current_price",       "Current Price",       "Financial Datasets AI"),
    ("market_cap",          "Market Cap",          "Financial Datasets AI"),
    ("earnings_history",    "Earnings History",    "Financial Datasets AI"),
    ("analyst_estimates",   "Analyst Estimates",   "Financial Datasets AI"),
    ("earnings_surprises",  "Earnings Surprises",  "FMP → Tavily"),
    ("earnings_guidance",   "Call Insights",       "FMP → Tavily"),
    ("peer_comparison",     "Peer Comparison",     "Tavily Search"),
    ("sec_filings_summary", "SEC Filings",         "SEC EDGAR"),
]


class _FallbackDetector(logging.Handler):
    """
    Logging handler that captures WARNING/ERROR records indicating
    fallback cascade activations in earnings_tools.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.fallbacks: List[str] = []
        self.errors: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        lower = msg.lower()
        if "fallback" in lower or "web search" in lower or "no structured" in lower:
            self.fallbacks.append(f"[{record.name}] {msg}")
        if record.levelno >= logging.ERROR:
            self.errors.append(f"[{record.name}] {msg}")


def run_earnings_test(ticker: str) -> None:
    """
    Run the earnings agent with full data transparency:
    - Live node-progress tree showing each LangGraph node as it executes
    - Data previews: first ~300 chars of every state field after the run
    - Fallback detection via log handler (catches cascade activations)
    - HTTP call summary (which APIs were actually hit, how many times)
    - Completeness scorecard + pass/fail verdict
    """
    ticker = ticker.upper()

    console.print()
    console.rule(f"[bold cyan]Earnings Data Integrity Test — {ticker}[/bold cyan]")
    console.print(
        f"\n  [dim]Running full 9-node LangGraph earnings pipeline with data transparency.[/dim]\n"
        f"  [dim]Node progress shown live. Data previews + scorecard shown after.[/dim]\n"
        f"  [dim]Press Ctrl+C to stop early.[/dim]\n"
    )

    # ── Shared tracking state ──────────────────────────────────────────────────

    _lock = threading.Lock()
    node_status:   Dict[str, str]   = {n[0]: "pending" for n in _EARNINGS_NODES}
    node_detail:   Dict[str, str]   = {n[0]: ""        for n in _EARNINGS_NODES}
    node_start_ts: Dict[str, float] = {}
    node_elapsed:  Dict[str, float] = {}

    # ── Fallback log detector ──────────────────────────────────────────────────

    fallback_detector = _FallbackDetector()
    _watched_loggers = ("tools.earnings_tools", "agents.earnings_agent", "tools.sec_tools")
    for _lgname in _watched_loggers:
        _lg = logging.getLogger(_lgname)
        _lg.setLevel(logging.WARNING)
        _lg.addHandler(fallback_detector)
        _lg.propagate = False   # don't let root's CRITICAL level swallow WARNINGs

    # ── HTTP call log ──────────────────────────────────────────────────────────

    call_log: List[CallRecord] = []
    # Dummy table for _patch_http_for_monitoring — we rebuild a nicer one at the end
    _dummy_table = Table(show_header=False, box=None)
    _dummy_table.add_column("a")
    _dummy_table.add_column("b")
    _dummy_table.add_column("c")
    _dummy_table.add_column("d")
    _dummy_table.add_column("e")
    _dummy_table.add_column("f")
    original_request = _patch_http_for_monitoring(call_log, _dummy_table)

    # ── Build node progress panel ──────────────────────────────────────────────

    def _make_progress_panel() -> Panel:
        tree = Tree(
            f"[bold]{ticker}[/bold] — LangGraph Earnings Agent (9 nodes, 2 LLM calls)"
        )
        with _lock:
            _status   = dict(node_status)
            _detail   = dict(node_detail)
            _elapsed  = dict(node_elapsed)

        done_count    = sum(1 for s in _status.values() if s == "done")
        running_count = sum(1 for s in _status.values() if s == "running")
        err_count     = sum(1 for s in _status.values() if s == "error")
        pending_count = len(_EARNINGS_NODES) - done_count - running_count - err_count

        for node_name, label, node_tag in _EARNINGS_NODES:
            st  = _status.get(node_name, "pending")
            det = _detail.get(node_name, "")
            ela = _elapsed.get(node_name)

            icon = {
                "pending": "[dim]○[/dim]",
                "running": "[bold yellow]◕[/bold yellow]",
                "done":    "[bold green]●[/bold green]",
                "error":   "[bold red]✗[/bold red]",
            }.get(st, "○")

            color = {
                "pending": "dim",
                "running": "yellow",
                "done":    "white",
                "error":   "red",
            }.get(st, "dim")

            time_str = f" [dim]({ela:.1f}s)[/dim]" if ela else ""
            branch = tree.add(
                f"{icon} [{color}]{node_tag} {label}[/{color}]{time_str}"
            )
            if det and st in ("done", "error"):
                branch.add(f"[dim]{det[:90]}[/dim]")

        subtitle = (
            f"[green]● {done_count} done[/green]  "
            f"[yellow]◕ {running_count} running[/yellow]  "
            f"[red]✗ {err_count} error[/red]  "
            f"[dim]○ {pending_count} pending[/dim]"
        )
        return Panel(
            tree,
            title="[bold cyan]Node Progress[/bold cyan]",
            subtitle=subtitle,
            border_style="cyan",
            padding=(0, 2),
        )

    # ── TestingEarningsAgent — intercepts _emit_progress ──────────────────────

    # Import deferred so we don't slow down other eval_monitor modes
    from agents.earnings_agent import EarningsAgent  # noqa: PLC0415

    class TestingEarningsAgent(EarningsAgent):  # type: ignore[misc]
        """Subclass that routes _emit_progress events into our tracker."""

        def _emit_progress(self_agent, node: str, status: str, detail: str = "") -> None:  # noqa: N805
            with _lock:
                if status == "started":
                    node_status[node] = "running"
                    node_start_ts[node] = time.time()
                elif status in ("completed", "done"):
                    node_status[node] = "done"
                    node_detail[node] = detail
                    if node in node_start_ts:
                        node_elapsed[node] = time.time() - node_start_ts[node]
                elif status == "error":
                    node_status[node] = "error"
                    node_detail[node] = detail

    # ── Run agent in background thread ────────────────────────────────────────

    result_holder: Dict[str, Any] = {}

    def _run_agent() -> None:
        try:
            try:
                from langchain.globals import set_verbose
                set_verbose(False)
            except Exception:
                pass
            os.environ["LANGCHAIN_VERBOSE"] = "false"

            agent = TestingEarningsAgent()
            initial_state = {
                "ticker": ticker,
                "quarters_back": 8,
                "company_name": "", "sector": "", "industry": "",
                "current_price": 0.0, "market_cap": 0.0,
                "earnings_history": "", "analyst_estimates": "",
                "earnings_surprises": "", "earnings_guidance": "",
                "peer_comparison": "", "sec_filings_summary": "",
                "comprehensive_analysis": "", "management_accountability": "",
                "investment_thesis": "", "rating": "", "price_target": 0.0,
                "key_catalysts": [], "key_risks": [],
                "final_report": "", "start_time": time.time(), "errors": [],
            }
            result_holder["state"] = agent.graph.invoke(initial_state)
        except KeyboardInterrupt:
            result_holder["cancelled"] = True
        except Exception as exc:
            result_holder["error"] = str(exc)

    agent_thread = threading.Thread(target=_run_agent, daemon=True)
    agent_thread.start()

    # ── Live node-progress display ─────────────────────────────────────────────

    with Live(console=console, refresh_per_second=4) as live:
        try:
            while agent_thread.is_alive():
                live.update(_make_progress_panel())
                time.sleep(0.25)
            live.update(_make_progress_panel())
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠ Interrupted by user[/yellow]")

    agent_thread.join(timeout=10)

    # Restore HTTP and loggers
    requests.Session.request = original_request  # type: ignore[method-assign]
    for _lgname in _watched_loggers:
        _lg = logging.getLogger(_lgname)
        _lg.removeHandler(fallback_detector)

    # ── Agent failed? ──────────────────────────────────────────────────────────

    if "error" in result_holder:
        console.print(
            f"\n[bold red]Agent error:[/bold red] {result_holder['error']}\n"
        )
        return
    if "cancelled" in result_holder:
        console.print("\n[yellow]Run cancelled by user.[/yellow]\n")
        return

    state = result_holder.get("state", {})

    # ── Section A: Data Previews ───────────────────────────────────────────────

    console.print()
    console.rule("[bold cyan]Data Previews — Actual Content Received by Agent[/bold cyan]")
    console.print()

    for field, label, source in _EARNINGS_FIELDS:
        value = state.get(field)

        if isinstance(value, (int, float)):
            if value > 0:
                status_icon = "[bold green]✓ LOADED[/bold green]"
                preview     = _fmt_num(value) if abs(value) >= 1e5 else str(value)
                border      = "green"
            else:
                status_icon = "[yellow]⚠ ZERO[/yellow]"
                preview     = "0  (may indicate data unavailable)"
                border      = "yellow"

        elif isinstance(value, str) and value.strip():
            if value.lower().startswith("error") or "error fetching" in value.lower():
                status_icon = "[bold red]✗ ERROR[/bold red]"
                preview     = value[:250]
                border      = "red"
            else:
                char_count  = len(value)
                # Show a clean multi-line excerpt (first 5 non-empty lines)
                lines = [ln for ln in value.splitlines() if ln.strip()][:6]
                excerpt = "\n".join(lines)[:350]
                status_icon = "[bold green]✓ LOADED[/bold green]"
                preview     = f"[dim]{char_count:,} chars total[/dim]\n\n{excerpt}"
                border      = "green"

        elif isinstance(value, list) and value:
            status_icon = "[bold green]✓ LOADED[/bold green]"
            preview     = f"{len(value)} items: " + " · ".join(str(i) for i in value[:3])
            border      = "green"

        else:
            status_icon = "[bold red]✗ MISSING[/bold red]"
            preview     = "[dim]No data received for this field[/dim]"
            border      = "red"

        body = f"{status_icon}   [dim]source: {source}[/dim]\n\n{preview}"
        console.print(
            Panel(body, title=f"[bold]{label}[/bold]", border_style=border, padding=(0, 2))
        )
        console.print()

    # ── Section B: HTTP Call Summary ───────────────────────────────────────────

    console.print()
    console.rule("[bold cyan]HTTP Call Summary — Every API Request Made[/bold cyan]")
    console.print()

    from collections import Counter  # noqa: PLC0415
    source_calls:   Counter = Counter()
    source_errors:  Counter = Counter()
    source_latency: Dict[str, float] = {}

    for rec in call_log:
        source_calls[rec.api] += 1
        if rec.status == "error":
            source_errors[rec.api] += 1
        source_latency[rec.api] = source_latency.get(rec.api, 0) + rec.latency_ms

    _source_roles: Dict[str, str] = {
        "Financial Datasets AI": "Company info · earnings history · analyst estimates",
        "FMP":                   "Earnings surprises · call transcripts (primary)",
        "SEC EDGAR":             "10-Q / 10-K filing analysis",
        "Tavily Search":         "Peer comparison · web fallback",
        "Anthropic LLM":        "Analysis LLM (Node 7) + Thesis LLM (Node 8)",
        "Perplexity":           "Web search (if configured)",
        "FRED":                 "Treasury rates",
        "Unknown":              "Unclassified request",
    }

    http_tbl = Table(
        box=box.ROUNDED, border_style="cyan", show_header=True,
        header_style="bold cyan",
        title=f"API Usage During Earnings Test — {ticker}",
    )
    http_tbl.add_column("Data Source", style="bold", min_width=24)
    http_tbl.add_column("Calls", justify="right", min_width=6)
    http_tbl.add_column("Errors", justify="right", min_width=8)
    http_tbl.add_column("Total Latency", justify="right", min_width=14)
    http_tbl.add_column("Role", min_width=50)

    for src, count in source_calls.most_common():
        errs      = source_errors.get(src, 0)
        total_lat = source_latency.get(src, 0)
        err_str   = f"[red]{errs}[/red]" if errs else "[green]0[/green]"
        role      = _source_roles.get(src, "—")
        http_tbl.add_row(src, str(count), err_str, _fmt_ms(total_lat), role)

    console.print(http_tbl)
    console.print(
        f"\n  Total HTTP requests: [bold]{len(call_log)}[/bold]"
        f"  ·  Errors: [bold red]{sum(source_errors.values())}[/bold red]"
        f"  ·  Total API time: [bold]{_fmt_ms(sum(source_latency.values()))}[/bold]\n"
    )

    # ── Section C: Fallback Analysis ───────────────────────────────────────────

    console.print()
    console.rule("[bold cyan]Fallback Analysis[/bold cyan]")
    console.print()

    tavily_calls = [r for r in call_log if r.api == "Tavily Search"]
    fmp_calls    = [r for r in call_log if r.api == "FMP"]

    # Log-based fallback detection
    if fallback_detector.fallbacks:
        console.print(
            f"[bold yellow]⚠  {len(fallback_detector.fallbacks)} fallback activation(s) logged:[/bold yellow]"
        )
        for fb in fallback_detector.fallbacks:
            console.print(f"   [yellow]•[/yellow] {fb}")
        console.print()
    else:
        console.print("[bold green]✓  No fallback warnings in logs (FMP tier active)[/bold green]\n")

    # Log-based error detection
    if fallback_detector.errors:
        console.print(f"[bold red]✗  {len(fallback_detector.errors)} error(s) logged:[/bold red]")
        for err in fallback_detector.errors:
            console.print(f"   [red]•[/red] {err}")
        console.print()

    # HTTP-pattern analysis for each tool
    fallback_tbl = Table(
        box=box.SIMPLE, show_header=True, header_style="bold",
        title="Per-Tool Source Analysis",
    )
    fallback_tbl.add_column("Tool / Data",         style="bold", min_width=26)
    fallback_tbl.add_column("Expected Source",      min_width=22)
    fallback_tbl.add_column("HTTP Evidence",        min_width=22)
    fallback_tbl.add_column("Verdict")

    # FMP evidence (surprises + transcripts)
    if fmp_calls:
        fmp_verdict = f"[green]✓ PRIMARY (FMP called {len(fmp_calls)}×)[/green]"
    elif not os.getenv("FMP_API_KEY"):
        fmp_verdict = "[yellow]⚠ FMP_API_KEY not set → Tavily fallback[/yellow]"
    else:
        fmp_verdict = "[yellow]⚠ FMP key set but no FMP calls — check key validity[/yellow]"

    fallback_tbl.add_row(
        "Earnings Surprises",
        "FMP → Tavily",
        f"FMP: {len(fmp_calls)} calls",
        fmp_verdict,
    )
    fallback_tbl.add_row(
        "Call Insights (transcripts)",
        "FMP → Tavily",
        f"FMP: {len(fmp_calls)} calls",
        fmp_verdict,
    )

    # Tavily for peer comparison (always expected)
    if tavily_calls:
        peer_verdict = f"[green]✓ NORMAL ({len(tavily_calls)} Tavily calls — expected)[/green]"
    else:
        peer_verdict = "[yellow]⚠ No Tavily calls (peer comparison may be empty)[/yellow]"

    fallback_tbl.add_row(
        "Peer Comparison",
        "Tavily Search (primary)",
        f"Tavily: {len(tavily_calls)} calls",
        peer_verdict,
    )

    # SEC EDGAR
    sec_calls = [r for r in call_log if r.api == "SEC EDGAR"]
    if sec_calls:
        sec_verdict = f"[green]✓ LOADED ({len(sec_calls)} EDGAR calls)[/green]"
    else:
        sec_verdict = "[yellow]⚠ No EDGAR calls — SEC filings may be empty[/yellow]"

    fallback_tbl.add_row(
        "SEC Filings",
        "SEC EDGAR (no key needed)",
        f"EDGAR: {len(sec_calls)} calls",
        sec_verdict,
    )

    console.print(fallback_tbl)
    console.print()

    # ── Section D: Completeness Scorecard ─────────────────────────────────────

    console.print()
    console.rule("[bold cyan]Data Completeness Scorecard[/bold cyan]")
    console.print()

    scorecard = Table(
        box=box.ROUNDED, border_style="cyan", show_header=True,
        header_style="bold cyan",
        title=f"Earnings Agent — Field Completeness for {ticker}",
    )
    scorecard.add_column("Data Field",       style="bold", min_width=22)
    scorecard.add_column("Expected Source",  min_width=24)
    scorecard.add_column("Status",          justify="center", min_width=14)
    scorecard.add_column("Content Preview", min_width=48)

    total_fields = 0
    loaded_fields = 0

    for field, label, source in _EARNINGS_FIELDS:
        total_fields += 1
        value = state.get(field)

        if isinstance(value, (int, float)):
            if value > 0:
                status_cell = "[green]✓ loaded[/green]"
                qual        = _fmt_num(value) if abs(value) >= 1e5 else str(round(value, 2))
                loaded_fields += 1
            else:
                status_cell = "[yellow]⚠ zero[/yellow]"
                qual        = "0"
        elif isinstance(value, str) and value.strip():
            if value.lower().startswith("error") or "error fetching" in value.lower():
                status_cell = "[red]✗ error[/red]"
                qual        = value[:60]
            else:
                short = value[:80].replace("\n", " ").strip()
                status_cell = "[green]✓ loaded[/green]"
                qual        = f"{len(value):,} chars  ·  {short}…"
                loaded_fields += 1
        elif isinstance(value, list) and value:
            status_cell   = "[green]✓ loaded[/green]"
            qual          = f"{len(value)} items"
            loaded_fields += 1
        else:
            status_cell = "[red]✗ missing[/red]"
            qual        = "—"

        scorecard.add_row(label, source, status_cell, qual)

    console.print(scorecard)

    # State-level errors logged by the agent
    state_errors = state.get("errors", [])
    if state_errors:
        console.print(
            f"\n  [yellow]⚠ Agent logged {len(state_errors)} non-critical state error(s):[/yellow]"
        )
        for se in state_errors:
            console.print(f"    [dim]• {se}[/dim]")
        console.print()

    # ── Section E: Verdict ─────────────────────────────────────────────────────

    console.print()
    console.rule("[bold cyan]Verdict[/bold cyan]")
    console.print()

    all_loaded   = loaded_fields == total_fields
    no_fallbacks = not fallback_detector.fallbacks
    no_errors    = not fallback_detector.errors and "error" not in result_holder

    verdict_items: List[str] = []

    if all_loaded:
        verdict_items.append(f"[bold green]✓ ALL {total_fields} DATA FIELDS LOADED[/bold green]")
    else:
        missing = total_fields - loaded_fields
        verdict_items.append(
            f"[bold yellow]⚠ {loaded_fields}/{total_fields} FIELDS LOADED · {missing} MISSING OR ERRORED[/bold yellow]"
        )

    if no_fallbacks:
        verdict_items.append("[bold green]✓ ZERO FALLBACKS DETECTED[/bold green]")
    else:
        verdict_items.append(
            f"[bold yellow]⚠ {len(fallback_detector.fallbacks)} FALLBACK ACTIVATION(S)[/bold yellow]"
        )

    if no_errors:
        verdict_items.append("[bold green]✓ ZERO ERRORS[/bold green]")
    else:
        n_err = len(fallback_detector.errors) + (1 if "error" in result_holder else 0)
        verdict_items.append(f"[bold red]✗ {n_err} ERROR(S) PRESENT[/bold red]")

    if state_errors:
        verdict_items.append(
            f"[yellow]⚠ {len(state_errors)} NON-CRITICAL STATE ISSUE(S)[/yellow]"
        )

    pass_all = all_loaded and no_fallbacks and no_errors
    verdict_color = "green" if pass_all else ("yellow" if loaded_fields >= total_fields * 0.7 else "red")
    verdict_label = "PASS" if pass_all else ("PARTIAL PASS" if loaded_fields >= total_fields * 0.7 else "FAIL")
    verdict_text  = "  ·  ".join(verdict_items)

    console.print(
        Panel(
            verdict_text,
            title=f"[bold] {verdict_label} [/bold]",
            border_style=verdict_color,
            padding=(0, 2),
        )
    )
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# 6.  MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

HEADER = """\
[bold cyan]Finance Agent Data Monitor[/bold cyan] [dim]v1.0[/dim]
[dim]Inspect data sources · visualise flows · evaluate tickers · monitor live agents[/dim]
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eval_monitor",
        description="Finance Agent Data Monitor & Evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval_monitor.py health
  python eval_monitor.py flow
  python eval_monitor.py flow --agent analyst
  python eval_monitor.py eval AAPL
  python eval_monitor.py eval NVDA --agent earnings
  python eval_monitor.py monitor AAPL --agent analyst
  python eval_monitor.py monitor TSLA --agent earnings
  python eval_monitor.py test AAPL          # full earnings data integrity test
  python eval_monitor.py test NVDA          # test with different ticker
        """,
    )
    sub = p.add_subparsers(dest="command", metavar="MODE")

    sub.add_parser("health", help="Check all API health, keys, quotas, and latency")

    flow_p = sub.add_parser("flow", help="Visualise data flow architecture")
    flow_p.add_argument("--agent", choices=list(AGENT_FLOWS.keys()),
                        help="Show only this agent's flow (default: all)")

    eval_p = sub.add_parser("eval", help="Fetch real data for a ticker from every source")
    eval_p.add_argument("ticker", help="Stock ticker symbol, e.g. AAPL")
    eval_p.add_argument("--agent", choices=list(AGENT_FLOWS.keys()),
                        help="(Unused — reserved for future agent-specific eval)")

    mon_p = sub.add_parser("monitor", help="Run an agent with live data-call instrumentation")
    mon_p.add_argument("ticker", help="Stock ticker symbol, e.g. AAPL")
    mon_p.add_argument("--agent", choices=["analyst", "earnings", "graph", "market"],
                       default="analyst", help="Which agent to run (default: analyst)")

    test_p = sub.add_parser(
        "test",
        help="Full earnings data integrity test — actual content, fallback detection, scorecard",
    )
    test_p.add_argument("ticker", help="Stock ticker symbol, e.g. AAPL")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    console.print(HEADER)

    if not args.command:
        parser.print_help()
        return

    if args.command == "health":
        checker = HealthChecker()
        results = checker.run_all()
        show_health(results)

    elif args.command == "flow":
        show_flow(filter_agent=getattr(args, "agent", None))

    elif args.command == "eval":
        evaluator = TickerEvaluator(args.ticker)
        evaluator.run()

    elif args.command == "monitor":
        run_monitor(args.ticker, args.agent)

    elif args.command == "test":
        run_earnings_test(args.ticker)


if __name__ == "__main__":
    main()
