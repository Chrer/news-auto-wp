from __future__ import annotations
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from .config import USER_AGENT, REQUEST_TIMEOUT

BAD_SELECTORS = [
    "script", "style", "noscript", "iframe", "svg", "form", "nav", "header", "footer",
    ".sharedaddy", ".share", ".social", ".comments", "#comments", ".related", ".advertisement",
    ".ads", ".ad", ".banner", ".newsletter", ".breadcrumb", ".author-box"
]
ARTICLE_SELECTORS = [
    "article", ".entry-content", ".post-content", ".td-post-content", ".single-content",
    ".article-content", ".news-content", ".nota-content", ".content", "main"
]


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def absolute_url(base_url: str, maybe_url: str | None) -> str | None:
    if not maybe_url:
        return None
    return urljoin(base_url, maybe_url)


def get_meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return clean_spaces(tag["content"])
    return None


def extract_image(soup: BeautifulSoup, page_url: str) -> str | None:
    image = get_meta(soup, "og:image", "twitter:image", "twitter:image:src")
    if image:
        return absolute_url(page_url, image)
    article = find_article_node(soup)
    if article:
        img = article.find("img")
        if img:
            return absolute_url(page_url, img.get("src") or img.get("data-src") or img.get("data-lazy-src"))
    return None


def find_article_node(soup: BeautifulSoup):
    for selector in ARTICLE_SELECTORS:
        node = soup.select_one(selector)
        if node:
            return node
    return soup.body or soup


def extract_paragraphs_from_node(node) -> list[str]:
    for selector in BAD_SELECTORS:
        for bad in node.select(selector):
            bad.decompose()
    paragraphs = []
    for tag in node.find_all(["p", "h2", "h3", "li"], recursive=True):
        text = clean_spaces(tag.get_text(" ", strip=True))
        if not text:
            continue
        low = text.lower()
        if len(text) < 35 and tag.name == "p":
            continue
        if any(x in low for x in ["también lee", "te recomendamos", "síguenos", "whatsapp", "facebook", "x.com", "publicidad"]):
            continue
        paragraphs.append(text)
    # Quita duplicados conservando orden
    seen = set()
    unique = []
    for p in paragraphs:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique[:30]


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
    paragraphs = extract_paragraphs_from_node(node)
    image = extract_image(soup, url)
    return {
        "title": title or "",
        "description": description or "",
        "paragraphs": paragraphs,
        "text": "

".join(paragraphs),
        "image": image,
    }
