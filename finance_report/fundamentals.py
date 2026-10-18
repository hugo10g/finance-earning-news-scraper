"""Yahoo Finance fundamental-statistic formatting and extraction.

These helpers keep the financial figures readable and consistent when they are
written into spreadsheets or narrative rationale blocks.
"""

from typing import Any, Dict, List

import pandas as pd


def format_financial_value(value: float, currency: str = "$") -> str:
    """Format large financial values compactly for report cells."""
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{currency}{value / 1_000_000_000:,.2f}B"
    if abs_value >= 1_000_000:
        return f"{currency}{value / 1_000_000:,.1f}M"
    return f"{currency}{value:,.2f}"


def get_yfinance_fundamental_stats(ticker: Any, info: Dict[str, Any]) -> List[str]:
    """Collect EPS, growth, and available quarterly statement details."""
    stats: List[str] = []
    used = [
        ("Trailing EPS", info.get("trailingEps")),
        ("Forward EPS estimate", info.get("forwardEps")),
        ("Yahoo Finance revenue growth", info.get("revenueGrowth")),
        ("Yahoo Finance earnings growth", info.get("earningsGrowth")),
    ]
    for label, value in used:
        if value is not None and pd.notna(value):
            if "growth" in label.lower():
                stats.append(f"{label}: {float(value) * 100:+.1f}%")
            else:
                stats.append(f"{label}: ${float(value):.2f}")

    try:
        # Pull the latest quarterly income statement and summarize the key rows.
        statement = ticker.quarterly_income_stmt
        if statement.empty or len(statement.columns) == 0:
            return stats
        latest = statement.columns[0]
        prior = statement.columns[4] if len(statement.columns) >= 5 else None
        label = pd.Timestamp(latest).strftime("%Y-%m-%d") if not isinstance(latest, str) else str(latest)
        row_aliases = {
            "Revenue": ("Total Revenue", "Operating Revenue", "Revenue"),
            "Net income": ("Net Income", "Net Income Common Stockholders"),
            "Diluted EPS": ("Diluted EPS", "Diluted Earnings Per Share"),
        }
        period_stats = []
        for name, aliases in row_aliases.items():
            key = next((alias for alias in aliases if alias in statement.index), None)
            if key is None:
                continue
            current = float(statement.loc[key, latest])
            rendered = (
                format_financial_value(current)
                if name in {"Revenue", "Net income"}
                else f"${current:.2f}"
            )
            detail = f"{name}: {rendered}"
            if prior is not None:
                previous = statement.loc[key, prior]
                if pd.notna(previous) and float(previous) != 0:
                    detail += f" (same quarter YoY {(current / float(previous) - 1) * 100:+.1f}%)"
            period_stats.append(detail)
        if period_stats:
            stats.append(f"Quarter ended {label}: " + "; ".join(period_stats))
    except Exception as exc:
        print(f"Yahoo Finance quarterly-statistics notice: {exc}")
    return stats
