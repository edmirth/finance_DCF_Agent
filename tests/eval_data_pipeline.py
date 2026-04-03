"""
Data Pipeline Eval — Finance DCF Agent
=======================================
Two-part evaluation:

  Part 1 — Tool-level data quality
    Calls each data-fetching tool directly, measures latency,
    checks that key fields are present in the response.

  Part 2 — End-to-end agent quality
    Runs the DCF and Earnings agents on real tickers and scores
    the final report against a checklist.

Usage:
    python tests/eval_data_pipeline.py                 # default tickers
    python tests/eval_data_pipeline.py AAPL NVDA MSFT  # custom tickers
    python tests/eval_data_pipeline.py --part1         # tool eval only
    python tests/eval_data_pipeline.py --part2         # agent eval only
"""
import sys
import os
import time
import re
import argparse

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg):    return f"{GREEN}✅  {RESET}{msg}"
def fail(msg):  return f"{RED}❌  {RESET}{msg}"
def warn(msg):  return f"{YELLOW}⚠️   {RESET}{msg}"
def header(msg):return f"\n{BOLD}{CYAN}{msg}{RESET}"
def dim(msg):   return f"{DIM}{msg}{RESET}"


# ═════════════════════════════════════════════════════════════════════════════
# PART 1 — Tool-level eval
# ═════════════════════════════════════════════════════════════════════════════

def _call(fn, *args, **kwargs):
    """Call a function, return (result, latency_s, error)."""
    start = time.time()
    try:
        result = fn(*args, **kwargs)
        return result, round(time.time() - start, 2), None
    except Exception as e:
        return None, round(time.time() - start, 2), str(e)


def eval_stock_info(ticker: str) -> dict:
    from tools.stock_tools import GetStockInfoTool
    result, latency, err = _call(GetStockInfoTool()._run, ticker)
    if err or not result or result.startswith("Error"):
        return {"name": "get_stock_info", "passed": False, "latency": latency,
                "detail": err or result}

    checks = {
        "company name": bool(re.search(r"Company:\s+\S", result)),
        "sector":       bool(re.search(r"Sector:\s+\S", result)),
        "market cap":   bool(re.search(r"Market Cap:\s+\$[\d,]+", result)),
        "price":        bool(re.search(r"Current Price:\s+\$[\d.]+", result)),
    }
    passed = all(checks.values())
    detail = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in checks.items())
    return {"name": "get_stock_info", "passed": passed, "latency": latency,
            "detail": detail, "checks": checks}


def eval_financial_metrics(ticker: str) -> dict:
    from tools.stock_tools import GetFinancialMetricsTool
    result, latency, err = _call(GetFinancialMetricsTool()._run, ticker)
    if err or not result or result.startswith("Error"):
        return {"name": "get_financial_metrics", "passed": False, "latency": latency,
                "detail": err or result}

    checks = {
        "revenue":   bool(re.search(r"Revenue:\s+\$[\d,]+", result)),
        "FCF":       bool(re.search(r"Free Cash Flow:", result)),
        "net income":bool(re.search(r"Net Income:", result)),
        "growth":    bool(re.search(r"Revenue CAGR|growth", result, re.I)),
    }
    passed = all(checks.values())
    detail = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in checks.items())
    return {"name": "get_financial_metrics", "passed": passed, "latency": latency,
            "detail": detail, "checks": checks}


def eval_quarterly_earnings(ticker: str) -> dict:
    from tools.earnings_tools import GetQuarterlyEarningsTool
    result, latency, err = _call(GetQuarterlyEarningsTool()._run, ticker, 8)
    if err or not result or result.startswith("Error"):
        return {"name": "get_quarterly_earnings", "passed": False, "latency": latency,
                "detail": err or result}

    # Count quarter rows in the table (format: "2025-Q3" or "Q3 2025")
    quarters_found = len(re.findall(r"\d{4}-Q[1-4]|Q[1-4]\s+\d{4}", result))
    checks = {
        "has quarters": quarters_found >= 4,
        "has revenue":  bool(re.search(r"\$\s*[\d,]+", result)),
        "has margins":  bool(re.search(r"margin|%", result, re.I)),
    }
    passed = all(checks.values())
    detail = f"{quarters_found} quarters returned, " + ", ".join(
        f"{k}={'✓' if v else '✗'}" for k, v in checks.items())
    return {"name": "get_quarterly_earnings", "passed": passed, "latency": latency,
            "detail": detail, "checks": checks}


