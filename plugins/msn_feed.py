#!/usr/bin/env python3
"""
plugins/msn_feed.py
-------------------
MSN — Homepage Feed (en-us)
https://www.msn.com/en-us

KEY FIX (v4)
------------
The v3 scroll loop was fragile: each iteration cost a Python→browser
round-trip (count, evaluate, wait), and MSN's lazy-load often hadn't
finished by the time the next count was checked. In the pipeline the
loop bailed at 16 cards; in the interactive menu it grew to 280. Same
code, different result — pure timing.

v4 moves the ENTIRE scroll loop into a single page.evaluate() async
call. The browser does all the waiting, so no IPC jitter, and the loop
only stops after 5 consecutive unchanged rounds (was 3).

SETUP (one-time)
----------------
    pip install playwright
    playwright install chromium

Interactive test
----------------
    python plugins/msn_feed.py
"""

from __future__ import annotations

import html as _html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

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
        headers: Dict[str, str] = {}

        def fetch_html(self) -> str:
            raise NotImplementedError("This plugin uses Playwright")

        @abstractmethod
        def get_items(self) -> List[Dict[str, Any]]:
            ...

        def parse_date(self, text: str) -> datetime:
            return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Optional Playwright import
# ---------------------------------------------------------------------------
try:
    from playwright.sync_api import sync_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    sync_playwright = None  # type: ignore
    _HAS_PLAYWRIGHT = False


# ===========================================================================
# JS: scroll (inside browser) → extract all cards, one round-trip total
# ===========================================================================
_SCROLL_AND_EXTRACT_JS = r"""
async () => {
    const CARD_SEL = 'cs-responsive-card[data-t*="ContentCard"]';

    // ----------------------------------------------------------------
    // Deep query that descends into every shadow root
    // ----------------------------------------------------------------
    const deepQueryAll = (root, selector) => {
        const results = [];
        if (root.shadowRoot) {
            results.push(...root.shadowRoot.querySelectorAll(selector));
            results.push(...deepQueryAll(root.shadowRoot, selector));
        }
        results.push(...root.querySelectorAll(selector));
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) {
                results.push(...deepQueryAll(el.shadowRoot, selector));
            }
        }
        return results;
    };
    const deepQueryOne = (root, selector) => {
        if (root.shadowRoot) {
            const hit = root.shadowRoot.querySelector(selector);
            if (hit) return hit;
            const nested = deepQueryOne(root.shadowRoot, selector);
            if (nested) return nested;
        }
        const direct = root.querySelector(selector);
        if (direct) return direct;
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) {
                const hit = deepQueryOne(el.shadowRoot, selector);
                if (hit) return hit;
            }
        }
        return null;
    };

    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    const countCards = () => deepQueryAll(document, CARD_SEL).length;

    // ----------------------------------------------------------------
    // Scroll loop (runs entirely inside the browser)
    // ----------------------------------------------------------------
    const scrollLog = [];
    let lastCount = -1;
    let staleRounds = 0;
    const MAX_ROUNDS = 25;
    const STALE_LIMIT = 5;

    for (let i = 0; i < MAX_ROUNDS; i++) {
        // Scroll to bottom
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(1500);

        // Nudge IntersectionObservers by scrolling up slightly,
        // then back to bottom
        window.scrollBy(0, -100);
        await sleep(250);
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(750);

        const count = countCards();
        if (count > lastCount) {
            staleRounds = 0;
            scrollLog.push(`round ${i + 1}: ${count} (+)`);
        } else {
            staleRounds++;
            scrollLog.push(
                `round ${i + 1}: ${count} (stale ${staleRounds})`
            );
            if (staleRounds >= STALE_LIMIT) {
                scrollLog.push(
                    `no new cards in ${STALE_LIMIT} rounds, stopping`
                );
                break;
            }
        }
        lastCount = count;
    }

    // ----------------------------------------------------------------
    // Extract all cards
    // ----------------------------------------------------------------
    const cards = deepQueryAll(document, CARD_SEL);
    const seen = new Set();
    const unique = [];
    for (const c of cards) {
        if (!seen.has(c)) { seen.add(c); unique.push(c); }
    }

    const items = unique.map(card => {
        const titleAttr = (card.getAttribute('title') || '').trim();

        let contentId = (card.getAttribute('id') || '').trim();
        if (!contentId) {
            const dataT = card.getAttribute('data-t') || '';
            const m = dataT.match(/c\.i&quot;:&quot;([^&]+)/);
            if (m) contentId = m[1];
        }

        let heading = deepQueryOne(card, 'a.heading');
        if (!heading) {
            heading = deepQueryOne(card, 'a[href*="/ar-"]')
                   || deepQueryOne(card, 'a[href*="/vi-"]')
                   || deepQueryOne(card, 'a[href*="/ss-"]');
        }
        const href = heading
            ? (heading.getAttribute('href') || heading.href || '').trim()
            : '';
        const headingText = heading
            ? (heading.textContent || '').trim()
            : '';

        let image = '';
        const img = deepQueryOne(card, 'img.media')
                 || deepQueryOne(card, 'img[slot="media"]');
        if (img) {
            image = img.getAttribute('src')
                 || img.getAttribute('data-src')
                 || '';
        }
        if (!image) {
            const video = deepQueryOne(card, 'video[poster]');
            if (video) image = video.getAttribute('poster') || '';
        }
        if (!image) {
            const anyImg = deepQueryOne(card, 'img[src], img[data-src]');
            if (anyImg) {
                const src = anyImg.getAttribute('src')
                          || anyImg.getAttribute('data-src')
                          || '';
                if (src
                    && !src.includes('/staticsb/')
                    && !src.includes('/fluent-icons/')
                    && !src.endsWith('.svg')) {
                    image = src;
                }
            }
        }

        let publisher = '';
        const pubEl = deepQueryOne(card, 'span.attribution-text')
                   || deepQueryOne(card, 'span[class*="attribution-text"]');
        if (pubEl) publisher = (pubEl.textContent || '').trim();

        let timeText = '';
        const timeEl = deepQueryOne(card, 'span.attribution-time')
                    || deepQueryOne(card, 'span[class*="attribution-time"]');
        if (timeEl) timeText = (timeEl.textContent || '').trim();

        return {
            title: titleAttr || headingText,
            id: contentId,
            href: href,
            image: image,
            publisher: publisher,
            time: timeText,
        };
    });

    return { scrollLog, items };
}
"""

