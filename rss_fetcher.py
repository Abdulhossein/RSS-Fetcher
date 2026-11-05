#!/usr/bin/env python3
"""
rss_fetcher.py
--------------
A complete, self-contained, plugin-based RSS feed generator.

Features:
- Automatic discovery of plugins in the ./plugins/ folder
- Individual feed per site
- Aggregated feeds per category
- Master aggregate feed (all.xml)
- Rich item support (title, link, description, content, author, categories,
  image, enclosures, extra, ...)
- Standards-compliant RSS 2.0 output (dc:creator, multiple categories, guid, etc.)
- Overwrite strategy (keeps latest \~100 items per site)

Usage:
    python rss_fetcher.py

Requirements:
    pip install feedgen requests beautifulsoup4 lxml
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
PLUGINS_DIR = BASE_DIR / "plugins"
FEEDS_DIR = BASE_DIR / "feeds"
SITES_DIR = FEEDS_DIR / "sites"
CATEGORIES_DIR = FEEDS_DIR / "categories"

# ---------------------------------------------------------------------------
# Base Plugin
# ---------------------------------------------------------------------------
class BasePlugin(ABC):
    """
    Base class that every plugin should inherit from.

    Required class attributes:
        name, url, title

    Recommended:
        description, language, categories, max_items, headers
    """

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
        """Download the listing page."""
        resp = requests.get(self.url, headers=self.headers, timeout=25)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    @abstractmethod
    def get_items(self) -> List[Dict[str, Any]]:
        """
        Must return a list of item dictionaries.

        See the full item schema in the design document.
        Minimum required keys: title, link
        """
        ...

    def parse_date(self, text: str) -> datetime:
        """Override this method for site-specific date parsing."""
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Feed builder
# ---------------------------------------------------------------------------
def build_rss(
    title: str,
    link: str,
    description: str,
    items: List[Dict[str, Any]],
    language: str = "en",
) -> str:
    """Build a standards-compliant RSS 2.0 feed and return it as a string."""
    fg = FeedGenerator()
    fg.title(title)
    fg.link(href=link or "https://example.com", rel="alternate")
    fg.description(description or title)
    fg.language(language)
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.generator("Custom RSS Fetcher")

    # Dublin Core for dc:creator
    try:
        fg.load_extension("dc")
    except Exception:
        pass

    for item in items:
        fe = fg.add_entry()

        fe.title(item["title"])
        fe.link(href=item["link"])

        # GUID
        guid = item.get("guid") or item["link"]
        fe.guid(guid, permalink=True)

        # Description (can contain HTML)
        if item.get("description"):
            fe.description(item["description"])

        # Full content
        if item.get("content"):
            fe.content(item["content"], type="CDATA")

        # Publication date
        if item.get("pubDate"):
            fe.pubDate(item["pubDate"])

        # Author → both author and dc:creator
        if item.get("author"):
            fe.author(name=item["author"])
            try:
                fg.dc.dc_creator(item["author"])
            except Exception:
                pass

        # Categories
        for cat in item.get("categories", []):
            if cat:
                fe.category(term=str(cat))

        # Main image (as enclosure of type image/*)
        if item.get("image"):
            fe.enclosure(item["image"], 0, "image/jpeg")

        # Additional enclosures (audio, video, files...)
        for enc in item.get("enclosures", []) or []:
            if not enc.get("url"):
                continue
            fe.enclosure(
                enc["url"],
                enc.get("length") or 0,
                enc.get("type") or "application/octet-stream",
            )

    return fg.rss_str(pretty=True).decode("utf-8")


# ---------------------------------------------------------------------------
# Plugin discovery
# ---------------------------------------------------------------------------
def discover_plugins() -> List[BasePlugin]:
    """Automatically find and instantiate all plugins in the plugins/ folder."""
    plugins: List[BasePlugin] = []

    if not PLUGINS_DIR.exists():
        print(f"⚠ Plugins directory not found: {PLUGINS_DIR}")
        return plugins

    # Make sure the package is importable
    sys.path.insert(0, str(BASE_DIR))

    for finder, module_name, ispkg in pkgutil.iter_modules([str(PLUGINS_DIR)]):
        if module_name.startswith("_"):
            continue

        try:
            module = importlib.import_module(f"plugins.{module_name}")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePlugin)
                    and attr is not BasePlugin
                ):
                    instance = attr()
                    if not instance.name or instance.name == "unnamed":
                        print(f"⚠ Plugin in {module_name} has no valid name – skipped")
                        continue
                    plugins.append(instance)
        except Exception as e:
            print(f"⚠ Failed to load plugin '{module_name}': {e}")
            traceback.print_exc()

    return plugins


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
def run() -> None:
    SITES_DIR.mkdir(parents=True, exist_ok=True)
    CATEGORIES_DIR.mkdir(parents=True, exist_ok=True)

    plugins = discover_plugins()
    print(f"Found {len(plugins)} plugin(s)\n")

    if not plugins:
        print("No plugins found. Add some files inside the plugins/ folder.")
        return

    all_items: List[Dict[str, Any]] = []
    category_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for plugin in plugins:
        print(f"→ Processing: {plugin.name}")

        try:
            raw_items = plugin.get_items()
            items = raw_items[: plugin.max_items]

            if not items:
                print("  ⚠ No items returned")
                continue

            # Ensure every item has the plugin categories + plugin name
            for item in items:
                cats = list(item.get("categories") or [])
                cats.extend(plugin.categories)
                cats.append(plugin.name)
                # unique while preserving order
                seen = set()
                item["categories"] = [c for c in cats if c and not (c in seen or seen.add(c))]

            # Write individual site feed
            rss_content = build_rss(
                title=plugin.title or plugin.name,
                link=plugin.url,
                description=plugin.description or plugin.title or plugin.name,
                items=items,
                language=plugin.language,
            )
            out_path = SITES_DIR / f"{plugin.name}.xml"
            out_path.write_text(rss_content, encoding="utf-8")
            print(f"  ✓ sites/{plugin.name}.xml  ({len(items)} items)")

            # Collect for aggregation
            all_items.extend(items)
            for cat in plugin.categories:
                category_map[cat].extend(items)

        except Exception as e:
            print(f"  ✗ Error while processing {plugin.name}: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Category feeds
    # ------------------------------------------------------------------
    print("\nBuilding category feeds...")
    for cat, items in category_map.items():
        # Deduplicate by link
        seen = set()
        unique_items = []
        for it in items:
            if it["link"] not in seen:
                seen.add(it["link"])
                unique_items.append(it)

        rss_content = build_rss(
            title=f"Category: {cat}",
            link="",
            description=f"Aggregated feed for category '{cat}'",
            items=unique_items[:400],
        )
        out_path = CATEGORIES_DIR / f"{cat}.xml"
        out_path.write_text(rss_content, encoding="utf-8")
        print(f"  ✓ categories/{cat}.xml  ({len(unique_items)} items)")

    # ------------------------------------------------------------------
    # Master feed
    # ------------------------------------------------------------------
    print("\nBuilding master feed...")
    seen = set()
    unique_all = []
    for it in all_items:
        if it["link"] not in seen:
            seen.add(it["link"])
            unique_all.append(it)

    rss_all = build_rss(
        title="All Feeds",
        link="",
        description="Master aggregate of all sources",
        items=unique_all[:800],
    )
    (FEEDS_DIR / "all.xml").write_text(rss_all, encoding="utf-8")
    print(f"  ✓ all.xml  ({len(unique_all)} items)")

    print("\nDone.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        sys.exit(0)

    run()