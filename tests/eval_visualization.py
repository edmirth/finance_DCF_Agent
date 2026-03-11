"""
Visualization Eval — Finance DCF Agent
=======================================
Three-layer evaluation of the chart pipeline:

  Suite A — Smart registry routing
    Replicates AgentChart.tsx resolveRenderer() in Python and verifies every
    data shape routes to the correct renderer (no API calls needed).

  Suite B — Chart spec schema validation
    Checks that generated specs have all required fields, valid types, and
    correct data structure for each chart type.

  Suite C — Tool chart emission (mocked API)
    Calls each charting tool with mocked financial data and verifies that
    CHART_DATA blocks are emitted, parseable, and structurally correct.

  Suite D — Live API integration (requires API keys)
    Calls compare_multiple_companies and compare_companies against real tickers
    and validates the full chart spec coming back from live data.

Usage:
    python tests/eval_visualization.py              # all suites
    python tests/eval_visualization.py --suite abc  # A, B, C only (no API)
    python tests/eval_visualization.py --suite d    # live API only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

# ── terminal colours ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg):     return f"{GREEN}✅  {RESET}{msg}"
def fail(msg):   return f"{RED}❌  {RESET}{msg}"
def warn(msg):   return f"{YELLOW}⚠️   {RESET}{msg}"
def header(msg): return f"\n{BOLD}{CYAN}{'═'*60}\n  {msg}\n{'═'*60}{RESET}"
def sub(msg):    return f"  {DIM}{msg}{RESET}"


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

CHART_DATA_RE = re.compile(
    r'---CHART_DATA:([^-\n]+)---\n(.*?)\n---END_CHART_DATA:[^-\n]+---',
    re.DOTALL,
)

def extract_chart_specs(text: str) -> list[dict]:
    """Extract all ---CHART_DATA--- blocks from a tool output string."""
    specs = []
    for m in CHART_DATA_RE.finditer(text):
        try:
            specs.append(json.loads(m.group(2).strip()))
        except json.JSONDecodeError as e:
            specs.append({"_parse_error": str(e), "_raw": m.group(2)[:200]})
    return specs

VALID_CHART_TYPES = {
    "line", "multi_line", "area",
    "bar", "bar_line", "grouped_bar", "stacked_bar", "beat_miss_bar",
    "pie", "donut",
    "scatter", "waterfall", "heatmap", "stat_card",
    "table",
}

def validate_spec(spec: dict) -> list[str]:
    """Return list of schema violation strings (empty = pass)."""
    errors = []
    if "_parse_error" in spec:
        return [f"JSON parse error: {spec['_parse_error']}"]

    if not spec.get("id"):
        errors.append("missing 'id'")
    if spec.get("chart_type") not in VALID_CHART_TYPES:
        errors.append(f"unknown chart_type '{spec.get('chart_type')}'")
    if not spec.get("title"):
        errors.append("missing 'title'")

    ct = spec.get("chart_type", "")

    if ct == "table":
        if not isinstance(spec.get("columns"), list):
            errors.append("table missing 'columns' list")
    elif ct in ("pie", "donut"):
        data = spec.get("data", [])
        if not data:
            errors.append("pie/donut has empty data")
        elif not all("label" in d and "value" in d for d in data):
            errors.append("pie/donut data rows must have {label, value}")
    elif ct == "heatmap":
        data = spec.get("data", [])
        if data and not all("row" in d and "col" in d and "value" in d for d in data):
            errors.append("heatmap data rows must have {row, col, value}")
    elif ct == "scatter":
        data = spec.get("data", [])
        if data and not all("x" in d and "y" in d for d in data):
            errors.append("scatter data rows must have {x, y}")
    elif ct == "waterfall":
        data = spec.get("data", [])
        if data and not all("label" in d and "value" in d for d in data):
            errors.append("waterfall data rows must have {label, value}")
    elif ct == "stat_card":
        data = spec.get("data", [])
        if data and not all("label" in d and "value" in d for d in data):
            errors.append("stat_card data rows must have {label, value}")
    else:
        # All time/category chart types
        if not isinstance(spec.get("data"), list) or not spec["data"]:
            errors.append(f"{ct}: 'data' must be a non-empty list")
        series = spec.get("series", [])
        if ct not in ("bar",) and not series:
            errors.append(f"{ct}: 'series' is empty")
        for i, s in enumerate(series):
            for field in ("key", "label", "type", "color"):
                if field not in s:
                    errors.append(f"series[{i}] missing '{field}'")
            if s.get("type") not in ("bar", "line", "area", None):
                errors.append(f"series[{i}] has invalid type '{s.get('type')}'")

    return errors


# ═════════════════════════════════════════════════════════════════════════════
# Suite A — Smart registry routing (Python replica of resolveRenderer)
# ═════════════════════════════════════════════════════════════════════════════

def _resolve_renderer(chart_type: str, data: list, series: list = None,
                      x_key: str = None, columns: list = None) -> str:
    """
    Python replica of AgentChart.tsx resolveRenderer().
    Returns the key of the renderer that would be selected.
    """
    series  = series or []
    data    = data or []
    columns = columns or []
    scores: dict[str, float] = {}

    # Shape-driven detectors
    if (data and "label" in data[0] and "value" in data[0]
            and "x" not in data[0] and "row" not in data[0]       # not scatter/heatmap
            and "type" not in data[0]                              # not waterfall
            and not isinstance(data[0].get("value"), str)         # not stat_card
            and chart_type != "donut"):                            # not donut
        scores["pie"] = 1.0
    if columns:
        scores["table"] = 1.0
    if chart_type == "donut":
        scores["donut"] = 1.0
    if chart_type == "stat_card" or (data and isinstance(data[0].get("value"), str) and "label" in data[0]):
        scores["stat_card"] = 0.95 if chart_type == "stat_card" else 0.75
    if chart_type == "heatmap" or (data and "row" in data[0] and "col" in data[0]):
        scores["heatmap"] = 0.95 if chart_type == "heatmap" else 0.9
    if chart_type == "scatter" or (data and "x" in data[0] and "y" in data[0]):
        scores["scatter"] = 0.95 if chart_type == "scatter" else 0.9
    if chart_type == "waterfall" or (data and "type" in data[0] and "label" in data[0]):
        scores["waterfall"] = 0.95 if chart_type == "waterfall" else 0.8

    # Series-driven detectors
    if x_key in ("company", "name", "category"):
        bar_count = sum(1 for s in series if s.get("type") == "bar")
        if bar_count <= 1 and data:
            scores["categorical_bar"] = 0.95
    if chart_type == "stacked_bar":
        scores["stacked_bar"] = 0.95
    bar_count = sum(1 for s in series if s.get("type") == "bar")
    if bar_count >= 2:
        scores["grouped_bar"] = 0.9
    if any(s.get("colorByField") for s in series):
        scores["beat_miss_bar"] = 0.95
    if chart_type == "area" or any(s.get("type") == "area" for s in series):
        scores["area"] = 0.95
    lines = sum(1 for s in series if s.get("type") == "line")
    bars  = bar_count
    if bars >= 1 and lines >= 1:
        scores["bar_line"] = 0.9
    if lines >= 2:
        scores["multi_line"] = 0.85

    # Generic fallbacks
    scores.setdefault("bar", 0.4)
    if lines == 1 and len(series) == 1:
        scores["line"] = 0.6

    # Backend hint baseline = 0.5
    hint_score = max(scores.get(chart_type, 0), 0.5)
    best_key, best_score = chart_type, hint_score

    for k, s in scores.items():
        if k != chart_type and s > best_score:
            best_key, best_score = k, s

    return best_key


def _rr(chart_type, data=None, series=None, x_key=None, columns=None):
    return _resolve_renderer(chart_type, data or [], series or [], x_key, columns or [])


REGISTRY_CASES: list[tuple[str, dict, str, str]] = [
    # (description, kwargs, expected_renderer, reason)

    # ── Shape-driven overrides ──────────────────────────────────────────────
    ("pie data shape → pie regardless of hint",
     dict(chart_type="bar", data=[{"label": "A", "value": 10}, {"label": "B", "value": 20}]),
     "pie", "data has {label,value} → pie wins at 1.0"),

    ("donut hint → donut",
     dict(chart_type="donut", data=[{"label": "X", "value": 5}]),
     "donut", "explicit hint"),

    ("table columns → table regardless of hint",
     dict(chart_type="bar", columns=["A", "B", "C"]),
     "table", "columns present → table wins at 1.0"),

    ("heatmap data shape → heatmap",
     dict(chart_type="bar", data=[{"row": "AAPL", "col": "MSFT", "value": 0.72}]),
     "heatmap", "row+col+value → heatmap at 0.9"),

    ("scatter data shape → scatter",
     dict(chart_type="bar", data=[{"x": 15.2, "y": 25.0, "label": "AAPL"}]),
     "scatter", "x+y fields → scatter at 0.9"),

    ("waterfall data shape → waterfall",
     dict(chart_type="bar", data=[{"label": "Revenue", "value": 100, "type": "positive"}]),
     "waterfall", "label+type+value → waterfall at 0.8"),

    ("stat_card hint → stat_card",
     dict(chart_type="stat_card", data=[{"label": "Price", "value": "$189.50"}]),
     "stat_card", "explicit hint"),

    # ── Series-driven upgrades ──────────────────────────────────────────────
    ("company x_key + 1 bar series → categorical_bar",
     dict(chart_type="bar", x_key="company",
          series=[{"key": "value", "label": "Revenue", "type": "bar", "color": "#2563EB"}],
          data=[{"company": "Apple", "value": 391}]),
     "categorical_bar", "x_key=company + single bar → colored bars"),

    ("2 bar series → grouped_bar overrides bar hint",
     dict(chart_type="bar",
          series=[{"key": "s1", "label": "A", "type": "bar", "color": "#000"},
                  {"key": "s2", "label": "B", "type": "bar", "color": "#111"}]),
     "grouped_bar", "2+ bar series → grouped_bar at 0.9"),

    ("1 bar + 1 line series → bar_line",
     dict(chart_type="bar",
          series=[{"key": "rev", "label": "Revenue", "type": "bar", "color": "#000"},
                  {"key": "margin", "label": "Margin", "type": "line", "color": "#111"}]),
     "bar_line", "mixed bar+line → bar_line at 0.9"),

    ("2+ line series → multi_line",
     dict(chart_type="bar",
          series=[{"key": "aapl", "label": "AAPL", "type": "line", "color": "#000"},
                  {"key": "msft", "label": "MSFT", "type": "line", "color": "#111"}]),
     "multi_line", "2 line series → multi_line at 0.85"),

    ("colorByField series → beat_miss_bar",
     dict(chart_type="bar",
          series=[{"key": "eps", "label": "EPS", "type": "bar", "color": "#000",
                   "colorByField": "beat", "colorIfTrue": "#10B981", "colorIfFalse": "#EF4444"}]),
     "beat_miss_bar", "colorByField present → beat_miss_bar at 0.95"),

    ("stacked_bar hint respected",
     dict(chart_type="stacked_bar",
          series=[{"key": "s1", "label": "A", "type": "bar", "color": "#000"},
                  {"key": "s2", "label": "B", "type": "bar", "color": "#111"}],
          data=[{"period": "2023", "s1": 10, "s2": 20}]),
     "stacked_bar", "explicit stacked_bar hint at 0.95 beats grouped_bar 0.9"),

    ("area hint respected",
     dict(chart_type="area",
          series=[{"key": "rev", "label": "Revenue", "type": "line", "color": "#000"}]),
     "area", "explicit area hint"),

    # ── Generic fallbacks ───────────────────────────────────────────────────
    ("bar hint with plain time series stays bar",
     dict(chart_type="bar", x_key="period",
          series=[{"key": "value", "label": "Revenue", "type": "bar", "color": "#000"}],
          data=[{"period": "2023", "value": 100}]),
     "bar", "backend hint wins at 0.5 when no detector scores higher"),

    ("multi_line hint with 2 line series → multi_line",
     dict(chart_type="multi_line",
          series=[{"key": "aapl", "label": "AAPL", "type": "line", "color": "#000"},
                  {"key": "msft", "label": "MSFT", "type": "line", "color": "#111"}]),
     "multi_line", "hint + series both agree"),
]


def run_suite_a() -> list[dict]:
    print(header("Suite A — Smart Registry Routing"))
    results = []
    for desc, kwargs, expected, reason in REGISTRY_CASES:
        got = _rr(**kwargs)
        passed = got == expected
        print(f"  {ok(desc) if passed else fail(desc)}")
        if not passed:
            print(f"    {DIM}expected {expected!r}, got {got!r} — {reason}{RESET}")
        else:
            print(sub(reason))
        results.append({"name": desc, "passed": passed, "expected": expected, "got": got})
    return results


# ═════════════════════════════════════════════════════════════════════════════
# Suite B — Chart spec schema validation
# ═════════════════════════════════════════════════════════════════════════════

VALID_SPECS: list[tuple[str, dict]] = [
    ("bar chart", {
        "id": "test_bar", "chart_type": "bar", "title": "Revenue",
        "data": [{"period": "2023", "value": 100}],
        "series": [{"key": "value", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB"}],
        "x_key": "period", "y_format": "currency_b",
    }),
    ("multi_line chart", {
        "id": "test_ml", "chart_type": "multi_line", "title": "Revenue History",
        "data": [{"period": "2022", "aapl": 394.3, "msft": 198.3},
                 {"period": "2023", "aapl": 383.3, "msft": 211.9}],
        "series": [{"key": "aapl", "label": "Apple ($B)", "type": "line", "color": "#2563EB"},
                   {"key": "msft", "label": "Microsoft ($B)", "type": "line", "color": "#10B981"}],
        "x_key": "period", "y_format": "currency_b",
    }),
    ("stacked_bar chart", {
        "id": "test_stacked", "chart_type": "stacked_bar", "title": "Segments",
        "data": [{"period": "Q1", "products": 45.2, "services": 12.3}],
        "series": [{"key": "products", "label": "Products", "type": "bar", "color": "#2563EB"},
                   {"key": "services", "label": "Services", "type": "bar", "color": "#10B981"}],
        "x_key": "period", "y_format": "currency_b",
    }),
    ("pie chart", {
        "id": "test_pie", "chart_type": "pie", "title": "Revenue Mix",
        "data": [{"label": "iPhone", "value": 52.3}, {"label": "Services", "value": 22.1}],
    }),
    ("donut chart", {
        "id": "test_donut", "chart_type": "donut", "title": "Portfolio",
        "data": [{"label": "AAPL", "value": 40}, {"label": "MSFT", "value": 30}],
    }),
    ("waterfall chart", {
        "id": "test_wf", "chart_type": "waterfall", "title": "P&L Bridge",
        "data": [{"label": "Revenue", "value": 100, "type": "total"},
                 {"label": "COGS", "value": -40, "type": "negative"},
                 {"label": "Gross Profit", "value": 60, "type": "subtotal"}],
        "y_format": "currency_b",
    }),
    ("scatter chart", {
        "id": "test_scatter", "chart_type": "scatter", "title": "P/E vs Growth",
        "data": [{"x": 28.5, "y": 8.3, "label": "AAPL"}, {"x": 35.1, "y": 12.1, "label": "MSFT"}],
        "x_label": "P/E Ratio", "y_label": "Revenue Growth (%)",
    }),
    ("heatmap chart", {
        "id": "test_hm", "chart_type": "heatmap", "title": "Correlation Matrix",
        "data": [{"row": "AAPL", "col": "MSFT", "value": 0.72},
                 {"row": "AAPL", "col": "GOOGL", "value": 0.68},
                 {"row": "MSFT", "col": "GOOGL", "value": 0.81}],
        "row_labels": ["AAPL", "MSFT"], "col_labels": ["MSFT", "GOOGL"],
    }),
    ("stat_card", {
        "id": "test_kpi", "chart_type": "stat_card", "title": "Key Metrics",
        "data": [{"label": "Revenue", "value": "$391B", "change": "+8.3%", "positive": True},
                 {"label": "P/E Ratio", "value": "28.5x"}],
    }),
    ("table", {
        "id": "test_table", "chart_type": "table", "title": "Income Statement",
        "columns": ["Metric", "2022", "2023", "2024"],
        "rows": [["Revenue", "$394B", "$383B", "$391B"],
                 ["Net Income", "$99B", "$97B", "$101B"]],
        "data": [],
    }),
    ("area chart", {
        "id": "test_area", "chart_type": "area", "title": "AUM Growth",
        "data": [{"period": "2022", "aum": 120.5}, {"period": "2023", "aum": 145.2}],
        "series": [{"key": "aum", "label": "AUM ($B)", "type": "line", "color": "#2563EB"}],
        "x_key": "period", "y_format": "currency_b",
    }),
    ("grouped_bar chart", {
        "id": "test_grouped", "chart_type": "grouped_bar", "title": "AAPL vs MSFT Metrics",
        "data": [{"metric": "Revenue", "aapl": 391, "msft": 245}],
        "series": [{"key": "aapl", "label": "Apple ($B)", "type": "bar", "color": "#2563EB"},
                   {"key": "msft", "label": "Microsoft ($B)", "type": "bar", "color": "#10B981"}],
        "x_key": "metric", "y_format": "currency_b",
    }),
    ("bar_line chart", {
        "id": "test_barline", "chart_type": "bar_line", "title": "Revenue & FCF Margin",
        "data": [{"period": "2022", "revenue": 394, "fcf_margin": 25.3}],
        "series": [{"key": "revenue", "label": "Revenue ($B)", "type": "bar", "color": "#2563EB", "yAxis": "left"},
                   {"key": "fcf_margin", "label": "FCF Margin (%)", "type": "line", "color": "#10B981", "yAxis": "right"}],
        "x_key": "period", "y_format": "currency_b", "y_right_format": "percent",
    }),
]

INVALID_SPECS: list[tuple[str, dict, str]] = [
    ("missing id",         {"chart_type": "bar", "title": "X", "data": []},  "missing 'id'"),
    ("unknown chart_type", {"id": "x", "chart_type": "bubble", "title": "X", "data": []}, "unknown chart_type"),
    ("missing title",      {"id": "x", "chart_type": "bar", "data": []},     "missing 'title'"),
    ("pie without label",  {"id": "x", "chart_type": "pie", "title": "X",
                             "data": [{"name": "A", "val": 10}]},              "must have {label, value}"),
    ("scatter without x/y",{"id": "x", "chart_type": "scatter", "title": "X",
                             "data": [{"a": 1, "b": 2}]},                      "must have {x, y}"),
]


def run_suite_b() -> list[dict]:
    print(header("Suite B — Chart Spec Schema Validation"))
    results = []

    print(f"  {BOLD}Valid specs (should pass){RESET}")
    for name, spec in VALID_SPECS:
        errors = validate_spec(spec)
        passed = len(errors) == 0
        print(f"    {ok(name) if passed else fail(name)}")
        if errors:
            for e in errors:
                print(f"      {RED}→ {e}{RESET}")
        results.append({"name": f"valid:{name}", "passed": passed})

    print(f"\n  {BOLD}Invalid specs (should fail validation){RESET}")
    for name, spec, expected_err in INVALID_SPECS:
        errors = validate_spec(spec)
        # Pass if at least one error was caught
        caught = any(expected_err.lower() in e.lower() for e in errors)
        print(f"    {ok(name) if caught else fail(name)}")
        if not caught:
            print(f"      {RED}→ expected error containing '{expected_err}', got: {errors}{RESET}")
        results.append({"name": f"invalid:{name}", "passed": caught})

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Suite C — Tool chart emission (mocked API)
# ═════════════════════════════════════════════════════════════════════════════

def _make_mock_fetcher(ticker_overrides: dict[str, dict] = None):
    """Build a MagicMock FinancialDataFetcher with realistic fake data."""
    BASE_INFO = {
        "company_name": "Apple Inc.", "sector": "Technology", "market_cap": 3_200_000_000_000,
        "current_price": 189.50, "shares_outstanding": 15_400_000_000,
    }
    BASE_METRICS = {
        "latest_revenue": 391_035_000_000, "latest_net_income": 97_000_000_000,
        "latest_fcf": 99_584_000_000, "latest_gross_profit": 180_683_000_000,
        "historical_revenue": [391e9, 383e9, 394e9, 365e9, 274e9],
        "historical_years":   ["2024", "2023", "2022", "2021", "2020"],
        "historical_fcf":     [99e9, 99e9, 111e9, 92e9, 73e9],
        "historical_gross_profit": [180e9, 169e9, 170e9, 152e9, 105e9],
        "shares_outstanding": 15_400_000_000,
    }

    MSFT_INFO = {**BASE_INFO, "company_name": "Microsoft Corp.", "market_cap": 2_900_000_000_000}
    MSFT_METRICS = {
        **BASE_METRICS,
        "latest_revenue": 245_122_000_000,
        "historical_revenue": [245e9, 211e9, 198e9, 168e9, 143e9],
        "latest_fcf": 63_000_000_000,
    }
    GOOGL_INFO = {**BASE_INFO, "company_name": "Alphabet Inc.", "market_cap": 2_000_000_000_000}
    GOOGL_METRICS = {
        **BASE_METRICS,
        "latest_revenue": 307_394_000_000,
        "historical_revenue": [307e9, 282e9, 257e9, 196e9, 161e9],
    }

    ticker_data = {
        "AAPL":  (BASE_INFO, BASE_METRICS),
        "MSFT":  (MSFT_INFO, MSFT_METRICS),
        "GOOGL": (GOOGL_INFO, GOOGL_METRICS),
    }
    if ticker_overrides:
        ticker_data.update(ticker_overrides)

    mock = MagicMock()
    def _get_info(ticker):  return ticker_data.get(ticker.upper(), (BASE_INFO, BASE_METRICS))[0]
    def _get_metrics(ticker): return ticker_data.get(ticker.upper(), (BASE_INFO, BASE_METRICS))[1]
    mock.get_stock_info.side_effect = _get_info
    mock.get_key_metrics.side_effect = _get_metrics
    mock.last_error_type = None
    return mock


def _check_tool_output(description: str, tool_fn, check_fn) -> dict:
    """Run a tool, extract specs, apply check_fn(specs, raw_output) → (passed, detail)."""
    try:
        raw = tool_fn()
        specs = extract_chart_specs(raw)
        passed, detail = check_fn(specs, raw)
    except Exception as e:
        passed, detail = False, f"exception: {e}"
    print(f"  {ok(description) if passed else fail(description)}")
    if not passed:
        print(f"    {RED}→ {detail}{RESET}")
    elif detail:
        print(sub(detail))
    return {"name": description, "passed": passed, "detail": detail}


def run_suite_c() -> list[dict]:
    print(header("Suite C — Tool Chart Emission (Mocked API)"))
    results = []
    mock_fetcher = _make_mock_fetcher()

    with patch("tools.research_assistant_tools.FinancialDataFetcher", return_value=mock_fetcher):
        from tools.research_assistant_tools import (
            CompanyComparisonTool,
            CompareMultipleCompaniesTool,
            QuickFinancialDataTool,
        )

        # ── compare_companies ─────────────────────────────────────────────
        results.append(_check_tool_output(
            "compare_companies(AAPL, MSFT) emits a CHART_DATA block",
            lambda: CompanyComparisonTool()._run("AAPL", "MSFT", "all"),
            lambda specs, _: (len(specs) > 0, f"{len(specs)} chart(s) emitted"),
        ))
        results.append(_check_tool_output(
            "compare_companies chart_type is multi_line",
            lambda: CompanyComparisonTool()._run("AAPL", "MSFT", "all"),
            lambda specs, _: (
                any(s.get("chart_type") == "multi_line" for s in specs),
                f"types: {[s.get('chart_type') for s in specs]}",
            ),
        ))
        results.append(_check_tool_output(
            "compare_companies chart has ≥2 data rows",
            lambda: CompanyComparisonTool()._run("AAPL", "MSFT", "all"),
            lambda specs, _: (
                any(len(s.get("data", [])) >= 2 for s in specs),
                f"data lengths: {[len(s.get('data',[])) for s in specs]}",
            ),
        ))
        results.append(_check_tool_output(
            "compare_companies chart passes schema validation",
            lambda: CompanyComparisonTool()._run("AAPL", "MSFT", "all"),
            lambda specs, _: (
                all(validate_spec(s) == [] for s in specs),
                "; ".join(e for s in specs for e in validate_spec(s)) or "all valid",
            ),
        ))

        # ── compare_multiple_companies: bar metrics ────────────────────────
        for metric, expected_type, expected_xkey in [
            ("revenue",    "bar", "company"),
            ("market_cap", "bar", "company"),
            ("growth",     "bar", "company"),
        ]:
            m = metric
            results.append(_check_tool_output(
                f"compare_multiple_companies metric={m} → bar chart with x_key=company",
                lambda m=m: CompareMultipleCompaniesTool()._run("AAPL,MSFT,GOOGL", m),
                lambda specs, _, et=expected_type, ek=expected_xkey: (
                    any(s.get("chart_type") == et and s.get("x_key") == ek for s in specs),
                    f"types: {[s.get('chart_type') for s in specs]}, x_keys: {[s.get('x_key') for s in specs]}",
                ),
            ))

        # ── compare_multiple_companies: revenue_history ────────────────────
        results.append(_check_tool_output(
            "compare_multiple_companies metric=revenue_history → multi_line chart",
            lambda: CompareMultipleCompaniesTool()._run("AAPL,MSFT,GOOGL", "revenue_history"),
            lambda specs, _: (
                any(s.get("chart_type") == "multi_line" for s in specs),
                f"types: {[s.get('chart_type') for s in specs]}",
            ),
        ))
        results.append(_check_tool_output(
            "revenue_history chart has one line series per company",
            lambda: CompareMultipleCompaniesTool()._run("AAPL,MSFT,GOOGL", "revenue_history"),
            lambda specs, _: (
                any(len([s for s in spec.get("series", []) if s.get("type") == "line"]) == 3
                    for spec in specs),
                f"series counts: {[len(spec.get('series',[])) for spec in specs]}",
            ),
        ))
        results.append(_check_tool_output(
            "revenue_history chart has period x_key",
            lambda: CompareMultipleCompaniesTool()._run("AAPL,MSFT,GOOGL", "revenue_history"),
            lambda specs, _: (
                any(s.get("x_key") == "period" for s in specs),
                f"x_keys: {[s.get('x_key') for s in specs]}",
            ),
        ))
        results.append(_check_tool_output(
            "revenue_history chart data has ≥3 year rows",
            lambda: CompareMultipleCompaniesTool()._run("AAPL,MSFT,GOOGL", "revenue_history"),
            lambda specs, _: (
                any(len(s.get("data", [])) >= 3 for s in specs),
                f"data row counts: {[len(s.get('data',[])) for s in specs]}",
            ),
        ))
        results.append(_check_tool_output(
            "all emitted specs pass schema validation",
            lambda: CompareMultipleCompaniesTool()._run("AAPL,MSFT,GOOGL", "revenue_history"),
            lambda specs, _: (
                all(validate_spec(s) == [] for s in specs),
                "; ".join(e for s in specs for e in validate_spec(s)) or "all valid",
            ),
        ))

        # ── get_quick_data ────────────────────────────────────────────────
        results.append(_check_tool_output(
            "get_quick_data emits ≥1 CHART_DATA block",
            lambda: QuickFinancialDataTool()._run("AAPL", "revenue"),
            lambda specs, _: (len(specs) >= 1, f"{len(specs)} chart(s) emitted"),
        ))
        results.append(_check_tool_output(
            "get_quick_data charts pass schema validation",
            lambda: QuickFinancialDataTool()._run("AAPL", "revenue"),
            lambda specs, _: (
                all(validate_spec(s) == [] for s in specs),
                "; ".join(e for s in specs for e in validate_spec(s)) or "all valid",
            ),
        ))

        # ── CHART_INSTRUCTION presence ────────────────────────────────────
        results.append(_check_tool_output(
            "all charting tools include CHART_INSTRUCTION placement hint",
            lambda: "\n".join([
                CompanyComparisonTool()._run("AAPL", "MSFT", "growth"),
                CompareMultipleCompaniesTool()._run("AAPL,MSFT", "revenue"),
            ]),
            lambda _, raw: (
                "CHART_INSTRUCTION" in raw,
                "CHART_INSTRUCTION found" if "CHART_INSTRUCTION" in raw else "missing CHART_INSTRUCTION",
            ),
        ))

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Suite D — Live API integration (real API calls)
# ═════════════════════════════════════════════════════════════════════════════

def run_suite_d(tickers: list[str] = None) -> list[dict]:
    print(header("Suite D — Live API Integration"))
    tickers = tickers or ["AAPL", "MSFT", "GOOGL"]
    tickers_str = ",".join(tickers)
    results = []

    api_key = os.getenv("FINANCIAL_DATASETS_API_KEY")
    if not api_key:
        print(warn("FINANCIAL_DATASETS_API_KEY not set — skipping Suite D"))
        return [{"name": "live_api", "passed": False, "detail": "API key missing"}]

    from tools.research_assistant_tools import CompareMultipleCompaniesTool, CompanyComparisonTool

    print(f"  {DIM}Tickers: {tickers_str}{RESET}")

    for metric in ["revenue", "market_cap", "revenue_history"]:
        start = time.time()
        try:
            raw = CompareMultipleCompaniesTool()._run(tickers_str, metric)
            latency = round(time.time() - start, 2)
            specs = extract_chart_specs(raw)
            errors = [e for s in specs for e in validate_spec(s)]
            passed = len(specs) > 0 and len(errors) == 0
            detail = f"{len(specs)} chart(s), {latency}s" + (f" — errors: {errors}" if errors else "")
        except Exception as e:
            passed, detail = False, str(e)

        desc = f"compare_multiple_companies metric={metric} → valid chart spec"
        print(f"  {ok(desc) if passed else fail(desc)}")
        print(sub(detail))
        results.append({"name": desc, "passed": passed, "detail": detail})

    # Two-company comparison
    t1, t2 = tickers[0], tickers[1]
    start = time.time()
    try:
        raw = CompanyComparisonTool()._run(t1, t2, "all")
        latency = round(time.time() - start, 2)
        specs = extract_chart_specs(raw)
        errors = [e for s in specs for e in validate_spec(s)]
        passed = len(specs) > 0 and len(errors) == 0
        detail = f"{len(specs)} chart(s), {latency}s" + (f" — errors: {errors}" if errors else "")
    except Exception as e:
        passed, detail = False, str(e)

    desc = f"compare_companies({t1}, {t2}) → valid chart spec"
    print(f"  {ok(desc) if passed else fail(desc)}")
    print(sub(detail))
    results.append({"name": desc, "passed": passed, "detail": detail})

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def print_summary(all_results: list[dict], elapsed: float):
    total  = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    failed = total - passed
    pct    = int(passed / total * 100) if total else 0

    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  Results: {GREEN}{passed} passed{RESET}{BOLD}, "
          f"{RED if failed else ''}{failed} failed{RESET}{BOLD}, "
          f"{total} total — {pct}% pass rate — {elapsed:.1f}s{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")

    if failed:
        print(f"\n{RED}{BOLD}  Failed tests:{RESET}")
        for r in all_results:
            if not r["passed"]:
                print(f"    {RED}• {r['name']}{RESET}")
                if r.get("detail"):
                    print(f"      {DIM}{r['detail']}{RESET}")


def main():
    parser = argparse.ArgumentParser(description="Visualization pipeline eval")
    parser.add_argument("--suite", default="abcd",
                        help="Suites to run: a=registry, b=schema, c=tools, d=live API (default: abcd)")
    parser.add_argument("tickers", nargs="*", help="Tickers for Suite D (default: AAPL MSFT GOOGL)")
    args = parser.parse_args()
    suites = args.suite.lower()

    start = time.time()
    all_results: list[dict] = []

    if "a" in suites:
        all_results.extend(run_suite_a())
    if "b" in suites:
        all_results.extend(run_suite_b())
    if "c" in suites:
        all_results.extend(run_suite_c())
    if "d" in suites:
        all_results.extend(run_suite_d(args.tickers or None))

    print_summary(all_results, time.time() - start)
    sys.exit(0 if all(r["passed"] for r in all_results) else 1)


if __name__ == "__main__":
    main()
