#!/usr/bin/env python3
"""
plugins/juejin.py
-----------------
Improved plugin for 稀土掘金 (juejin.cn)

- Better cover image extraction
- Reliable statistics (view / digg / comment / collect)
- Cleaner tags & categories
- Interactive test now shows the first 3 articles

API:
    POST https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed

Sort types:
    200 = Recommended
    300 = Latest
    3   = Hot (3 days)
    7   = Hot (7 days)
    30  = Hot (30 days)

Interactive test:
    python plugins/juejin.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Import BasePlugin (with fallback for standalone testing)
# ---------------------------------------------------------------------------
try:
    from rss_fetcher import BasePlugin
except ImportError:
    from abc import ABC, abstractmethod
    from typing import List, Dict

    class BasePlugin(ABC):
        name: str = "unnamed"
        url: str = ""
        title: str = ""
        description: str = ""
        language: str = "zh-cn"
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
            raise NotImplementedError("This plugin uses API, not HTML")

        @abstractmethod
        def get_items(self) -> List[Dict[str, Any]]:
            ...

        def parse_date(self, text: str) -> datetime:
            return datetime.now(timezone.utc)


# ===========================================================================
#  Juejin Plugin – Improved Version
# ===========================================================================
class JuejinPlugin(BasePlugin):
    """
    稀土掘金 (juejin.cn) – Improved version with better image & stats support
    """

    name = "juejin"
    url = "https://juejin.cn"
    title = "稀土掘金"
    description = "稀土掘金 - 一个帮助开发者成长的社区"
    language = "zh-cn"
    categories = ["chinese", "tech"]
    max_items = 50

    # -------------------- Configuration --------------------
    API_URL = "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed"
    SORT_TYPE = 300              # 300 = latest | 200 = recommend | 3/7/30 = hot
    LIMIT_PER_REQUEST = 20

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://juejin.cn",
        "Referer": "https://juejin.cn/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def get_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        cursor = "0"
        collected = 0

        while collected < self.max_items:
            payload = {
                "id_type": 2,
                "client_type": 2608,
                "sort_type": self.SORT_TYPE,
                "cursor": cursor,
                "limit": self.LIMIT_PER_REQUEST,
            }

            try:
                resp = requests.post(
                    self.API_URL,
                    headers=self.headers,
                    json=payload,
                    timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[juejin] API request failed: {e}")
                break

            if data.get("err_no") != 0:
                print(f"[juejin] API error: {data.get('err_msg', 'unknown')}")
                break

            entries = data.get("data") or []
            if not entries:
                break

            for entry in entries:
                if entry.get("item_type") != 2:
                    continue

                parsed = self._parse_entry(entry)
                if parsed:
                    items.append(parsed)
                    collected += 1
                    if collected >= self.max_items:
                        break

            if not data.get("has_more"):
                break

            cursor = data.get("cursor")
            if not cursor:
                break

        return items

    def _parse_entry(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        item_info = entry.get("item_info") or {}
        article = item_info.get("article_info") or {}
        author_info = item_info.get("author_user_info") or {}

        article_id = article.get("article_id")
        if not article_id:
            return None

        title = (article.get("title") or "").strip()
        if not title:
            return None

        link = f"https://juejin.cn/post/{article_id}"

        description = (
            article.get("brief_content")
            or article.get("brief")
            or ""
        ).strip()

        # -------------------- Cover Image --------------------
        image = None
        possible_covers = [
            article.get("cover_image"),
            article.get("cover_image_list"),
            item_info.get("cover_image"),
            article.get("image"),
        ]

        for cover in possible_covers:
            if not cover:
                continue
            if isinstance(cover, list) and cover:
                cover = cover[0]
            if isinstance(cover, str) and cover.startswith("http"):
                image = cover
                break

        # -------------------- Author --------------------
        author = (
            author_info.get("user_name")
            or (article.get("author_user_info") or {}).get("user_name")
            or None
        )

        # -------------------- Date --------------------
        pub_date = datetime.now(timezone.utc)
        timestamp = article.get("ctime") or article.get(
            "rtime") or article.get("mtime")
        if timestamp:
            try:
                pub_date = datetime.fromtimestamp(
                    int(timestamp), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                pass

        # -------------------- Tags & Categories --------------------
        tags: List[str] = []
        for t in (item_info.get("tags") or []):
            name = t.get("tag_name") or t.get("name")
            if name:
                tags.append(name)

        category_info = item_info.get("category") or {}
        cat_name = category_info.get("category_name")
        if cat_name and cat_name not in tags:
            tags.append(cat_name)

        all_categories = list(dict.fromkeys(self.categories + tags))

        # -------------------- Statistics --------------------
        extra = {
            "view_count": self._safe_int(article.get("view_count")),
            "digg_count": self._safe_int(article.get("digg_count")),
            "comment_count": self._safe_int(article.get("comment_count")),
            "collect_count": self._safe_int(article.get("collect_count")),
            "hot_index": self._safe_int(article.get("hot_index")),
            "article_id": str(article_id),
        }
        extra = {k: v for k, v in extra.items() if v is not None}

        item: Dict[str, Any] = {
            "title": title,
            "link": link,
            "description": description or title,
            "content": None,
            "pubDate": pub_date,
            "author": author,
            "guid": link,
            "categories": all_categories,
            "image": image,
            "enclosures": [],
            "extra": extra,
        }

        if image:
            item["enclosures"].append({
                "url": image,
                "type": "image/jpeg",
                "length": 0,
                "title": "Cover image"
            })

        return item

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None


# ===========================================================================
# Interactive test mode – shows first 3 articles
# ===========================================================================
def interactive_test():
    print("=" * 70)
    print("Interactive Test – JuejinPlugin (Improved)")
    print("=" * 70)

    plugin = JuejinPlugin()
    print(f"Plugin      : {plugin.name}")
    print(f"URL          : {plugin.url}")
    print(f"Sort type    : {plugin.SORT_TYPE}")
    print(f"Max items    : {plugin.max_items}")
    print("-" * 70)

    try:
        print("Fetching articles from Juejin API...")
        items = plugin.get_items()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\n✅ Extracted {len(items)} articles\n")

    if not items:
        print("No articles found.")
        return

    # Show the first 3 articles so we can verify images & stats
    for idx, item in enumerate(items[:3], start=1):
        print(
            f"─── Article #{idx} ──────────────────────────────────────────────")
        print(f"Title       : {item.get('title')}")
        print(f"Link        : {item.get('link')}")
        print(f"Author      : {item.get('author')}")
        print(f"Date        : {item.get('pubDate')}")
        print(f"Categories  : {item.get('categories')}")
        print(f"Image       : {item.get('image')}")

        extra = item.get("extra") or {}
        print(f"Views       : {extra.get('view_count')}")
        print(f"Diggs       : {extra.get('digg_count')}")
        print(f"Comments    : {extra.get('comment_count')}")
        print(f"Collects    : {extra.get('collect_count')}")

        desc = item.get("description") or ""
        if len(desc) > 200:
            desc = desc[:200] + " ..."
        print(f"Description : {desc}")
        print()

    print("=" * 70)
    print("Test finished. (Showing first 3 articles)")
    print("=" * 70)


if __name__ == "__main__":
    interactive_test()
