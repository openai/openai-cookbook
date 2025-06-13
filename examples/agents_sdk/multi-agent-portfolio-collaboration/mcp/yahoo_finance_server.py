import json
from enum import Enum
import os
import pandas as pd
import yfinance as yf
from mcp.server.fastmcp import FastMCP
from pathlib import Path
import uuid
import asyncio
import logging

# Helper to ensure outputs dir exists and return path (repo root)
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Single shared outputs folder at the repository root
OUTPUTS_DIR = _REPO_ROOT / "outputs"

# Ensure the directory exists
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Set up logging
LOGS_DIR = _REPO_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "yahoo_finance_server.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: write DataFrame to <repo>/outputs and strip any timezone info
# ---------------------------------------------------------------------------

def _strip_tz(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.select_dtypes(include=["datetimetz"]).columns:
        out[col] = out[col].dt.tz_localize(None)
    return out

def save_df_to_csv(df, base_name):
    df_clean = _strip_tz(df)
    file_path = OUTPUTS_DIR / f"{base_name}.csv"
    if file_path.exists():
        unique_id = uuid.uuid4().hex[:8]
        file_path = OUTPUTS_DIR / f"{base_name}_{unique_id}.csv"
    df_clean.to_csv(file_path, index=False)
    return str(file_path), list(df_clean.columns)

def save_json_to_file(data, base_name):
    file_path = OUTPUTS_DIR / f"{base_name}.json"
    if file_path.exists():
        unique_id = uuid.uuid4().hex[:8]
        file_path = OUTPUTS_DIR / f"{base_name}_{unique_id}.json"
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)
    # Schema: for dict, top-level keys; for list, type of first element or 'list'; else type
    if isinstance(data, dict):
        schema = list(data.keys())
        preview = {k: data[k] for k in list(data)[:PREVIEW_ROWS]}
    elif isinstance(data, list):
        schema = [type(data[0]).__name__] if data else ["list"]
        preview = data[:PREVIEW_ROWS]
    else:
        schema = [type(data).__name__]
        preview = data
    return str(file_path), schema, preview

class FinancialType(str, Enum):
    income_stmt = "income_stmt"
    quarterly_income_stmt = "quarterly_income_stmt"
    balance_sheet = "balance_sheet"
    quarterly_balance_sheet = "quarterly_balance_sheet"
    cashflow = "cashflow"
    quarterly_cashflow = "quarterly_cashflow"

class HolderType(str, Enum):
    major_holders = "major_holders"
    institutional_holders = "institutional_holders"
    mutualfund_holders = "mutualfund_holders"
    insider_transactions = "insider_transactions"
    insider_purchases = "insider_purchases"
    insider_roster_holders = "insider_roster_holders"

class RecommendationType(str, Enum):
    recommendations = "recommendations"
    upgrades_downgrades = "upgrades_downgrades"

# Initialize FastMCP server
yfinance_server = FastMCP(
    "yfinance",
    instructions="""
# Yahoo Finance MCP Server

This server is used to get information about a given ticker symbol from yahoo finance.

Available tools:
- get_historical_stock_prices: Get historical stock prices for a given ticker symbol from yahoo finance. Include the following information: Date, Open, High, Low, Close, Volume, Adj Close.
- get_stock_info: Get stock information for a given ticker symbol from yahoo finance. Include the following information: Stock Price & Trading Info, Company Information, Financial Metrics, Earnings & Revenue, Margins & Returns, Dividends, Balance Sheet, Ownership, Analyst Coverage, Risk Metrics, Other.
- get_yahoo_finance_news: Get news for a given ticker symbol from yahoo finance.
- get_stock_actions: Get stock dividends and stock splits for a given ticker symbol from yahoo finance.
- get_financial_statement: Get financial statement for a given ticker symbol from yahoo finance. You can choose from the following financial statement types: income_stmt, quarterly_income_stmt, balance_sheet, quarterly_balance_sheet, cashflow, quarterly_cashflow.
- get_holder_info: Get holder information for a given ticker symbol from yahoo finance. You can choose from the following holder types: major_holders, institutional_holders, mutualfund_holders, insider_transactions, insider_purchases, insider_roster_holders.
- get_option_expiration_dates: Fetch the available options expiration dates for a given ticker symbol.
- get_option_chain: Fetch the option chain for a given ticker symbol, expiration date, and option type.
- get_recommendations: Get recommendations or upgrades/downgrades for a given ticker symbol from yahoo finance. You can also specify the number of months back to get upgrades/downgrades for, default is 12.
""",
)

