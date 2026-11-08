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
- Overwrite strategy (keeps latest ~100 items per site)

Usage:
    python rss_fetcher.py
    python rss_fetcher.py --readme-only   # rewrite README tables without fetching

Requirements:
    pip install feedgen requests beautifulsoup4 lxml
"""

from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import re
import sys
import traceback
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import requests
from feedgen.feed import FeedGenerator

# ---------------------------------------------------------------------------
# Paths & limits
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
PLUGINS_DIR = BASE_DIR / "plugins"
FEEDS_DIR = BASE_DIR / "feeds"
SITES_DIR = FEEDS_DIR / "sites"
CATEGORIES_DIR = FEEDS_DIR / "categories"

CATEGORY_ITEM_CAP = 400
MASTER_ITEM_CAP = 800
DEFAULT_MAX_ITEMS = 100
FETCH_TIMEOUT = (10, 25)
MAX_FETCH_BYTES = 5 * 1024 * 1024

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_SAFE_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
_SAFE_REF = re.compile(r"^[\w./-]+$")

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
    max_items: int = DEFAULT_MAX_ITEMS
    headers: Dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def fetch_html(self) -> str:
        """Download the listing page (HTTP/HTTPS only)."""
        url = (self.url or "").strip()
        if not _is_http_url(url):
            raise ValueError(f"Refusing to fetch non-HTTP URL: {url!r}")
        with requests.get(
            url,
            headers=self.headers,
            timeout=FETCH_TIMEOUT,
            allow_redirects=True,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            # Bound body size so a huge/malicious response cannot exhaust the Action runner.
            raw = resp.raw.read(MAX_FETCH_BYTES + 1, decode_content=True)
            if len(raw) > MAX_FETCH_BYTES:
                raise ValueError(f"Response too large for {url}")
            encoding = resp.encoding or "utf-8"
            return raw.decode(encoding, errors="replace")

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
# Helpers
# ---------------------------------------------------------------------------
def _is_http_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value).strip())
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def safe_feed_name(name: str) -> Optional[str]:
    """Return a filename-safe token, or None if it cannot be used as a feed id."""
    text = (name or "").strip()
    if not text or ".." in text or "/" in text or "\\" in text:
        return None
    if _SAFE_NAME.fullmatch(text):
        return text
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip(".-")[:80]
    if slug and _SAFE_NAME.fullmatch(slug) and ".." not in slug:
        return slug
    return None


def _as_str_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    try:
        return [str(v) for v in value if v]
    except TypeError:
        return []


def _item_cap(plugin: Any) -> int:
    try:
        cap = int(getattr(plugin, "max_items", DEFAULT_MAX_ITEMS))
    except (TypeError, ValueError):
        cap = DEFAULT_MAX_ITEMS
    return cap if cap > 0 else DEFAULT_MAX_ITEMS


def _aware_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    return None


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _safe_feed_path(directory: Path, name: str) -> Optional[Path]:
    safe = safe_feed_name(name)
    if not safe:
        return None
    directory = directory.resolve()
    path = (directory / f"{safe}.xml").resolve()
    try:
        path.relative_to(directory)
    except ValueError:
        return None
    return path


def _take(items: Iterable[Any], limit: int) -> List[Any]:
    out: List[Any] = []
    for item in items:
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _dedupe_by_link(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique: List[Dict[str, Any]] = []
    for item in items:
        link = item.get("link")
        if not link or link in seen:
            continue
        seen.add(link)
        unique.append(item)
    return unique


def _normalize_item(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    link = str(item.get("link") or "").strip()
    if not title or not _is_http_url(link):
        return None
    normalized = dict(item)
    normalized["title"] = title
    normalized["link"] = link
    if normalized.get("guid"):
        normalized["guid"] = str(normalized["guid"]).strip()
    return normalized


def _default_feed_link() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "Abdulhossein/RSS-Fetcher")
    if not _SAFE_REPO.fullmatch(repo):
        repo = "Abdulhossein/RSS-Fetcher"
    return f"https://github.com/{repo}"


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
    fg.link(href=link if _is_http_url(link) else _default_feed_link(), rel="alternate")
    fg.description(description or title)
    fg.language(language or "en")
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.generator("Custom RSS Fetcher")

    dc_ok = False
    try:
        fg.load_extension("dc")
        dc_ok = True
    except Exception:
        pass

    for item in items:
        try:
            _add_entry(fg, item, dc_ok=dc_ok)
        except Exception as exc:
            print(f"  ⚠ skipped item: {exc}")

    return fg.rss_str(pretty=True).decode("utf-8")


def _add_entry(fg: FeedGenerator, item: Dict[str, Any], dc_ok: bool) -> None:
    fe = fg.add_entry()
    fe.title(item["title"])
    fe.link(href=item["link"])

    guid = item.get("guid") or item["link"]
    fe.guid(guid, permalink=(guid == item["link"]))

    if item.get("description"):
        fe.description(str(item["description"]))

    if item.get("content"):
        fe.content(str(item["content"]), type="CDATA")

    pub = _aware_datetime(item.get("pubDate"))
    if pub is not None:
        fe.pubDate(pub)

    author = item.get("author")
    if author:
        author = str(author)
        fe.author(name=author)
        if dc_ok:
            try:
                fe.dc.dc_creator(author)
            except Exception:
                pass

    for cat in _as_str_list(item.get("categories")):
        fe.category(term=cat)

    image = item.get("image")
    if image and _is_http_url(image):
        fe.enclosure(str(image), 0, "image/jpeg")

    for enc in item.get("enclosures") or []:
        if not isinstance(enc, dict):
            continue
        url = enc.get("url")
        if not _is_http_url(url):
            continue
        try:
            length = int(enc.get("length") or 0)
        except (TypeError, ValueError):
            length = 0
        fe.enclosure(
            str(url),
            max(length, 0),
            str(enc.get("type") or "application/octet-stream"),
        )


# ---------------------------------------------------------------------------
# Plugin discovery
# ---------------------------------------------------------------------------
def discover_plugins() -> List[BasePlugin]:
    """Automatically find and instantiate all plugins in the plugins/ folder."""
    plugins: List[BasePlugin] = []

    if not PLUGINS_DIR.exists():
        print(f"⚠ Plugins directory not found: {PLUGINS_DIR}")
        return plugins

    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    # When this script is run directly it is loaded as "__main__", while plugins
    # import "rss_fetcher" as a separate module copy. That makes issubclass()
    # fail on identity grounds, so accept any concrete class that quacks like
    # a plugin instead of relying on strict inheritance from this BasePlugin.
    def _is_plugin_class(attr: Any, module_name: str) -> bool:
        return (
            isinstance(attr, type)
            and getattr(attr, "__module__", None) == module_name
            and hasattr(attr, "get_items")
            and callable(getattr(attr, "get_items", None))
            and not inspect.isabstract(attr)
            and not attr.__name__.startswith("_")
        )

    seen_names = set()

    for finder, module_name, ispkg in pkgutil.iter_modules([str(PLUGINS_DIR)]):
        if module_name.startswith("_"):
            continue

        try:
            module = importlib.import_module(f"plugins.{module_name}")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if not _is_plugin_class(attr, module.__name__):
                    continue
                instance = attr()
                raw_name = getattr(instance, "name", "") or ""
                name = safe_feed_name(raw_name)
                if not name or name == "unnamed":
                    print(
                        f"⚠ Plugin in {module_name} has no valid name – skipped")
                    continue
                instance.name = name
                if name in seen_names:
                    print(
                        f"⚠ Duplicate plugin name '{name}' in {module_name} – skipped")
                    continue
                seen_names.add(name)
                plugins.append(instance)
        except Exception as e:
            print(f"⚠ Failed to load plugin '{module_name}': {e}")
            traceback.print_exc()

    return plugins


# ---------------------------------------------------------------------------
# README auto-update (master + category tables)
# ---------------------------------------------------------------------------
README_PATH = BASE_DIR / "README.md"
README_FEEDS_START = "<!-- AUTO:FEEDS:START -->"
README_FEEDS_END = "<!-- AUTO:FEEDS:END -->"
README_LINKS_START = "<!-- AUTO:FEED-LINKS:START -->"
README_LINKS_END = "<!-- AUTO:FEED-LINKS:END -->"


def _md_ref(prefix: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "unnamed"
    return f"{prefix}-{slug}"


def _md_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").replace("[", "").replace("]", "")


def _raw_feed_base() -> str:
    """GitHub raw URL prefix; rewritten on forks by env or the Actions step."""
    repo = os.environ.get("GITHUB_REPOSITORY", "Abdulhossein/RSS-Fetcher")
    if not _SAFE_REPO.fullmatch(repo):
        repo = "Abdulhossein/RSS-Fetcher"
    ref = os.environ.get("GITHUB_REF_NAME") or os.environ.get("GITHUB_REF", "main")
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/") :]
    if not _SAFE_REF.fullmatch(ref) or ".." in ref:
        ref = "main"
    return f"https://raw.githubusercontent.com/{repo}/refs/heads/{ref}"


def _replace_marked(text: str, start: str, end: str, inner: str) -> str:
    start_idx = text.find(start)
    end_idx = text.find(end)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise ValueError(f"README.md is missing markers {start} … {end}")
    return (
        text[: start_idx + len(start)]
        + "\n"
        + inner.rstrip()
        + "\n"
        + text[end_idx:]
    )


def update_readme(
    category_sources: Dict[str, List[str]],
    category_counts: Dict[str, int],
    master_count: int,
) -> None:
    """Rewrite README with the master feed and one row per category."""
    if not README_PATH.exists():
        print("⚠ README.md not found – skipped table update")
        return

    base = _raw_feed_base()
    links: List[str] = [
        "<!-- Feed link targets. GitHub Action rewrites owner/repo/branch. -->",
        f"[feed-all]: {base}/feeds/all.xml",
    ]

    rows: List[str] = [
        "| Feed | Items |",
        "|------|-------|",
        f"| [all.xml][feed-all] | {master_count} |",
    ]
    for cat in sorted(category_sources):
        safe = safe_feed_name(cat)
        if not safe:
            continue
        ref = _md_ref("feed-cat", safe)
        items = category_counts.get(cat, 0)
        rows.append(
            f"| [categories/{_md_cell(safe)}.xml][{ref}] | {items} |"
        )
        links.append(f"[{ref}]: {base}/feeds/categories/{safe}.xml")

    feeds_block = "\n".join(rows)

    text = README_PATH.read_text(encoding="utf-8")
    text = _replace_marked(text, README_FEEDS_START, README_FEEDS_END, feeds_block)
    text = _replace_marked(
        text, README_LINKS_START, README_LINKS_END, "\n".join(links)
    )
    README_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"  ✓ README.md  (all + {len(category_sources)} categories)")


def _xml_item_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return path.read_text(encoding="utf-8").count("<item>")
    except OSError:
        return 0


def _category_sources(plugins: List[Any]) -> Dict[str, List[str]]:
    sources: Dict[str, List[str]] = defaultdict(list)
    for plugin in plugins:
        for cat in _as_str_list(getattr(plugin, "categories", None)):
            safe = safe_feed_name(cat)
            if safe and plugin.name not in sources[safe]:
                sources[safe].append(plugin.name)
    return sources


def update_readme_from_plugins(plugins: List[Any]) -> None:
    """Fill README tables from plugin metadata and existing XML item counts."""
    category_sources = _category_sources(plugins)
    category_counts = {
        cat: _xml_item_count(CATEGORIES_DIR / f"{cat}.xml") for cat in category_sources
    }
    update_readme(
        category_sources,
        category_counts,
        _xml_item_count(FEEDS_DIR / "all.xml"),
    )


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
    category_sources = _category_sources(plugins)

    for plugin in plugins:
        print(f"→ Processing: {plugin.name}")

        try:
            raw_items = plugin.get_items()
            if raw_items is None:
                print("  ⚠ No items returned")
                continue

            cap = _item_cap(plugin)
            items = []
            for raw in _take(raw_items, cap):
                item = _normalize_item(raw)
                if item:
                    items.append(item)

            if not items:
                print("  ⚠ No items returned")
                continue

            plugin_cats = [
                c for c in (_as_str_list(plugin.categories)) if safe_feed_name(c)
            ]
            for item in items:
                cats = _as_str_list(item.get("categories"))
                cats.extend(plugin_cats)
                cats.append(plugin.name)
                seen = set()
                item["categories"] = [
                    c for c in cats if c and not (c in seen or seen.add(c))]

            rss_content = build_rss(
                title=plugin.title or plugin.name,
                link=plugin.url,
                description=plugin.description or plugin.title or plugin.name,
                items=items,
                language=plugin.language or "en",
            )
            out_path = _safe_feed_path(SITES_DIR, plugin.name)
            if out_path is None:
                print(f"  ⚠ Unsafe plugin name '{plugin.name}' – skipped write")
                continue
            _write_text(out_path, rss_content)
            print(f"  ✓ sites/{plugin.name}.xml  ({len(items)} items)")

            all_items.extend(items)
            for cat in plugin_cats:
                safe = safe_feed_name(cat)
                if safe:
                    category_map[safe].extend(items)

        except Exception as e:
            print(f"  ✗ Error while processing {plugin.name}: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Category feeds
    # ------------------------------------------------------------------
    print("\nBuilding category feeds...")
    category_counts: Dict[str, int] = {}
    for cat, items in category_map.items():
        unique_items = _dedupe_by_link(items)[:CATEGORY_ITEM_CAP]

        rss_content = build_rss(
            title=f"Category: {cat}",
            link="",
            description=f"Aggregated feed for category '{cat}'",
            items=unique_items,
        )
        out_path = _safe_feed_path(CATEGORIES_DIR, cat)
        if out_path is None:
            print(f"  ⚠ Unsafe category name '{cat}' – skipped")
            continue
        _write_text(out_path, rss_content)
        category_counts[cat] = len(unique_items)
        print(f"  ✓ categories/{cat}.xml  ({len(unique_items)} items)")

    # ------------------------------------------------------------------
    # Master feed
    # ------------------------------------------------------------------
    print("\nBuilding master feed...")
    unique_all = _dedupe_by_link(all_items)[:MASTER_ITEM_CAP]

    rss_all = build_rss(
        title="All Feeds",
        link="",
        description="Master aggregate of all sources",
        items=unique_all,
    )
    _write_text(FEEDS_DIR / "all.xml", rss_all)
    print(f"  ✓ all.xml  ({len(unique_all)} items)")

    print("\nUpdating README feed tables...")
    try:
        update_readme(category_sources, category_counts, len(unique_all))
    except Exception as e:
        print(f"  ⚠ README update failed: {e}")
        traceback.print_exc()

    print("\nDone.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Windows consoles often use a legacy code page (e.g. cp1256) that cannot
    # encode the symbols used in the log output; force UTF-8 when possible.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--readme-only":
        plugins = discover_plugins()
        print(f"Found {len(plugins)} plugin(s)\n")
        print("Updating README feed tables...")
        update_readme_from_plugins(plugins)
        print("\nDone.")
        sys.exit(0)

    run()
