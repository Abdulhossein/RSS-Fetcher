#!/usr/bin/env python3
"""
plugins/_drweil_base.py
-----------------------
Uses the multi-method anti-bot bypass module (antibot_bypass.py in project
root) to fetch the HTML listing pages. This bypasses Cloudflare even when
plain requests / curl_cffi / cloudscraper are blocked, because it falls back
to real browser engines (Playwright / Selenium / undetected-chromedriver).

Prefixed with `_` so rss_fetcher's loader skips it.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# Ensure project root is importable so `import antibot_bypass` works both
# when loaded by rss_fetcher.py and when running plugins/*.py standalone.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import antibot_bypass
except ImportError as e:
    raise ImportError(
        f"antibot_bypass.py must be in the project root ({_PROJECT_ROOT}). "
        f"Original error: {e}"
    )


# ---- Session state: cache which bypass method actually worked ----
_WORKING_METHOD = None
_WORKING_METHOD_NAME: Optional[str] = None


def _looks_valid(html: Optional[str]) -> bool:
    """Reject Cloudflare challenge pages and empty responses."""
    if not html or len(html) < 500:
        return False
    low = html.lower()
    if "cf-browser-verification" in low:
        return False
    if "checking your browser" in low:
        return False
    if "just a moment" in low and "challenge" in low:
        return False
    return True


def _fetch_html(url: str) -> Optional[str]:
    """
    Fetch HTML through antibot_bypass, reusing the method that worked before.

    We deliberately do NOT call antibot_bypass.get_html() because its cache
    key is per-domain (drweil.com.pkl), which would return page 1's HTML for
    every paginated URL. We drive METHODS ourselves and validate content.
    """
    global _WORKING_METHOD, _WORKING_METHOD_NAME

    # Fast path — reuse previously successful method
    if _WORKING_METHOD is not None:
        try:
            html = _WORKING_METHOD(url)
            if _looks_valid(html):
                return html
            print(f"[drweil] {_WORKING_METHOD_NAME} returned invalid HTML, "
                  f"retrying all methods…")
        except Exception as e:
            print(f"[drweil] {_WORKING_METHOD_NAME} raised: {e}")
        _WORKING_METHOD = None
        _WORKING_METHOD_NAME = None

    # Slow path — try every method
    for method in antibot_bypass.METHODS:
        name = method.__name__
        try:
            html = method(url)
        except Exception as e:
            print(f"[drweil] {name} raised: {e}")
            continue

        if _looks_valid(html):
            _WORKING_METHOD = method
            _WORKING_METHOD_NAME = name
            print(f"[drweil] ✓ {name} worked")
            return html

        size = len(html) if html else 0
        print(f"[drweil] ✗ {name} ({size} bytes)")

    return None


class DrWeilBasePlugin:
    """Shared HTML-scraping logic for all DrWeil.com blog feeds."""

    name: str = "drweil_base"
    url: str = ""
    title: str = ""
    description: str = ""
    language: str = "en"
    categories: List[str] = []
    max_items: int = 50

    ITEM_SELECTOR = (
        'article[itemtype="http://schema.org/BlogPosting"]'
        ':not(.article-list-small)'
    )
    MAX_PAGES = 6
    PAGE_DELAY = 1.5

    def get_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen: set = set()

        for page in range(1, self.MAX_PAGES + 1):
            if len(items) >= self.max_items:
                break

            page_url = self.url if page == 1 else urljoin(
                self.url, f"page/{page}/")
            print(f"[{self.name}] page {page}: {page_url}")

            html = _fetch_html(page_url)
            if not html:
                print(f"[{self.name}] all methods failed — stopping")
                break

            soup = BeautifulSoup(html, "lxml")
            elements = soup.select(self.ITEM_SELECTOR)
            if not elements:
                print(f"[{self.name}] no articles on page {page} — stopping")
                break

            new = 0
            for el in elements:
                item = self._parse_article(el)
                if not item or item["link"] in seen:
                    continue
                seen.add(item["link"])
                items.append(item)
                new += 1
                if len(items) >= self.max_items:
                    break

            print(f"[{self.name}] page {page}: +{new} (total {len(items)})")

            if new == 0:
                break
            if page < self.MAX_PAGES:
                time.sleep(self.PAGE_DELAY)

        return items

    def _parse_article(self, el) -> Optional[Dict[str, Any]]:
        title_a = el.select_one("h2.featured-title a, h4.article-title a")
        if not title_a:
            return None

        title = title_a.get_text(strip=True)
        href = title_a.get("href")
        if not title or not href:
            return None

        link = urljoin(self.url, href)

        image = None
        img = el.select_one("a.image img")
        if img:
            src = img.get("src") or img.get(
                "data-src") or img.get("data-lazy-src")
            if src:
                image = urljoin(self.url, src)

        description = ""
        desc_el = el.select_one(".excerpt")
        if desc_el:
            description = desc_el.get_text(strip=True)

        pub_date = datetime.now(timezone.utc)
        date_meta = el.select_one("meta[itemprop='datePublished']")
        if date_meta and date_meta.get("content"):
            pub_date = self.parse_date(date_meta["content"])

        tags: List[str] = []
        slug = el.select_one("a.slug")
        if slug:
            t = slug.get_text(strip=True)
            if t:
                tags.append(t)
        all_categories = list(dict.fromkeys(self.categories + tags))

        author = "Dr. Weil"
        author_meta = el.select_one(
            "[itemprop='author'] meta[itemprop='name']")
        if author_meta and author_meta.get("content"):
            author = author_meta["content"].strip() or author

        enclosures: List[Dict[str, Any]] = []
        if image:
            enclosures.append({
                "url": image,
                "type": self._image_mime(image),
                "length": 0,
                "title": "Cover image",
            })

        return {
            "title":       title,
            "link":        link,
            "description": description or title,
            "content":     None,
            "pubDate":     pub_date,
            "author":      author,
            "guid":        link,
            "categories":  all_categories,
            "image":       image,
            "enclosures":  enclosures,
            "extra":       {},
        }

    @staticmethod
    def _image_mime(url: str) -> str:
        lowered = url.lower().split("?")[0]
        if lowered.endswith(".png"):
            return "image/png"
        if lowered.endswith(".webp"):
            return "image/webp"
        if lowered.endswith(".gif"):
            return "image/gif"
        return "image/jpeg"

    def parse_date(self, text: str) -> datetime:
        text = text.strip()
        for fmt in (
            "%B %d, %Y",
            "%b %d, %Y",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(text, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return datetime.now(timezone.utc)


def run_interactive_test(plugin: "DrWeilBasePlugin", limit: int = 3) -> None:
    print("=" * 72)
    print(f"Interactive Test – {type(plugin).__name__}")
    print("=" * 72)
    print(f"Plugin     : {plugin.name}")
    print(f"URL        : {plugin.url}")
    print(f"Categories : {plugin.categories}")
    print(f"Methods    : {len(antibot_bypass.METHODS)}")
    print("-" * 72)

    try:
        items = plugin.get_items()
    except Exception as e:
        import traceback
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        return

    print(f"\n✅ Extracted {len(items)} items\n")
    if not items:
        return

    for idx, item in enumerate(items[:limit], start=1):
        print(
            f"─── Article #{idx} ──────────────────────────────────────────────")
        print(f"Title       : {item.get('title')}")
        print(f"Link        : {item.get('link')}")
        print(f"Date        : {item.get('pubDate')}")
        print(f"Author      : {item.get('author')}")
        print(f"Categories  : {item.get('categories')}")
        print(f"Image       : {item.get('image')}")
        desc = item.get("description") or ""
        if len(desc) > 200:
            desc = desc[:200] + " ..."
        print(f"Description : {desc}\n")

    print("=" * 72)
    print(f"Test finished. (Showing first {min(limit, len(items))} items)")
    print("=" * 72)