PREVIEW_ROWS = 20

# --- Tool: get_historical_stock_prices ---
def get_historical_stock_prices_sync(ticker, period, interval):
    logger.info(f"Called get_historical_stock_prices_sync: ticker={ticker}, period={period}, interval={interval}")
    company = yf.Ticker(ticker)
    if company.isin is None:
        logger.error(f"Company ticker {ticker} not found.")
        return json.dumps({"error": f"Company ticker {ticker} not found."})
    hist_data = company.history(period=period, interval=interval)
    hist_data = hist_data.reset_index(names="Date")
    file_base = f"{ticker}_{period}_{interval}_historical"
    file_path, schema = save_df_to_csv(hist_data, file_base)
    preview_json = hist_data.head(PREVIEW_ROWS).to_json(orient="records", date_format="iso")
    logger.info(f"Returning historical data for {ticker}")
    return json.dumps({
        "file_path": file_path,
        "schema": schema,
        "preview": json.loads(preview_json)
    })

@yfinance_server.tool(
    name="get_historical_stock_prices",
    description="""Get historical stock prices for a given ticker symbol from yahoo finance. Include the following information: Date, Open, High, Low, Close, Volume, Adj Close.\nArgs:\n    ticker: str\n        The ticker symbol of the stock to get historical prices for, e.g. \"AAPL\"\n    period : str\n        Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max\n        Either Use period parameter or use start and end\n        Default is \"1mo\"\n    interval : str\n        Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo\n        Intraday data cannot extend last 60 days\n        Default is \"1d\"\n""",
)
async def get_historical_stock_prices(ticker: str, period: str = "1mo", interval: str = "1d") -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, get_historical_stock_prices_sync, ticker, period, interval),
            timeout=30
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "Timeout fetching historical stock prices"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Tool: get_stock_info ---
def get_stock_info_sync(ticker):
    logger.info(f"Called get_stock_info_sync: ticker={ticker}")
    company = yf.Ticker(ticker)
    if company.isin is None:
        logger.error(f"Company ticker {ticker} not found.")
        return json.dumps({"error": f"Company ticker {ticker} not found."})
    info = company.info
    file_path, schema, preview = save_json_to_file(info, f"{ticker}_stock_info")
    logger.info(f"Returning stock info for {ticker}")
    return json.dumps({
        "file_path": file_path,
        "schema": schema,
        "preview": preview
    })

@yfinance_server.tool(
    name="get_stock_info",
    description="""Get stock information for a given ticker symbol from yahoo finance. Include the following information:\nStock Price & Trading Info, Company Information, Financial Metrics, Earnings & Revenue, Margins & Returns, Dividends, Balance Sheet, Ownership, Analyst Coverage, Risk Metrics, Other.\n\nArgs:\n    ticker: str\n        The ticker symbol of the stock to get information for, e.g. \"AAPL\"\n""",
)
async def get_stock_info(ticker: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, get_stock_info_sync, ticker),
            timeout=30
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "Timeout fetching stock info"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Tool: get_yahoo_finance_news ---
def get_yahoo_finance_news_sync(ticker):
    logger.info(f"Called get_yahoo_finance_news_sync: ticker={ticker}")
    company = yf.Ticker(ticker)
    if company.isin is None:
        logger.error(f"Company ticker {ticker} not found.")
        return json.dumps({"error": f"Company ticker {ticker} not found."})
    try:
        news = company.news
    except Exception as e:
        logger.error(f"Error getting news for {ticker}: {e}")
        return json.dumps({"error": f"Error: getting news for {ticker}: {e}"})
    news_list = []
    for news_item in news:
        if news_item.get("content", {}).get("contentType", "") == "STORY":
            title = news_item.get("content", {}).get("title", "")
            summary = news_item.get("content", {}).get("summary", "")
            description = news_item.get("content", {}).get("description", "")
            url = news_item.get("content", {}).get("canonicalUrl", {}).get("url", "")
            news_list.append(
                {"title": title, "summary": summary, "description": description, "url": url}
            )
    if not news_list:
        logger.warning(f"No news found for company with ticker {ticker}.")
        return json.dumps({"error": f"No news found for company that searched with {ticker} ticker."})
    file_path, schema, preview = save_json_to_file(news_list, f"{ticker}_news")
    logger.info(f"Returning news for {ticker}")
    return json.dumps({
        "file_path": file_path,
        "schema": schema,
        "preview": preview
    })

