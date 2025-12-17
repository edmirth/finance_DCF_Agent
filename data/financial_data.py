"""
Financial Data Fetcher using Financial Datasets AI API
"""
import requests
import os
import time
from typing import Dict, Optional, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FinancialDataFetcher:
    """Fetches financial data for DCF analysis using financialdatasets.ai API

    Implements singleton pattern to share cache across all instances.
    """

    BASE_URL = "https://api.financialdatasets.ai"
    _instance = None
    _shared_cache = {}

    def __new__(cls, api_key: Optional[str] = None):
        """Singleton pattern to ensure cache is shared across all instances"""
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
        # Only initialize once (singleton pattern)
        if self._initialized:
            return

        self.api_key = api_key or os.getenv("FINANCIAL_DATASETS_API_KEY")
        if not self.api_key:
            raise ValueError("Financial Datasets API key not found. Set FINANCIAL_DATASETS_API_KEY environment variable.")

        self.headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        # Use class-level shared cache instead of instance cache
        self.cache = self._shared_cache
        self.cache_ttl = 900  # 15 minutes TTL for financial data
        self._initialized = True

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Retrieve data from cache if valid"""
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
        """Save data to cache with timestamp"""
        self.cache[cache_key] = {
            'data': data,
            'timestamp': time.time()
        }
        logger.info(f"Cached {cache_key}")

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make API GET request with error handling"""
        url = f"{self.BASE_URL}{endpoint}"
        try:
            logger.info(f"Making GET request to {endpoint} with params: {params}")
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                logger.error(f"Invalid API key for Financial Datasets")
            elif response.status_code == 404:
                logger.error(f"Ticker not found: {params.get('ticker', 'unknown')}")
            elif response.status_code == 402:
                logger.error(f"This endpoint requires a paid subscription")
            else:
                logger.error(f"HTTP error {response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error making request to {endpoint}: {e}")
            return None

    def _make_post_request(self, endpoint: str, payload: Dict) -> Optional[Dict]:
        """Make API POST request with error handling"""
        url = f"{self.BASE_URL}{endpoint}"
        try:
            logger.info(f"Making POST request to {endpoint} with payload: {payload}")
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                logger.error(f"Invalid API key for Financial Datasets")
            elif response.status_code == 402:
                logger.error(f"This endpoint requires a paid subscription")
            elif response.status_code == 400:
                logger.error(f"Bad request - invalid filter parameters")
            else:
                logger.error(f"HTTP error {response.status_code}: {e}")
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
                interest_expenses = []
                income_taxes = []
                pretax_incomes = []
                fiscal_years = []

                for stmt in income_statements[:5]:  # Last 5 years
                    revenue = stmt.get("revenue", 0) or stmt.get("revenues", 0) or 0
                    net_income = stmt.get("net_income", 0) or 0
                    ebit = stmt.get("operating_income", 0) or stmt.get("ebit", 0) or 0
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
                metrics["latest_interest_expense"] = interest_expenses[0] if interest_expenses else 0
                metrics["historical_years"] = fiscal_years

                # Calculate effective tax rate
                if pretax_incomes[0] > 0 and income_taxes[0] > 0:
                    metrics["effective_tax_rate"] = abs(income_taxes[0]) / pretax_incomes[0]
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

            # Extract debt, cash, and working capital from balance sheet
            if balance_sheets:
                latest_bs = balance_sheets[0]

                # Total debt
                total_debt = latest_bs.get("total_debt", 0) or 0
                metrics["total_debt"] = float(total_debt)

                # Cash and cash equivalents
                cash = latest_bs.get("cash_and_equivalents", 0) or latest_bs.get("cash_and_cash_equivalents", 0) or 0
                metrics["cash_and_equivalents"] = float(cash)

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

            # Cache the result before returning
            self._save_to_cache(cache_key, metrics)
            return metrics

        except Exception as e:
            logger.error(f"Error extracting key metrics for {ticker}: {e}")
            return {}

    def calculate_historical_growth_rate(self, values: List[float]) -> float:
        """Calculate CAGR from historical values"""
        if not values or len(values) < 2:
            return 0.0

        # Remove zeros and negatives
        clean_values = [v for v in values if v > 0]
        if len(clean_values) < 2:
            return 0.0

        try:
            beginning_value = clean_values[-1]
            ending_value = clean_values[0]
            num_years = len(clean_values) - 1

            cagr = (pow(ending_value / beginning_value, 1 / num_years) - 1)
            return round(cagr, 4)
        except:
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
