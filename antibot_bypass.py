"""
antibot_bypass.py
-----------------
Multi-method anti-bot HTML fetcher.

Each method is optional — if its dependency isn't installed, the method is
simply not registered in METHODS. This lets the module import cleanly in any
environment (local, GitHub Actions, minimal container) with only the
dependencies that are actually available.
"""

import os
import pickle
from urllib.parse import urlparse

import requests

# ---------------------------------------------------------------------------
# Optional dependencies — each wrapped so a missing module doesn't break import
# ---------------------------------------------------------------------------
try:
    import cloudscraper
    _HAS_CLOUDSCRAPER = True
except ImportError:
    _HAS_CLOUDSCRAPER = False

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False

try:
    from playwright.sync_api import sync_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

try:
    from selenium import webdriver
    _HAS_SELENIUM = True
except ImportError:
    _HAS_SELENIUM = False

try:
    import undetected_chromedriver as uc
    _HAS_UC = True
except ImportError:
    _HAS_UC = False


CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def site_name(url):
    return urlparse(url).netloc.replace("www.", "")


def cache_file(url):
    return os.path.join(CACHE_DIR, f"{site_name(url)}.pkl")


def load_cache(url):
    fname = cache_file(url)
    if os.path.exists(fname):
        with open(fname, "rb") as f:
            return pickle.load(f)
    return None


def save_cache(url, html):
    fname = cache_file(url)
    with open(fname, "wb") as f:
        pickle.dump(html, f)


def user_agent():
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------
def method_requests(url):
    try:
        r = requests.get(url, headers={"User-Agent": user_agent()}, timeout=15)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception:
        pass
    return None


if _HAS_CLOUDSCRAPER:
    def method_cloudscraper(url):
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows"},
            )
            r = scraper.get(url, timeout=20)
            if r.status_code == 200 and len(r.text) > 500:
                return r.text
        except Exception:
            pass
        return None


if _HAS_HTTPX:
    def method_httpx(url):
        try:
            with httpx.Client(follow_redirects=True) as client:
                r = client.get(
                    url,
                    headers={"User-Agent": user_agent()},
                    timeout=20,
                )
                if r.status_code == 200 and len(r.text) > 500:
                    return r.text
        except Exception:
            pass
        return None


if _HAS_CURL_CFFI:
    def method_curl_cffi(url):
        try:
            r = curl_requests.get(
                url,
                timeout=20,
                impersonate="chrome124",
            )
            if r.status_code == 200 and len(r.text) > 500:
                return r.text
        except Exception:
            pass
        return None


if _HAS_PLAYWRIGHT:
    def method_playwright(url):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                ctx = browser.new_context(
                    user_agent=user_agent(),
                    viewport={"width": 1366, "height": 900},
                )
                page = ctx.new_page()
                page.goto(url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(2500)
                html = page.content()
                browser.close()
                if len(html) > 500:
                    return html
        except Exception:
            pass
        return None


if _HAS_SELENIUM:
    def method_selenium(url):
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument(
                "--disable-blink-features=AutomationControlled")
            options.add_argument(f"user-agent={user_agent()}")
            driver = webdriver.Chrome(options=options)
            driver.get(url)
            html = driver.page_source
            driver.quit()
            if len(html) > 500:
                return html
        except Exception:
            pass
        return None


if _HAS_UC:
    def method_undetected_chromedriver(url):
        try:
            options = uc.ChromeOptions()
            options.add_argument("--no-sandbox")
            options.add_argument(
                "--disable-blink-features=AutomationControlled")
            driver = uc.Chrome(options=options, headless=True)
            driver.get(url)
            html = driver.page_source
            driver.quit()
            if len(html) > 500:
                return html
        except Exception:
            pass
        return None


def method_rotating_user_agents(url):
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        user_agent(),
    ]
    for ua in agents:
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=10)
            if r.status_code == 200 and len(r.text) > 500:
                return r.text
        except Exception:
            pass
    return None


def method_rotating_referrers(url):
    referrers = ["https://google.com",
                 "https://duckduckgo.com", "https://bing.com"]
    for ref in referrers:
        try:
            r = requests.get(
                url,
                headers={"Referer": ref, "User-Agent": user_agent()},
                timeout=10,
            )
            if r.status_code == 200 and len(r.text) > 500:
                return r.text
        except Exception:
            pass
    return None


def method_fake_ip(url):
    headers = {
        "User-Agent": user_agent(),
        "X-Forwarded-For": "5.45.16.91",
        "Client-IP": "5.45.16.91",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception:
        pass
    return None


def method_accept_all(url):
    headers = {
        "User-Agent": user_agent(),
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception:
        pass
    return None


def method_combined(url):
    headers = {
        "User-Agent": user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://google.com",
        "Accept-Language": "en,en-US;q=0.9",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Registry — only methods whose dependencies are installed
# ---------------------------------------------------------------------------
def _build_methods():
    methods = [method_requests]

    if _HAS_CURL_CFFI:
        methods.append(method_curl_cffi)
    if _HAS_CLOUDSCRAPER:
        methods.append(method_cloudscraper)
    if _HAS_HTTPX:
        methods.append(method_httpx)
    if _HAS_PLAYWRIGHT:
        methods.append(method_playwright)
    if _HAS_UC:
        methods.append(method_undetected_chromedriver)
    if _HAS_SELENIUM:
        methods.append(method_selenium)

    methods.extend([
        method_rotating_user_agents,
        method_rotating_referrers,
        method_fake_ip,
        method_accept_all,
        method_combined,
    ])
    return methods


METHODS = _build_methods()


def get_html(url):
    cached = load_cache(url)
    if cached:
        return cached
    for method in METHODS:
        html = method(url)
        if html:
            save_cache(url, html)
            return html
    return None