@yfinance_server.tool(
    name="get_yahoo_finance_news",
    description="""Get news for a given ticker symbol from yahoo finance.\n\nArgs:\n    ticker: str\n        The ticker symbol of the stock to get news for, e.g. \"AAPL\"\n""",
)
async def get_yahoo_finance_news(ticker: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, get_yahoo_finance_news_sync, ticker),
            timeout=30
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "Timeout fetching news"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Tool: get_stock_actions ---
def get_stock_actions_sync(ticker):
    logger.info(f"Called get_stock_actions_sync: ticker={ticker}")
    try:
        company = yf.Ticker(ticker)
    except Exception as e:
        logger.error(f"Error getting stock actions for {ticker}: {e}")
        return json.dumps({"error": f"Error: getting stock actions for {ticker}: {e}"})
    actions_df = company.actions
    actions_df = actions_df.reset_index(names="Date")
    file_path, schema = save_df_to_csv(actions_df, f"{ticker}_actions")
    preview_json = actions_df.head(PREVIEW_ROWS).to_json(orient="records", date_format="iso")
    logger.info(f"Returning stock actions for {ticker}")
    return json.dumps({
        "file_path": file_path,
        "schema": schema,
        "preview": json.loads(preview_json)
    })

@yfinance_server.tool(
    name="get_stock_actions",
    description="""Get stock dividends and stock splits for a given ticker symbol from yahoo finance.\n\nArgs:\n    ticker: str\n        The ticker symbol of the stock to get stock actions for, e.g. \"AAPL\"\n""",
)
async def get_stock_actions(ticker: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, get_stock_actions_sync, ticker),
            timeout=30
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "Timeout fetching stock actions"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Tool: get_financial_statement ---
def get_financial_statement_sync(ticker, financial_type):
    logger.info(f"Called get_financial_statement_sync: ticker={ticker}, financial_type={financial_type}")
    company = yf.Ticker(ticker)
    if company.isin is None:
        logger.error(f"Company ticker {ticker} not found.")
        return json.dumps({"error": f"Company ticker {ticker} not found."})
    if financial_type == FinancialType.income_stmt:
        financial_statement = company.income_stmt
    elif financial_type == FinancialType.quarterly_income_stmt:
        financial_statement = company.quarterly_income_stmt
    elif financial_type == FinancialType.balance_sheet:
        financial_statement = company.balance_sheet
    elif financial_type == FinancialType.quarterly_balance_sheet:
        financial_statement = company.quarterly_balance_sheet
    elif financial_type == FinancialType.cashflow:
        financial_statement = company.cashflow
    elif financial_type == FinancialType.quarterly_cashflow:
        financial_statement = company.quarterly_cashflow
    else:
        logger.error(f"Invalid financial type {financial_type} for {ticker}.")
        return json.dumps({"error": f"Error: invalid financial type {financial_type}. Please use one of the following: {list(FinancialType)}."})
    df = financial_statement.transpose().reset_index(names="date")
    file_path, schema = save_df_to_csv(df, f"{ticker}_{financial_type}")
    preview_json = df.head(PREVIEW_ROWS).to_json(orient="records", date_format="iso")
    logger.info(f"Returning financial statement for {ticker}, type={financial_type}")
    return json.dumps({
        "file_path": file_path,
        "schema": schema,
        "preview": json.loads(preview_json)
    })

