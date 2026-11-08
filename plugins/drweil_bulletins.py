#!/usr/bin/env python3
"""
plugins/drweil_bulletins.py
---------------------------
Dr. Weil's Weekly Bulletin — https://www.drweil.com/blog/bulletins/

Feed: feeds/sites/drweil_bulletins.xml
"""

from __future__ import annotations

try:
    from . import _drweil_base
except ImportError:
    import _drweil_base


class DrWeilBulletinsPlugin(_drweil_base.DrWeilBasePlugin):
    name = "drweil_bulletins"
    url = "https://www.drweil.com/blog/bulletins/"
    title = "Dr. Weil's Weekly Bulletin"
    description = "Current health news, insights and healthy recipes from Andrew Weil, M.D."
    language = "en"
    categories = ["health", "wellness"]
    max_items = 50


if __name__ == "__main__":
    _drweil_base.run_interactive_test(DrWeilBulletinsPlugin())
