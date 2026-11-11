#!/usr/bin/env python3
"""
plugins/aibase_daily.py
-----------------------
AIBase — AI Daily Brief
https://news.aibase.com/daily

This site is a Nuxt.js SSR app. The full daily-brief data lives inside
a `<script id="__NUXT_DATA__">` block in the rendered HTML, encoded in
Nuxt's "devalue" format (a flat array of values where objects store
references as integer indices into the same array).

We prefer parsing that JSON over HTML scraping because it gives us:
    - precise publish timestamps (not "4 days ago")
    - numeric view counts (not "18.4K")
    - the article `oid` for direct linking

HTML scraping is kept as a fallback in case the devalue layout changes.

Pagination: the HTML page ignores `?page=N` (always returns page 1).
The Nuxt app paginates client-side via the JSON API at
`https://mcpapi.aibase.cn/api/aiInfo/dailyNews?pageNo=N`. We call that
endpoint directly and fall back to the HTML/devalue path if it fails.

Interactive test:
    python plugins/aibase_daily.py
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
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
            raise NotImplementedError("This plugin uses _http_get()")

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
            print(f"[aibase_daily] curl_cffi status={resp.status_code}")
        except Exception as e:
            print(f"[aibase_daily] curl_cffi failed: {e}")

    if _HAS_ANTIBOT:
        try:
            html = _antibot.get_html(url)
            if html and len(html) > 500:
                return html
        except Exception as e:
            print(f"[aibase_daily] antibot_bypass failed: {e}")

    resp = _requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# ===========================================================================
# Plugin
# ===========================================================================
class AIBaseDailyPlugin(BasePlugin):
    """AIBase — AI Daily Brief."""

    name = "aibase_daily"
    url = "https://news.aibase.com/daily"
    title = "AI Daily Brief — AIBase"
    description = (
        "Daily digest of AI industry news in 3 minutes: model releases, "
        "product updates, and market trends."
    )
    language = "zh-cn"
    categories = ["Chinese", "tech"]
    max_items = 100

    # 20 items per page → 5 pages covers max_items=100
    MAX_PAGES = 6
    PAGE_DELAY = 1.0

    # The Nuxt app paginates client-side via this JSON API; the HTML
    # page ignores ?page=N and always returns page 1.
    API_URL = "https://mcpapi.aibase.cn/api/aiInfo/dailyNews"
    API_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://news.aibase.com/",
    }

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
        "Referer": "https://news.aibase.com/",
        "Upgrade-Insecure-Requests": "1",
    }

    # Devalue tags used by Nuxt/Vue that wrap a value by index.
    # Everything else is a regular array of refs / dict of refs.
    _WRAP_TAGS = {"ShallowReactive", "Reactive", "ShallowRef", "Ref"}
    _EMPTY_TAGS = {"EmptyRef", "EmptyShallowRef", "EmptyReactive"}

    # HTML fallback
    HTML_CARD_SELECTOR = 'div[pathstr="client/doc"] a[href^="/daily/"]'

    # ------------------------------------------------------------------
    # Main extraction
    # ------------------------------------------------------------------
    def get_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen_links: set = set()
        seen_oids: set = set()

        for page in range(1, self.MAX_PAGES + 1):
            if len(items) >= self.max_items:
                break

            # Primary: JSON API (the HTML page ignores ?page=N)
            page_items = self._fetch_api_page(page)

            if page_items is None:
                # Fallback: HTML page + devalue/HTML parsing
                page_url = self.url if page == 1 else f"{self.url}?page={page}"
                try:
                    html = _http_get(page_url, self.headers)
                except Exception as e:
                    print(f"[{self.name}] fetch failed for {page_url}: {e}")
                    break

                page_items = self._parse_devalue(html)
                if not page_items:
                    print(f"[{self.name}] devalue empty, falling back to HTML")
                    page_items = self._parse_html(html)

            if not page_items:
                print(f"[{self.name}] no items on page {page}")
                break

            new = 0
            for item in page_items:
                if item["link"] in seen_links:
                    continue
                # Guard against pagination not working (same content repeated)
                oid = item.get("extra", {}).get("daily_id")
                if oid and oid in seen_oids:
                    continue
                seen_links.add(item["link"])
                if oid:
                    seen_oids.add(oid)
                items.append(item)
                new += 1
                if len(items) >= self.max_items:
                    break

            print(f"[{self.name}] page {page}: +{new} (total {len(items)})")
            if new == 0:
                # Pagination didn't advance — stop to avoid infinite requests
                break

            if page < self.MAX_PAGES:
                time.sleep(self.PAGE_DELAY)

        return items

    # ------------------------------------------------------------------
    # JSON API (primary) — the HTML page ignores ?page=N
    # ------------------------------------------------------------------
    def _fetch_api_page(self, page: int) -> Optional[List[Dict[str, Any]]]:
        """Fetch one page from the JSON API. Returns None on failure."""
        params = {
            "pageNo": page,
            "t": int(time.time() * 1000),
            "langType": "en",
        }
        try:
            if _HAS_CURL_CFFI:
                resp = _curl_requests.get(
                    self.API_URL,
                    params=params,
                    headers=self.API_HEADERS,
                    timeout=25,
                    impersonate=_IMPERSONATE,
                )
                if resp.status_code != 200:
                    print(f"[{self.name}] API status={resp.status_code}")
                    return None
                payload = resp.json()
            else:
                resp = _requests.get(
                    self.API_URL,
                    params=params,
                    headers=self.API_HEADERS,
                    timeout=25,
                )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            print(f"[{self.name}] API fetch failed for page {page}: {e}")
            return None

        if not isinstance(payload, dict):
            return None
        if payload.get("code") != 200:
            print(f"[{self.name}] API error: {payload.get('msg')}")
            return None
        data = payload.get("data") or {}
        raw_list = data.get("list") or []
        if not isinstance(raw_list, list):
            return None

        items: List[Dict[str, Any]] = []
        for entry in raw_list:
            if not isinstance(entry, dict):
                continue
            item = self._devalue_entry_to_item(entry)
            if item:
                items.append(item)
        return items

    # ------------------------------------------------------------------
    # Devalue parsing (fallback)
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_nuxt_data(html: str) -> Optional[list]:
        m = re.search(
            r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None

    def _resolve_devalue(
        self, data: list, ref: Any, depth: int = 0
    ) -> Any:
        """Resolve a devalue reference into a Python value."""
        if depth > 200:
            return None
        if not isinstance(ref, int):
            return ref
        if ref < 0 or ref >= len(data):
            return None

        val = data[ref]

        if isinstance(val, list):
            if len(val) == 2 and isinstance(val[0], str):
                tag = val[0]
                if tag in self._WRAP_TAGS:
                    return self._resolve_devalue(data, val[1], depth + 1)
                if tag in self._EMPTY_TAGS:
                    return None
            return [self._resolve_devalue(data, v, depth + 1) for v in val]

        if isinstance(val, dict):
            return {
                k: self._resolve_devalue(data, v, depth + 1)
                for k, v in val.items()
            }

        return val

    def _parse_devalue(self, html: str) -> List[Dict[str, Any]]:
        raw = self._extract_nuxt_data(html)
        if not raw or not isinstance(raw, list) or len(raw) < 2:
            return []

        try:
            root = self._resolve_devalue(raw, 1)
            if not isinstance(root, dict):
                return []
            # Path /daily should be for the English version
            inner = root.get("data") or {}
            if not isinstance(inner, dict):
                return []
            get_daily = inner.get("getDailyNews") or {}
            if not isinstance(get_daily, dict):
                return []
            resp = get_daily.get("data") or {}
            if not isinstance(resp, dict):
                return []
            raw_list = resp.get("list") or []
            if not isinstance(raw_list, list):
                return []
        except Exception as e:
            print(f"[{self.name}] devalue structure error: {e}")
            return []

        items: List[Dict[str, Any]] = []
        for entry in raw_list:
            if not isinstance(entry, dict):
                continue
            item = self._devalue_entry_to_item(entry)
            if item:
                items.append(item)
        return items

    def _devalue_entry_to_item(
        self, entry: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        oid = entry.get("oid")
        title = (entry.get("title") or "").strip()
        if not oid or not title:
            return None

        link = f"https://news.aibase.com/daily/{oid}"

        description = (entry.get("description") or "").strip()

        # ---- Image ----
        image = None
        thumb = entry.get("thumb")
        if isinstance(thumb, str) and thumb:
            image = thumb
            if image.startswith("//"):
                image = "https:" + image

        # ---- Date ----
        pub_date = datetime.now(timezone.utc)
        create_time = entry.get("createTime")
        if create_time:
            pub_date = self.parse_date(str(create_time))

        # ---- Author ----
        author = (entry.get("author") or "").strip()
        source = (entry.get("sourceName") or "").strip()
        if not author:
            author = source or "AIBase"

        # ---- Enclosures ----
        enclosures: List[Dict[str, Any]] = []
        if image:
            enclosures.append({
                "url": image,
                "type": self._image_mime(image),
                "length": 0,
                "title": "Cover image",
            })

        # ---- Extra ----
        extra: Dict[str, Any] = {"daily_id": str(oid)}
        pv = entry.get("pv")
        if pv is not None:
            try:
                extra["view_count"] = int(pv)
            except (ValueError, TypeError):
                pass
        if source:
            extra["source"] = source
        if entry.get("author"):
            extra["author"] = entry["author"]
        # Chinese subtitle is a nice bilingual touch for the feed
        subtitle_zh = (entry.get("subtitle") or "").strip()
        if subtitle_zh:
            extra["subtitle_zh"] = subtitle_zh

        return {
            "title":       title,
            "link":        link,
            "description": description or title,
            "content":     None,
            "pubDate":     pub_date,
            "author":      author,
            "guid":        link,
            "categories":  list(self.categories),
            "image":       image,
            "enclosures":  enclosures,
            "extra":       extra,
        }

    # ------------------------------------------------------------------
    # HTML fallback (if devalue layout ever changes)
    # ------------------------------------------------------------------
    def _parse_html(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(self.HTML_CARD_SELECTOR)
        items: List[Dict[str, Any]] = []

        for card in cards:
            href = card.get("href") or ""
            if not href.startswith("/daily/"):
                continue
            link = urljoin(self.url, href)

            # Extract oid from the URL
            m = re.search(r"/daily/(\d+)", href)
            oid = m.group(1) if m else None

            # Title: first div with class "font600" inside the card
            title_el = card.select_one("div.font600")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # Image
            image = None
            img = card.select_one("img[src]")
            if img:
                src = img.get("src")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    image = urljoin(self.url, src)

            # Description: hidden div (visible on desktop)
            description = ""
            desc_el = card.select_one("div.hidden.md\\:block div.truncate2")
            if not desc_el:
                # Tailwind escapes vary — fall back to any .truncate2 that
                # is not the title
                for el in card.select(".truncate2"):
                    if el is not title_el:
                        description = el.get_text(strip=True)
                        break
            else:
                description = desc_el.get_text(strip=True)

            # Date / pv from the info row
            pub_date = datetime.now(timezone.utc)
            view_count = None
            info_divs = card.select(
                "div.flex.items-center.gap-\\[4px\\]"
            )
            # Fallback: look for icon classes
            for div in card.select("i.icon-rili"):
                parent = div.parent
                if parent:
                    text = parent.get_text(strip=True)
                    if text:
                        pub_date = self._parse_relative_date(text)
                        break

            for div in card.select("i.icon-fangwenliang1"):
                parent = div.parent
                if parent:
                    text = parent.get_text(strip=True)
                    view_count = self._parse_view_count(text)
                    break

            enclosures: List[Dict[str, Any]] = []
            if image:
                enclosures.append({
                    "url": image,
                    "type": self._image_mime(image),
                    "length": 0,
                    "title": "Cover image",
                })

            extra: Dict[str, Any] = {}
            if oid:
                extra["daily_id"] = oid
            if view_count is not None:
                extra["view_count"] = view_count

            items.append({
                "title":       title,
                "link":        link,
                "description": description or title,
                "content":     None,
                "pubDate":     pub_date,
                "author":      "AIBase",
                "guid":        link,
                "categories":  list(self.categories),
                "image":       image,
                "enclosures":  enclosures,
                "extra":       extra,
            })

        return items

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _parse_relative_date(self, text: str) -> datetime:
        """Parse strings like '4 days ago', '5 days ago', '11-03'."""
        text = text.strip()
        now = datetime.now(timezone.utc)

        m = re.match(r"(\d+)\s+days?\s+ago", text, re.IGNORECASE)
        if m:
            return now - timedelta(days=int(m.group(1)))

        m = re.match(r"(\d+)\s+hours?\s+ago", text, re.IGNORECASE)
        if m:
            return now - timedelta(hours=int(m.group(1)))

        m = re.match(r"(\d+)\s+minutes?\s+ago", text, re.IGNORECASE)
        if m:
            return now - timedelta(minutes=int(m.group(1)))

        if text.lower() == "just now":
            return now

        # MM-DD (assume current year, China time UTC+8)
        m = re.match(r"(\d{1,2})-(\d{1,2})$", text)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            try:
                dt = datetime(now.year, month, day, 12,
                              0, 0, tzinfo=timezone.utc)
                # If in the future (spans a year boundary), use previous year
                if dt > now + timedelta(days=1):
                    dt = dt.replace(year=now.year - 1)
                return dt
            except ValueError:
                pass

        return now

    @staticmethod
    def _parse_view_count(text: str) -> Optional[int]:
        """Parse '18.4K', '27.9K', '1.2M', '543' into an integer."""
        if not text:
            return None
        m = re.match(r"([\d.]+)\s*([KM]?)", text.strip(), re.IGNORECASE)
        if not m:
            return None
        try:
            num = float(m.group(1))
        except ValueError:
            return None
        suffix = m.group(2).upper()
        if suffix == "K":
            num *= 1_000
        elif suffix == "M":
            num *= 1_000_000
        return int(num)

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
        """
        Parse createTime from the devalue payload.

        Format seen in the wild: "2026-11-06 15:58:54" — site is Chinese,
        so assume China Standard Time (UTC+8) when no timezone is given.
        """
        text = text.strip()
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(text, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
                return dt.astimezone(timezone.utc)
            except ValueError:
                continue
        return datetime.now(timezone.utc)


# ===========================================================================
# Interactive test
# ===========================================================================
def interactive_test():
    print("=" * 72)
    print("Interactive Test — AIBaseDailyPlugin")
    print("=" * 72)
    plugin = AIBaseDailyPlugin()
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
        extra = item.get("extra") or {}
        if "view_count" in extra:
            print(f"Views       : {extra['view_count']}")
        if "subtitle_zh" in extra:
            zh = extra["subtitle_zh"]
            print(f"Subtitle_zh : {zh[:80]}{'...' if len(zh) > 80 else ''}")
        desc = item.get("description") or ""
        if len(desc) > 200:
            desc = desc[:200] + " ..."
        print(f"Description : {desc}\n")

    print("=" * 72)
    print(f"Test finished. (Showing first {min(3, len(items))} items)")
    print("=" * 72)


if __name__ == "__main__":
    interactive_test()
