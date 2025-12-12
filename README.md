# DCF Analysis Agent

An AI-powered financial analysis agent built with LangChain that performs comprehensive DCF (Discounted Cash Flow) valuations on stocks. Simply ask for a DCF analysis on any stock ticker, and the agent will gather data, make intelligent assumptions, calculate intrinsic value across multiple scenarios, and provide investment recommendations.

## Features

- **Automated DCF Analysis**: Complete valuation analysis with just a ticker symbol
- **Multi-Scenario Analysis**: Bull, Base, and Bear case scenarios
- **Intelligent Assumptions**: Agent uses historical data to inform projections
- **Real Financial Data**: Fetches live data via Financial Datasets AI API
- **LangChain Integration**: Uses ReAct pattern for autonomous decision-making
- **OpenAI LLM**: Leverages GPT-4 for intelligent financial analysis
- **Investment Recommendations**: Provides actionable Buy/Hold/Sell recommendations

## How It Works

The agent follows a systematic approach:

1. **Information Gathering**: Fetches company info, sector, industry, market cap
2. **Financial Analysis**: Retrieves historical revenue, FCF, debt, cash data
3. **Assumption Formation**: Uses historical growth rates and company fundamentals
4. **DCF Calculation**: Projects 5-year cash flows with terminal value
5. **Scenario Analysis**: Generates Bull, Base, and Bear case valuations
6. **Recommendation**: Provides investment insights based on upside potential

## Installation

### Prerequisites

- Python 3.8+
- OpenAI API key
- Financial Datasets API key (get free at [financialdatasets.ai](https://financialdatasets.ai))

### Setup

1. Clone or download this project:
```bash
cd finance_dcf_agent
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your API keys:
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY and FINANCIAL_DATASETS_API_KEY
```

## Usage

### Quick Analysis (Single Ticker)

```bash
python main.py --ticker AAPL
```

### Interactive Mode

```bash
python main.py --interactive
```

In interactive mode, you can ask natural language questions:
- "Perform a DCF analysis on Tesla"
- "What is the intrinsic value of Microsoft?"
- "Analyze Apple with conservative growth assumptions"

### Using Different Models

```bash
python main.py --ticker GOOGL --model gpt-4
```

## Example Output

```
================================================================================
DCF VALUATION ANALYSIS
================================================================================

BASE SCENARIO
--------------------------------------------------------------------------------
Current Stock Price: $178.50
Intrinsic Value per Share: $215.32
Upside Potential: 20.64%

Enterprise Value: $3,450,000,000,000
Equity Value: $3,420,000,000,000
Terminal Value: $2,100,000,000,000
Discount Rate (WACC): 9.20%

Key Assumptions:
  - Revenue Growth Rate: 10.0%
  - FCF Margin: 15.0%
  - Terminal Growth Rate: 2.5%
  - Beta: 1.15

================================================================================

INVESTMENT RECOMMENDATION
--------------------------------------------------------------------------------
BUY: Stock appears significantly undervalued
Base case upside potential: 20.64%
```

## Architecture

### Components

1. **financial_data.py**: Financial data fetcher using Financial Datasets AI API
   - Fetches company information, financial statements
   - Calculates historical growth rates
   - Extracts key metrics for DCF analysis

2. **dcf_calculator.py**: DCF calculation engine
   - Projects future free cash flows
   - Calculates terminal value
   - Computes enterprise and equity value
   - Generates multi-scenario analysis

3. **tools.py**: LangChain tools
   - `get_stock_info`: Fetch company information
   - `get_financial_metrics`: Retrieve key financial data
   - `perform_dcf_analysis`: Execute complete DCF valuation

4. **agent.py**: LangChain agent with ReAct pattern
   - Orchestrates analysis workflow
   - Makes intelligent decisions on assumptions
   - Provides comprehensive analysis

5. **main.py**: CLI interface
   - Command-line argument parsing
   - Interactive and batch modes

## DCF Methodology

The agent implements a standard DCF valuation approach:

### Assumptions
- **Revenue Growth**: Based on historical CAGR or user-specified
- **FCF Margin**: Free cash flow as % of revenue
- **Terminal Growth**: Long-term perpetual growth rate (typically 2-3%)
- **Discount Rate**: WACC calculated using CAPM model

### Calculation Steps
1. Project 5-year free cash flows based on revenue growth and FCF margin
2. Calculate terminal value using perpetuity growth method
3. Discount all cash flows to present value using WACC
4. Add cash and subtract debt to get equity value
5. Divide by shares outstanding for per-share intrinsic value

### Scenarios
- **Bull Case**: Higher growth (+50%), improved margins (+20%), lower risk
- **Base Case**: Standard assumptions based on historical data
- **Bear Case**: Lower growth (-50%), compressed margins (-20%), higher risk

## Customization

### Custom Assumptions

You can modify default assumptions in `dcf_calculator.py`:

```python
assumptions = DCFAssumptions(
    revenue_growth_rate=0.12,  # 12% growth
    fcf_margin=0.20,  # 20% FCF margin
    terminal_growth_rate=0.03,  # 3% terminal growth
    risk_free_rate=0.04,  # 4% risk-free rate
    market_risk_premium=0.08,  # 8% equity risk premium
    projection_years=5
)
```

### API Information

The application uses Financial Datasets AI for financial data:

- **Free tier available** at [financialdatasets.ai](https://financialdatasets.ai)
- Provides 30,000+ tickers with 30+ years of historical data
- No rate limiting issues like free Yahoo Finance
- Professional-grade financial statements and metrics

## Limitations

- **Data Quality**: Relies on publicly available financial data
- **Assumptions**: DCF is highly sensitive to assumptions
- **Market Factors**: Doesn't account for market sentiment or macroeconomic events
- **Company-Specific Risks**: May not capture all risks
- **Historical Bias**: Assumes past trends continue

## Best Practices

1. **Cross-Reference**: Compare with other valuation methods (P/E, EV/EBITDA)
2. **Sensitivity Analysis**: Review all three scenarios
3. **Qualitative Factors**: Consider competitive position, management quality
4. **Regular Updates**: Refresh analysis quarterly with new data
5. **Conservative Assumptions**: When in doubt, be conservative

## Troubleshooting

### "Could not fetch data for ticker"
- Verify the ticker symbol is correct
- Check internet connection
- Try a different ticker to test if API is working

### "OpenAI API key not found"
- Ensure `.env` file exists with `OPENAI_API_KEY=your_key`
- Check that you're in the correct directory

### "Insufficient financial data"
- Some companies (especially small/new ones) may lack complete data
- Try a larger, established company

## Future Enhancements

- [ ] Support for additional data sources (Bloomberg, FactSet)
- [ ] Monte Carlo simulation for probabilistic valuation
- [ ] Comparable company analysis
- [ ] Export results to PDF/Excel
- [ ] Web interface
- [ ] Real-time market data integration
- [ ] Multi-stock portfolio analysis

## Contributing

Contributions are welcome! Areas for improvement:
- Additional financial models (DDM, APV, etc.)
- Enhanced data validation
- More sophisticated assumption logic
- Better error handling
- Unit tests

## License

MIT License - Feel free to use and modify as needed.

## Disclaimer

This tool is for educational and research purposes only. It does not constitute financial advice. Always conduct your own research and consult with a qualified financial advisor before making investment decisions. Past performance does not guarantee future results.

## Support

For issues, questions, or suggestions, please open an issue on the repository.

---

Built with LangChain, OpenAI GPT-4, and Financial Datasets AI.
