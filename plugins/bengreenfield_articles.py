#!/usr/bin/env python3
"""
plugins/bengreenfield_articles.py
---------------------------------
Ben Greenfield Life — Articles
https://bengreenfieldlife.com/article/

WordPress + Elementor site. Pagination via /article/page/N/ (up to
page/95/). Each page has ~18 cards.

Interactive test:
    python plugins/bengreenfield_articles.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# BasePlugin fallback
# ---------------------------------------------------------------------------
try:
    from rss_fetcher import BasePlugin
except ImportError:
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
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

        def fetch_html(self) -> str:
            raise NotImplementedError("This plugin overrides _fetch()")

        @abstractmethod
        def get_items(self) -> List[Dict[str, Any]]:
            ...

        def parse_date(self, text: str) -> datetime:
            return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# HTTP backend: curl_cffi > antibot_bypass > requests
# ---------------------------------------------------------------------------
import requests as _requests

try:
    from curl_cffi import requests as _curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False

try:
    import antibot_bypass as _antibot
    _HAS_ANTIBOT = True
except ImportError:
    _HAS_ANTIBOT = False

_IMPERSONATE = "chrome124"


def _http_get(url: str, headers: Dict[str, str], timeout: int = 25) -> str:
    if _HAS_CURL_CFFI:
        try:
            resp = _curl_requests.get(
                url,
                headers=headers,
                timeout=timeout,
                impersonate=_IMPERSONATE,
            )
            if resp.status_code == 200 and len(resp.text) > 500:
                return resp.text
            print(
                f"[bengreenfield_articles] curl_cffi status={resp.status_code}")
        except Exception as e:
            print(f"[bengreenfield_articles] curl_cffi failed: {e}")

    if _HAS_ANTIBOT:
        try:
            html = _antibot.get_html(url)
            if html and len(html) > 500:
                return html
        except Exception as e:
            print(f"[bengreenfield_articles] antibot_bypass failed: {e}")

    resp = _requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# ===========================================================================
# Plugin
# ===========================================================================
class BenGreenfieldArticlesPlugin(BasePlugin):
    name = "bengreenfield_articles"
    url = "https://bengreenfieldlife.com/article/"
    title = "Ben Greenfield Life — Articles"
    description = (
        "Deeply researched fitness, biohacking, nutrition, and longevity "
        "articles by Ben Greenfield."
    )
    language = "en"
    categories = ["health", "fitness"]
    max_items = 50

    # Only grab cards from the loop grid, not other posts rendered in
    # header/footer widgets.  data-elementor-type="loop-item" is the most
    # precise marker on every article card.
    ITEM_SELECTOR = 'div[data-elementor-type="loop-item"].e-loop-item'

    # 18 per page × 6 pages = 108, enough for max_items=50
    MAX_PAGES = 6
    PAGE_DELAY = 1.0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://bengreenfieldlife.com/",
        "Upgrade-Insecure-Requests": "1",
    }

    # ------------------------------------------------------------------
    def get_items(self) -> List[Dict[str, Any]]:
        import time

        items: List[Dict[str, Any]] = []
        seen: set = set()

        for page in range(1, self.MAX_PAGES + 1):
            if len(items) >= self.max_items:
                break

            page_url = (
                self.url
                if page == 1
                else self.url.rstrip("/") + f"/page/{page}/"
            )

            try:
                html = _http_get(page_url, self.headers)
            except Exception as e:
                print(f"[{self.name}] fetch failed for {page_url}: {e}")
                break

            soup = BeautifulSoup(html, "lxml")
            elements = soup.select(self.ITEM_SELECTOR)
            if not elements:
                print(f"[{self.name}] no items on page {page}")
                break

            new = 0
            for el in elements:
                item = self._parse_item(el)
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

    # ------------------------------------------------------------------
    def _parse_item(self, el) -> Optional[Dict[str, Any]]:
        # ---- Title ----
        title_el = el.select_one(
            '[data-widget_type="theme-post-title.default"] '
            'h2.elementor-heading-title'
        )
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None

        # ---- Link (Read More button) ----
        link_a = el.select_one('a.elementor-button[href]')
        if not link_a or not link_a.get("href"):
            # Fallback: image anchor
            link_a = el.select_one(
                '[data-widget_type="theme-post-featured-image.default"] '
                'a[href]'
            )
        if not link_a or not link_a.get("href"):
            return None
        link = urljoin(self.url, link_a["href"])

        # ---- Image ----
        image = None
        img = el.select_one(
            '[data-widget_type="theme-post-featured-image.default"] img'
        )
        if img:
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
            )
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                image = urljoin(self.url, src)

        # ---- Date ----
        pub_date = datetime.now(timezone.utc)
        time_el = el.select_one('li[itemprop="datePublished"] time')
        if time_el:
            text = time_el.get_text(strip=True) or time_el.get("datetime")
            if text:
                pub_date = self.parse_date(text)

        # ---- Excerpt ----
        description = ""
        desc_el = el.select_one(
            '[data-widget_type="theme-post-excerpt.default"] p'
        )
        if desc_el:
            description = desc_el.get_text(strip=True)

        # ---- Tags (from WP post classes) ----
        tags: List[str] = []
        for cls in (el.get("class") or []):
            if cls.startswith("tag-"):
                tags.append(cls[4:].replace("-", " "))
        # Post type prefix sometimes contains category-* classes:
        for cls in (el.get("class") or []):
            if cls.startswith("category-") and cls != "category-article":
                pass  # too noisy; skip generic category-* classes
        all_categories = list(dict.fromkeys(self.categories + tags))

        # ---- Enclosures ----
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
            "author":      "Ben Greenfield",
            "guid":        link,
            "categories":  all_categories,
            "image":       image,
            "enclosures":  enclosures,
            "extra":       {},
        }

    # ------------------------------------------------------------------
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
            "%B %d, %Y",            # November 5, 2026
            "%b %d, %Y",            # Nov 5, 2026
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


# ===========================================================================
# Interactive test
# ===========================================================================
def interactive_test():
    print("=" * 72)
    print("Interactive Test — BenGreenfieldArticlesPlugin")
    print("=" * 72)
    plugin = BenGreenfieldArticlesPlugin()
    print(f"Plugin    : {plugin.name}")
    print(f"URL       : {plugin.url}")
    print(f"Max items : {plugin.max_items}")
    print(
        "HTTP      : "
        + ("curl_cffi" if _HAS_CURL_CFFI else "requests")
        + (" + antibot_bypass" if _HAS_ANTIBOT else "")
    )
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

    for idx, item in enumerate(items[:3], start=1):
        print(
            f"─── Article #{idx} ──────────────────────────────────────────────")
        print(f"Title       : {item.get('title')}")
        print(f"Link        : {item.get('link')}")
        print(f"Date        : {item.get('pubDate')}")
        print(f"Author      : {item.get('author')}")
        print(f"Categories  : {item.get('categories')[:6]}")
        print(f"Image       : {item.get('image')}")
        desc = item.get("description") or ""
        if len(desc) > 200:
            desc = desc[:200] + " ..."
        print(f"Description : {desc}\n")

    print("=" * 72)
    print(f"Test finished. (Showing first {min(3, len(items))} items)")
    print("=" * 72)


if __name__ == "__main__":
    interactive_test()
