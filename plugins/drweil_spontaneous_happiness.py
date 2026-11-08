#!/usr/bin/env python3
"""
plugins/drweil_spontaneous_happiness.py
---------------------------------------
Dr. Weil's Spontaneous Happiness
— https://www.drweil.com/blog/spontaneous-happiness/
Feed: feeds/sites/drweil_spontaneous_happiness.xml
"""
from __future__ import annotations
try:
    from . import _drweil_base
except ImportError:
    import _drweil_base


class DrWeilSpontaneousHappinessPlugin(_drweil_base.DrWeilBasePlugin):
    name = "drweil_spontaneous_happiness"
    url = "https://www.drweil.com/blog/spontaneous-happiness/"
    title = "Dr. Weil's Spontaneous Happiness"
    description = "Insights on happiness, well-being and integrative mental health from Dr. Weil."
    language = "en"
    categories = ["health", "happiness", "wellness"]
    max_items = 50
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def interactive_test():
    print("=" * 70)
    print("Interactive Test – DrWeilSpontaneousHappinessPlugin")
    print("=" * 70)
    plugin = DrWeilSpontaneousHappinessPlugin()
    print(f"Plugin      : {plugin.name}")
    print(f"URL         : {plugin.url}")
    print(f"Max items   : {plugin.max_items}")
    print(f"Categories  : {plugin.categories}")
    print("-" * 70)
    try:
        print("Fetching articles from Dr. Weil's Spontaneous Happiness...")
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
    for idx, item in enumerate(items[:3], start=1):
        print(
            f"─── Article #{idx} ──────────────────────────────────────────────")
        print(f"Title       : {item.get('title')}")
        print(f"Link        : {item.get('link')}")
        print(f"Author      : {item.get('author')}")
        print(f"Date        : {item.get('pubDate')}")
        print(f"Categories  : {item.get('categories')}")
        print(f"Image       : {item.get('image')}")
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
