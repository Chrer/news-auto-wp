from __future__ import annotations
import re
from typing import Iterable
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import feedparser
from .config import USER_AGENT

COMMON_FEED_PATHS = ["/feed/", "/rss/", "/rss.xml", "/feed.xml", "/atom.xml"]


def normalize_url(url: str) -> str:
    return (url or "").strip()


def discover_feed(home_url: str) -> str | None:
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(home_url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("link"):
            link_type = (link.get("type") or "").lower()
            rel = " ".join(link.get("rel") or []).lower()
            href = link.get("href")
            if href and ("rss" in link_type or "atom" in link_type or "alternate" in rel):
                return urljoin(home_url, href)
    except Exception:
        pass

    for path in COMMON_FEED_PATHS:
        candidate = urljoin(home_url.rstrip("/") + "/", path.lstrip("/"))
        try:
            parsed = feedparser.parse(candidate)
            if parsed.entries:
                return candidate
        except Exception:
            continue
    return None


def html_to_text(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def get_entry_image(entry) -> str | None:
    media_content = entry.get("media_content") or []
    for item in media_content:
        url = item.get("url")
        if url:
            return url
    media_thumbnail = entry.get("media_thumbnail") or []
    for item in media_thumbnail:
        url = item.get("url")
        if url:
            return url
    links = entry.get("links") or []
    for link in links:
        if str(link.get("type", "")).startswith("image/") and link.get("href"):
            return link.get("href")
    return None


def read_feed(source: dict) -> list[dict]:
    feed_url = source.get("feed_url") or discover_feed(source["home_url"])
    if not feed_url:
        return []
    parsed = feedparser.parse(feed_url)
    items = []
    for entry in parsed.entries[:15]:
        title = html_to_text(entry.get("title", ""))
        link = normalize_url(entry.get("link", ""))
        summary = html_to_text(entry.get("summary", "") or entry.get("description", ""))
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "url": link,
                "summary": summary,
                "published": entry.get("published", ""),
                "image": get_entry_image(entry),
                "source_name": source.get("name", "Fuente"),
                "default_category": source.get("category"),
            }
        )
    return items
