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


if __name__ == "__main__":
    _drweil_base.run_interactive_test(DrWeilSpontaneousHappinessPlugin())
