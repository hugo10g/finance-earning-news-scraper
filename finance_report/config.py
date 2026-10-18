"""Project-level configuration and default watchlist helpers.

This module keeps the browser, request, and calendar inputs in one place so the
research pipeline can run even when the scraper has not yet generated a JSON
calendar file.
"""

import json
import os
from typing import Dict, List

# Default watchlist used when an earnings_calendar.json file is missing or invalid.
DEFAULT_WATCHLIST = ["AXP", "SLB", "ITW", "BAH", "GNTX", "NVDA", "AAPL", "MSFT"]

# Browser-facing request metadata for outbound calls and Selenium sessions.
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def load_watchlist(json_path: str = "earnings_calendar.json") -> List[str]:
    """Load unique ticker symbols, falling back to the default watchlist."""
    # Keep the pipeline usable when the separate calendar scraper has not run.
    if not os.path.exists(json_path):
        return DEFAULT_WATCHLIST.copy()
    try:
        with open(json_path, "r", encoding="utf-8") as calendar_file:
            data = json.load(calendar_file)
        tickers = [str(item["ticker"]).upper() for item in data if item.get("ticker")]
        return list(dict.fromkeys(tickers))
    except Exception:
        return DEFAULT_WATCHLIST.copy()


def load_earnings_dates(json_path: str = "earnings_calendar.json") -> Dict[str, str]:
    """Load earnings dates keyed by upper-case ticker symbol."""
    # Return an empty map instead of crashing if the file is absent or malformed.
    try:
        with open(json_path, "r", encoding="utf-8") as calendar_file:
            entries = json.load(calendar_file)
        return {
            str(item["ticker"]).upper(): str(item.get("earnings_date", "N/A"))
            for item in entries
            if item.get("ticker")
        }
    except Exception:
        return {}