@yfinance_server.tool(
    name="get_financial_statement",
    description="""Get financial statement for a given ticker symbol from yahoo finance. You can choose from the following financial statement types: income_stmt, quarterly_income_stmt, balance_sheet, quarterly_balance_sheet, cashflow, quarterly_cashflow.\n\nArgs:\n    ticker: str\n        The ticker symbol of the stock to get financial statement for, e.g. \"AAPL\"\n    financial_type: str\n        The type of financial statement to get. You can choose from the following financial statement types: income_stmt, quarterly_income_stmt, balance_sheet, quarterly_balance_sheet, cashflow, quarterly_cashflow.\n""",
)
async def get_financial_statement(ticker: str, financial_type: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, get_financial_statement_sync, ticker, financial_type),
            timeout=30
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "Timeout fetching financial statement"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Tool: get_holder_info ---
def get_holder_info_sync(ticker, holder_type):
    logger.info(f"Called get_holder_info_sync: ticker={ticker}, holder_type={holder_type}")
    company = yf.Ticker(ticker)
    if company.isin is None:
        logger.error(f"Company ticker {ticker} not found.")
        return json.dumps({"error": f"Company ticker {ticker} not found."})
    if holder_type == HolderType.major_holders:
        df = company.major_holders.reset_index(names="metric")
    elif holder_type == HolderType.institutional_holders:
        df = company.institutional_holders
    elif holder_type == HolderType.mutualfund_holders:
        df = company.mutualfund_holders
    elif holder_type == HolderType.insider_transactions:
        df = company.insider_transactions
    elif holder_type == HolderType.insider_purchases:
        df = company.insider_purchases
    elif holder_type == HolderType.insider_roster_holders:
        df = company.insider_roster_holders
    else:
        logger.error(f"Invalid holder type {holder_type} for {ticker}.")
        return json.dumps({"error": f"Error: invalid holder type {holder_type}. Please use one of the following: {list(HolderType)}."})
    df = df.reset_index() if df.index.name or df.index.names else df
    file_path, schema = save_df_to_csv(df, f"{ticker}_{holder_type}")
    preview_json = df.head(PREVIEW_ROWS).to_json(orient="records", date_format="iso")
    logger.info(f"Returning holder info for {ticker}, type={holder_type}")
    return json.dumps({
        "file_path": file_path,
        "schema": schema,
        "preview": json.loads(preview_json)
    })

@yfinance_server.tool(
    name="get_holder_info",
    description="""Get holder information for a given ticker symbol from yahoo finance. You can choose from the following holder types: major_holders, institutional_holders, mutualfund_holders, insider_transactions, insider_purchases, insider_roster_holders.\n\nArgs:\n    ticker: str\n        The ticker symbol of the stock to get holder information for, e.g. \"AAPL\"\n    holder_type: str\n        The type of holder information to get. You can choose from the following holder types: major_holders, institutional_holders, mutualfund_holders, insider_transactions, insider_purchases, insider_roster_holders.\n""",
)
async def get_holder_info(ticker: str, holder_type: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, get_holder_info_sync, ticker, holder_type),
            timeout=30
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "Timeout fetching holder info"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Tool: get_option_expiration_dates ---
def get_option_expiration_dates_sync(ticker):
    logger.info(f"Called get_option_expiration_dates_sync: ticker={ticker}")
    company = yf.Ticker(ticker)
    if company.isin is None:
        logger.error(f"Company ticker {ticker} not found.")
        return json.dumps({"error": f"Company ticker {ticker} not found."})
    dates = list(company.options)
    file_path, schema, preview = save_json_to_file(dates, f"{ticker}_option_expiration_dates")
    logger.info(f"Returning option expiration dates for {ticker}")
    return json.dumps({
        "file_path": file_path,
        "schema": schema,
        "preview": preview
    })

@yfinance_server.tool(
    name="get_option_expiration_dates",
    description="""Fetch the available options expiration dates for a given ticker symbol.\n\nArgs:\n    ticker: str\n        The ticker symbol of the stock to get option expiration dates for, e.g. \"AAPL\"\n""",
)
async def get_option_expiration_dates(ticker: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, get_option_expiration_dates_sync, ticker),
            timeout=30
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "Timeout fetching option expiration dates"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Tool: get_option_chain ---
def get_option_chain_sync(ticker, expiration_date, option_type):
    logger.info(f"Called get_option_chain_sync: ticker={ticker}, expiration_date={expiration_date}, option_type={option_type}")
    company = yf.Ticker(ticker)
    if company.isin is None:
        logger.error(f"Company ticker {ticker} not found.")
        return json.dumps({"error": f"Company ticker {ticker} not found."})
    if expiration_date not in company.options:
        logger.error(f"No options available for {ticker} on date {expiration_date}.")
        return json.dumps({"error": f"No options available for the date {expiration_date}. You can use `get_option_expiration_dates` to get the available expiration dates."})
    if option_type not in ["calls", "puts"]:
        logger.error(f"Invalid option type {option_type} for {ticker}.")
        return json.dumps({"error": "Invalid option type. Please use 'calls' or 'puts'."})
    option_chain = company.option_chain(expiration_date)
    df = option_chain.calls if option_type == "calls" else option_chain.puts
    file_path, schema = save_df_to_csv(df, f"{ticker}_{expiration_date}_{option_type}_options")
    preview_json = df.head(PREVIEW_ROWS).to_json(orient="records", date_format="iso")
    logger.info(f"Returning option chain for {ticker}, date={expiration_date}, type={option_type}")
    return json.dumps({
        "file_path": file_path,
        "schema": schema,
        "preview": json.loads(preview_json)
    })

