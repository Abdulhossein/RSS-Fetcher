# توجه: برای استفاده از بخش‌های کامنت‌شده باید ماژول‌های مربوطه را نصب کنید.
# اگر کامنت برداشته شد، متد/ماژول فعال می‌شود.

import os
import requests, cloudscraper, httpx
# import cfscrape        # فعال فقط با نصب ماژول مربوطه
# import mechanicalsoup  # فعال فقط با نصب ماژول مربوطه
# import aiohttp, asyncio# فعال فقط با نصب ماژول مربوطه
# import browser_cookie3 # فعال فقط با نصب ماژول مربوطه
# import fake_useragent  # فعال فقط با نصب ماژول مربوطه
# import torrequest      # فعال فقط با نصب ماژول مربوطه
# import pycurl          # فعال فقط با نصب ماژول مربوطه
# import Scrapy          # فعال فقط با نصب ماژول مربوطه
from playwright.sync_api import sync_playwright
from selenium import webdriver
import undetected_chromedriver as uc
# import socks, socket   # فعال فقط با نصب ماژول مربوطه
import pickle
from urllib.parse import urlparse

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
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
    try:
        # from fake_useragent import UserAgent
        # return UserAgent().random
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    except:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def method_requests(url):
    h = {"User-Agent": user_agent()}
    try:
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code == 200 and len(r.text)>500:
            return r.text
    except: pass
    return None

def method_cloudscraper(url):
    try:
        scraper = cloudscraper.create_scraper()
        r = scraper.get(url, timeout=20)
        if r.status_code == 200 and len(r.text)>500: return r.text
    except: pass
    return None

# def method_cfscrape(url):
#     try:
#         scraper = cfscrape.create_scraper()
#         r = scraper.get(url, timeout=20)
#         if r.status_code == 200 and len(r.text)>500: return r.text
#     except: pass
#     return None

def method_httpx(url):
    try:
        with httpx.Client() as client:
            r = client.get(url, headers={"User-Agent": user_agent()}, timeout=20)
            if r.status_code == 200 and len(r.text)>500: return r.text
    except: pass
    return None

def method_playwright(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": user_agent()})
            page.goto(url, wait_until="domcontentloaded", timeout=35000)
            html = page.content()
            browser.close()
            if len(html)>500: return html
    except: pass
    return None

def method_selenium(url):
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument(f'user-agent={user_agent()}')
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        html = driver.page_source
        driver.quit()
        if len(html)>500: return html
    except: pass
    return None

def method_undetected_chromedriver(url):
    try:
        options = uc.ChromeOptions()
        options.headless = True
        driver = uc.Chrome(options=options)
        driver.get(url)
        html = driver.page_source
        driver.quit()
        if len(html)>500: return html
    except: pass
    return None

# def method_tor(url):
#     try:
#         with torrequest.TorRequest() as tor:
#             r = tor.get(url)
#             if r.status_code == 200 and len(r.text)>500: return r.text
#     except: pass
#     return None

# def method_mechanicalsoup(url):
#     try:
#         browser = mechanicalsoup.StatefulBrowser()
#         browser.open(url)
#         html = browser.get_current_page().prettify()
#         browser.close()
#         if len(html)>500: return html
#     except: pass
#     return None

# async def method_aiohttp(url):
#     headers = {"User-Agent": user_agent()}
#     async with aiohttp.ClientSession() as session:
#         try:
#             async with session.get(url, headers=headers, timeout=20) as resp:
#                 html = await resp.text()
#                 if resp.status == 200 and len(html)>500: return html
#         except: pass
#     return None

# def method_aiohttp_sync(url):
#     return asyncio.run(method_aiohttp(url))

# def method_browsercookie(url):
#     try:
#         cookies = browser_cookie3.chrome()
#         r = requests.get(url, cookies=cookies, headers={"User-Agent": user_agent()}, timeout=20)
#         if r.status_code == 200 and len(r.text)>500: return r.text
#     except: pass
#     return None

# def method_pycurl(url):
#     try:
#         buffer = []
#         def writer(data): buffer.append(data)
#         c = pycurl.Curl()
#         c.setopt(pycurl.URL, url)
#         c.setopt(pycurl.WRITEFUNCTION, writer)
#         c.setopt(pycurl.USERAGENT, user_agent())
#         c.setopt(pycurl.FOLLOWLOCATION, True)
#         c.setopt(pycurl.TIMEOUT, 20)
#         c.perform()
#         c.close()
#         html = b''.join(buffer).decode('utf-8','ignore')
#         if len(html)>500: return html
#     except: pass
#     return None

# def method_scrapy(url):
#     try:
#         import scrapy
#         from scrapy.http import Request
#         class SimpleSpider(scrapy.Spider):
#             name = "simple"
#             def start_requests(self): yield Request(url)
#             def parse(self, response): return response.text
#         # برای استفاده واقعی باید این را با Scrapy framework اجرا کنی
#         return None
#     except: pass
#     return None

# def method_proxy_socks(url):
#     try:
#         socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
#         socket.socket = socks.socksocket
#         r = requests.get(url, headers={"User-Agent": user_agent()}, timeout=20)
#         if r.status_code == 200 and len(r.text)>500: return r.text
#     except: pass
#     return None

# def method_curl_cffi(url):
#     try:
#         from curl_cffi import requests as curl_requests
#         r = curl_requests.get(url)
#         if r.status_code == 200 and len(r.text)>500: return r.text
#     except: pass
#     return None

def method_rotating_user_agents(url):
    agents = [
        "Mozilla/5.0 ... Edge/123.0.0.0",
        "Mozilla/5.0 ... Safari/537.36",
        user_agent()
    ]
    for ua in agents:
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=10)
            if r.status_code == 200 and len(r.text)>500: return r.text
        except: pass
    return None

def method_rotating_referrers(url):
    referrers = [
        "https://google.com", "https://duckduckgo.com", "https://bing.com"
    ]
    for ref in referrers:
        try:
            r = requests.get(url, headers={"Referer": ref, "User-Agent": user_agent()}, timeout=10)
            if r.status_code == 200 and len(r.text)>500: return r.text
        except: pass
    return None

def method_fake_ip(url):
    headers = {
        "User-Agent": user_agent(),
        "X-Forwarded-For": "5.45.16.91",
        "Client-IP": "5.45.16.91"
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200 and len(r.text)>500: return r.text
    except: pass
    return None

def method_accept_all(url):
    headers = {
        "User-Agent": user_agent(),
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200 and len(r.text)>500: return r.text
    except: pass
    return None

def method_combined(url):
    # چند هدر مختلف با هم
    headers = {
        "User-Agent": user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://google.com",
        "Accept-Language": "en,en-US;q=0.9",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1"
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200 and len(r.text)>500: return r.text
    except: pass
    return None

METHODS = [
    method_requests,
    method_cloudscraper,
    # method_cfscrape,
    method_httpx,
    method_playwright,
    method_selenium,
    method_undetected_chromedriver,
    # method_tor,
    # method_mechanicalsoup,
    # method_aiohttp_sync,
    # method_browsercookie,
    # method_pycurl,
    # method_scrapy,
    # method_proxy_socks,
    # method_curl_cffi,
    method_rotating_user_agents,
    method_rotating_referrers,
    method_fake_ip,
    method_accept_all,
    method_combined,
]

def get_html(url):
    cached = load_cache(url)
    if cached: return cached
    for method in METHODS:
        html = method(url)
        if html:
            save_cache(url, html)
            return html
    return None