def eval_analyst_estimates(ticker: str) -> dict:
    from tools.earnings_tools import GetAnalystEstimatesTool
    result, latency, err = _call(GetAnalystEstimatesTool()._run, ticker)
    if err or not result or result.startswith("Error"):
        return {"name": "get_analyst_estimates", "passed": False, "latency": latency,
                "detail": err or result}

    checks = {
        "has EPS":     bool(re.search(r"EPS|eps", result)),
        "has revenue": bool(re.search(r"[Rr]evenue", result)),
        "has data":    len(result) > 100,
    }
    passed = all(checks.values())
    detail = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in checks.items())
    return {"name": "get_analyst_estimates", "passed": passed, "latency": latency,
            "detail": detail, "checks": checks}


def eval_earnings_surprises(ticker: str) -> dict:
    from tools.earnings_tools import GetEarningsSurprisesTool
    result, latency, err = _call(GetEarningsSurprisesTool()._run, ticker, 8)
    if err or not result or result.startswith("Error"):
        return {"name": "get_earnings_surprises", "passed": False, "latency": latency,
                "detail": err or result}

    checks = {
        "has beat/miss": bool(re.search(r"beat|miss|surprise", result, re.I)),
        "has actual EPS":bool(re.search(r"Actual|actual", result)),
        "has data":      len(result) > 100,
    }
    passed = all(checks.values())
    detail = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in checks.items())
    return {"name": "get_earnings_surprises", "passed": passed, "latency": latency,
            "detail": detail, "checks": checks}


def eval_sec_filings(ticker: str) -> dict:
    from tools.sec_tools import GetSECFilingsTool
    result, latency, err = _call(GetSECFilingsTool()._run, ticker, "10-K", 3)
    if err or not result or result.startswith("Error"):
        return {"name": "get_sec_filings", "passed": False, "latency": latency,
                "detail": err or result}

    checks = {
        "has filings": bool(re.search(r"10-K|10-Q|filing", result, re.I)),
        "has date":    bool(re.search(r"\d{4}-\d{2}-\d{2}|\d{4}", result)),
        "has data":    len(result) > 50,
    }
    passed = all(checks.values())
    detail = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in checks.items())
    return {"name": "get_sec_filings", "passed": passed, "latency": latency,
            "detail": detail, "checks": checks}


TOOL_EVALS = [
    eval_stock_info,
    eval_financial_metrics,
    eval_quarterly_earnings,
    eval_analyst_estimates,
    eval_earnings_surprises,
    eval_sec_filings,
]


def run_part1(tickers: list[str]) -> list[dict]:
    print(header("PART 1 — TOOL-LEVEL DATA EVAL"))
    print(dim("  Calling each data tool directly and checking field completeness.\n"))

    all_results = []

    for ticker in tickers:
        print(f"  {BOLD}Ticker: {ticker}{RESET}")
        ticker_results = []

        for eval_fn in TOOL_EVALS:
            r = eval_fn(ticker)
            ticker_results.append(r)
            all_results.append(r)

            status = ok(f"{r['name']:<30} {r['latency']}s  {r['detail']}") \
                if r["passed"] else \
                fail(f"{r['name']:<30} {r['latency']}s  {r['detail'][:80]}")
            print(f"    {status}")

        passed = sum(1 for r in ticker_results if r["passed"])
        total  = len(ticker_results)
        color  = GREEN if passed == total else (YELLOW if passed >= total * 0.7 else RED)
        print(f"    {color}{BOLD}{passed}/{total} tools passed{RESET}\n")

    # Summary
    total_passed = sum(1 for r in all_results if r["passed"])
    total_all    = len(all_results)
    avg_latency  = round(sum(r["latency"] for r in all_results) / total_all, 2)
    pct          = round(total_passed / total_all * 100)

    print(f"  {BOLD}PART 1 SUMMARY:{RESET} {total_passed}/{total_all} passed ({pct}%)  "
          f"avg latency {avg_latency}s")

    return all_results


# ═════════════════════════════════════════════════════════════════════════════
# PART 2 — End-to-end agent eval
# ═════════════════════════════════════════════════════════════════════════════

