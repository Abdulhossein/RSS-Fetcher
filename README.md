# RSS Fetcher

Plugin-based RSS 2.0 generator. Drop a `.py` file in `plugins/`; `rss_fetcher.py` discovers it, pulls items, and writes feeds.

---

## RSS Feeds

Subscribe to the master feed or a category. Tables below are rewritten on every run from plugin `categories`.

<!-- AUTO:FEEDS:START -->
| Feed | Items |
|------|-------|
| [all.xml][feed-all] | 800 |
| [categories/chinese.xml][feed-cat-chinese] | 300 |
| [categories/english.xml][feed-cat-english] | 400 |
| [categories/fitness.xml][feed-cat-fitness] | 320 |
| [categories/happiness.xml][feed-cat-happiness] | 60 |
| [categories/health.xml][feed-cat-health] | 380 |
| [categories/lifestyle.xml][feed-cat-lifestyle] | 100 |
| [categories/news.xml][feed-cat-news] | 100 |
| [categories/tech.xml][feed-cat-tech] | 300 |
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
[feed-cat-chinese]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/chinese.xml
[feed-cat-english]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/english.xml
[feed-cat-fitness]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/fitness.xml
[feed-cat-happiness]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/happiness.xml
[feed-cat-health]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/health.xml
[feed-cat-lifestyle]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/lifestyle.xml
[feed-cat-news]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/news.xml
[feed-cat-tech]: https://raw.githubusercontent.com/Abdulhossein/RSS-Fetcher/refs/heads/main/feeds/categories/tech.xml
<!-- AUTO:FEED-LINKS:END -->
