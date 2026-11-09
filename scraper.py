#!/usr/bin/env python3
"""Scrape Yahoo Finance's earnings calendar into JSON.

Examples: scraper.py | scraper.py --start 2026-10-19 | scraper.py --days 10 -o out.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timedelta

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

# Shared logger and Yahoo Finance calendar endpoint used throughout the scraper.
log = logging.getLogger("earnings")
BASE_URL = "https://finance.yahoo.com/calendar/earnings"
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
PRIVACY_TEXT = "your privacy is important to us"
NO_RESULTS_TEXT = "no results"
BODY_TEXT_JS = "return (document.body && document.body.innerText || '').toLowerCase();"
CLICK_CONSENT_JS = """
    const order = ['reject all', 'accept all', 'agree', 'continue'];
    const text = el => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
    const controls = [...document.querySelectorAll('button,[role="button"],a,input[type="submit"]')];
    for (const label of order) {
        const target = controls.find(el => text(el) === label);
        if (target) { target.click(); return true; }
    }
    return false;
"""
READ_TABLE_JS = """
    const table = document.querySelector('table');
    if (!table) return {headers: [], rows: []};
    const headers = [...table.querySelectorAll('thead th')].map(th => th.innerText.trim());
    const rows = [...table.querySelectorAll('tbody tr')]
        .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))
        .filter(cells => cells.length >= 2);
    return {headers, rows};
"""


def make_driver() -> webdriver.Chrome:
    """Create a headless Chrome driver tuned for Yahoo Finance table scraping."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = "eager"
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)
    try:
        # Some environments expose a headless browser user-agent; normalize it for site checks.
        user_agent = driver.execute_script("return navigator.userAgent").replace("HeadlessChrome", "Chrome")
        driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": user_agent})
    except WebDriverException:
        log.debug("Could not override user agent", exc_info=True)
    return driver


def read_calendar(driver) -> dict:
    return driver.execute_script(READ_TABLE_JS)


def _click_consent(driver) -> bool:
    # Yahoo often injects a consent box that blocks the earnings table; click the
    # most common dismissal buttons when they appear.
    if driver.execute_script(CLICK_CONSENT_JS):
        return True
    for frame in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.frame(frame)
            if driver.execute_script(CLICK_CONSENT_JS):
                return True
        except WebDriverException:
            pass
        finally:
            driver.switch_to.default_content()
    return False


def dismiss_yahoo_consent(driver, timeout: float = 6.0) -> bool:
    """Dismiss Yahoo consent only when detected; return whether a control was clicked."""
    deadline = time.monotonic() + timeout
    clicked = False
    while time.monotonic() < deadline:
        body = driver.execute_script(BODY_TEXT_JS)
        if PRIVACY_TEXT in body or "consent" in driver.current_url.lower():
            clicked = _click_consent(driver) or clicked
            if clicked:
                return True
        elif read_calendar(driver)["rows"]:
            return False
        time.sleep(0.4)
    if not read_calendar(driver)["rows"]:
        clicked = _click_consent(driver) or clicked
    return clicked


def load_page(driver, url: str, timeout: float = 20.0, retries: int = 2) -> dict | None:
    def ready(browser):
        data = read_calendar(browser)
        if data["headers"] or NO_RESULTS_TEXT in browser.execute_script(BODY_TEXT_JS):
            return data
        return False

    for attempt in range(1, retries + 2):
        try:
            driver.get(url)
            dismiss_yahoo_consent(driver)
            return WebDriverWait(driver, timeout).until(ready)
        except (TimeoutException, WebDriverException) as exc:
            log.warning("Attempt %d failed for %s (%s)", attempt, url, type(exc).__name__)
            time.sleep(1.5 * attempt)
    return None


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")


def parse_rows(data: dict, day: str) -> list[dict]:
    # Yahoo's table headers vary slightly by page layout, so normalize them before
    # converting row values into a consistent JSON record.
    keys = [_key(header) for header in data["headers"]]
    entries = []
    for cells in data["rows"]:
        record = dict(zip(keys, cells)) if len(keys) == len(cells) else {"symbol": cells[0], "company": cells[1]}
        ticker = record.pop("symbol", "").strip()
        if TICKER_RE.fullmatch(ticker):
            entries.append({"ticker": ticker, "company": record.pop("company", "").strip(), "earnings_date": day, **record})
    return entries


def scrape_day(driver, day: str, page_size: int = 100, max_pages: int = 30) -> list[dict]:
    results = {}
    offset = 0
    for page in range(max_pages):
        url = f"{BASE_URL}?day={day}&offset={offset}&size={page_size}"
        data = load_page(driver, url)
        if data is None:
            log.error("[%s page %d] giving up after retries", day, page + 1)
            break
        entries = parse_rows(data, day)
        added = 0
        for entry in entries:
            key = (entry["ticker"], day)
            if key not in results:
                results[key] = entry
                added += 1
        log.info("[%s page %d] %d rows, %d new", day, page + 1, len(data["rows"]), added)
        # A short page means Yahoo has no more rows for this day; requesting the
        # next offset would only time out on an empty table.
        if added == 0 or len(data["rows"]) < page_size:
            break
        offset += len(data["rows"])
    return list(results.values())


def business_days(start: date, count: int) -> list[str]:
    days, current = [], start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def default_start() -> date:
    # Use the next Monday as the default calendar anchor so the scraper covers the
    # upcoming work week without needing any CLI arguments.
    today = date.today()
    return today + timedelta(days=(0 - today.weekday()) % 7)


def write_json_atomic(path: str, data: list[dict]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    fd, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=4, ensure_ascii=False)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def scrape_yahoo_earnings(start: date, days: int, output: str, page_size: int) -> str | None:
    if days < 1 or page_size < 1 or page_size > 100:
        raise ValueError("days must be positive and page_size must be between 1 and 100")
    day_list = business_days(start, days)
    log.info("Scraping %d business days: %s -> %s", len(day_list), day_list[0], day_list[-1])
    entries = []
    driver = make_driver()
    try:
        for day in day_list:
            entries.extend(scrape_day(driver, day, page_size))
    finally:
        driver.quit()
    if not entries:
        log.warning("No earnings rows scraped; %s left unchanged.", output)
        return None
    write_json_atomic(output, entries)
    log.info("Saved %d reporting firms to %s", len(entries), output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=lambda value: datetime.strptime(value, "%Y-%m-%d").date())
    parser.add_argument("--days", type=int, default=5, help="number of business days (default 5)")
    parser.add_argument("-o", "--output", default="earnings_calendar.json")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    return 0 if scrape_yahoo_earnings(args.start or default_start(), args.days, args.output, args.page_size) else 1


if __name__ == "__main__":
    sys.exit(main())