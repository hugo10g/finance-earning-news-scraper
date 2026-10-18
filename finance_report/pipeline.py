"""Ticker-by-ticker orchestration for the research pipeline."""

from concurrent.futures import ThreadPoolExecutor
from numbers import Real
from typing import Any, Dict, List

import pandas as pd
import yfinance as yf

from .config import load_earnings_dates
from .fundamentals import format_financial_value, get_yfinance_fundamental_stats
from .news import NewsResearchMixin
from .reporting import ReportingMixin
from .scoring import (
    ANALYST_TARGET_HORIZON_MONTHS,
    POSITIVE_NEWS_SIGNAL,
    estimate_holding_period_upside,
    score_recommendation,
)


class SeleniumExplicitQuantitativePipeline(NewsResearchMixin, ReportingMixin):
    """Coordinate market data, online news, scoring, and workbook reporting."""

    ANALYST_TARGET_HORIZON_MONTHS = ANALYST_TARGET_HORIZON_MONTHS
    POSITIVE_NEWS_SIGNAL = POSITIVE_NEWS_SIGNAL

    def __init__(self, holding_period_months: int = 1):
        if not isinstance(holding_period_months, int) or holding_period_months <= 0:
            raise ValueError("holding_period_months must be a positive integer")
        # Keep the selected holding-period horizon at the pipeline level for later
        # use in target scaling and rationale summaries.
        self.holding_period_months = holding_period_months
        self.earnings_dates = load_earnings_dates()

    def estimate_holding_period_upside(self, price: float, target_price: float):
        return estimate_holding_period_upside(price, target_price, self.holding_period_months)

    @staticmethod
    def _score(
        revenue_growth: float,
        holding_period_upside: float,
        undervalued: bool,
        positive_news: bool,
    ):
        return score_recommendation(revenue_growth, holding_period_upside, undervalued, positive_news)

    @staticmethod
    def _format_financial_value(value: float, currency: str = "$") -> str:
        """Retain the original helper on the public pipeline class."""
        return format_financial_value(value, currency)

    def get_yfinance_fundamental_stats(self, ticker: Any, info: Dict[str, Any]) -> List[str]:
        return get_yfinance_fundamental_stats(ticker, info)

    def process_ticker(self, ticker_symbol: str) -> Dict[str, Any]:
        try:
            # Pull the current market snapshot and any available analyst target.
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            hist = ticker.history(period="1d")
            price = round(float(hist["Close"].iloc[-1]), 2) if not hist.empty else "N/A"
            forward_pe = info.get("forwardPE")
            trailing_pe = info.get("trailingPE")
            peg_ratio = info.get("pegRatio")
            raw_growth = info.get("revenueGrowth")
            revenue_growth = (
                float(raw_growth)
                if isinstance(raw_growth, Real) and pd.notna(raw_growth)
                else 0.0
            )
            company_name = info.get("longName") or info.get("shortName") or ticker_symbol
            if info.get("quoteType", "EQUITY") == "ETF":
                return {"ticker": ticker_symbol, "valid": False}

            # Gather article evidence and convert it into summary statistics.
            research = self._research_online(ticker_symbol, company_name)

            target_mean_price = info.get("targetMeanPrice")
            analyst_upside = 0.0
            holding_period_upside = None
            if (
                isinstance(target_mean_price, Real)
                and pd.notna(target_mean_price)
                and isinstance(price, Real)
                and price > 0
            ):
                analyst_upside = round(((target_mean_price - price) / price) * 100, 2)
                holding_period_upside = self.estimate_holding_period_upside(price, target_mean_price)

            # Build the cheap screening signals: valuation, growth, and positive news.
            is_undervalued = bool(
                (peg_ratio and 0 < peg_ratio < 2.5)
                or (forward_pe and trailing_pe and forward_pe < trailing_pe)
            )
            has_positive_news = any(self.POSITIVE_NEWS_SIGNAL.search(sentence) for sentence in research["evidence"])
            combined_score, recommendation = self._score(
                revenue_growth, holding_period_upside, is_undervalued, has_positive_news
            )

            fundamental_stats = self.get_yfinance_fundamental_stats(ticker, info)
            unique_stats = list(dict.fromkeys(research["stats"]))
            stat_sections = []
            if fundamental_stats:
                stat_sections.append("Yahoo Finance reported fundamentals:\n" + "\n".join(fundamental_stats))
            if unique_stats:
                stat_sections.append("Financial details found in news:\n" + "\n".join(unique_stats))
            stat_str = "\n\n".join(stat_sections) if stat_sections else "No EPS/revenue figures available."
            if research["reasons"]:
                reason_str = "\n".join(research["reasons"])
            elif not research["total"]:
                reason_str = "No online news links were returned by Google News or Yahoo Finance."
            elif research["pages"] == 0:
                reason_str = (
                    f"Found {research['total']} links and attempted {research['attempted']} article pages, "
                    "but none returned substantive article paragraphs. Visible text may have been only a "
                    "headline, page shell, or publisher access wall."
                )
            else:
                reason_str = (
                    f"Read substantive text from {research['pages']} article page(s), but found no sentences "
                    "with extractable EPS, revenue, or guidance results. Used "
                    f"{research['summaries']} substantive search-result summary/summaries when article text "
                    "was unavailable."
                )

            return {
                "Ticker": ticker_symbol,
                "Price ($)": price,
                "Earnings Date": self.earnings_dates.get(ticker_symbol.upper(), "N/A"),
                "Forward P/E": round(forward_pe, 2) if forward_pe else "N/A",
                "PEG Ratio": round(peg_ratio, 2)
                if isinstance(peg_ratio, Real) and pd.notna(peg_ratio)
                else "N/A",
                "Analyst Upside (%)": analyst_upside,
                "Holding Period (Months)": self.holding_period_months,
                "Projected Holding-Period Upside (%)": holding_period_upside
                if holding_period_upside is not None
                else "N/A",
                "Revenue Growth (%)": round(revenue_growth * 100, 2),
                "Online Articles Reviewed": research["reviewed"],
                "Article Pages Read": research["pages"],
                "Article Summaries Used": research["summaries"],
                "Yahoo Finance Fundamentals": "\n".join(fundamental_stats)
                if fundamental_stats
                else "N/A",
                "News Article Statistics": "\n".join(unique_stats) if unique_stats else "N/A",
                "Article Links & Outlets": "\n\n".join(dict.fromkeys(research["sources"]))
                if research["sources"]
                else "N/A",
                "Scraped Statistics": stat_str,
                "Detailed Reasons & News Findings": reason_str,
                "Final Score": combined_score,
                "Recommendation": recommendation,
                "valid": True,
            }
        except Exception as exc:
            print(f"Research notice for {ticker_symbol}: {exc}")
            return {"ticker": ticker_symbol, "valid": False}

    def run_pipeline(self, watchlist: List[str]) -> pd.DataFrame:
        results = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            for row in executor.map(self.process_ticker, watchlist):
                if row.get("valid", False):
                    results.append(row)
                    print(f"✓ Chrome successfully scraped [{row['Ticker']}]")
        return pd.DataFrame(results)

    def build_priority_list(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        buys = df[df["Recommendation"].isin(["STRONG BUY", "BUY"])].copy()
        if "Final Score" in buys.columns:
            buys["Final Score"] = pd.to_numeric(buys["Final Score"], errors="coerce").fillna(0.0)
        return buys.sort_values(by="Final Score", ascending=False, kind="stable").reset_index(drop=True)
