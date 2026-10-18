"""Rule-based score calculations and horizon-adjusted target estimates.

The model is intentionally simple: it weights a handful of signals to create a
screening score rather than a predictive return forecast.
"""

import re
from typing import Optional, Tuple

# Analyst target estimates are treated as a 12-month reference point.
ANALYST_TARGET_HORIZON_MONTHS = 12

# Positive news phrases that strengthen the fundamental and earnings narrative.
POSITIVE_NEWS_SIGNAL = re.compile(
    r"\b(?:raises?|raised|beats?|beating|exceeds?|exceeded|above estimates|strong growth|record (?:revenue|earnings)|increases?|increased|growth accelerated|reaffirmed guidance)\b",
    re.I,
)


def estimate_holding_period_upside(
    price: float, target_price: float, holding_period_months: int
) -> Optional[float]:
    """Scale an analyst's 12-month target estimate to a shorter horizon."""
    if price <= 0 or target_price <= 0:
        return None
    # Compounding the target return over a shorter period keeps the model aligned
    # with a 12-month analyst view while adapting to the selected horizon.
    return round(
        ((target_price / price) ** (holding_period_months / ANALYST_TARGET_HORIZON_MONTHS) - 1) * 100,
        1,
    )


def score_recommendation(
    revenue_growth: float,
    holding_period_upside: Optional[float],
    undervalued: bool,
    positive_news: bool,
) -> Tuple[float, str]:
    """Calculate the project's screening score and its recommendation label."""
    # Cap each signal's contribution so no single metric can dominate the score.
    score = round(
        0.25 * min(1.0, max(0.0, revenue_growth * 2.0))
        + 0.30 * positive_news
        + 0.15 * undervalued
        + min(0.20, max(0.0, (holding_period_upside or 0.0) / 100.0)),
        3,
    )
    # These labels are screening thresholds, not calibrated return predictions.
    recommendation = "STRONG BUY" if score >= 0.65 else "BUY" if score >= 0.50 else "HOLD / WATCH"
    return score, recommendation
