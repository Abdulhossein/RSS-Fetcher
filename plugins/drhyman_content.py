#!/usr/bin/env python3
"""
plugins/drhyman_content.py
--------------------------
Mark Hyman, MD — Content Library
https://drhyman.com/blogs/content/

Shopify-based content library. Extracts articles, recipes, and podcast
episodes from Dr. Mark Hyman's blog. Pagination via ?page=N (up to ~78
pages, ~34 items per page).

The listing page has no excerpt/summary, so description is built from
reading time / episode number / tags. Full content is not fetched to
keep requests reasonable (1 per page instead of 1 per article).

Interactive test:
    python plugins/drhyman_content.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# BasePlugin fallback for standalone testing
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
# HTTP backend selection: curl_cffi > antibot_bypass > requests
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
    """Fetch HTML using the best available anti-bot backend."""
    # 1. curl_cffi — real Chrome TLS fingerprint (fast, usually enough for Shopify)
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
            print(f"[drhyman_content] curl_cffi status={resp.status_code}")
        except Exception as e:
            print(f"[drhyman_content] curl_cffi failed: {e}")

    # 2. antibot_bypass — multi-method fallback (Playwright/Selenium/etc.)
    if _HAS_ANTIBOT:
        try:
            html = _antibot.get_html(url)
            if html and len(html) > 500:
                return html
        except Exception as e:
            print(f"[drhyman_content] antibot_bypass failed: {e}")

    # 3. Plain requests
    resp = _requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# ===========================================================================
# Plugin
# ===========================================================================
class DrHymanContentPlugin(BasePlugin):
    """Mark Hyman, MD — Content Library."""

    name = "drhyman_content"
    url = "https://drhyman.com/blogs/content/"
    title = "Mark Hyman, MD — Content Library"
    description = (
        "Articles, recipes, and podcast episodes from Dr. Mark Hyman "
        "on functional medicine and healthy living."
    )
    language = "en"
    categories = ["health", "wellness", "nutrition"]
    max_items = 50

    # Marketing tiles have class "marketing-tile" and reuse the article card
    # markup for shop promos — filter them out.
    ITEM_SELECTOR = "div.blog-articles__article.article:not(.marketing-tile)"

    # 34 items per page → 6 pages is more than enough for max_items=50
    MAX_PAGES = 6

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
        "Referer": "https://drhyman.com/",
        "Upgrade-Insecure-Requests": "1",
    }

    # ------------------------------------------------------------------
    # Main extraction
    # ------------------------------------------------------------------
    def get_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen: set = set()

        for page in range(1, self.MAX_PAGES + 1):
            if len(items) >= self.max_items:
                break

            # Pagination is ?page=N on the base URL (with or without trailing slash)
            if page == 1:
                page_url = self.url
            else:
                page_url = self.url.rstrip("/") + f"?page={page}"

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

        return items

    # ------------------------------------------------------------------
    # Single card parser
    # ------------------------------------------------------------------
    def _parse_item(self, el) -> Optional[Dict[str, Any]]:
        # ---- Title + Link ----
        title_a = el.select_one("h3.card__heading a.full-unstyled-link")
        if not title_a:
            return None

        title = title_a.get_text(strip=True)
        href = (title_a.get("href") or "").strip()
        if not title or not href:
            return None

        link = urljoin(self.url, href)

        # ---- Image ----
        image = None
        img = el.select_one("div.article-card__image img, img.motion-reduce")
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
        time_el = el.select_one("time[datetime]")
        if time_el and time_el.get("datetime"):
            pub_date = self.parse_date(time_el["datetime"])

        # ---- Tags ----
        tags: List[str] = []
        for pill in el.select("div.pills span.pill"):
            tag = pill.get_text(strip=True)
            if tag:
                tags.append(tag)

        # ---- Extra info (reading time / episode) ----
        extra: Dict[str, Any] = {}
        info = el.select_one("div.article-card__info")
        if info:
            for span in info.select("span"):
                text = span.get_text(strip=True)
                if not text:
                    continue
                low = text.lower()
                if "min read" in low or "mins read" in low:
                    extra["reading_time"] = text
                elif low.startswith("episode"):
                    extra["episode"] = text
                elif "lesson" in low:
                    extra["lessons"] = text

        # ---- Categories = base + tags (dedup, order preserved) ----
        all_categories = list(dict.fromkeys(self.categories + tags))

        # ---- Author ----
        author = "Mark Hyman, MD"

        # ---- Enclosures ----
        enclosures: List[Dict[str, Any]] = []
        if image:
            enclosures.append({
                "url": image,
                "type": self._image_mime(image),
                "length": 0,
                "title": "Cover image",
            })

        # ---- Description ----
        # No excerpt on the listing page, so build from extras + tags.
        # Falls back to the title if nothing useful exists.
        desc_parts: List[str] = []
        if extra.get("episode"):
            desc_parts.append(str(extra["episode"]))
        if extra.get("reading_time"):
            desc_parts.append(str(extra["reading_time"]))
        if extra.get("lessons"):
            desc_parts.append(str(extra["lessons"]))
        if tags:
            desc_parts.append(" · ".join(tags))
        description = " · ".join(desc_parts) if desc_parts else title

        return {
            "title": title,
            "link": link,
            "description": description,
            "content": None,
            "pubDate": pub_date,
            "author": author,
            "guid": link,
            "categories": all_categories,
            "image": image,
            "enclosures": enclosures,
            "extra": extra,
        }

    # ------------------------------------------------------------------
    # Helpers
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
            "%Y-%m-%dT%H:%M:%SZ",     # 2026-11-06T22:14:32Z
            "%Y-%m-%dT%H:%M:%S%z",    # 2026-11-06T22:14:32+00:00
            "%Y-%m-%dT%H:%M:%S",      # 2026-11-06T22:14:32
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
    print("Interactive Test — DrHymanContentPlugin")
    print("=" * 72)
    plugin = DrHymanContentPlugin()
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
        print(f"Categories  : {item.get('categories')}")
        print(f"Image       : {item.get('image')}")
        if item.get("extra"):
            print(f"Extra       : {item['extra']}")
        desc = item.get("description") or ""
        if len(desc) > 200:
            desc = desc[:200] + " ..."
        print(f"Description : {desc}\n")

    print("=" * 72)
    print(f"Test finished. (Showing first {min(3, len(items))} items)")
    print("=" * 72)


if __name__ == "__main__":
    interactive_test()
