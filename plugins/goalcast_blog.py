#!/usr/bin/env python3
"""
plugins/goalcast_blog.py
------------------------
Goalcast — Blog
https://www.goalcast.com/blog/

Goalcast is a Next.js app that server-renders the entire post dataset
into the initial HTML — the "posts" array is embedded inside the React
Server Components (RSC) payload, which is a series of:

    self.__next_f.push([1, "<escaped JSON-ish chunk>"])
    self.__next_f.push([1, "<escaped JSON-ish chunk>"])

The client-side pagination buttons slice that in-memory array and never
hit the server for more data, so `/blog/page/N/` returns the same 20
cards as page 1. We therefore parse the RSC payload directly, which
gives us the *full* dataset in a single HTTP request.

Strategy:
    1. Fetch /blog/ once.
    2. Concatenate all `__next_f.push` string chunks.
    3. Locate `"posts":`, balance brackets to isolate the array, json.loads it.
    4. Map each entry to the plugin item schema.

HTML scraping (matching the `blog_postCard*__*` class prefixes) is kept
as a fallback in case the RSC layout ever changes. It only scrapes what
is rendered on the current page — the RSC path is the way to get the
whole catalogue.

Pagination: /blog/page/N/ is *not* a valid API — it re-serves page 1.
We still attempt it as a last resort because the site may someday fix
the routing, but in practice the RSC path will always win.

Interactive test:
    python plugins/goalcast_blog.py
"""

from __future__ import annotations

