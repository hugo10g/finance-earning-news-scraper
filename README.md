# Finance Earnings News Report Scraper

## Introduction

This project combines Yahoo Finance fundamentals with earnings-related online news to create a structured company research report. A companion browser scraper collects upcoming earnings-calendar entries from Yahoo Finance. The workflow is intended to reduce repetitive information gathering; its output is a starting point for independent research, not an investment recommendation.

### Financial Research Context

Financial details are spread across company pages, quarterly statements, news articles, and search results. This project brings selected data into one reviewable workbook while keeping article links and source evidence alongside the numerical indicators.

## Features

| Feature | Description |
| --- | --- |
| Earnings calendar | Collects calendar rows from Yahoo Finance, including company, ticker, date, and available table fields. |
| Fundamental data | Retrieves price, EPS, revenue and earnings growth, valuation ratios, analyst target information, and quarterly income-statement figures through `yfinance`. |
| News research | Searches Bing News, Google News, and Yahoo Finance headlines for earnings, EPS, revenue, and guidance coverage. |
| Article extraction | Reads accessible article pages using Selenium and extracts relevant financial statements; uses eligible Bing summaries if article pages are unavailable. |
| Holding-period scoring | Scales analyst-target upside to the selected holding horizon and combines it with growth, valuation, and news signals. |
| Excel reporting | Exports a priority research list and detailed worksheets with statistics, rationale, and source links. |
| Safer calendar output | Handles Yahoo consent prompts, retries page loads, paginates by offset, and leaves the existing output unchanged when no rows are collected. |

## What Data the Project Collects

The fields depend on what Yahoo Finance, the news outlets, and the calendar page make available at run time.

| Data | Examples |
| --- | --- |
| Calendar | Ticker, company, earnings date, event name, call time, EPS estimate, reported EPS, surprise, market capitalization. |
| Market and valuation | Current price, forward P/E, PEG ratio, analyst target, analyst upside. |
| Fundamentals | Trailing and forward EPS, revenue growth, earnings growth, quarterly revenue, net income, diluted EPS, and year-over-year comparisons where available. |
| News evidence | Article title, outlet, publication date when available, article URL, extracted EPS/revenue/guidance sentences, and whether summary evidence was used. |
| Research output | Holding-period upside estimate, rule-based score, recommendation label, rationale, and research considerations. |

## Directory Structure

```text
finance-earning-news-report-scraper/
├── noaimain.py                  # Backward-compatible command-line entry point
├── finance_report/              # Research pipeline modules
│   ├── config.py                # Settings and earnings-calendar input
│   ├── fundamentals.py          # Yahoo Finance fundamental statistics
│   ├── news.py                  # News search and article extraction
│   ├── pipeline.py              # Ticker processing and orchestration
│   ├── reporting.py             # Rationale and Excel workbook output
│   └── scoring.py               # Score and holding-period calculations
├── scraper.py                   # Yahoo Finance earnings calendar scraper
├── requirements.txt             # Python dependencies
├── earnings_calendar.json       # Generated calendar input (optional)
├── explicit_selenium_report.xlsx # Generated research workbook
├── cache/                        # Optional cached evaluation data
├── LICENSE
└── README.md
```

Generated files may not exist until the corresponding scripts have been run.

## Setup

The project requires Python 3.10 or newer, Google Chrome for Selenium, and network access to Yahoo Finance and the news feeds. From the project directory, create an environment and install the listed packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate`.

## Usage

### 1. Collect the Earnings Calendar

The calendar scraper defaults to five business days beginning on the upcoming Monday (today when it is Monday). It handles the Yahoo consent dialog and writes the result to `earnings_calendar.json`:

```bash
source .venv/bin/activate
python scraper.py
```

To set the start date, number of business days, page size, output file, or logging verbosity:

```bash
python scraper.py --start 2026-10-19 --days 5
python scraper.py --start 2026-10-19 --days 10 --page-size 100 -o earnings_calendar.json
python scraper.py --days 5 --verbose
```

If Yahoo returns no rows, the scraper leaves the existing output file unchanged. Site changes, consent behavior, or access restrictions can affect results; check the log messages when troubleshooting.

### 2. Run the Earnings and News Research Pipeline

The research pipeline uses tickers and earnings dates from a valid `earnings_calendar.json`. If that file is missing or invalid, it uses its built-in default watchlist. It combines Yahoo Finance data with accessible online article evidence and exports the research workbook:

```bash
source .venv/bin/activate
python noaimain.py
```

The research code is split by responsibility in `finance_report/`; `noaimain.py` remains the simple command-line entry point and can still be imported by existing scripts.

The default holding horizon is one month. To use a different horizon, change the initialization near the bottom of `noaimain.py`. For example, set a five-month horizon with:

```python
pipeline = SeleniumExplicitQuantitativePipeline(holding_period_months=5)
```

## Scoring and Recommendations

The rule-based score ranges from 0 to 1. Revenue growth contributes up to 0.25, positive news language contributes 0.30, the valuation screen contributes 0.15, and positive analyst-target upside scaled to the holding period contributes up to 0.20.

| Score | Output label |
| --- | --- |
| 0.65 or higher | STRONG BUY |
| 0.50 to below 0.65 | BUY |
| Below 0.50 | HOLD / WATCH |

```text
Score = growth signal + positive-news signal + valuation signal + horizon-adjusted upside

0.65–1.00  -> STRONG BUY
0.50–0.649 -> BUY
0.00–0.499 -> HOLD / WATCH
```

The analyst target is treated as a 12-month estimate and scaled to the selected horizon; this does not forecast actual returns. The scoring logic is a screening heuristic, not a validated predictive model.

## Output

The pipeline writes `explicit_selenium_report.xlsx` with the full research results and a separate BUY/STRONG BUY shortlist. No capital allocation or share-count sizing is performed.

```text
explicit_selenium_report.xlsx
├── Priority Research List
├── Full Signal Justification
└── Research Details
```

The workbook includes available score inputs, fundamentals, extracted article statistics, source links, detailed rationale, and rule-based research considerations. News evidence may come from an accessible article page or, when allowed by the pipeline, a search-result summary; verify important figures against original company disclosures.

## Use Cases

- **Investors** can use the workbook as a starting point for comparing earnings-related signals across a watchlist.
- **Analysts and researchers** can review financial statistics alongside the related article links and extracted evidence.
- **Developers** can adapt the calendar scraper and structured output for their own research workflow.

## FAQs

**Does the score predict whether a stock will rise?**

No. It is a rule-based screen based on selected fundamentals, news phrases, valuation indicators, and analyst targets. It is not a prediction or a guarantee.

**Does the pipeline always read the full article?**

No. Selenium reads accessible pages, but publishers may block access with paywalls, consent dialogs, or other restrictions. Eligible Bing News summaries may be used when an article page is unavailable, and the report includes source information for verification.

**Can I choose the holding period?**

Yes. Change the `holding_period_months` value where the pipeline is initialized in `noaimain.py`.

**What happens if Yahoo blocks the earnings-calendar scraper?**

The scraper logs failed attempts and does not replace the existing JSON file when it collects no rows. Yahoo's page structure and access policies can change.

**Does this project provide personalized financial advice?**

No. It is for educational and informational research. Review company filings, earnings releases, cash flow, debt, and other risks before making any investment decision.

## Performance and Results

The scripts report operational results such as the number of calendar rows captured, online articles reviewed, article pages read, summaries used, and generated report sheets. No fixed extraction-accuracy or pages-per-minute benchmark is claimed because results vary with network conditions, provider availability, and website access restrictions.

## License

See [LICENSE](LICENSE).
