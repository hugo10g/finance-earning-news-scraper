"""News discovery, article extraction, and evidence parsing."""

import html
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlencode, urlsplit

import requests
import yfinance as yf
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from .config import CHROME_USER_AGENT, REQUEST_HEADERS


class NewsResearchMixin:
    """Methods for collecting, screening, and extracting financial news."""

    FINANCIAL_TERMS = re.compile(
        r"\b(?:guidance|outlook|forecast|EPS|earnings per share|revenue|sales|earnings|estimates?|expectations?|consensus|margin)\b",
        re.I,
    )
    FINANCIAL_VALUE = re.compile(
        r"(?:\$\s*\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s*(?:%|percent|basis points?|billion|million|thousand|bn|mm|m|per share)\b|\b(?:EPS|earnings per share)\D{0,15}\d[\d,]*(?:\.\d+)?)",
        re.I,
    )
    PERFORMANCE_TERMS = re.compile(
        r"\b(?:beat|beats|beating|miss|misses|missed|exceed|exceeds|exceeded|raise|raises|raised|lower|lowers|lowered|increase|increased|decrease|decreased|expects?|project(?:s|ed)|reaffirm(?:s|ed)|grew|growth|rose|fell|declined|dropped|reported|posted|delivered|generated)\b",
        re.I,
    )
    BOILERPLATE_TERMS = re.compile(
        r"\b(?:we use cookies and data|if you choose to|accept all|reject all|cookie settings|cookie policy|cookie consent|privacy policy|privacy choices|strictly necessary cookies|do not sell or share|personalized ads|targeted advertising|sign in to continue|subscribe to read|enable javascript)\b",
        re.I,
    )

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\W+", " ", text).strip().lower()

    def clean_article_body(self, text: str, title: str = "") -> str:
        if not text:
            return ""
        title_words = set(self._normalize_text(title).split())
        paragraphs = []
        for part in re.split(r"\n+", text):
            paragraph = part.strip()
            if not paragraph or self.BOILERPLATE_TERMS.search(paragraph):
                continue
            has_value_signal = bool(self.FINANCIAL_VALUE.search(paragraph)) and bool(self.FINANCIAL_TERMS.search(paragraph))
            if len(paragraph) < 60 and not has_value_signal:
                continue
            title_overlap = len(title_words & set(self._normalize_text(paragraph).split())) / max(1, len(title_words))
            if len(paragraph) < 350 and title_overlap >= 0.75 and not has_value_signal:
                continue
            paragraphs.append(paragraph)
        return "\n".join(paragraphs)

    def is_substantive_article_text(self, text: str, title: str = "") -> bool:
        body = self.clean_article_body(text, title)
        if self.FINANCIAL_VALUE.search(body) and self.FINANCIAL_TERMS.search(body):
            return True
        paragraphs = [paragraph for paragraph in body.splitlines() if paragraph]
        return len(self._normalize_text(body)) >= 120 and (
            len(paragraphs) >= 1 or len(re.findall(r"[.!?](?:\s|$)", body)) >= 2
        )

    def _fetch_rss(self, url: str, source_name: str) -> List[Dict[str, str]]:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=12)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        bing = source_name == "Bing News"
        articles = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if bing:
                link = parse_qs(urlsplit(link).query).get("url", [link])[0]
            source_tag = item.find("source")
            source = (source_tag.text or "").strip() if source_tag is not None else source_name
            snippet = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
            snippet = re.sub(r"\s+", " ", html.unescape(snippet)).strip()
            if title and link and "dars.gov.et" not in source.lower():
                articles.append(
                    {
                        "title": title,
                        "link": link,
                        "snippet": snippet,
                        "source": source or source_name,
                        "published": (item.findtext("pubDate") or "").strip(),
                        "snippet_source": "Bing News summary" if bing else "Google News snippet",
                    }
                )
        return articles

    def collect_online_news(self, ticker_symbol: str, company_name: str = "") -> List[Dict[str, str]]:
        name = company_name.strip() or ticker_symbol
        feeds = [
            (
                "Bing News",
                "https://www.bing.com/news/search?"
                + urlencode({"q": f'"{name}" guidance EPS revenue earnings', "format": "rss"}),
            ),
            (
                "Google News",
                "https://news.google.com/rss/search?"
                + urlencode(
                    {
                        "q": f'"{name}" (guidance OR EPS OR revenue OR earnings)',
                        "hl": "en-US",
                        "gl": "US",
                        "ceid": "US:en",
                    }
                ),
            ),
        ]
        articles: List[Dict[str, str]] = []
        for source_name, url in feeds:
            try:
                articles.extend(self._fetch_rss(url, source_name))
            except Exception as exc:
                print(f"{source_name} search notice for {ticker_symbol}: {exc}")

        try:
            yahoo_news = yf.Ticker(ticker_symbol).news or []
            for item in yahoo_news:
                content = item.get("content") if isinstance(item.get("content"), dict) else item
                title = content.get("title") or item.get("title") or ""
                click_url = content.get("clickThroughUrl") or {}
                canonical_url = content.get("canonicalUrl") or {}
                link = (
                    click_url.get("url") if isinstance(click_url, dict) else None
                ) or (
                    canonical_url.get("url") if isinstance(canonical_url, dict) else None
                ) or item.get("link") or ""
                if title and link:
                    articles.append(
                        {
                            "title": str(title),
                            "link": str(link),
                            "snippet": "",
                            "source": "Yahoo Finance news",
                            "published": "",
                            "snippet_source": "Yahoo Finance headline",
                        }
                    )
        except Exception as exc:
            print(f"Yahoo Finance news notice for {ticker_symbol}: {exc}")

        unique, seen = [], set()
        for article in articles:
            key = article["link"].rstrip("/").lower()
            if key not in seen:
                seen.add(key)
                unique.append(article)
        return unique

    def create_chrome_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"user-agent={CHROME_USER_AGENT}")
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    def scrape_url_with_explicit_selenium(self, driver, url: str, title: str = "") -> str:
        if not url or not url.startswith("http"):
            return ""
        try:
            driver.set_page_load_timeout(15)
            driver.get(url)
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            for label in ("Reject all", "Reject", "Only necessary"):
                try:
                    for element in driver.find_elements(
                        By.XPATH,
                        "//button[contains(translate(normalize-space(.), "
                        f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{label.lower()}')]",
                    ):
                        if element.is_displayed() and element.is_enabled():
                            element.click()
                            break
                except Exception:
                    pass

            body_text = driver.execute_script("return document.body && document.body.innerText || '';" )
            body_text = re.sub(r"\s+", "\n", body_text)
            cleaned = self.clean_article_body(body_text, title)
            if self.is_substantive_article_text(cleaned, title):
                return cleaned
            return ""
        except Exception:
            return ""

    def extract_stats_and_reasons(self, full_text: str, title: str = "") -> Dict[str, Any]:
        if not full_text:
            return {"reasons": [], "stats": []}
        full_text = self.clean_article_body(full_text, title)
        if not self.is_substantive_article_text(full_text):
            return {"reasons": [], "stats": []}
        blocks = []
        for block in re.split(r"\n+|(?<=[.!?])\s+", html.unescape(full_text)):
            clean = re.sub(r"\s+", " ", block).strip()
            if clean and not self.BOILERPLATE_TERMS.search(clean):
                blocks.append(clean)
        reasons, stats = [], []
        for sentence in blocks:
            if not self.FINANCIAL_TERMS.search(sentence):
                continue
            has_value = bool(self.FINANCIAL_VALUE.search(sentence))
            has_context = bool(self.PERFORMANCE_TERMS.search(sentence))
            if not (has_value or has_context):
                continue
            if sentence and sentence not in reasons:
                reasons.append(sentence)
            if (has_value or has_context) and sentence and sentence not in stats:
                stats.append(sentence)
        return {"reasons": reasons[:6], "stats": stats[:8]}

    def _article_relevance(self, article: Dict[str, str], ticker_symbol: str, company_name: str) -> int:
        title = article["title"].lower()
        score = sum(
            points
            for phrase, points in [
                ("guidance", 8),
                ("revenue", 7),
                ("eps", 7),
                ("earnings", 5),
                ("estimate", 4),
                ("forecast", 4),
                ("quarterly results", 3),
                ("results", 2),
                ("beat", 2),
                ("miss", 2),
            ]
            if phrase in title
        )
        if ticker_symbol.lower() in title or company_name.lower() in title:
            score += 2
        snippet = article.get("snippet", "")
        if article.get("snippet_source") == "Bing News summary":
            score += 15
        if self.FINANCIAL_VALUE.search(snippet):
            score += 4
        if self.FINANCIAL_TERMS.search(snippet) and self.PERFORMANCE_TERMS.search(snippet):
            score += 3
        if len(snippet) >= 160:
            score += 2
        return score

    def _research_online(self, ticker_symbol: str, company_name: str) -> Dict[str, Any]:
        articles = self.collect_online_news(ticker_symbol, company_name)
        relevant = sorted(
            articles,
            key=lambda article: self._article_relevance(article, ticker_symbol, company_name),
            reverse=True,
        )[:6]
        result = {
            "total": len(articles),
            "reviewed": len(relevant),
            "attempted": 0,
            "pages": 0,
            "summaries": 0,
            "reasons": [],
            "stats": [],
            "evidence": [],
            "sources": [],
        }
        driver = self.create_chrome_driver() if relevant else None
        try:
            for article in relevant:
                text = ""
                if driver:
                    result["attempted"] += 1
                    text = self.scrape_url_with_explicit_selenium(driver, article["link"], article["title"])
                if text:
                    result["pages"] += 1
                else:
                    # Only accept Bing's summary as fallback evidence; other snippets
                    # can be short search previews rather than article content.
                    text = self.clean_article_body(article.get("snippet", ""), article["title"])
                    if (
                        article.get("snippet_source") != "Bing News summary"
                        or not self.is_substantive_article_text(text)
                    ):
                        continue
                    result["summaries"] += 1
                extracted = self.extract_stats_and_reasons(text, article["title"])
                if not extracted["reasons"]:
                    continue
                published = f" | {article['published']}" if article.get("published") else ""
                result["reasons"].append(
                    f"• {article['source']}{published}: \"{article['title']}\"\n  "
                    + "\n  ".join(extracted["reasons"][:5])
                )
                result["sources"].append(f"{article['source']}: {article['title']}\n{article['link']}")
                result["evidence"].extend(extracted["reasons"])
                result["stats"].extend(extracted["stats"])
        finally:
            if driver:
                driver.quit()
        return result
