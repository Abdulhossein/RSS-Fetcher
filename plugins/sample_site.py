#!/usr/bin/env python3
"""
plugins/sample_site.py
----------------------
Official complete & dynamic sample plugin.

This file is intentionally written as a rich template so you can copy it
and adapt it for any real website.

It demonstrates:
- Full item schema (title, link, description, content, author, categories,
  image, enclosures, extra, ...)
- Flexible extraction (CSS selectors + ability to override everything)
- Date parsing hook
- Interactive test mode (run this file directly)

Usage (normal – discovered by rss_fetcher.py):
    Just place this file inside the plugins/ folder.

Usage (interactive test):
    python plugins/sample_site.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Import BasePlugin
# When this file lives inside the real project, use the relative import.
# For standalone testing we fall back to a minimal BasePlugin definition.
# ---------------------------------------------------------------------------
try:
    from rss_fetcher import BasePlugin
except ImportError:
    # Minimal fallback so you can run this file alone for testing
    from abc import ABC, abstractmethod

    class BasePlugin(ABC):
        name: str = "unnamed"
        url: str = ""
        title: str = ""
        description: str = ""
        language: str = "en"
        categories: List[str] = []
        max_items: int = 100
        headers: Dict[str, str] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        def fetch_html(self) -> str:
            resp = requests.get(self.url, headers=self.headers, timeout=25)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text

        @abstractmethod
        def get_items(self) -> List[Dict[str, Any]]:
            ...

        def parse_date(self, text: str) -> datetime:
            return datetime.now(timezone.utc)


# ===========================================================================
#  SAMPLE PLUGIN – COMPLETE TEMPLATE
# ===========================================================================
class SampleSitePlugin(BasePlugin):
    """
    Complete dynamic example plugin.

    Change the values below and the selectors to match any real website.
    You can also completely rewrite get_items() if the site is complex
    (API, JavaScript-rendered, etc.).
    """

    # ------------------------------------------------------------------
    # Basic metadata (REQUIRED)
    # ------------------------------------------------------------------
    name = "sample_site"                    # unique filename-safe name
    url = "https://example.com/news"        # listing page
    title = "Sample News Site"
    description = "Latest articles from the Sample News Site"
    language = "en"
    categories = ["news", "tech"]           # used for category aggregation
    max_items = 100

    # ------------------------------------------------------------------
    # CSS Selectors (change these for your target site)
    # ------------------------------------------------------------------
    item_selector = "article.post, .post-item, .news-item, .entry"
    title_selector = "h2 a, h3 a, .title a, .entry-title a"
    link_selector = "h2 a, h3 a, .title a, .entry-title a"
    description_selector = ".excerpt, .summary, .description, .entry-summary, p"
    content_selector = None                 # optional – full content if available on list page
    date_selector = "time, .date, .published, .post-date, .entry-date"
    author_selector = ".author, .byline, .writer, .entry-author"
    image_selector = "img.cover, img.thumbnail, img.wp-post-image, .post-thumbnail img, img"

    # ------------------------------------------------------------------
    # Optional extra headers (cookies, authorization, etc.)
    # ------------------------------------------------------------------
    # headers = {
    #     "User-Agent": "...",
    #     "Cookie": "session=...",
    # }

    # ------------------------------------------------------------------
    # Main extraction method
    # ------------------------------------------------------------------
    def get_items(self) -> List[Dict[str, Any]]:
        """
        Returns a list of rich item dictionaries.
        You can completely replace this method for complex sites.
        """
        html = self.fetch_html()
        soup = BeautifulSoup(html, "lxml")
        items: List[Dict[str, Any]] = []

        elements = soup.select(self.item_selector)
        if not elements:
            print(f"[{self.name}] Warning: no elements found with selector '{self.item_selector}'")
            return items

        for el in elements[: self.max_items]:
            try:
                item = self._parse_single_item(el)
                if item and item.get("title") and item.get("link"):
                    items.append(item)
            except Exception as e:
                # Continue even if one item fails
                print(f"[{self.name}] Skipping one item due to error: {e}")
                continue

        return items

    def _parse_single_item(self, el: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Extract one item from a single HTML element."""

        # Title
        title_el = el.select_one(self.title_selector)
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None

        # Link
        link_el = el.select_one(self.link_selector)
        if not link_el or not link_el.get("href"):
            return None
        link = urljoin(self.url, link_el["href"])

        # Description
        description = ""
        if self.description_selector:
            desc_el = el.select_one(self.description_selector)
            if desc_el:
                # Keep some HTML if present
                description = str(desc_el) if desc_el.find() else desc_el.get_text(strip=True)

        # Full content (rarely available on listing pages)
        content = None
        if self.content_selector:
            content_el = el.select_one(self.content_selector)
            if content_el:
                content = str(content_el)

        # Author
        author = None
        if self.author_selector:
            author_el = el.select_one(self.author_selector)
            if author_el:
                author = author_el.get_text(strip=True)

        # Date
        pub_date = datetime.now(timezone.utc)
        if self.date_selector:
            date_el = el.select_one(self.date_selector)
            if date_el:
                # Prefer datetime attribute if present
                date_text = date_el.get("datetime") or date_el.get_text(strip=True)
                pub_date = self.parse_date(date_text)

        # Image
        image = None
        if self.image_selector:
            img_el = el.select_one(self.image_selector)
            if img_el:
                src = img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy-src")
                if src:
                    image = urljoin(self.url, src)

        # Build the full item according to the agreed schema
        item: Dict[str, Any] = {
            "title": title,
            "link": link,
            "description": description or title,
            "content": content,
            "pubDate": pub_date,
            "author": author,
            "guid": link,
            "categories": self.categories.copy(),
            "image": image,
            "enclosures": [],          # can be filled for audio/video
            "extra": {
                # Example of unlimited extra data
                # "views": 1234,
                # "reading_time": "5 min",
                # "is_featured": False,
            },
        }

        # Example of adding an enclosure (uncomment & adapt if needed)
        # if image:
        #     item["enclosures"].append({
        #         "url": image,
        #         "type": "image/jpeg",
        #         "length": 0,
        #         "title": "Cover image"
        #     })

        return item

    def parse_date(self, text: str) -> datetime:
        """
        Override this method for real sites.
        This is only a naive fallback.
        """
        text = text.strip()
        # Try common ISO formats first
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d %b %Y",
            "%b %d, %Y",
        ):
            try:
                dt = datetime.strptime(text, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        # Fallback
        return datetime.now(timezone.utc)


# ===========================================================================
#  INTERACTIVE TEST MODE
# ===========================================================================
def interactive_test():
    """
    Run this file directly to test the plugin interactively.
    It will fetch the page, extract items, and print a nice preview
    of the first (latest) item.
    """
    print("=" * 70)
    print("Interactive Test Mode – SampleSitePlugin")
    print("=" * 70)

    plugin = SampleSitePlugin()

    print(f"\nPlugin name   : {plugin.name}")
    print(f"Target URL    : {plugin.url}")
    print(f"Categories    : {plugin.categories}")
    print(f"Max items     : {plugin.max_items}")
    print("-" * 70)

    try:
        print("Fetching page...")
        items = plugin.get_items()
    except Exception as e:
        print(f"\n❌ Error while fetching/parsing: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\n✅ Successfully extracted {len(items)} items\n")

    if not items:
        print("No items found. Check your CSS selectors.")
        return

    # Show a clean preview of the first item
    first = items[0]

    print("─── Preview of the latest item ───────────────────────────────")
    print(f"Title       : {first.get('title')}")
    print(f"Link        : {first.get('link')}")
    print(f"Author      : {first.get('author')}")
    print(f"Date        : {first.get('pubDate')}")
    print(f"Categories  : {first.get('categories')}")
    print(f"Image       : {first.get('image')}")
    print(f"GUID        : {first.get('guid')}")

    desc = first.get("description") or ""
    # Shorten long descriptions for readability
    if len(desc) > 300:
        desc = desc[:300] + " ..."
    print(f"\nDescription :\n{desc}")

    if first.get("extra"):
        print(f"\nExtra       : {json.dumps(first['extra'], ensure_ascii=False, indent=2)}")

    print("\n─── Raw first item (JSON) ────────────────────────────────────")
    # Make datetime serializable
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)

    print(json.dumps(first, ensure_ascii=False, indent=2, default=default))
    print("=" * 70)
    print("Test finished. If everything looks good, the plugin is ready.")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Entry point for interactive testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    interactive_test()