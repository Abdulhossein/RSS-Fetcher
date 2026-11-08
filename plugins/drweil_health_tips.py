#!/usr/bin/env python3
"""
plugins/drweil_health_tips.py
-----------------------------
Dr. Weil's Health Tips — https://www.drweil.com/blog/health-tips/

Feed: feeds/sites/drweil_health_tips.xml
"""

from __future__ import annotations

try:
    from . import _drweil_base
except ImportError:
    import _drweil_base


class DrWeilHealthTipsPlugin(_drweil_base.DrWeilBasePlugin):
    name = "drweil_health_tips"
    url = "https://www.drweil.com/blog/health-tips/"
    title = "Dr. Weil's Health Tips"
    description = "Practical health tips and lifestyle advice from Andrew Weil, M.D."
    language = "en"
    categories = ["health", "wellness", "tips"]
    max_items = 50


if __name__ == "__main__":
    _drweil_base.run_interactive_test(DrWeilHealthTipsPlugin())
