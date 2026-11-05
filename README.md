# RSS Fetcher — Plugin-Based RSS Feed Generator

A self-contained, plugin-based RSS 2.0 feed generator in pure Python. Each website gets its own isolated plugin module; the main script discovers plugins automatically, extracts items, and writes standards-compliant RSS feeds — one per site, one per category, plus a master aggregate feed.

**Version:** 1.1 · **Date:** 2026-11-05

---

## 📡 Generated RSS Feeds

All feeds are regenerated on every run of `python rss_fetcher.py` and written to the `feeds/` folder. Subscribe to any of them in your favorite RSS reader.

### Category Feeds (`feeds/categories/`)

Aggregated across all plugins that declare the category, deduplicated by link:

| Feed | Sources | Items |
|------|---------|-------|
| [categories/tech.xml](feeds/categories/tech.xml) | juejin, sample_site | 50 |
| [categories/programming.xml](feeds/categories/programming.xml) | juejin | 50 |
| [categories/news.xml](feeds/categories/news.xml) | sample_site *(once its URL is fixed)* | — |

### Master Feed

| Feed | Description | Items |
|------|-------------|-------|
| [feeds/all.xml](feeds/all.xml) | Master aggregate of all sources (deduplicated by link, capped at 800) | 50 |

### Per-Site Feeds (`feeds/sites/`)

<details>
<summary>📡 Site feeds — click to expand (scrollable, 25 rows per view)</summary>

<div style="max-height: 640px; overflow-y: auto;">

| Feed | Source | Language | Categories | Items |
|------|--------|----------|------------|-------|
| [sites/juejin.xml](feeds/sites/juejin.xml) | 稀土掘金 (juejin.cn) | zh-cn | tech, programming | 50 |
| [sites/sample_site.xml](feeds/sites/sample_site.xml) | Sample News Site *(template — placeholder URL, currently 404s)* | en | news, tech | — |

</div>

</details>

> **Note:** The tables above reflect the plugins currently in the `plugins/` folder. When you add a new plugin, its site feed and category feeds appear automatically on the next run — update this section to list them.

---

## ✨ Features

- **Automatic plugin discovery** — drop a `.py` file into `plugins/` and it's picked up on the next run.
- **Individual feed per site** — `feeds/sites/{plugin.name}.xml`.
- **Aggregated feeds per category** — `feeds/categories/{category}.xml`, deduplicated by link.
- **Master aggregate feed** — `feeds/all.xml` (all sources, capped at 800 items).
- **Rich item support** — title, link, description, full content, author, categories, cover image, enclosures, and an open-ended `extra` dict.
- **Standards-compliant RSS 2.0** — `dc:creator` (Dublin Core extension), multiple `<category>` elements, `guid`, CDATA content, `<enclosure>`, RFC 822 dates.
- **Overwrite strategy** — keeps only the latest ~100 items per site (configurable via `max_items`).
- **Robust discovery** — plugins are matched by their contract (a concrete class with `get_items()`), so plugins work whether they import `BasePlugin` from the main module or define their own fallback copy.

---

## 📁 Directory Structure

```text
RSS Fetcher/
├── rss_fetcher.py              # Main single-file entry point (portable)
├── plugins/                    # One Python file per website
│   ├── __init__.py
│   ├── juejin.py               # 稀土掘金 (juejin.cn) — JSON API based
│   └── sample_site.py          # Official sample / template plugin (CSS selectors)
├── feeds/                      # Generated output (overwritten on each run)
│   ├── sites/                  # One feed per plugin/site
│   │   └── juejin.xml
│   ├── categories/             # One aggregated feed per category
│   │   ├── tech.xml
│   │   └── programming.xml
│   └── all.xml                 # Master aggregate of everything
└── README.md
```

---

## 🚀 Usage

### Requirements

```bash
pip install feedgen requests beautifulsoup4 lxml
```

### Run

```bash
python rss_fetcher.py
```

Output on a successful run:

```text
Found 2 plugin(s)

→ Processing: juejin
  ✓ sites/juejin.xml  (50 items)
→ Processing: sample_site
  ✗ Error while processing sample_site: 404 Client Error: Not Found ...

Building category feeds...
  ✓ categories/tech.xml  (50 items)
  ✓ categories/programming.xml  (50 items)

Building master feed...
  ✓ all.xml  (50 items)

Done.
```

### Test a single plugin interactively

Both bundled plugins have an interactive test mode:

```bash
python plugins/juejin.py        # shows the first 3 articles
python plugins/sample_site.py   # tests selector extraction
```

---

## 🧩 Writing a Plugin

### Quick start

1. Copy `plugins/sample_site.py` and rename the file.
2. Change the class name, `name`, `url`, `title`, `description`, and `categories`.
3. Fill in the CSS selectors for your target site — or rewrite `get_items()` entirely (API, JSON, browser automation, anything goes).
4. Run `python rss_fetcher.py`. The new plugin is discovered automatically.
5. Verify the generated XML in `feeds/sites/`.