# Hydration check: at least one card has a non-empty title attribute.
_HYDRATION_JS = r"""
() => {
    const walk = (root, out) => {
        if (root.shadowRoot) {
            out.push(...root.shadowRoot.querySelectorAll(
                'cs-responsive-card[data-t*="ContentCard"]'
            ));
        }
        out.push(...root.querySelectorAll(
            'cs-responsive-card[data-t*="ContentCard"]'
        ));
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) walk(el.shadowRoot, out);
        }
    };
    const cards = [];
    walk(document, cards);
    return cards.some(c => (c.getAttribute('title') || '').length > 0);
}
"""


# ===========================================================================
# Plugin
# ===========================================================================
class MSNFeedPlugin(BasePlugin):
    """MSN — Homepage Feed (en-us)."""

    name = "msn_feed"
    url = "https://www.msn.com/en-us"
    title = "MSN — Homepage Feed"
    description = (
        "Latest news, entertainment, sports, and lifestyle stories from MSN."
    )
    language = "en"
    categories = ["English", "news"]
    max_items = 100

    MAX_FETCH_ATTEMPTS = 3

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    _CARD_SELECTOR = 'cs-responsive-card[data-t*="ContentCard"]'

    # ==================================================================
    # Public entry point
    # ==================================================================
    def get_items(self) -> List[Dict[str, Any]]:
        if not _HAS_PLAYWRIGHT:
            print(
                "[msn_feed] ERROR: Playwright is not installed.\n"
                "  Run: pip install playwright\n"
                "  Then: playwright install chromium",
                file=sys.stderr,
            )
            return []

        raw_cards = self._fetch_and_extract()
        if not raw_cards:
            print(f"[{self.name}] no cards returned from page")
            return []

        reference_time = datetime.now(timezone.utc)

        items: List[Dict[str, Any]] = []
        seen_ids: set = set()
        seen_links: set = set()
        skipped = 0

        for raw in raw_cards:
            if len(items) >= self.max_items:
                break

            item = self._build_item(raw, reference_time)
            if not item:
                skipped += 1
                continue

            content_id = (item.get("extra") or {}).get("content_id")
            if content_id and content_id in seen_ids:
                skipped += 1
                continue
            if item["link"] in seen_links:
                skipped += 1
                continue

            if content_id:
                seen_ids.add(content_id)
            seen_links.add(item["link"])
            items.append(item)

        print(
            f"[{self.name}] extracted {len(items)} items "
            f"({skipped} skipped/invalid)"
        )
        return items

    # ==================================================================
    # Fetch + retry wrapper
    # ==================================================================
    def _fetch_and_extract(self) -> List[Dict[str, Any]]:
        for attempt in range(1, self.MAX_FETCH_ATTEMPTS + 1):
            print(
                f"[{self.name}] attempt {attempt}/{self.MAX_FETCH_ATTEMPTS}"
            )
            result = self._try_fetch_once()
            if result:
                return result
            print(
                f"[{self.name}] attempt {attempt} returned 0 cards"
            )
        return []

    # ==================================================================
    # Single Playwright run
    # ==================================================================
    def _try_fetch_once(self) -> List[Dict[str, Any]]:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        user_agent=self.headers["User-Agent"],
                        viewport={"width": 1920, "height": 1080},
                        locale="en-US",
                        extra_http_headers={
                            "Accept-Language": "en-US,en;q=0.9",
                        },
                    )
                    page = context.new_page()
                    print(f"[{self.name}] loading {self.url} …")

                    page.goto(
                        self.url,
                        wait_until="load",
                        timeout=90_000,
                    )

                    # --- Step 1: cards exist in DOM ---
                    try:
                        page.wait_for_selector(
                            self._CARD_SELECTOR, timeout=45_000
                        )
                    except Exception:
                        print(
                            f"[{self.name}] no cards after 45s, "
                            "trying scroll"
                        )
                        page.evaluate("window.scrollBy(0, 800)")
                        page.wait_for_timeout(3000)

                    # --- Step 2: at least one card is hydrated ---
                    try:
                        page.wait_for_function(
                            _HYDRATION_JS, timeout=20_000
                        )
                        print(f"[{self.name}] cards hydrated")
                    except Exception:
                        print(
                            f"[{self.name}] hydration wait timed out; "
                            "continuing anyway"
                        )

                    # --- Step 3+4: scroll & extract, all in-browser ---
                    print(
                        f"[{self.name}] scrolling & extracting "
                        "(in-browser) …"
                    )
                    result = page.evaluate(_SCROLL_AND_EXTRACT_JS)

                    if not isinstance(result, dict):
                        print(
                            f"[{self.name}] unexpected JS result type: "
                            f"{type(result).__name__}"
                        )
                        return []

                    for line in result.get("scrollLog", []):
                        print(f"[{self.name}] {line}")

                    raw_cards = result.get("items") or []
                    n = len(raw_cards)
                    print(
                        f"[{self.name}] JS extracted {n} raw cards"
                    )

                    if n:
                        valid = sum(
                            1 for r in raw_cards
                            if (r.get("title") or "").strip()
                            and (r.get("href") or "").strip()
                        )
                        print(
                            f"[{self.name}] {valid}/{n} raw cards "
                            "have title+href"
                        )

                    return raw_cards
                finally:
                    browser.close()
        except Exception as e:
            print(f"[{self.name}] Playwright error: {e}", file=sys.stderr)
            return []

    # ==================================================================
    # Raw card dict → plugin item
    # ==================================================================
    def _build_item(
        self,
        raw: Dict[str, Any],
        reference_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        try:
            title = _html.unescape(raw.get("title") or "").strip()
            if not title:
                return None

            href = (raw.get("href") or "").strip()
            if not href or href.startswith(("javascript:", "#")):
                return None
            link = urljoin(self.url, _html.unescape(href))

            content_id = (raw.get("id") or "").strip() or None

            image = None
            img_raw = (raw.get("image") or "").strip()
            if img_raw:
                if img_raw.startswith("//"):
                    img_raw = "https:" + img_raw
                image = urljoin(self.url, _html.unescape(img_raw))

            publisher = _html.unescape(
                raw.get("publisher") or ""
            ).strip()

            pub_date = self._parse_relative_time(
                raw.get("time") or "", reference_time
            )

            extra: Dict[str, Any] = {}
            if content_id:
                extra["content_id"] = content_id
            if publisher:
                extra["publisher"] = publisher

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
                "description": title,
                "content":     None,
                "pubDate":     pub_date,
                "author":      publisher or "MSN",
                "guid":        link,
                "categories":  list(self.categories),
                "image":       image,
                "enclosures":  enclosures,
                "extra":       extra,
            }
        except Exception as e:
            print(
                f"[{self.name}] card parse error: {e}",
                file=sys.stderr,
            )
            return None

    # ==================================================================
    # Helpers
    # ==================================================================
    def _parse_relative_time(
        self, text: str, reference: datetime
    ) -> datetime:
        if not text:
            return reference
        text = text.strip().lower()

        if text in ("just now", "now"):
            return reference

        m = re.match(
            r"(\d+)\s*m(?:in(?:ute)?s?)?(?:\s+ago)?$", text
        )
        if m:
            return reference - timedelta(minutes=int(m.group(1)))

        m = re.match(
            r"(\d+)\s*h(?:(?:ou)?rs?)?(?:\s+ago)?$", text
        )
        if m:
            return reference - timedelta(hours=int(m.group(1)))

        m = re.match(
            r"(\d+)\s*d(?:ays?)?(?:\s+ago)?$", text
        )
        if m:
            return reference - timedelta(days=int(m.group(1)))

        if "yesterday" in text:
            return reference - timedelta(days=1)

        return reference

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
        text = text.strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(text, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                continue
        return datetime.now(timezone.utc)


# ===========================================================================
# Interactive menu
# ===========================================================================
def _fmt_date(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(dt)


def _print_item(idx: int, item: Dict[str, Any]) -> None:
    print(f"─── Item #{idx} ───────────────────────────────────────────────")
    print(f"Title       : {item.get('title')}")
    print(f"Link        : {item.get('link')}")
    print(f"Date        : {_fmt_date(item.get('pubDate'))}")
    print(f"Author      : {item.get('author')}")
    print(f"Image       : {item.get('image')}")
    extra = item.get("extra") or {}
    if "content_id" in extra:
        print(f"Content ID  : {extra['content_id']}")
    print()


def _print_compact(idx: int, item: Dict[str, Any]) -> None:
    print(
        f"{idx:>3}. [{_fmt_date(item.get('pubDate'))}] "
        f"{item.get('title')}"
    )


def _save_json(items: List[Dict[str, Any]], path: str) -> None:
    serializable = []
    for it in items:
        copy = dict(it)
        if isinstance(copy.get("pubDate"), datetime):
            copy["pubDate"] = copy["pubDate"].isoformat()
        serializable.append(copy)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(items)} items to {path}")


def _save_rss(items: List[Dict[str, Any]], path: str) -> None:
    from xml.sax.saxutils import escape

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<rss version="2.0">')
    lines.append("  <channel>")
    lines.append(f"    <title>{escape('MSN — Homepage Feed')}</title>")
    lines.append(f"    <link>{escape(MSNFeedPlugin.url)}</link>")
    lines.append(
        f"    <description>"
        f"{escape('Latest news and stories from MSN')}"
        f"</description>"
    )
    lines.append(
        f"    <lastBuildDate>"
        f"{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}"
        f"</lastBuildDate>"
    )
    for it in items:
        lines.append("    <item>")
        lines.append(f"      <title>{escape(it['title'])}</title>")
        lines.append(f"      <link>{escape(it['link'])}</link>")
        lines.append(
            f'      <guid isPermaLink="true">{escape(it["guid"])}</guid>'
        )
        lines.append(
            f"      <description>"
            f"{escape(it.get('description') or it['title'])}"
            f"</description>"
        )
        if isinstance(it.get("pubDate"), datetime):
            lines.append(
                f"      <pubDate>"
                f"{it['pubDate'].strftime('%a, %d %b %Y %H:%M:%S +0000')}"
                f"</pubDate>"
            )
        for cat in it.get("categories", []):
            lines.append(f"      <category>{escape(cat)}</category>")
        if it.get("image"):
            lines.append(
                f'      <enclosure url="{escape(it["image"])}" '
                f'type="image/jpeg" length="0"/>'
            )
        extra = it.get("extra") or {}
        if extra.get("publisher"):
            lines.append(
                f"      <source>{escape(extra['publisher'])}</source>"
            )
        lines.append("    </item>")
    lines.append("  </channel>")
    lines.append("</rss>")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ Saved {len(items)} items to {path}")


def _dump_raw() -> None:
    """Debug: fetch the page and print raw card dicts, no filtering."""
    if not _HAS_PLAYWRIGHT:
        print("Playwright not installed.")
        return
    plugin = MSNFeedPlugin()
    raw = plugin._fetch_and_extract()
    print(f"\nRaw cards returned: {len(raw)}")
    for i, r in enumerate(raw, 1):
        title = (r.get("title") or "")[:60]
        href = (r.get("href") or "")[:80]
        print(f"  #{i}: title={title!r}")
        print(f"       href ={href!r}")
        print(f"       id   ={r.get('id')!r}")
        print(f"       image={'yes' if r.get('image') else 'no'}")
        print(f"       time ={r.get('time')!r}")


def interactive_test() -> None:
    print("=" * 72)
    print("MSN Feed — Interactive Menu")
    print("=" * 72)
    print(
        "Playwright : "
        + ("installed" if _HAS_PLAYWRIGHT else "NOT INSTALLED")
    )
    if not _HAS_PLAYWRIGHT:
        print(
            "\n  To use this plugin, install Playwright:\n"
            "    pip install playwright\n"
            "    playwright install chromium"
        )
        return
    print(f"URL        : {MSNFeedPlugin.url}")
    print(f"Max items  : {MSNFeedPlugin.max_items}")
    print("-" * 72)

    plugin = MSNFeedPlugin()
    items: Optional[List[Dict[str, Any]]] = None

    while True:
        print()
        print("Options:")
        print("  [1] Fetch feed")
        print("  [2] Show first 10 items")
        print("  [3] Show ALL items (verbose)")
        print("  [4] Show ALL items (compact)")
        print("  [5] Save to JSON")
        print("  [6] Save to XML (RSS)")
        print("  [7] Show stats")
        print("  [8] Dump RAW cards (debug)")
        print("  [0] Exit")
        try:
            choice = input("Choice: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return

        if choice == "1":
            items = plugin.get_items()
            print(f"\n✅ Fetched {len(items)} items")
        elif choice == "2":
            if items is None:
                items = plugin.get_items()
            if not items:
                print("No items.")
                continue
            for i, it in enumerate(items[:10], 1):
                _print_item(i, it)
        elif choice == "3":
            if items is None:
                items = plugin.get_items()
            if not items:
                print("No items.")
                continue
            for i, it in enumerate(items, 1):
                _print_item(i, it)
        elif choice == "4":
            if items is None:
                items = plugin.get_items()
            if not items:
                print("No items.")
                continue
            for i, it in enumerate(items, 1):
                _print_compact(i, it)
        elif choice == "5":
            if items is None:
                items = plugin.get_items()
            if not items:
                print("No items to save.")
                continue
            path = input(
                f"Filename [{os.getcwd()}/msn_feed.json]: "
            ).strip() or "msn_feed.json"
            _save_json(items, path)
        elif choice == "6":
            if items is None:
                items = plugin.get_items()
            if not items:
                print("No items to save.")
                continue
            path = input(
                f"Filename [{os.getcwd()}/msn_feed.xml]: "
            ).strip() or "msn_feed.xml"
            _save_rss(items, path)
        elif choice == "7":
            if items is None:
                items = plugin.get_items()
            if not items:
                print("No items.")
                continue
            publishers: Dict[str, int] = {}
            with_image = 0
            dates: List[datetime] = []
            for it in items:
                pub = (it.get("extra") or {}).get("publisher", "MSN")
                publishers[pub] = publishers.get(pub, 0) + 1
                if it.get("image"):
                    with_image += 1
                if isinstance(it.get("pubDate"), datetime):
                    dates.append(it["pubDate"])
            print(f"Total items    : {len(items)}")
            print(f"With image     : {with_image}")
            print(f"Unique sources : {len(publishers)}")
            if dates:
                print(
                    f"Oldest         : "
                    f"{min(dates).strftime('%Y-%m-%d %H:%M')}"
                )
                print(
                    f"Newest         : "
                    f"{max(dates).strftime('%Y-%m-%d %H:%M')}"
                )
            print("Top publishers :")
            for pub, cnt in sorted(
                publishers.items(), key=lambda kv: -kv[1]
            )[:10]:
                print(f"  {cnt:>3} × {pub}")
        elif choice == "8":
            _dump_raw()
        elif choice == "0":
            print("Bye.")
            return
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    interactive_test()