@yfinance_server.tool(
    name="get_option_chain",
    description="""Fetch the option chain for a given ticker symbol, expiration date, and option type.\n\nArgs:\n    ticker: str\n        The ticker symbol of the stock to get option chain for, e.g. \"AAPL\"\n    expiration_date: str\n        The expiration date for the options chain (format: 'YYYY-MM-DD')\n    option_type: str\n        The type of option to fetch ('calls' or 'puts')\n""",
)
async def get_option_chain(ticker: str, expiration_date: str, option_type: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, get_option_chain_sync, ticker, expiration_date, option_type),
            timeout=30
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "Timeout fetching option chain"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- Tool: get_recommendations ---
def get_recommendations_sync(ticker, recommendation_type, months_back=12):
    logger.info(f"Called get_recommendations_sync: ticker={ticker}, recommendation_type={recommendation_type}, months_back={months_back}")
    company = yf.Ticker(ticker)
    if company.isin is None:
        logger.error(f"Company ticker {ticker} not found.")
        return json.dumps({"error": f"Company ticker {ticker} not found."})
    try:
        if recommendation_type == RecommendationType.recommendations:
            df = company.recommendations
        elif recommendation_type == RecommendationType.upgrades_downgrades:
            upgrades_downgrades = company.upgrades_downgrades.reset_index()
            cutoff_date = pd.Timestamp.now() - pd.DateOffset(months=months_back)
            upgrades_downgrades = upgrades_downgrades[
                upgrades_downgrades["GradeDate"] >= cutoff_date
            ]
            upgrades_downgrades = upgrades_downgrades.sort_values("GradeDate", ascending=False)
            latest_by_firm = upgrades_downgrades.drop_duplicates(subset=["Firm"])
            df = latest_by_firm
        else:
            logger.error(f"Invalid recommendation type {recommendation_type} for {ticker}.")
            return json.dumps({"error": f"Invalid recommendation type {recommendation_type}."})
        df = df.reset_index() if df.index.name or df.index.names else df
        file_path, schema = save_df_to_csv(df, f"{ticker}_{recommendation_type}_recommendations")
        preview_json = df.head(PREVIEW_ROWS).to_json(orient="records", date_format="iso")
        logger.info(f"Returning recommendations for {ticker}, type={recommendation_type}, months_back={months_back}")
        return json.dumps({
            "file_path": file_path,
            "schema": schema,
            "preview": json.loads(preview_json)
        })
    except Exception as e:
        logger.error(f"Error getting recommendations for {ticker}: {e}")
        return json.dumps({"error": f"Error: getting recommendations for {ticker}: {e}"})

@yfinance_server.tool(
    name="get_recommendations",
    description="""Get recommendations or upgrades/downgrades for a given ticker symbol from yahoo finance. You can also specify the number of months back to get upgrades/downgrades for, default is 12.\n\nArgs:\n    ticker: str\n        The ticker symbol of the stock to get recommendations for, e.g. \"AAPL\"\n    recommendation_type: str\n        The type of recommendation to get. You can choose from the following recommendation types: recommendations, upgrades_downgrades.\n    months_back: int\n        The number of months back to get upgrades/downgrades for, default is 12.\n""",
)
async def get_recommendations(ticker: str, recommendation_type: str, months_back: int = 12) -> str:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, get_recommendations_sync, ticker, recommendation_type, months_back),
            timeout=30
        )
    except asyncio.TimeoutError:
        return json.dumps({"error": "Timeout fetching recommendations"})
    except Exception as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    # Initialize and run the server
    print("Starting Yahoo Finance MCP server...")
    yfinance_server.run(transport="stdio") 