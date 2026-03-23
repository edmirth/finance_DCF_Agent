"""
Financial Data Fetcher using Financial Datasets AI API and FMP API
"""
import requests
import os
import time
import threading
from typing import Dict, Optional, List
import logging
from shared.retry_utils import retry_with_backoff, RetryConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# FMP API Configuration
FMP_BASE_URL = "https://financialmodelingprep.com/stable"


class FinancialDataFetcher:
    """Fetches financial data for DCF analysis using financialdatasets.ai API

    Implements singleton pattern to share cache across all instances.
    Thread-safe cache operations for concurrent access.
    """

    BASE_URL = "https://api.financialdatasets.ai"
    _instance = None
    _shared_cache = {}
    _cache_lock = threading.RLock()  # Thread-safe cache access
    _instance_lock = threading.Lock()  # Thread-safe singleton initialization
    _thread_local = threading.local()  # Per-thread error state (avoids cross-request races)

    def __new__(cls, api_key: Optional[str] = None):
        """Singleton pattern to ensure cache is shared across all instances (thread-safe)"""
        # Double-checked locking pattern for thread-safe singleton
        if cls._instance is None:
            with cls._instance_lock:
                # Check again inside the lock to prevent race condition
                if cls._instance is None:
                    cls._instance = super(FinancialDataFetcher, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the fetcher with API key

        Args:
            api_key: Financial Datasets API key (if not provided, will use FINANCIAL_DATASETS_API_KEY env var)
        """
        # Only initialize once (singleton pattern).
        # If a different explicit key is passed after initialisation (e.g., in tests or
        # multi-key scenarios), update the key so it is not silently ignored.
        if self._initialized:
            resolved_key = api_key or os.getenv("FINANCIAL_DATASETS_API_KEY")
            if resolved_key and resolved_key != self.api_key:
                logger.info("FinancialDataFetcher: updating API key on existing singleton instance.")
                self.api_key = resolved_key
                self.headers["X-API-KEY"] = self.api_key
            return

        self.api_key = api_key or os.getenv("FINANCIAL_DATASETS_API_KEY")
        if not self.api_key:
            raise ValueError("Financial Datasets API key not found. Set FINANCIAL_DATASETS_API_KEY environment variable.")

        self.headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

        # FMP API key (optional, for DCF comparison)
        self.fmp_api_key = os.getenv("FMP_API_KEY")
        if not self.fmp_api_key:
            logger.warning("FMP_API_KEY not set. FMP DCF comparison features will be unavailable.")

        # Use class-level shared cache instead of instance cache
        self.cache = self._shared_cache
        self.cache_ttl = 900  # 15 minutes TTL for financial data
        self._initialized = True

    @property
    def last_error_type(self) -> Optional[str]:
        """Per-thread error type — prevents concurrent requests from overwriting each other."""
        return getattr(self._thread_local, 'last_error_type', None)

    @last_error_type.setter
    def last_error_type(self, value: Optional[str]) -> None:
        self._thread_local.last_error_type = value

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Retrieve data from cache if valid (thread-safe)"""
        with self._cache_lock:  # Bug #14 Fix: Thread-safe read
            if cache_key in self.cache:
                cached_entry = self.cache[cache_key]
                if time.time() - cached_entry['timestamp'] < self.cache_ttl:
                    logger.info(f"Cache hit for {cache_key}")
                    return cached_entry['data']
                else:
                    # Cache expired, remove it
                    logger.info(f"Cache expired for {cache_key}")
                    del self.cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, data: Dict) -> None:
        """Save data to cache with timestamp (thread-safe)"""
        with self._cache_lock:  # Bug #14 Fix: Thread-safe write
            self.cache[cache_key] = {
                'data': data,
                'timestamp': time.time()
            }
            logger.info(f"Cached {cache_key}")

    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0
    ))
    def _make_request_with_retry(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Internal method with retry logic (raises exceptions)"""
        url = f"{self.BASE_URL}{endpoint}"
        logger.info(f"Making GET request to {endpoint} with params: {params}")
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make API GET request with error handling and retry logic"""
        self.last_error_type = None  # Reset before each request
        try:
            return self._make_request_with_retry(endpoint, params)
        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response is not None:
                status = e.response.status_code
                if status == 401:
                    logger.error(f"Invalid API key for Financial Datasets")
                    self.last_error_type = "auth_failure"
                elif status == 404:
                    logger.error(f"Ticker not found: {params.get('ticker', 'unknown')}")
                    self.last_error_type = "not_found"
                elif status == 402:
                    logger.error(f"This endpoint requires a paid subscription")
                    self.last_error_type = "auth_failure"
                else:
                    logger.error(f"HTTP error {status}: {e}")
                    self.last_error_type = "api_failure"
            else:
                self.last_error_type = "api_failure"
            return None
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.error(f"Network error making request to {endpoint}: {e}")
            self.last_error_type = "api_failure"
            return None
        except Exception as e:
            logger.error(f"Error making request to {endpoint}: {e}")
            self.last_error_type = "api_failure"
            return None

    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0
    ))
    def _make_post_request_with_retry(self, endpoint: str, payload: Dict) -> Dict:
        """Internal method with retry logic (raises exceptions)"""
        url = f"{self.BASE_URL}{endpoint}"
        logger.info(f"Making POST request to {endpoint} with payload: {payload}")
        response = requests.post(url, headers=self.headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def _make_post_request(self, endpoint: str, payload: Dict) -> Optional[Dict]:
        """Make API POST request with error handling and retry logic"""
        try:
            return self._make_post_request_with_retry(endpoint, payload)
        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 401:
                    logger.error(f"Invalid API key for Financial Datasets")
                elif e.response.status_code == 402:
                    logger.error(f"This endpoint requires a paid subscription")
                elif e.response.status_code == 400:
                    logger.error(f"Bad request - invalid filter parameters")
                else:
                    logger.error(f"HTTP error {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error making POST request to {endpoint}: {e}")
            return None

    def get_stock_info(self, ticker: str) -> Dict:
        """Get comprehensive stock information"""
        # Check cache first
        cache_key = f"stock_info_{ticker.upper()}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Get company facts for basic information
            company_data = self._make_request("/company/facts", params={"ticker": ticker})

            if not company_data or "company_facts" not in company_data:
                logger.error(f"No company facts data returned for {ticker}")
                return {}

            facts = company_data["company_facts"]

            # Get market cap directly from company facts (it's already there!)
            market_cap = facts.get("market_cap", 0) or 0

            # Calculate current price from market cap and shares
            current_price = 0
            shares = facts.get("weighted_average_shares", 0) or 0

            if market_cap and shares:
                current_price = market_cap / shares

            logger.info(f"Stock info for {ticker}: market_cap={market_cap}, shares={shares}, price={current_price}")

            # Fallback: Financial Datasets often omits real-time market_cap/price.
            # Use FMP batch-quote (free tier) to fill any zeros.
            if (not market_cap or not current_price) and self.fmp_api_key:
                try:
                    resp = requests.get(
                        f"{FMP_BASE_URL}/batch-quote",
                        params={"symbols": ticker, "apikey": self.fmp_api_key},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        quote_list = resp.json()
                        if isinstance(quote_list, list) and quote_list:
                            quote = quote_list[0]
                            if not market_cap:
                                market_cap = quote.get("marketCap", 0) or 0
                            if not current_price:
                                current_price = quote.get("price", 0) or 0
                            logger.info(
                                f"FMP batch-quote fallback for {ticker}: "
                                f"price={current_price}, mktcap={market_cap}"
                            )
                except Exception as _e:
                    logger.warning(f"FMP batch-quote fallback failed for {ticker}: {_e}")

            result = {
                "symbol": ticker,
                "company_name": facts.get("name", "Unknown"),
                "sector": facts.get("sector", "Unknown"),
                "industry": facts.get("industry", "Unknown"),
                "market_cap": market_cap,
                "current_price": current_price,
                "currency": "USD",  # Default to USD for US stocks
            }

            # Cache the result
            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error fetching stock info for {ticker}: {e}")
            return {}

    def get_financial_statements(self, ticker: str) -> Dict:
        """Fetch income statement, balance sheet, and cash flow"""
        # Check cache first
        cache_key = f"financial_statements_{ticker.upper()}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Get annual financial statements (last 5 years)
            params = {
                "ticker": ticker,
                "period": "annual",
                "limit": 5
            }

            data = self._make_request("/financials", params=params)

            if not data:
                logger.error(f"No financial statements data returned for {ticker}")
                return {}

            # The API returns data in {"financials": {income_statements: [], balance_sheets: [], cash_flow_statements: []}} format
            financials_dict = data.get("financials", {})

            if not financials_dict:
                logger.error(f"Empty financials dict for {ticker}")
                return {}

            # Extract the arrays directly
            income_statements = financials_dict.get("income_statements", [])
            balance_sheets = financials_dict.get("balance_sheets", [])
            cash_flow_statements = financials_dict.get("cash_flow_statements", [])

            logger.info(f"Retrieved financials for {ticker}: {len(income_statements)} income statements, {len(balance_sheets)} balance sheets, {len(cash_flow_statements)} cash flow statements")

            result = {
                "income_statements": income_statements,
                "balance_sheets": balance_sheets,
                "cash_flow_statements": cash_flow_statements
            }

            # Cache the result
            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error fetching financial statements for {ticker}: {e}")
            return {}

    def get_quarterly_financials(self, ticker: str, limit: int = 8) -> Dict:
        """
        Fetch quarterly financial statements (income, balance sheet, cash flow)

        Args:
            ticker: Stock ticker symbol
            limit: Number of quarters to fetch (default: 8 = 2 years)

        Returns:
            Dict with quarterly income_statements, balance_sheets, cash_flow_statements
        """
        # Check cache first
        cache_key = f"quarterly_financials_{ticker.upper()}_{limit}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Get quarterly financial statements
            params = {
                "ticker": ticker,
                "period": "quarterly",  # KEY CHANGE - quarterly instead of annual
                "limit": limit
            }

            data = self._make_request("/financials", params=params)

            if not data:
                logger.error(f"No quarterly financial statements data returned for {ticker}")
                return {}

            # The API returns data in {"financials": {income_statements: [], balance_sheets: [], cash_flow_statements: []}} format
            financials_dict = data.get("financials", {})

            if not financials_dict:
                logger.error(f"Empty quarterly financials dict for {ticker}")
                return {}

            # Extract the arrays directly
            income_statements = financials_dict.get("income_statements", [])
            balance_sheets = financials_dict.get("balance_sheets", [])
            cash_flow_statements = financials_dict.get("cash_flow_statements", [])

            logger.info(f"Retrieved quarterly financials for {ticker}: {len(income_statements)} income statements, {len(balance_sheets)} balance sheets, {len(cash_flow_statements)} cash flow statements")

            result = {
                "income_statements": income_statements,
                "balance_sheets": balance_sheets,
                "cash_flow_statements": cash_flow_statements
            }

            # Cache the result
            self._save_to_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error fetching quarterly financial statements for {ticker}: {e}")
            return {}

    def get_financial_metrics_api(self, ticker: str, period: str = "annual", limit: int = 1) -> List[Dict]:
        """
        Fetch pre-computed financial metrics from the /financial-metrics endpoint.

        Returns ratios like margins, growth rates, returns, valuation multiples,
        and leverage / liquidity metrics — so callers don't have to compute them
        manually from raw statements.

        Args:
            ticker: Stock ticker symbol
            period: "annual", "quarterly", or "ttm"
            limit: Number of periods to fetch (default 1 = most recent)

        Returns:
            List of metric dicts (most recent first), empty list on failure
        """
        cache_key = f"financial_metrics_api_{ticker.upper()}_{period}_{limit}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        params = {"ticker": ticker, "period": period, "limit": limit}
        data = self._make_request("/financial-metrics", params=params)

        if not data:
            logger.warning(f"No /financial-metrics data for {ticker}")
            return []

        metrics_list = data.get("financial_metrics", [])
        if not metrics_list:
            logger.warning(f"Empty financial_metrics list for {ticker}")
            return []

        logger.info(f"Fetched {len(metrics_list)} period(s) of /financial-metrics for {ticker}")
        self._save_to_cache(cache_key, metrics_list)
        return metrics_list

    def get_key_metrics(self, ticker: str) -> Dict:
        """Extract key metrics needed for DCF analysis"""
        # Check cache first
        cache_key = f"key_metrics_{ticker.upper()}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Get company facts for basic info
            company_data = self._make_request("/company/facts", params={"ticker": ticker})

            if not company_data or "company_facts" not in company_data:
                logger.error(f"No company facts data for {ticker}")
                return {}

            facts = company_data["company_facts"]

            # Get financial statements
            statements = self.get_financial_statements(ticker)
            income_statements = statements.get("income_statements", [])
            balance_sheets = statements.get("balance_sheets", [])
            cash_flow_statements = statements.get("cash_flow_statements", [])

            # Initialize metrics
            metrics = {
                "ticker": ticker,
                "beta": 1.0,  # Default beta since not provided by API
                "shares_outstanding": facts.get("weighted_average_shares", 0) or 0,
            }

            # Extract historical revenue, income, and operating metrics from income statements
            if income_statements:
                revenues = []
                net_incomes = []
                ebits = []
                gross_profits = []
                interest_expenses = []
                income_taxes = []
                pretax_incomes = []
                fiscal_years = []

                for stmt in income_statements[:5]:  # Last 5 years
                    revenue = stmt.get("revenue", 0) or stmt.get("revenues", 0) or 0
                    net_income = stmt.get("net_income", 0) or 0
                    ebit = stmt.get("operating_income", 0) or stmt.get("ebit", 0) or 0
                    gross_profit = (
                        stmt.get("gross_profit", 0) or stmt.get("gross_income", 0)
                        or stmt.get("grossProfit", 0) or 0
                    )
                    interest = stmt.get("interest_expense", 0) or 0
                    tax = stmt.get("income_tax_expense", 0) or 0
                    pretax = stmt.get("pretax_income", 0) or stmt.get("income_before_tax", 0) or 0

                    # Extract fiscal year from various possible fields
                    fiscal_year = stmt.get("fiscal_period", "") or stmt.get("report_period", "")
                    if fiscal_year and isinstance(fiscal_year, str):
                        # Extract year from strings like "2025-FY" or "2025-09-27"
                        fiscal_year = fiscal_year.split("-")[0]

                    revenues.append(float(revenue))
                    net_incomes.append(float(net_income))
                    ebits.append(float(ebit))
                    gross_profits.append(float(gross_profit))
                    interest_expenses.append(float(interest))
                    income_taxes.append(float(tax))
                    pretax_incomes.append(float(pretax))
                    fiscal_years.append(str(fiscal_year) if fiscal_year else "")

                metrics["historical_revenue"] = revenues
                metrics["latest_revenue"] = revenues[0] if revenues else 0
                metrics["historical_net_income"] = net_incomes
                metrics["latest_net_income"] = net_incomes[0] if net_incomes else 0
                metrics["historical_ebit"] = ebits
                metrics["latest_ebit"] = ebits[0] if ebits else 0
                metrics["historical_gross_profit"] = gross_profits
                metrics["latest_gross_profit"] = gross_profits[0] if gross_profits else 0
                metrics["latest_interest_expense"] = interest_expenses[0] if interest_expenses else 0
                metrics["historical_years"] = fiscal_years

                # Calculate effective tax rate.
                # Allow negative income_taxes (tax benefit/credit) when pretax income is
                # positive — the downstream tool clamps negative effective rates to 0%.
                # Only fall back to the 21% default when pretax income is zero or negative,
                # since dividing by a non-positive pretax figure produces a meaningless rate.
                if pretax_incomes[0] > 0:
                    metrics["effective_tax_rate"] = income_taxes[0] / pretax_incomes[0]
                else:
                    metrics["effective_tax_rate"] = 0.21  # Default to US federal rate

                # Update shares outstanding from latest income statement if available
                latest_shares = income_statements[0].get("weighted_average_shares", 0)
                if latest_shares:
                    metrics["shares_outstanding"] = float(latest_shares)

                logger.info(f"Revenue data for {ticker}: {len(revenues)} years, latest={metrics['latest_revenue']}")
                logger.info(f"EBIT data for {ticker}: latest={metrics['latest_ebit']}")
            else:
                logger.warning(f"No income statements found for {ticker}")
                metrics["historical_revenue"] = []
                metrics["latest_revenue"] = 0
                metrics["historical_net_income"] = []
                metrics["latest_net_income"] = 0

            # Extract historical free cash flow, D&A, and CapEx
            if cash_flow_statements:
                free_cash_flows = []
                depreciation_amortization = []
                capex_values = []

                for stmt in cash_flow_statements[:5]:
                    fcf = stmt.get("free_cash_flow", 0) or 0
                    da = stmt.get("depreciation_and_amortization", 0) or stmt.get("depreciation_amortization", 0) or 0
                    capex = abs(stmt.get("capital_expenditure", 0) or stmt.get("capex", 0) or stmt.get("purchase_of_ppe", 0) or 0)

                    free_cash_flows.append(float(fcf))
                    depreciation_amortization.append(float(da))
                    capex_values.append(float(capex))

                metrics["historical_fcf"] = free_cash_flows
                metrics["latest_fcf"] = free_cash_flows[0] if free_cash_flows else 0
                metrics["latest_depreciation_amortization"] = depreciation_amortization[0] if depreciation_amortization else 0
                metrics["latest_capex"] = capex_values[0] if capex_values else 0

                logger.info(f"FCF data for {ticker}: {len(free_cash_flows)} years, latest={metrics['latest_fcf']}")
                logger.info(f"D&A for {ticker}: latest={metrics['latest_depreciation_amortization']}")
                logger.info(f"CapEx for {ticker}: latest={metrics['latest_capex']}")
            else:
                logger.warning(f"No cash flow statements found for {ticker}")
                metrics["historical_fcf"] = []
                metrics["latest_fcf"] = 0
                metrics["latest_depreciation_amortization"] = 0
                metrics["latest_capex"] = 0

            # Extract debt, cash, and working capital from balance sheet
            if balance_sheets:
                latest_bs = balance_sheets[0]

                # Total debt
                total_debt = latest_bs.get("total_debt", 0) or 0
                metrics["total_debt"] = float(total_debt)

                # Cash and cash equivalents
                cash = latest_bs.get("cash_and_equivalents", 0) or latest_bs.get("cash_and_cash_equivalents", 0) or 0
                metrics["cash_and_equivalents"] = float(cash)

                # Shareholders equity (for book value)
                shareholders_equity = (
                    latest_bs.get("shareholders_equity", 0)
                    or latest_bs.get("total_equity", 0)
                    or latest_bs.get("stockholders_equity", 0)
                    or latest_bs.get("total_shareholders_equity", 0)
                    or 0
                )
                metrics["shareholders_equity"] = float(shareholders_equity)

                # Current assets and liabilities for working capital
                current_assets = latest_bs.get("current_assets", 0) or latest_bs.get("total_current_assets", 0) or 0
                current_liabilities = latest_bs.get("current_liabilities", 0) or latest_bs.get("total_current_liabilities", 0) or 0
                metrics["current_assets"] = float(current_assets)
                metrics["current_liabilities"] = float(current_liabilities)
                metrics["net_working_capital"] = float(current_assets - current_liabilities)

                logger.info(f"Balance sheet for {ticker}: debt={total_debt}, cash={cash}, NWC={metrics['net_working_capital']}")
            else:
                logger.warning(f"No balance sheets found for {ticker}")
                metrics["total_debt"] = 0
                metrics["cash_and_equivalents"] = 0

            # ----------------------------------------------------------------
            # Enrich with pre-computed ratios from /financial-metrics API
            # ----------------------------------------------------------------
            api_metrics = self.get_financial_metrics_api(ticker, period="annual", limit=1)
            if api_metrics:
                latest = api_metrics[0]

                # Growth rates — prefer API over manual CAGR calculation
                metrics["revenue_growth_rate"] = latest.get("revenue_growth")
                metrics["fcf_growth_rate"] = latest.get("free_cash_flow_growth")
                metrics["earnings_growth_rate"] = latest.get("earnings_growth")
                metrics["ebitda_growth_rate"] = latest.get("ebitda_growth")
                metrics["operating_income_growth_rate"] = latest.get("operating_income_growth")

                # Profitability margins
                metrics["gross_margin"] = latest.get("gross_margin")
                metrics["operating_margin"] = latest.get("operating_margin")
                metrics["net_margin"] = latest.get("net_margin")
                metrics["fcf_margin_api"] = None  # not a standard field on this endpoint

                # Return metrics
                metrics["return_on_equity"] = latest.get("return_on_equity")
                metrics["return_on_assets"] = latest.get("return_on_assets")
                metrics["return_on_invested_capital"] = latest.get("return_on_invested_capital")

                # Valuation multiples
                metrics["enterprise_value_api"] = latest.get("enterprise_value")
                metrics["price_to_earnings"] = latest.get("price_to_earnings_ratio")
                metrics["price_to_book"] = latest.get("price_to_book_ratio")
                metrics["price_to_sales"] = latest.get("price_to_sales_ratio")
                metrics["ev_to_ebitda"] = latest.get("enterprise_value_to_ebitda_ratio")
                metrics["ev_to_revenue"] = latest.get("enterprise_value_to_revenue_ratio")
                metrics["peg_ratio"] = latest.get("peg_ratio")
                metrics["fcf_yield"] = latest.get("free_cash_flow_yield")

                # Leverage & liquidity
                metrics["debt_to_equity_ratio"] = latest.get("debt_to_equity")
                metrics["debt_to_assets_ratio"] = latest.get("debt_to_assets")
                metrics["interest_coverage_ratio"] = latest.get("interest_coverage")
                metrics["current_ratio"] = latest.get("current_ratio")
                metrics["quick_ratio"] = latest.get("quick_ratio")
                metrics["cash_ratio"] = latest.get("cash_ratio")

                # Per-share metrics
                metrics["earnings_per_share"] = latest.get("earnings_per_share")
                metrics["book_value_per_share"] = latest.get("book_value_per_share")
                metrics["fcf_per_share"] = latest.get("free_cash_flow_per_share")

                # Efficiency
                metrics["asset_turnover"] = latest.get("asset_turnover")
                metrics["working_capital_turnover"] = latest.get("working_capital_turnover")

                logger.info(f"Merged /financial-metrics API ratios for {ticker}")
            else:
                logger.warning(f"Could not enrich key metrics with /financial-metrics API for {ticker}")

            # ----------------------------------------------------------------
            # Standardise margins against our own income-statement EBIT.
            # The /financial-metrics API may compute operating_margin from a
            # broader "EBIT" figure that includes other income/expense items
            # (e.g. NVDA: operating_income=$130B vs ebit=$141B → 60.4% vs 65.6%).
            # We always prefer operating_income for DCF and force consistency.
            # ----------------------------------------------------------------
            rev = metrics.get("latest_revenue", 0) or 0
            if rev > 0:
                raw_op_margin = (metrics.get("latest_ebit", 0) or 0) / rev
                api_op_margin = metrics.get("operating_margin")
                if api_op_margin is not None and abs(raw_op_margin - api_op_margin) > 0.02:
                    logger.info(
                        f"{ticker}: /financial-metrics operating_margin ({api_op_margin:.2%}) "
                        f"differs from operating_income/revenue ({raw_op_margin:.2%}) by "
                        f"{abs(raw_op_margin - api_op_margin)*100:.1f} pp — "
                        f"using income-statement value for DCF consistency"
                    )
                metrics["operating_margin"] = raw_op_margin

                raw_net_margin = (metrics.get("latest_net_income", 0) or 0) / rev
                metrics.setdefault("net_margin", raw_net_margin)

                raw_gross_margin = (metrics.get("latest_gross_profit", 0) or 0) / rev
                metrics.setdefault("gross_margin", raw_gross_margin)

            # Cache the result before returning
            self._save_to_cache(cache_key, metrics)
            return metrics

        except Exception as e:
            logger.error(f"Error extracting key metrics for {ticker}: {e}")
            return {}

    def calculate_historical_growth_rate(self, values: List[float]) -> float:
        """Calculate CAGR from historical values.

        Values are expected newest-first (index 0 = most recent year).
        Zeros and negatives are excluded from the endpoints, but the actual
        time span (number of years between the first and last usable value) is
        preserved.  The previous approach used len(clean_values)-1 as the
        exponent, which underestimates the period when negatives exist mid-series
        and therefore overstates the growth rate.
        """
        if not values or len(values) < 2:
            return 0.0

        # Find the most-recent and oldest indices that have positive values.
        # Preserving the original indices keeps the time span correct.
        indexed = [(i, v) for i, v in enumerate(values) if v > 0]
        if len(indexed) < 2:
            return 0.0

        # index 0 = most recent, higher index = older
        recent_idx, recent_val = indexed[0]    # smallest index → newest
        oldest_idx, oldest_val = indexed[-1]   # largest index → oldest

        num_years = oldest_idx - recent_idx    # actual elapsed years
        if num_years <= 0:
            return 0.0

        try:
            cagr = (pow(recent_val / oldest_val, 1 / num_years) - 1)
            return round(cagr, 4)
        except (ZeroDivisionError, ValueError, OverflowError) as e:
            logger.warning(f"CAGR calculation failed: {e}")
            return 0.0

    def screen_stocks(self, filters: List[Dict], limit: int = 50, sort_by: Optional[str] = None) -> List[Dict]:
        """
        Screen stocks based on financial criteria using Financial Datasets API

        Args:
            filters: List of filter dicts with {field, operator, value}
                    Example: [{"field": "revenue", "operator": "gte", "value": 1000000000}]
            limit: Maximum number of results to return (default: 50)
            sort_by: Optional field to sort by (e.g., 'pe_ratio', 'revenue', 'net_income')
                    If None, results will be diverse across the alphabet

        Returns:
            List of companies matching criteria with ticker and financial metrics
        """
        # Create cache key from filters, limit, and sort_by
        import hashlib
        import json
        import random
        filter_str = json.dumps(filters, sort_keys=True)
        cache_key = f"screener_{hashlib.md5(filter_str.encode()).hexdigest()}_{limit}_{sort_by or 'diverse'}"

        # Check cache first
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            # Fetch a larger pool of results from API to ensure diversity
            # API returns alphabetically sorted results, so we need more to avoid only getting "A" stocks
            fetch_limit = min(500, max(limit * 10, 100))  # Fetch 10x what we need, up to 500

            payload = {
                "filters": filters,
                "limit": fetch_limit
            }

            # Make POST request to screener endpoint
            response = self._make_post_request("/financials/search/screener", payload)

            if not response:
                logger.error("No response from screener API")
                return []

            # Extract search results (API returns 'results' key, not 'search_results')
            results = response.get("results", [])

            if not results:
                logger.info("No stocks matched the screening criteria")
                return []

            logger.info(f"Screener found {len(results)} stocks matching criteria (returning {min(limit, len(results))})")

            # Sort or diversify results
            if sort_by and sort_by in results[0]:
                # Sort by specified field (ascending for pe_ratio, descending for revenue/net_income)
                reverse_sort = sort_by in ['revenue', 'net_income', 'market_cap']
                try:
                    sorted_results = sorted(
                        results,
                        key=lambda x: x.get(sort_by, 0) or 0,
                        reverse=reverse_sort
                    )
                    final_results = sorted_results[:limit]
                    logger.info(f"Sorted results by {sort_by} ({'desc' if reverse_sort else 'asc'})")
                except Exception as e:
                    logger.warning(f"Could not sort by {sort_by}: {e}. Using diverse sampling instead.")
                    final_results = self._diversify_results(results, limit)
            else:
                # Diversify results across alphabet to avoid only showing "A" stocks
                final_results = self._diversify_results(results, limit)

            # Cache the results
            self._save_to_cache(cache_key, final_results)

            return final_results

        except Exception as e:
            logger.error(f"Error screening stocks: {e}")
            return []

    def _diversify_results(self, results: List[Dict], limit: int) -> List[Dict]:
        """
        Diversify results across alphabet to avoid alphabetical bias

        Takes every Nth result to ensure diversity across the alphabet
        """
        if len(results) <= limit:
            return results

        # Calculate step size to sample evenly across all results
        step = len(results) / limit
        diverse_results = []

        for i in range(limit):
            index = int(i * step)
            if index < len(results):
                diverse_results.append(results[index])

        logger.info(f"Diversified {len(results)} results to {len(diverse_results)} evenly distributed stocks")
        return diverse_results

    # =========================================================================
    # FMP DCF API Methods (for cross-validation and levered DCF)
    # =========================================================================

    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=2.0,
        max_delay=60.0
    ))
    def _make_fmp_request_with_retry(self, endpoint: str, params: Dict) -> Dict:
        """Internal method with retry logic (raises exceptions)"""
        url = f"{FMP_BASE_URL}{endpoint}"
        logger.info(f"Making FMP request to {endpoint}")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        # FMP returns list for most endpoints
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        elif isinstance(data, dict):
            return data
        else:
            # Raise so the retry decorator can retry on transient empty responses
            raise requests.exceptions.HTTPError(
                f"Empty response from FMP for {endpoint}"
            )

    def _make_fmp_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make FMP API request with error handling and retry logic"""
        if not self.fmp_api_key:
            logger.error("FMP API key not configured. Cannot make FMP requests.")
            return None

        if params is None:
            params = {}
        params["apikey"] = self.fmp_api_key

        try:
            return self._make_fmp_request_with_retry(endpoint, params)
        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 401:
                    logger.error("Invalid FMP API key")
                elif e.response.status_code == 403:
                    logger.error("FMP API endpoint requires higher subscription tier")
                else:
                    logger.error(f"FMP HTTP error {e.response.status_code}: {e}")
            else:
                logger.warning(f"FMP request failed for {endpoint}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error making FMP request to {endpoint}: {e}")
            return None

    def get_fmp_dcf(self, ticker: str) -> Dict:
        """
        Fetch FMP's pre-calculated DCF value (standard unlevered DCF).

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with dcf, stock_price, date fields
        """
        cache_key = f"fmp_dcf_{ticker.upper()}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        data = self._make_fmp_request("/discounted-cash-flow", {"symbol": ticker})

        if data:
            result = {
                "ticker": ticker,
                "dcf_value": data.get("dcf", 0),
                "stock_price": data.get("Stock Price", data.get("stockPrice", 0)),
                "date": data.get("date", ""),
            }
            self._save_to_cache(cache_key, result)
            logger.info(f"FMP DCF for {ticker}: ${result['dcf_value']:.2f}")
            return result

        return {"ticker": ticker, "dcf_value": None, "error": "Could not fetch FMP DCF"}

    def get_fmp_levered_dcf(self, ticker: str) -> Dict:
        """
        Fetch FMP's levered DCF (post-debt valuation, FCFE-based).

        The levered DCF accounts for debt by:
        - Discounting Free Cash Flow to Equity (after debt payments)
        - Using Cost of Equity as discount rate (not WACC)

        This is more appropriate for highly leveraged companies.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with levered_dcf, stock_price, date fields
        """
        cache_key = f"fmp_levered_dcf_{ticker.upper()}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        data = self._make_fmp_request("/levered-discounted-cash-flow", {"symbol": ticker})

        if data:
            result = {
                "ticker": ticker,
                "levered_dcf_value": data.get("dcf", 0),
                "stock_price": data.get("Stock Price", data.get("stockPrice", 0)),
                "date": data.get("date", ""),
            }
            self._save_to_cache(cache_key, result)
            logger.info(f"FMP Levered DCF for {ticker}: ${result['levered_dcf_value']:.2f}")
            return result

        return {"ticker": ticker, "levered_dcf_value": None, "error": "Could not fetch FMP Levered DCF"}

    def get_fmp_custom_dcf(self, ticker: str, assumptions: Dict) -> Dict:
        """
        Run custom DCF with specified assumptions via FMP's Custom DCF Advanced API.

        This allows sending our assumptions to FMP for an independent calculation
        to validate our internal DCF implementation.

        Args:
            ticker: Stock ticker symbol
            assumptions: Dict with DCF parameters:
                - revenueGrowthPct: Revenue growth rate (e.g., 0.10 for 10%)
                - ebitdaPct: EBITDA margin (e.g., 0.25 for 25%)
                - depreciationAndAmortizationPct: D&A as % of revenue
                - capitalExpenditurePct: CapEx as % of revenue
                - taxRate: Tax rate (e.g., 0.21 for 21%)
                - longTermGrowthRate: Terminal growth rate
                - riskFreeRate: Risk-free rate
                - marketRiskPremium: Market risk premium
                - beta: Stock beta
                - costOfDebt: Cost of debt

        Returns:
            Dict with custom DCF results
        """
        cache_key = f"fmp_custom_dcf_{ticker.upper()}_{hash(frozenset(assumptions.items()))}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        # Build params from assumptions
        params = {"symbol": ticker}

        # Map our assumption names to FMP parameter names
        param_mapping = {
            "revenue_growth_rate": "revenueGrowthPct",
            "ebitda_margin": "ebitdaPct",
            "depreciation_to_revenue": "depreciationAndAmortizationPct",
            "capex_to_revenue": "capitalExpenditurePct",
            "tax_rate": "taxRate",
            "terminal_growth_rate": "longTermGrowthRate",
            "risk_free_rate": "riskFreeRate",
            "market_risk_premium": "marketRiskPremium",
            "beta": "beta",
            "cost_of_debt": "costOfDebt",
        }

        for our_key, fmp_key in param_mapping.items():
            if our_key in assumptions and assumptions[our_key] is not None:
                params[fmp_key] = assumptions[our_key]

        data = self._make_fmp_request("/custom-discounted-cash-flow", params)

        if data:
            result = {
                "ticker": ticker,
                "custom_dcf_value": data.get("dcf", data.get("equityValuePerShare", 0)),
                "enterprise_value": data.get("enterpriseValue", 0),
                "equity_value": data.get("equityValue", 0),
                "terminal_value": data.get("terminalValue", 0),
                "assumptions_used": assumptions,
            }
            self._save_to_cache(cache_key, result)
            logger.info(f"FMP Custom DCF for {ticker}: ${result['custom_dcf_value']:.2f}")
            return result

        return {"ticker": ticker, "custom_dcf_value": None, "error": "Could not fetch FMP Custom DCF"}
