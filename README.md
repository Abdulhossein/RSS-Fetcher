# RSS Fetcher

Plugin-based RSS 2.0 generator. Drop a `.py` file in `plugins/`; `rss_fetcher.py` discovers it, pulls items, and writes feeds.

**Version:** 1.2 · **Date:** 2026-11-08

---

## RSS Feeds

Subscribe to the master feed or a category. Tables below are rewritten on every run from plugin `categories`.

<!-- AUTO:FEEDS:START -->
| Feed | Items |
|------|-------|
| [all.xml][feed-all] | 200 |
| [categories/happiness.xml][feed-cat-happiness] | 50 |
| [categories/health.xml][feed-cat-health] | 150 |
| [categories/programming.xml][feed-cat-programming] | 50 |
| [categories/tech.xml][feed-cat-tech] | 50 |
| [categories/tips.xml][feed-cat-tips] | 50 |
| [categories/wellness.xml][feed-cat-wellness] | 150 |
<!-- AUTO:FEEDS:END -->

---

## Usage

```bash
pip install -r requirements.txt
python rss_fetcher.py
```

Refresh these tables without fetching:

```bash
python rss_fetcher.py --readme-only
```

Add a site by adding a plugin (class with `name`, `url`, `title`, `categories`, and `get_items()`). Files starting with `_` are shared libraries and are skipped. A failing plugin is skipped; the rest still run.

A GitHub Action regenerates feeds daily at 05:00 UTC.

<!-- AUTO:FEED-LINKS:START -->
<!-- Feed link targets. GitHub Action rewrites owner/repo/branch. -->
[feed-all]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/all.xml
[feed-cat-happiness]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/happiness.xml
[feed-cat-health]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/health.xml
[feed-cat-programming]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/programming.xml
[feed-cat-tech]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/tech.xml
[feed-cat-tips]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/tips.xml
[feed-cat-wellness]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/wellness.xml
<!-- AUTO:FEED-LINKS:END -->
