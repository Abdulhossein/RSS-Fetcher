#!/usr/bin/env python3
"""
plugins/drweil_blog.py
----------------------
Dr. Weil's Blog (main listing) — https://www.drweil.com/blog/

Feed: feeds/sites/drweil_blog.xml
"""

from __future__ import annotations

try:
    from . import _drweil_base
except ImportError:
    import _drweil_base


class DrWeilBlogPlugin(_drweil_base.DrWeilBasePlugin):
    name = "drweil_blog"
    url = "https://www.drweil.com/blog/"
    title = "Dr. Weil's Blog"
    description = "All articles from DrWeil.com — integrative medicine, healthy living and more."
    language = "en"
    categories = ["health", "wellness"]
    max_items = 50


if __name__ == "__main__":
    _drweil_base.run_interactive_test(DrWeilBlogPlugin())
