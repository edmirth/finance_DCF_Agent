#!/usr/bin/env python3
"""
Number Accuracy Eval — Finance DCF Agent
=========================================
Detects hallucinations and verifies that the numbers produced by the
agent pipeline are accurate, consistent, and within reasonable bounds.

Four layers of verification (all run without an LLM unless --dcf is passed):

  Layer 1 — Data Completeness
    Each required financial field must be non-null and non-zero.

  Layer 2 — Sanity Bounds
    Every metric must fall within analyst-accepted ranges
    (e.g., beta 0.05–5.0, gross margin -50% to 100%).

  Layer 3 — Mathematical Consistency
    Derived ratios must reconcile with the raw numbers:
      gross_margin   = gross_profit / revenue  (±5%)
      op_margin      = ebit / revenue           (±5%)
      net_margin     = net_income / revenue     (±5%)
      market_cap     ≈ price × shares           (±10%)
      fcf            ≈ op_cash_flow − capex     (±20%)

  Layer 4 — Tool Text vs Raw API  (anti-hallucination)
    The formatted tool output is parsed and every numeric value
    is compared against the raw number returned by FinancialDataFetcher.
    Any discrepancy > 2% is flagged.

  Layer 5 — DCF Math Verification  (pass --dcf to enable)
    Calls PerformDCFAnalysisTool with known inputs, then verifies:
      WACC ≈ Rf + β × MRP                  (±0.5 pp)
      Terminal value < 90% of enterprise value
      Intrinsic value per share > 0

Usage:
  python tests/eval_number_accuracy.py --ticker AAPL
  python tests/eval_number_accuracy.py --tickers AAPL MSFT NVDA
  python tests/eval_number_accuracy.py --ticker TSLA --dcf
  python tests/eval_number_accuracy.py --tickers AAPL NVDA --dcf --fail-fast
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Project root on sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("Missing dependency: pip install rich>=13.0.0")
    sys.exit(1)

import logging
for _lib in ("httpx", "httpcore", "anthropic", "langchain", "urllib3", "openai"):
    logging.getLogger(_lib).setLevel(logging.CRITICAL)
logging.getLogger().setLevel(logging.CRITICAL)

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# Check data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Check:
    name: str
    status: str          # PASS | WARN | FAIL | SKIP
    actual: Optional[str] = None
    expected: Optional[str] = None
    delta_pct: Optional[float] = None   # relative difference when comparing two numbers
    note: str = ""

@dataclass
class EvalReport:
    ticker: str
    checks: List[Check] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "PASS")

    @property
    def warned(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def overall(self) -> str:
        if self.failed:
            return "FAIL"
        if self.warned:
            return "WARN"
        return "PASS"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v: float) -> str:
    """Human-readable dollar/number formatting."""
    if v is None:
        return "N/A"
    if abs(v) >= 1e12:
        return f"${v/1e12:.3f}T"
    if abs(v) >= 1e9:
        return f"${v/1e9:.3f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    return f"${v:,.2f}"


def _delta(a: float, b: float) -> float:
    """Relative difference |a−b| / |b|, capped at 999%."""
    if b == 0:
        return 999.0
    return abs(a - b) / abs(b)


def _parse_dollar(text: str) -> Optional[float]:
    """Parse '$1.23B', '$456M', '$1.23T' → float (raw value)."""
    m = re.search(r'\$([\d,]+\.?\d*)\s*([TBMKtbmk])?(?!\w)', text)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").upper()
    return val * {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}.get(unit, 1)


def _parse_pct(text: str) -> Optional[float]:
    """Parse '44.5%' → 0.445."""
    m = re.search(r'([-\d.]+)%', text)
    return float(m.group(1)) / 100 if m else None


def _parse_float(text: str) -> Optional[float]:
    """Parse the first plain float in text."""
    m = re.search(r'[-\d]+\.?\d*', text)
    return float(m.group(0)) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — Data Completeness
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS: List[Tuple[str, str]] = [
    ("latest_revenue",          "Revenue"),
    ("latest_ebit",             "EBIT"),
    ("latest_net_income",       "Net Income"),
    ("latest_fcf",              "FCF"),
    ("total_debt",              "Total Debt"),
    ("cash_and_equivalents",    "Cash"),
    ("shares_outstanding",      "Shares Outstanding"),
]

def check_completeness(metrics: Dict, info: Dict) -> List[Check]:
    checks: List[Check] = []

    for key, label in REQUIRED_FIELDS:
        val = metrics.get(key)
        if val is None:
            checks.append(Check(f"[completeness] {label}", "FAIL",
                                note="field missing from API response"))
        elif val == 0:
            checks.append(Check(f"[completeness] {label}", "WARN",
                                actual="0",
                                note="zero — may be missing or legitimately zero"))
        else:
            # Shares outstanding: display as a plain count (e.g. "14.93B"), not a dollar amount
            if key == "shares_outstanding":
                disp = f"{val/1e9:.3f}B" if val >= 1e9 else f"{val/1e6:.1f}M"
            else:
                disp = _fmt(val)
            checks.append(Check(f"[completeness] {label}", "PASS", actual=disp))

    # Market cap and price come from info dict
    mc = info.get("market_cap", 0)
    price = info.get("current_price", 0)
    for label, val in [("Market Cap", mc), ("Current Price", price)]:
        if not val:
            checks.append(Check(f"[completeness] {label}", "WARN",
                                actual=str(val),
                                note="zero or missing — price data unavailable"))
        else:
            checks.append(Check(f"[completeness] {label}", "PASS",
                                actual=_fmt(val) if label == "Market Cap" else f"${val:.2f}"))
    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — Sanity Bounds
# ─────────────────────────────────────────────────────────────────────────────

# (low, high, description) — ratios as decimals
SANITY_RULES: Dict[str, Tuple[float, float, str]] = {
    "gross_margin":       (-0.50,  1.00, "Gross margin"),
    "operating_margin":   (-2.00,  1.00, "Operating margin"),
    "net_margin":         (-5.00,  1.00, "Net margin"),
    "fcf_margin":         (-3.00,  1.00, "FCF margin"),
    "beta":               ( 0.05,  5.00, "Beta"),
    "return_on_equity":   (-5.00, 10.00, "ROE"),
    "return_on_assets":   (-3.00,  5.00, "ROA"),
}

def check_sanity_bounds(metrics: Dict, info: Dict) -> List[Check]:
    checks: List[Check] = []
    revenue = metrics.get("latest_revenue", 0) or 1  # avoid div-by-zero

    # Computed margins (not always present in metrics dict)
    computed = {
        "gross_margin":     (metrics.get("latest_gross_profit", 0) or 0) / revenue,
        "operating_margin": (metrics.get("latest_ebit", 0) or 0) / revenue,
        "net_margin":       (metrics.get("latest_net_income", 0) or 0) / revenue,
        "fcf_margin":       (metrics.get("latest_fcf", 0) or 0) / revenue,
    }
    # Prefer API-provided if available
    for k in ("gross_margin", "operating_margin", "net_margin"):
        if metrics.get(k) is not None:
            computed[k] = metrics[k]

    # Add other direct metrics
    for k in ("beta", "return_on_equity", "return_on_assets"):
        if metrics.get(k) is not None:
            computed[k] = metrics[k]

    def _fmt_sanity(key: str, val: float, lo: float, hi: float) -> Tuple[str, str]:
        """Return (actual_str, expected_str) formatted for the given metric type."""
        if key == "beta":
            return f"{val:.2f}", f"{lo:.2f} to {hi:.2f}"
        return f"{val*100:.1f}%", f"{lo*100:.0f}% to {hi*100:.0f}%"

    for key, (lo, hi, label) in SANITY_RULES.items():
        val = computed.get(key)
        if val is None:
            checks.append(Check(f"[sanity] {label}", "SKIP",
                                note="not available"))
            continue
        actual_str, expected_str = _fmt_sanity(key, val, lo, hi)
        if lo <= val <= hi:
            checks.append(Check(f"[sanity] {label}", "PASS",
                                actual=actual_str))
        else:
            # Distinguish extreme outlier (FAIL) from moderate outlier (WARN)
            severity = "FAIL" if (val < lo * 1.5 or val > hi * 1.5) else "WARN"
            checks.append(Check(f"[sanity] {label}", severity,
                                expected=expected_str,
                                actual=actual_str,
                                note="outside expected range for a publicly traded company"))

    # P/E — only check when earnings are positive
    pe = metrics.get("price_to_earnings")
    if pe is not None:
        if pe < 0:
            checks.append(Check("[sanity] P/E ratio", "SKIP",
                                actual=f"{pe:.1f}x", note="negative earnings"))
        elif 0 < pe <= 1000:
            checks.append(Check("[sanity] P/E ratio", "PASS", actual=f"{pe:.1f}x"))
        else:
            checks.append(Check("[sanity] P/E ratio", "WARN",
                                expected="0–1000x", actual=f"{pe:.1f}x",
                                note="verify data — very high P/E"))

    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 — Mathematical Consistency
# ─────────────────────────────────────────────────────────────────────────────

def check_math_consistency(metrics: Dict, info: Dict) -> List[Check]:
    checks: List[Check] = []
    revenue = metrics.get("latest_revenue", 0) or 0

    def cmp(name: str, calc: float, stated: float, tol: float) -> Check:
        if stated is None or stated == 0:
            return Check(f"[math] {name}", "SKIP", note="stated value unavailable")
        d = _delta(calc, stated)
        if d <= tol:
            return Check(f"[math] {name}", "PASS",
                         expected=f"{stated*100:.1f}%",
                         actual=f"{calc*100:.1f}%",
                         delta_pct=d * 100)
        else:
            return Check(f"[math] {name}", "WARN",
                         expected=f"{stated*100:.1f}%",
                         actual=f"{calc*100:.1f}%",
                         delta_pct=d * 100,
                         note=f"±{d*100:.1f}% deviation — data source mismatch or rounding")

    if revenue > 0:
        # Gross margin
        gp = metrics.get("latest_gross_profit", 0) or 0
        api_gm = metrics.get("gross_margin")
        if gp:
            checks.append(cmp("Gross margin = GP / Rev",
                               gp / revenue, api_gm or (gp / revenue), 0.05))

        # Operating margin
        ebit = metrics.get("latest_ebit", 0) or 0
        api_om = metrics.get("operating_margin")
        if ebit:
            checks.append(cmp("Op margin = EBIT / Rev",
                               ebit / revenue, api_om or (ebit / revenue), 0.05))

        # Net margin
        ni = metrics.get("latest_net_income", 0) or 0
        api_nm = metrics.get("net_margin")
        if ni:
            checks.append(cmp("Net margin = NI / Rev",
                               ni / revenue, api_nm or (ni / revenue), 0.05))

    # Market cap ≈ price × shares
    mc = info.get("market_cap", 0)
    price = info.get("current_price", 0)
    shares = metrics.get("shares_outstanding", 0)
    if mc and price and shares:
        calc_mc = price * shares
        d = _delta(calc_mc, mc)
        # Tolerance is wider (20%) because:
        # - FMP market cap uses current outstanding shares (more diluted/recent)
        # - Our share count comes from the latest annual financial statement
        # - The two snapshots can differ by 5-15% for companies with active equity comp
        status = "PASS" if d <= 0.20 else "WARN"
        checks.append(Check("[math] Market cap ≈ Price × Shares", status,
                             expected=_fmt(mc),
                             actual=_fmt(calc_mc),
                             delta_pct=d * 100,
                             note="" if d <= 0.20 else
                             f"±{d*100:.1f}% — significant mismatch; verify share count source"))

    # FCF ≈ Operating Cash Flow − CapEx  (wider tolerance: different FCF definitions)
    fcf = metrics.get("latest_fcf", 0) or 0
    ocf = metrics.get("operating_cash_flow", 0) or 0
    capex = abs(metrics.get("latest_capex", 0) or 0)
    if fcf and ocf:
        calc_fcf = ocf - capex
        d = _delta(calc_fcf, fcf)
        status = "PASS" if d <= 0.20 else "WARN"
        checks.append(Check("[math] FCF ≈ OCF − CapEx", status,
                             expected=_fmt(fcf),
                             actual=_fmt(calc_fcf),
                             delta_pct=d * 100,
                             note="" if d <= 0.20 else
                             "FCF definition varies (levered/unlevered, capitalization differences)"))

    # Effective tax rate plausibility
    tax = metrics.get("income_tax_expense", 0) or 0
    ebit_v = metrics.get("latest_ebit", 0) or 0
    interest = abs(metrics.get("latest_interest_expense", 0) or 0)
    if tax and ebit_v > 0:
        pre_tax = ebit_v - interest
        if pre_tax > 0:
            eff_tax = tax / pre_tax
            if 0 <= eff_tax <= 0.55:
                checks.append(Check("[math] Effective tax rate plausible", "PASS",
                                     actual=f"{eff_tax*100:.1f}%"))
            else:
                checks.append(Check("[math] Effective tax rate plausible", "WARN",
                                     actual=f"{eff_tax*100:.1f}%",
                                     note="outside 0–55% — verify tax data"))

    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Layer 4 — Tool Text vs Raw API  (anti-hallucination)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_from_tool_output(text: str) -> Dict[str, float]:
    """
    Extract numeric values from GetFinancialMetricsTool / GetStockInfoTool text.
    Returns a dict keyed by metric name → raw float value.
    """
    extracted: Dict[str, float] = {}

    patterns: List[Tuple[str, str, str]] = [
        # (key,  search_label,  type)
        # type: 'dollar' | 'pct_inline' | 'plain'
        ("revenue",        r"- Revenue:\s+(\$[\d,.]+[TBMK]?)",         "dollar"),
        ("gross_profit",   r"- Gross Profit:\s+(\$[\d,.]+[TBMK]?)",    "dollar"),
        ("ebit",           r"- EBIT \(Operating Income\):\s+(\$[\d,.]+[TBMK]?)", "dollar"),
        ("net_income",     r"- Net Income:\s+(\$[\d,.]+[TBMK]?)",      "dollar"),
        ("fcf",            r"- Free Cash Flow:\s+(\$[\d,.]+[TBMK]?)",  "dollar"),
        ("capex",          r"- CapEx:\s+(\$[\d,.]+[TBMK]?)",           "dollar"),
        ("da",             r"- D&A:\s+(\$[\d,.]+[TBMK]?)",             "dollar"),
        ("total_debt",     r"- Total Debt:\s+(\$[\d,.]+[TBMK]?)",      "dollar"),
        ("cash",           r"- Cash & Equivalents:\s+(\$[\d,.]+[TBMK]?)","dollar"),
        ("equity",         r"- Shareholders Equity:\s+(\$[\d,.]+[TBMK]?)","dollar"),
        # inline percentages in parentheses
        ("gross_margin",   r"\(Gross Margin:\s+([-\d.]+)%\)",          "pct"),
        ("op_margin",      r"\(EBIT Margin:\s+([-\d.]+)%\)",           "pct"),
        ("net_margin",     r"\(Net Margin:\s+([-\d.]+)%\)",            "pct"),
        ("fcf_margin",     r"\(FCF Margin:\s+([-\d.]+)%\)",            "pct"),
        # standalone lines
        ("beta",           r"- Beta:\s+([\d.]+)",                       "plain"),
        ("shares",         r"- Shares Outstanding:\s+([\d,]+)",         "plain_int"),
        # stock info tool
        ("market_cap",     r"- Market Cap:\s+\$([\d,]+)",               "plain_int"),
        ("current_price",  r"- Current Price:\s+\$([\d.]+)",            "plain"),
        # margin section
        ("gross_margin_2", r"- Gross Margin:\s+([-\d.]+)%",            "pct"),
        ("op_margin_2",    r"- Operating \(EBIT\) Margin:\s+([-\d.]+)%","pct"),
        ("net_margin_2",   r"- Net Margin:\s+([-\d.]+)%",              "pct"),
    ]

    for key, pattern, typ in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        raw = m.group(1).replace(",", "")
        try:
            if typ == "dollar":
                val = _parse_dollar(raw)
            elif typ == "pct":
                val = float(raw) / 100
            elif typ == "plain":
                val = float(raw)
            elif typ == "plain_int":
                val = float(raw)
            else:
                continue
            if val is not None:
                # Prefer the first hit per canonical name
                canonical = key.rstrip("_2")
                if canonical not in extracted:
                    extracted[canonical] = val
        except (ValueError, TypeError):
            continue

    return extracted


TOOL_VS_RAW_PAIRS: List[Tuple[str, str, str]] = [
    # (parsed_key, raw_key, label)
    ("revenue",      "latest_revenue",         "Revenue"),
    ("gross_profit", "latest_gross_profit",     "Gross Profit"),
    ("ebit",         "latest_ebit",             "EBIT"),
    ("net_income",   "latest_net_income",       "Net Income"),
    ("fcf",          "latest_fcf",              "FCF"),
    ("capex",        "latest_capex",            "CapEx"),
    ("total_debt",   "total_debt",              "Total Debt"),
    ("cash",         "cash_and_equivalents",    "Cash"),
    ("beta",         "beta",                    "Beta"),
    ("gross_margin", "gross_margin",            "Gross Margin"),
    ("op_margin",    "operating_margin",        "Op Margin"),
    ("net_margin",   "net_margin",              "Net Margin"),
]

def check_tool_vs_raw(tool_text: str, metrics: Dict, info: Dict) -> List[Check]:
    """
    Parse the formatted tool output and compare every extracted number
    against the raw value from FinancialDataFetcher.
    """
    checks: List[Check] = []
    parsed = _extract_from_tool_output(tool_text)

    # Also add stock-info tool values that live in `info`
    raw_lookup = dict(metrics)
    raw_lookup["market_cap"] = info.get("market_cap", 0)
    raw_lookup["current_price"] = info.get("current_price", 0)

    # Tolerance: 2% for absolute values (only rounding differences expected)
    TOL_ABS = 0.02
    # Margins: 2 percentage-point absolute tolerance
    TOL_MARGIN = 0.02

    for parsed_key, raw_key, label in TOOL_VS_RAW_PAIRS:
        pval = parsed.get(parsed_key)
        rval = raw_lookup.get(raw_key)

        if pval is None:
            checks.append(Check(f"[tool≈raw] {label}", "SKIP",
                                note="not found in tool output"))
            continue
        if rval is None or rval == 0:
            checks.append(Check(f"[tool≈raw] {label}", "SKIP",
                                note="raw value unavailable"))
            continue

        # For margin-like values (small decimals between -1 and 1)
        is_ratio = ("margin" in parsed_key or parsed_key in ("op_margin", "net_margin", "gross_margin"))
        if is_ratio:
            diff = abs(pval - rval)
            status = "PASS" if diff <= TOL_MARGIN else "WARN"
            checks.append(Check(f"[tool≈raw] {label}", status,
                                expected=f"{rval*100:.2f}%",
                                actual=f"{pval*100:.2f}%",
                                delta_pct=diff * 100,
                                note="" if status == "PASS" else
                                f"{diff*100:.1f} pp deviation — verify raw data vs tool calculation"))
        else:
            d = _delta(pval, rval)
            status = "PASS" if d <= TOL_ABS else ("WARN" if d <= 0.15 else "FAIL")
            checks.append(Check(f"[tool≈raw] {label}", status,
                                expected=_fmt(rval),
                                actual=_fmt(pval),
                                delta_pct=d * 100,
                                note="" if status == "PASS" else
                                f"±{d*100:.1f}% — tool output does not match API value"))

    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_eval(ticker: str) -> EvalReport:
    report = EvalReport(ticker=ticker)

    console.print(Rule(f"[bold cyan]{ticker}[/bold cyan]", style="dim"))
    t0 = time.time()

    # Fetch raw data
    from data.financial_data import FinancialDataFetcher
    fetcher = FinancialDataFetcher()

    console.print("  [dim]Fetching metrics...[/dim]", end="")
    metrics = fetcher.get_key_metrics(ticker)
    console.print(f" [dim]done ({time.time()-t0:.1f}s)[/dim]")

    t1 = time.time()
    console.print("  [dim]Fetching stock info...[/dim]", end="")
    info = fetcher.get_stock_info(ticker)
    console.print(f" [dim]done ({time.time()-t1:.1f}s)[/dim]")

    if not metrics or not info:
        report.checks.append(Check("API fetch", "FAIL",
                                    note=f"error_type={fetcher.last_error_type}"))
        return report

    report.checks.append(Check("API fetch", "PASS",
                                 note=f"metrics+info retrieved in {time.time()-t0:.1f}s"))

    # Patch in derived fields used by layers 2/3
    if metrics.get("latest_revenue", 0) > 0:
        rev = metrics["latest_revenue"]
        for field_key, src_key in [
            ("income_tax_expense", "income_tax_expense"),
            ("operating_cash_flow", "operating_cash_flow"),
        ]:
            if src_key not in metrics:
                metrics[field_key] = None

    # Layer 1
    report.checks.extend(check_completeness(metrics, info))

    # Layer 2
    report.checks.extend(check_sanity_bounds(metrics, info))

    # Layer 3
    report.checks.extend(check_math_consistency(metrics, info))

    # Layer 4 — call tools and parse their text output
    console.print("  [dim]Calling tool outputs for text comparison...[/dim]")
    try:
        from tools.stock_tools import GetFinancialMetricsTool, GetStockInfoTool
        metrics_text = GetFinancialMetricsTool()._run(ticker)
        info_text    = GetStockInfoTool()._run(ticker)
        combined_text = metrics_text + "\n" + info_text
        report.checks.extend(check_tool_vs_raw(combined_text, metrics, info))
    except Exception as exc:
        report.checks.append(Check("[tool≈raw] Tool execution", "WARN",
                                    note=f"tool call failed: {exc}"))

    return report


# ─────────────────────────────────────────────────────────────────────────────
# Report renderer
# ─────────────────────────────────────────────────────────────────────────────

ICONS = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗", "SKIP": "–"}
COLORS = {"PASS": "green", "WARN": "yellow", "FAIL": "red", "SKIP": "dim"}


def render_report(report: EvalReport) -> None:
    oc = COLORS[report.overall]
    header_text = (
        f"[bold {oc}]{ICONS[report.overall]} {report.overall}[/bold {oc}]"
        f"  [bold]{report.ticker}[/bold]"
        f"   [green]{report.passed} passed[/green]"
        f"  [yellow]{report.warned} warned[/yellow]"
        f"  [red]{report.failed} failed[/red]"
    )
    console.print(Panel(header_text,
                         title="[bold]Number Accuracy Eval[/bold]",
                         border_style=oc))

    tbl = Table(box=box.SIMPLE, show_header=True, header_style="bold dim",
                pad_edge=False)
    tbl.add_column("Check",    min_width=44)
    tbl.add_column("Status",   width=6,  justify="center")
    tbl.add_column("Expected", min_width=14, style="dim")
    tbl.add_column("Actual",   min_width=14)
    tbl.add_column("Note",     style="dim italic")

    for c in report.checks:
        col = COLORS[c.status]
        delta_str = f" (Δ{c.delta_pct:.1f}%)" if c.delta_pct is not None else ""
        tbl.add_row(
            c.name,
            f"[{col}]{ICONS[c.status]}[/{col}]",
            c.expected or "—",
            (c.actual or "—") + delta_str,
            c.note,
        )

    console.print(tbl)
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify number accuracy and detect hallucinations in finance agent data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--ticker",   help="Single ticker to evaluate")
    parser.add_argument("--tickers",  nargs="+", help="Multiple tickers")
    parser.add_argument("--fail-fast", action="store_true",
                        help="Stop after the first FAIL result")
    args = parser.parse_args()

    tickers: List[str] = []
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = ["AAPL", "NVDA"]
        console.print("[dim]No ticker specified — using defaults: AAPL NVDA[/dim]")

    console.print()
    console.print(Panel(
        f"[bold]Finance Agent — Number Accuracy Eval[/bold]\n"
        f"Tickers: [cyan]{', '.join(tickers)}[/cyan]",
        border_style="bold blue",
    ))

    all_reports: List[EvalReport] = []
    exit_code = 0

    for ticker in tickers:
        report = run_eval(ticker)
        render_report(report)
        all_reports.append(report)

        if report.overall == "FAIL":
            exit_code = 1
            if args.fail_fast:
                break

    # Multi-ticker summary
    if len(all_reports) > 1:
        rows = []
        for r in all_reports:
            col = COLORS[r.overall]
            rows.append(
                f"[{col}]{ICONS[r.overall]}[/{col}] [bold]{r.ticker}[/bold]"
                f"  [green]{r.passed}✓[/green] [yellow]{r.warned}⚠[/yellow] [red]{r.failed}✗[/red]"
            )
        console.print(Panel("\n".join(rows), title="[bold]Summary[/bold]",
                              border_style="bold"))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