### Plugin contract

A plugin is any concrete class that exposes a `get_items()` method returning a list of item dictionaries. Inheriting from `BasePlugin` (in `rss_fetcher.py`) gives you `fetch_html()`, a default `User-Agent`, and `parse_date()` for free — but is optional. Discovery is contract-based, so a plugin that defines its own minimal `BasePlugin` fallback (for standalone testing) still works.

Required class attributes:

| Attribute | Type | Purpose |
|-----------|------|---------|
| `name` | `str` | Unique, filename-safe identifier — used as the feed filename |
| `url` | `str` | Listing page URL (or API endpoint) |
| `title` | `str` | Feed title |

Recommended:

| Attribute | Default | Purpose |
|-----------|---------|---------|
| `description` | `""` | Feed description |
| `language` | `"en"` | Feed language code |
| `categories` | `[]` | Drives category feed aggregation |
| `max_items` | `100` | Per-site item cap |
| `headers` | Chrome UA | Custom HTTP headers (cookies, auth, …) |

### Standard item schema

Every item returned by `get_items()` follows this structure:

```python
{
    # === Required ===
    "title": str,
    "link": str,

    # === Highly recommended ===
    "description": str,          # may contain HTML
    "content": str,              # full content → content:encoded
    "pubDate": datetime,         # timezone-aware preferred
    "author": str,               # → author + dc:creator
    "guid": str,                 # falls back to link
    "categories": list[str],

    # === Media ===
    "image": str,                # main image / thumbnail URL → <enclosure>
    "enclosures": [              # audio, video, files, …
        {"url": str, "type": str, "length": int | None, "title": str | None}
    ],

    # === Open extension point ===
    "extra": dict                # anything custom: views, likes, duration, …
}
```

Anything that doesn't fit a named field goes into `extra`. For example, the juejin plugin stores `view_count`, `digg_count`, `comment_count`, `collect_count`, `hot_index`, and `article_id` there.

### Bundled plugins

#### `plugins/juejin.py` — 稀土掘金 (juejin.cn)

- **Method:** JSON API (`POST https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed`) with cursor-based pagination — no HTML parsing.
- **Sort types:** `300` = latest (default), `200` = recommended, `3`/`7`/`30` = hot (3/7/30 days).
- **Extracts:** title, link, brief description, cover image (with fallback candidates), author, publish date (from Unix timestamp), tags + category, and engagement stats into `extra`.
- **Output:** `feeds/sites/juejin.xml` (50 items).

#### `plugins/sample_site.py` — Sample template

- **Method:** CSS selectors via BeautifulSoup over a listing page.
- **Purpose:** official template to copy for new plugins; demonstrates the full item schema, flexible selectors, date parsing hook, and interactive test mode.
- **Note:** points at the placeholder `https://example.com/news`, which returns 404 — expected until you adapt it to a real site.

---

## ⚙️ How It Works

On every run the system performs:

1. **Discover** all plugins in `plugins/` (skipping `_`-prefixed modules).
2. **Run** each plugin and collect items (capped at `max_items`); plugin categories are merged into each item.
3. **Write** individual feed → `feeds/sites/{plugin.name}.xml`.
4. **Group** items by declared categories → `feeds/categories/{category}.xml` (deduplicated by `link`, capped at 400).
5. **Write** master feed → `feeds/all.xml` (deduplicated by `link`, capped at 800).

A failing plugin (network error, bad selectors, …) is reported and skipped — it never aborts the whole run.

### Feed quality guarantees

- Proper RSS 2.0 structure via [`feedgen`](https://github.com/lkiesow/python-feedgen)
- `dc:creator` via the Dublin Core extension
- Multiple `<category>` elements per item
- `guid` with permalink
- CDATA for HTML in `description` / `content:encoded`
- `<enclosure>` support (images, audio, video)
- Correct RFC 822 dates

---

## 🗺️ Future Extension Points

Already supported by the design:

- Playwright / Selenium inside any plugin
- Full-text extraction (readability / trafilatura)
- Proxy / cookie / custom header support per plugin
- Podcast-specific fields via `enclosures` + `extra`
- Media RSS tags
- Caching layer in `rss_fetcher.py`
- Scheduled runs via GitHub Actions

---

## 📋 Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Main architecture | Single file + plugins folder | Portability & cleanliness |
| Plugin matching | Contract-based (`get_items()`), not strict inheritance | Immune to double-import identity issues when run as `__main__` |
| Item schema | Rich + open `extra` dict | Maximum flexibility |
| Categories | Declared per plugin + auto aggregation | Clean feed grouping |
| Item limit | ~100 per site, overwrite | Practical & lightweight |
| Feed quality | RSS 2.0 + dc:creator + enclosures | Compatibility with all readers |
| Extraction freedom | Full freedom inside `get_items()` | Can handle any website |
| Error handling | Per-plugin isolation | One bad site never breaks the run |
