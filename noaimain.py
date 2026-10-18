"""Backward-compatible command-line entry point for the modular pipeline."""

# Keep imports here so older scripts importing these names from noaimain keep
# working without needing to know about the new finance_report package layout.
from finance_report.config import (
    CHROME_USER_AGENT,
    DEFAULT_WATCHLIST,
    REQUEST_HEADERS,
    load_earnings_dates,
    load_watchlist,
)
from finance_report.pipeline import SeleniumExplicitQuantitativePipeline


def main() -> None:
    # Load the calendar input; if it is missing we fall back to the default list.
    watchlist = load_watchlist("earnings_calendar.json")
    pipeline = SeleniumExplicitQuantitativePipeline(holding_period_months=1)

    print("\n=========================================================================")
    print(
        " Explicit Selenium Chrome Scraping Pipeline "
        f"(Zero AI; {pipeline.holding_period_months}-month horizon)"
    )
    print("=========================================================================")

    # Run the research flow and then build the shortlist of BUY / STRONG BUY names.
    df_results = pipeline.run_pipeline(watchlist)
    df_portfolio = pipeline.build_priority_list(df_results)

    print("\n=========================================================================")
    print(" PRIORITY RESEARCH LIST (NO POSITION SIZING)")
    print("=========================================================================")
    if not df_portfolio.empty:
        for _, row in df_portfolio.iterrows():
            print(f"Ticker: {row['Ticker']} | Rec: {row['Recommendation']} | Score: {row['Final Score']}")
            print(f"Research Considerations: {pipeline.build_research_considerations(row)}")
            print(f"Scraped Stats: {row['Scraped Statistics']}")
            print(f"Reasons & Findings:\n{row['Detailed Reasons & News Findings']}")
            print("-" * 75)
    else:
        print("No buy signals triggered.")

    # Export the final workbook so the results are saved locally in Excel format.
    pipeline.export_report(df_portfolio, df_results)


if __name__ == "__main__":
    main()
