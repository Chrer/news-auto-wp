from __future__ import annotations
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
from email.utils import parsedate_to_datetime
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from .config import USER_AGENT, REQUEST_TIMEOUT
from .smart_cleaner import strip_junk_nodes, extract_clean_text_blocks, clean_paragraphs

ARTICLE_SELECTORS = [
    "article", ".entry-content", ".post-content", ".td-post-content", ".single-content",
    ".article-content", ".news-content", ".nota-content", ".content", ".story-body", "main"
]
DATE_META_NAMES = [
    "article:published_time", "article:modified_time", "og:updated_time", "date", "pubdate",
    "publishdate", "timestamp", "DC.date.issued", "dc.date", "sailthru.date"
]


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def absolute_url(base_url: str, maybe_url: str | None) -> str | None:
    if not maybe_url:
        return None
    return urljoin(base_url, maybe_url)


def get_meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"itemprop": name})
        if tag and tag.get("content"):
            return clean_spaces(tag["content"])
    return None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def extract_date(soup: BeautifulSoup) -> datetime | None:
    value = get_meta(soup, *DATE_META_NAMES)
    dt = parse_datetime(value)
    if dt:
        return dt
    time_tag = soup.find("time")
    if time_tag:
        dt = parse_datetime(time_tag.get("datetime") or time_tag.get_text(" ", strip=True))
        if dt:
            return dt
    return None


def find_article_node(soup: BeautifulSoup):
    for selector in ARTICLE_SELECTORS:
        node = soup.select_one(selector)
        if node:
            return node
    return soup.body or soup


def extract_image(soup: BeautifulSoup, page_url: str) -> str | None:
    image = get_meta(soup, "og:image", "twitter:image", "twitter:image:src", "image")
    if image:
        return absolute_url(page_url, image)
    article = find_article_node(soup)
    if article:
        for img in article.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or img.get("data-original")
            if src:
                return absolute_url(page_url, src)
    return None


def extract_paragraphs_from_node(node, title: str = "") -> list[str]:
    # Mini limpiador inteligente local: quita publicidad, relacionados, botones, redes, newsletter, menús y texto repetido.
    paragraphs = extract_clean_text_blocks(node, title=title)
    return paragraphs[:60]


def extract_tags(soup: BeautifulSoup) -> list[str]:
    tags: list[str] = []
    # Meta keywords tradicional
    keywords = get_meta(soup, "keywords", "news_keywords")
    if keywords:
        for part in re.split(r"[,;|]", keywords):
            value = clean_spaces(part)
            if value:
                tags.append(value)
    # OpenGraph/article tags
    for meta in soup.find_all("meta", property="article:tag"):
        value = clean_spaces(meta.get("content", ""))
        if value:
            tags.append(value)
    # Links o elementos visibles de tags, pero no se agregan al contenido de la nota
    for a in soup.select("a[rel~='tag'], .tags a, .tagcloud a, .entry-tags a, .post-tags a"):
        value = clean_spaces(a.get_text(" ", strip=True))
        if value:
            tags.append(value)
    clean_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        tag = clean_spaces(re.sub(r"^[#]+", "", tag))[:50]
        key = tag.lower()
        if not tag or len(tag) < 3 or key in seen:
            continue
        if any(bad in key for bad in ["publicidad", "whatsapp", "facebook", "twitter", "instagram", "newsletter"]):
            continue
        seen.add(key)
        clean_tags.append(tag)
    return clean_tags[:12]


def fetch_full_article(url: str) -> dict:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    title = get_meta(soup, "og:title", "twitter:title")
    if not title and soup.title:
        title = clean_spaces(soup.title.get_text(" ", strip=True))
    description = get_meta(soup, "og:description", "description", "twitter:description")
    node = find_article_node(soup)
    # Limpia basura antes de extraer contenido
    strip_junk_nodes(node)
    paragraphs = extract_paragraphs_from_node(node, title=title or "")
    image = extract_image(soup, url)
    published_dt = extract_date(soup)
    tags = extract_tags(soup)
    return {
        "title": title or "",
        "description": description or "",
        "paragraphs": paragraphs,
        "text": "\n\n".join(paragraphs),
        "image": image,
        "published_dt": published_dt,
        "tags": tags,
    }
