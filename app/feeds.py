from __future__ import annotations
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import feedparser
from .config import USER_AGENT
from .text_utils import decode_entities, canonical_url, clean_tag_name, safe_slug

COMMON_FEED_PATHS = ["/feed/", "/rss/", "/rss.xml", "/feed.xml", "/atom.xml"]


def normalize_url(url: str) -> str:
    return canonical_url(url or "")


def discover_feed(home_url: str) -> str | None:
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(home_url, headers=headers, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
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
    return decode_entities(text)


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


def get_entry_tags(entry) -> list[str]:
    tags = []
    for item in entry.get("tags", []) or []:
        term = item.get("term") if isinstance(item, dict) else None
        if term:
            tags.append(html_to_text(term))
    # Algunos feeds guardan categorías en category/categories
    cat = entry.get("category")
    if cat:
        tags.append(html_to_text(cat))
    clean = []
    seen = set()
    for tag in tags:
        tag = clean_tag_name(tag)
        key = tag.lower()
        if tag and len(tag) >= 3 and key not in seen:
            seen.add(key)
            clean.append(tag)
    return clean[:12]

def parse_entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if value:
            try:
                dt = parsedate_to_datetime(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass
    return None


def source_identifier(source: dict) -> str:
    return source.get("id") or safe_slug(source.get("name") or source.get("home_url") or "fuente")


def read_feed(source: dict) -> list[dict]:
    feed_url = source.get("feed_url") or discover_feed(source["home_url"])
    if not feed_url:
        return []
    parsed = feedparser.parse(feed_url)
    items = []
    for entry in parsed.entries[:25]:
        title = html_to_text(entry.get("title", ""))
        link = normalize_url(entry.get("link", ""))
        summary = html_to_text(entry.get("summary", "") or entry.get("description", ""))
        if not title or not link:
            continue
        published_dt = parse_entry_datetime(entry)
        items.append(
            {
                "title": title,
                "url": link,
                "summary": summary,
                "published": entry.get("published", "") or entry.get("updated", ""),
                "published_dt": published_dt,
                "image": get_entry_image(entry),
                "source_name": source.get("name", "Fuente"),
                "source_id": source_identifier(source),
                "extraction_category": source.get("extraction_category") or source.get("category"),
                "target_category": source.get("target_category") or source.get("category"),
                "default_category": source.get("target_category") or source.get("category"),
                "default_categories": source.get("target_category") or source.get("category"),
                "source_status": source.get("status"),
                "source_full_article": bool(source.get("full_article", True)),
                "tags": get_entry_tags(entry),
            }
        )
    return items