def score_earnings_report(report: str, ticker: str) -> list[dict]:
    """Return a list of check dicts for an Earnings report."""
    checks = [
        {
            "name": "report generated",
            "passed": bool(report) and len(report) > 200,
            "detail": f"{len(report)} chars",
        },
        {
            "name": "has quarterly data",
            "passed": bool(re.search(r"Q[1-4]\s*\d{4}|quarter|quarterly", report, re.I)),
            "detail": "quarterly breakdown present",
        },
        {
            "name": "has revenue figures",
            "passed": bool(re.search(r"[Rr]evenue.*\$|\\$.*[Rr]evenue", report)),
            "detail": "revenue numbers present",
        },
        {
            "name": "has EPS data",
            "passed": bool(re.search(r"EPS|earnings per share", report, re.I)),
            "detail": "EPS data present",
        },
        {
            "name": "has analyst estimates / consensus",
            "passed": bool(re.search(r"analyst|estimate|consensus|forecast", report, re.I)),
            "detail": "analyst context present",
        },
        {
            "name": "has investment rating",
            "passed": bool(re.search(r"\b(BUY|SELL|HOLD|OUTPERFORM|UNDERPERFORM)\b", report)),
            "detail": "rating present",
        },
        {
            "name": "sufficient depth (>400 words)",
            "passed": len(report.split()) > 400,
            "detail": f"{len(report.split())} words",
        },
    ]
    return checks


def run_agent_eval(agent_label: str, run_fn, score_fn, ticker: str) -> dict:
    """Run one agent, score its output, print results."""
    print(f"\n  {BOLD}{agent_label} — {ticker}{RESET}")
    print(f"  {dim('Running... (this may take 30-90s)')}")

    report, latency, err = _call(run_fn, ticker)

    if err:
        print(f"    {fail(f'Agent crashed: {err[:120]}')}")
        return {"agent": agent_label, "ticker": ticker, "passed": 0, "total": 0,
                "latency": latency, "crashed": True}

    checks = score_fn(report or "", ticker)

    for c in checks:
        line = ok(f"{c['name']:<45} {dim(c['detail'])}") \
               if c["passed"] else \
               fail(f"{c['name']:<45} {dim(c['detail'])}")
        print(f"    {line}")

    passed = sum(1 for c in checks if c["passed"])
    total  = len(checks)
    pct    = round(passed / total * 100)
    color  = GREEN if pct >= 80 else (YELLOW if pct >= 60 else RED)
    print(f"    {color}{BOLD}Score: {passed}/{total} ({pct}%)  {latency}s{RESET}")

    return {"agent": agent_label, "ticker": ticker, "passed": passed,
            "total": total, "pct": pct, "latency": latency, "crashed": False}


def run_part2(tickers: list[str]) -> list[dict]:
    print(header("PART 2 — END-TO-END AGENT EVAL"))
    print(dim("  Running full agents on each ticker and scoring the final report.\n"))

    from agents.earnings_agent import create_earnings_agent

    earnings_model = os.getenv("EVAL_EARNINGS_MODEL", "claude-haiku-4-5-20251001")
    print(f"  {dim(f'Earnings model: {earnings_model}')}\n")

    earnings_agent = create_earnings_agent(model=earnings_model)

    all_results = []

    for ticker in tickers:
        all_results.append(run_agent_eval(
            "Earnings Agent",
            lambda t: earnings_agent.analyze(t),
            score_earnings_report,
            ticker,
        ))

    # Summary
    completed = [r for r in all_results if not r.get("crashed")]
    if completed:
        avg_pct = round(sum(r["pct"] for r in completed) / len(completed))
        avg_lat = round(sum(r["latency"] for r in completed) / len(completed))
        color   = GREEN if avg_pct >= 80 else (YELLOW if avg_pct >= 60 else RED)
        print(f"\n  {BOLD}PART 2 SUMMARY:{RESET} avg score {color}{avg_pct}%{RESET}  "
              f"avg latency {avg_lat}s  ({len(completed)}/{len(all_results)} agents completed)")

    return all_results


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Finance agent data pipeline eval")
    parser.add_argument("tickers", nargs="*", default=["AAPL", "NVDA"],
                        help="Tickers to evaluate (default: AAPL NVDA)")
    parser.add_argument("--part1", action="store_true", help="Tool-level eval only")
    parser.add_argument("--part2", action="store_true", help="Agent eval only")
    args = parser.parse_args()

    run_p1 = args.part1 or (not args.part1 and not args.part2)
    run_p2 = args.part2 or (not args.part1 and not args.part2)

    tickers = [t.upper() for t in args.tickers]

    print(f"\n{BOLD}{'=' * 60}")
    print("  FINANCE AGENT — DATA PIPELINE EVAL")
    print(f"  Tickers: {', '.join(tickers)}")
    print(f"{'=' * 60}{RESET}")

    if run_p1:
        run_part1(tickers)

    if run_p2:
        run_part2(tickers)

    print(f"\n{BOLD}{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    main()
