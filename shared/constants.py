"""
Shared constants for the Finance DCF Agent system.

This module contains constants used across multiple modules including
tool descriptions, phase mappings, and other configuration values.
"""

from typing import Dict

# Friendly tool descriptions for UI display
TOOL_DESCRIPTIONS: Dict[str, str] = {
    'get_quick_data': '[Fetching] financial metrics',
    'get_date_context': '[Checking] time period context',
    'get_stock_info': '[Getting] company information',
    'get_financial_metrics': '[Retrieving] historical financials',
    'search_web': '[Searching] the web for current data',
    'perform_dcf_analysis': '[Running] DCF valuation model',
    'calculate': '[Performing] calculation',
    'get_recent_news': '[Fetching] recent news',
    'compare_companies': '[Comparing] companies',
    'analyze_industry': '[Analyzing] industry structure',
    'analyze_competitors': '[Analyzing] competitive landscape',
    'analyze_moat': '[Evaluating] competitive moat',
    'analyze_management': '[Assessing] management quality',
    'get_market_overview': '[Getting] market overview',
    'get_sector_rotation': '[Analyzing] sector rotation',
    'classify_market_regime': '[Classifying] market regime',
    'get_market_news': '[Fetching] market news',
    'screen_stocks': '[Screening] stocks',
    'get_value_stocks': '[Finding] value stocks',
    'get_growth_stocks': '[Finding] growth stocks',
    'get_dividend_stocks': '[Finding] dividend stocks',
    'calculate_portfolio_metrics': '[Calculating] portfolio metrics',
    'analyze_diversification': '[Analyzing] diversification',
    'identify_tax_loss_harvesting': '[Finding] tax loss opportunities',
    'get_quarterly_earnings': '[Fetching] quarterly earnings data',
    'get_analyst_estimates': '[Getting] analyst consensus estimates',
    'get_earnings_surprises': '[Analyzing] earnings surprises',
    'analyze_earnings_guidance': '[Reviewing] earnings call guidance',
    'compare_peer_earnings': '[Comparing] peer earnings',
    'get_price_targets': '[Getting] analyst price targets',
    'get_analyst_ratings': '[Fetching] analyst rating changes',
    'get_earnings_call_insights': '[Analyzing] earnings call transcripts',
    'get_sec_filings': '[Fetching] SEC EDGAR filings',
    'analyze_sec_filing': '[Analyzing] SEC filing content',
    'get_sec_financials': '[Retrieving] SEC XBRL financials',
}

# Map tools to reasoning phases for better UI organization
TOOL_TO_PHASE: Dict[str, str] = {
    'get_stock_info': 'gathering_data',
    'get_financial_metrics': 'gathering_data',
    'get_quick_data': 'gathering_data',
    'get_date_context': 'gathering_data',
    'get_market_overview': 'gathering_data',
    'get_sector_rotation': 'gathering_data',
    'search_web': 'searching',
    'get_recent_news': 'reviewing',
    'get_market_news': 'reviewing',
    'screen_stocks': 'reviewing',
    'get_value_stocks': 'reviewing',
    'get_growth_stocks': 'reviewing',
    'get_dividend_stocks': 'reviewing',
    'analyze_industry': 'analyzing',
    'analyze_competitors': 'analyzing',
    'analyze_moat': 'analyzing',
    'analyze_management': 'analyzing',
    'compare_companies': 'analyzing',
    'classify_market_regime': 'analyzing',
    'analyze_diversification': 'analyzing',
    'perform_dcf_analysis': 'calculating',
    'calculate': 'calculating',
    'calculate_portfolio_metrics': 'calculating',
    'identify_tax_loss_harvesting': 'calculating',
    'get_sec_filings': 'gathering_data',
    'analyze_sec_filing': 'analyzing',
    'get_sec_financials': 'gathering_data',
}