import json
import re
import time
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
            print(f"[goalcast_blog] curl_cffi status={resp.status_code}")
        except Exception as e:
            print(f"[goalcast_blog] curl_cffi failed: {e}")

    if _HAS_ANTIBOT:
        try:
            html = _antibot.get_html(url)
            if html and len(html) > 500:
                return html
        except Exception as e:
            print(f"[goalcast_blog] antibot_bypass failed: {e}")

    resp = _requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _http_get_with_retry(
    url: str,
    headers: Dict[str, str],
    retries: int = 2,
    base_delay: float = 1.5,
) -> Optional[str]:
    """
    Fetch a page, retrying on transient failures.

    Returns None (instead of raising) when the page is definitively
    missing (404 / 410) so callers can stop quietly.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return _http_get(url, headers)
        except _requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                return None
            last_exc = e
        except Exception as e:
            last_exc = e
        if attempt < retries:
            delay = base_delay * (2 ** attempt)
            print(f"[goalcast_blog] retry {attempt + 1}/{retries} "
                  f"for {url} in {delay:.1f}s ({last_exc})")
            time.sleep(delay)
    print(f"[goalcast_blog] giving up on {url}: {last_exc}")
    return None


# ===========================================================================
# Plugin
# ===========================================================================
class GoalcastBlogPlugin(BasePlugin):
    """Goalcast — Blog."""

    name = "goalcast_blog"
    url = "https://www.goalcast.com/blog/"
    title = "Blog — Goalcast"
    description = (
        "Inspiring stories, motivational content, and life lessons from "
        "Goalcast. Browse articles on personal development, mindset, and "
        "overcoming adversity."
    )
    language = "en"
    categories = ["English", "Lifestyle"]

    # The RSC payload gives us the entire catalogue in one request, so
    # we raise the cap generously. Subclass and override to trim.
    max_items = 100

    # HTML fallback config — kept for resilience, though /blog/page/N/
    # currently re-serves page 1, so the fallback will only ever yield
    # the 20 items rendered on the first page.
    MAX_PAGES = 20
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
        "Referer": "https://www.goalcast.com/",
        "Upgrade-Insecure-Requests": "1",
    }

    # CSS selector fragments — match the stable class-prefix portion so
    # we stay resilient against Next.js hashed suffixes changing per build.
    CARD_SELECTOR = 'a[class*="blog_postCard__"]'
    TITLE_SELECTOR = 'h2[class*="blog_postCardTitle__"]'
    EXCERPT_SELECTOR = 'p[class*="blog_postCardExcerpt__"]'
    CATEGORY_SELECTOR = 'span[class*="blog_postCardCategory__"]'
    DATE_SELECTOR = 'span[class*="blog_postCardDate__"]'
    READ_TIME_SELECTOR = 'span[class*="blog_postCardReadTime__"]'

    # ==================================================================
    # Main extraction
    # ==================================================================
    def get_items(self) -> List[Dict[str, Any]]:
        started_at = time.time()

        # ---- Primary: one fetch, parse the RSC payload ----
        html: Optional[str] = None
        try:
            html = _http_get_with_retry(self.url, self.headers)
        except Exception as e:
            print(f"[{self.name}] initial fetch failed: {e}")

        if html:
            rsc_items = self._extract_rsc_posts(html)
            if rsc_items:
                print(f"[{self.name}] RSC payload: {len(rsc_items)} posts")
                unique: List[Dict[str, Any]] = []
                seen: set = set()
                for item in rsc_items:
                    if item["link"] in seen:
                        continue
                    seen.add(item["link"])
                    unique.append(item)
                    if len(unique) >= self.max_items:
                        break
                print(f"[{self.name}] done: {len(unique)} items "
                      f"in {time.time() - started_at:.0f}s")
                return unique

        # ---- Fallback: HTML paging (currently re-serves page 1) ----
        print(f"[{self.name}] RSC payload empty — falling back to HTML paging")
        return self._get_items_html_fallback(started_at)

    def _get_items_html_fallback(
        self, started_at: float
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen_links: set = set()
        pages_crawled = 0

        for page in range(1, self.MAX_PAGES + 1):
            if len(items) >= self.max_items:
                break

            page_url = (
                self.url
                if page == 1
                else f"https://www.goalcast.com/blog/page/{page}/"
            )
            page_html = _http_get_with_retry(page_url, self.headers)
            if page_html is None:
                print(f"[{self.name}] page {page} unavailable, stopping")
                break

            pages_crawled += 1
            page_items = self._parse_html(page_html)
            if not page_items:
                print(f"[{self.name}] no items on page {page}, stopping")
                break

            new = 0
            for item in page_items:
                if item["link"] in seen_links:
                    continue
                seen_links.add(item["link"])
                items.append(item)
                new += 1
                if len(items) >= self.max_items:
                    break

            print(f"[{self.name}] page {page}/{self.MAX_PAGES}: "
                  f"+{new} (total {len(items)})")
            if new == 0:
                print(f"[{self.name}] no new items on page {page}, stopping")
                break
            if page < self.MAX_PAGES:
                time.sleep(self.PAGE_DELAY)

        print(f"[{self.name}] done: {len(items)} items across "
              f"{pages_crawled} page(s) in {time.time() - started_at:.0f}s")
        return items

    # ==================================================================
    # RSC payload extraction (primary)
    # ==================================================================
    _RSC_PUSH_RE = re.compile(
        r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)',
        re.DOTALL,
    )

    def _extract_rsc_posts(self, html: str) -> List[Dict[str, Any]]:
        """
        Pull the `posts` array out of the React Server Components payload
        embedded in the initial HTML.

        Next.js ships the payload as a series of:
            self.__next_f.push([1, "<escaped JSON-ish string>"])
        We concatenate those strings, locate `"posts":`, and balance
        brackets to isolate the array — no full Flight parser required.
        """
        chunks: List[str] = []
        for m in self._RSC_PUSH_RE.finditer(html):
            raw = m.group(1)
            try:
                chunks.append(json.loads(f'"{raw}"'))
            except json.JSONDecodeError:
                continue

        if not chunks:
            return []

        payload = "".join(chunks)

        idx = payload.find('"posts":')
        if idx == -1:
            return []

        start = payload.find('[', idx)
        if start == -1:
            return []

        depth = 0
        end = -1
        in_string = False
        escape = False
        for i in range(start, len(payload)):
            ch = payload[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end == -1 or depth != 0:
            return []

        try:
            posts = json.loads(payload[start: end + 1])
        except json.JSONDecodeError:
            return []

        if not isinstance(posts, list):
            return []

        items: List[Dict[str, Any]] = []
        for entry in posts:
            if not isinstance(entry, dict):
                continue
            item = self._rsc_entry_to_item(entry)
            if item:
                items.append(item)
        return items

    def _rsc_entry_to_item(
        self, entry: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Map a raw RSC post object to the plugin item schema."""
        title = (entry.get("title") or "").strip()
        slug = (entry.get("slug") or "").strip()
        if not title or not slug:
            return None

        link = urljoin("https://www.goalcast.com", f"/{slug}/")

        pub_date = datetime.now(timezone.utc)
        published_at = entry.get("publishedAt")
        if published_at:
            pub_date = self.parse_date(str(published_at))

        image = entry.get("featuredImage")
        if isinstance(image, str) and image.startswith("//"):
            image = "https:" + image

        category = (entry.get("category") or "").strip()
        read_time = entry.get("readTime")

        enclosures: List[Dict[str, Any]] = []
        if image and isinstance(image, str):
            enclosures.append({
                "url": image,
                "type": self._image_mime(image),
                "length": 0,
                "title": "Cover image",
            })

        extra: Dict[str, Any] = {}
        if category:
            extra["goalcast_category"] = category
        if isinstance(read_time, int) and read_time > 0:
            extra["read_time_minutes"] = read_time

        return {
            "title":       title,
            "link":        link,
            "description": (entry.get("excerpt") or title).strip(),
            "content":     None,
            "pubDate":     pub_date,
            "author":      "Goalcast",
            "guid":        link,
            "categories":  list(self.categories),
            "image":       image if isinstance(image, str) and image else None,
            "enclosures":  enclosures,
            "extra":       extra,
        }

    # ==================================================================
    # HTML fallback parser
    # ==================================================================
    def _parse_html(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(self.CARD_SELECTOR)
        items: List[Dict[str, Any]] = []

        for card in cards:
            href = card.get("href") or ""
            if not href:
                continue
            link = urljoin("https://www.goalcast.com", href)

            # --- Title ---
            title_el = card.select_one(self.TITLE_SELECTOR)
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # --- Excerpt ---
            description = ""
            excerpt_el = card.select_one(self.EXCERPT_SELECTOR)
            if excerpt_el:
                description = excerpt_el.get_text(" ", strip=True)

            # --- Category ---
            category = ""
            category_el = card.select_one(self.CATEGORY_SELECTOR)
            if category_el:
                category = category_el.get_text(strip=True)

            # --- Date ---
            pub_date = datetime.now(timezone.utc)
            date_el = card.select_one(self.DATE_SELECTOR)
            if date_el:
                pub_date = self._parse_card_date(date_el.get_text(strip=True))

            # --- Read time ---
            read_time: Optional[int] = None
            rt_el = card.select_one(self.READ_TIME_SELECTOR)
            if rt_el:
                read_time = self._parse_read_time(
                    rt_el.get_text(" ", strip=True))

            # --- Image ---
            image = None
            img = card.select_one("img[src]")
            if img:
                src = img.get("src") or ""
                if src.startswith("//"):
                    src = "https:" + src
                if src:
                    image = urljoin("https://www.goalcast.com", src)

            # --- Enclosures ---
            enclosures: List[Dict[str, Any]] = []
            if image:
                enclosures.append({
                    "url": image,
                    "type": self._image_mime(image),
                    "length": 0,
                    "title": "Cover image",
                })

            # --- Extra ---
            extra: Dict[str, Any] = {}
            if category:
                extra["goalcast_category"] = category
            if read_time is not None:
                extra["read_time_minutes"] = read_time

            items.append({
                "title":       title,
                "link":        link,
                "description": description or title,
                "content":     None,
                "pubDate":     pub_date,
                "author":      "Goalcast",
                "guid":        link,
                "categories":  list(self.categories),
                "image":       image,
                "enclosures":  enclosures,
                "extra":       extra,
            })

        return items

    # ==================================================================
    # Helpers
    # ==================================================================
    def _parse_card_date(self, text: str) -> datetime:
        """
        Parse a card date like "Feb 9, 2025".

        Goalcast displays dates in the site's local timezone (US Eastern).
        We normalize to noon UTC on that day so ordering is stable and
        readers in other zones don't see an off-by-one day flip.
        """
        text = text.strip()
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text, fmt)
                return dt.replace(
                    hour=12, minute=0, second=0,
                    tzinfo=timezone.utc,
                )
            except ValueError:
                continue
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_read_time(text: str) -> Optional[int]:
        """Parse '1 min read', '8 min read' into an integer."""
        m = re.search(r"(\d+)\s*min", text, re.IGNORECASE)
        return int(m.group(1)) if m else None

    @staticmethod
    def _image_mime(url: str) -> str:
        lowered = url.lower().split("?")[0]
        if lowered.endswith(".png"):
            return "image/png"
        if lowered.endswith(".webp"):
            return "image/webp"
        if lowered.endswith(".gif"):
            return "image/gif"
        if lowered.endswith(".svg"):
            return "image/svg+xml"
        return "image/jpeg"

    def parse_date(self, text: str) -> datetime:
        """
        Parse an ISO-8601 date string from the RSC payload.

        Examples: "2025-02-09T05:50:22Z", "2025-02-09T05:50:22+00:00".
        Falls back to the card-date parser for hand-scraped strings.
        """
        text = text.strip()
        # ISO first (RSC entries)
        iso_candidates = (
            text,
            text.replace("Z", "+00:00"),
        )
        for candidate in iso_candidates:
            try:
                dt = datetime.fromisoformat(candidate)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                continue
        # Fall back to card-style strings
        return self._parse_card_date(text)


# ===========================================================================
# Interactive test
# ===========================================================================
def interactive_test():
    print("=" * 72)
    print("Interactive Test — GoalcastBlogPlugin")
    print("=" * 72)
    plugin = GoalcastBlogPlugin()
    print(f"Plugin     : {plugin.name}")
    print(f"URL        : {plugin.url}")
    print(f"Categories : {plugin.categories}")
    print(f"Max items  : {plugin.max_items}")
    print(
        "HTTP       : "
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
        if "goalcast_category" in extra:
            print(f"GC category : {extra['goalcast_category']}")
        if "read_time_minutes" in extra:
            print(f"Read time   : {extra['read_time_minutes']} min")
        desc = item.get("description") or ""
        if len(desc) > 200:
            desc = desc[:200] + " ..."
        print(f"Description : {desc}\n")

    print("=" * 72)
    print(f"Test finished. (Showing first {min(3, len(items))} items)")
    print("=" * 72)


if __name__ == "__main__":
    interactive_test()
