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

CATEGORY_ALIASES = {
    "ciencia-y-tecnologia": "Ciencia y Tecnología",
    "ciencia": "Ciencia y Tecnología",
    "tecnologia": "Ciencia y Tecnología",
    "tecnología": "Ciencia y Tecnología",
    "clima": "Clima",
    "deportes": "Deportes",
    "economia": "Economía",
    "economía": "Economía",
    "internacional": "Internacional",
    "internacionales": "Internacional",
    "nacional": "Nacional",
    "opinion": "Opinión",
    "opinión": "Opinión",
    "policiaca": "Policiaca",
    "seguridad": "Policiaca",
    "politica": "Política",
    "política": "Política",
    "sinaloa": "Sinaloa",
}


def _norm_token(value: str) -> str:
    value = decode_entities(value or "").lower()
    value = value.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ü", "u").replace("ñ", "n")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def infer_category_from_url(url: str) -> str | None:
    """Detecta la categoría real por la URL de la noticia.

    Esto evita que un feed general publique la misma URL en varias categorías.
    Ejemplo: /sinaloa/ => Sinaloa, /policiaca/ => Policiaca.
    """
    tokenized = _norm_token(url or "")
    checks = [
        ("ciencia-y-tecnologia", "Ciencia y Tecnología"),
        ("tecnologia", "Ciencia y Tecnología"),
        ("ciencia", "Ciencia y Tecnología"),
        ("policiaca", "Policiaca"),
        ("seguridad", "Policiaca"),
        ("deportes", "Deportes"),
        ("economia", "Economía"),
        ("internacional", "Internacional"),
        ("nacional", "Nacional"),
        ("opinion", "Opinión"),
        ("politica", "Política"),
        ("clima", "Clima"),
        ("sinaloa", "Sinaloa"),
    ]
    # Para noticiasdelaciencia.com todo cae en Ciencia y Tecnología salvo configuración contraria.
    if "noticiasdelaciencia" in tokenized:
        return "Ciencia y Tecnología"
    for slug, category in checks:
        if f"-{slug}-" in f"-{tokenized}-" or f"/{slug}/" in (url or "").lower():
            return category
    return None


def source_allows_url(source: dict, url: str) -> bool:
    """Filtra entradas cuando un feed descubierto es general y no de la sección.

    Si la URL permite detectar categoría y no coincide con extraction_category, se descarta.
    Si no se puede detectar categoría, se permite para no perder fuentes sin URLs claras.
    """
    if source.get("strict_category_filter", True) is False:
        return True
    expected = source.get("extraction_category") or source.get("target_category") or source.get("category")
    expected_norm = _norm_token(str(expected or ""))
    if not expected_norm:
        return True
    detected = infer_category_from_url(url)
    if not detected:
        return True
    return _norm_token(detected) == expected_norm


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
        if not source_allows_url(source, link):
            continue
        detected_category = infer_category_from_url(link)
        target_category = detected_category or source.get("target_category") or source.get("category")
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
                "url_category": detected_category,
                "target_category": target_category,
                "default_category": target_category,
                "default_categories": target_category,
                "source_status": source.get("status"),
                "source_full_article": bool(source.get("full_article", True)),
                "tags": get_entry_tags(entry),
            }
        )
    return items
