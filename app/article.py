from __future__ import annotations
import json
import re
import html
from datetime import datetime, timezone
from urllib.parse import urljoin
from email.utils import parsedate_to_datetime
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from .config import USER_AGENT, REQUEST_TIMEOUT
from .smart_cleaner import strip_junk_nodes, extract_clean_text_blocks, extract_loose_text_blocks, clean_paragraphs, clean_spaces as _clean_spaces
from .text_utils import decode_entities, clean_tag_name, clean_text_global

ARTICLE_SELECTORS = [
    "article", "[itemprop='articleBody']", ".entry-content", ".post-content", ".td-post-content", ".single-content",
    ".article-content", ".news-content", ".nota-content", ".story-body", ".post-body", ".article-body",
    "main"
]
DATE_META_NAMES = [
    "article:published_time", "article:modified_time", "og:updated_time", "date", "pubdate",
    "publishdate", "timestamp", "DC.date.issued", "dc.date", "sailthru.date"
]


def clean_spaces(text: str) -> str:
    return decode_entities(text or "")


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
    # JSON-LD
    for data in extract_json_ld(soup):
        value = data.get("datePublished") or data.get("dateModified")
        dt = parse_datetime(value)
        if dt:
            return dt
    return None


def extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []
    for script in soup.find_all("script", type=lambda v: v and "ld+json" in v):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        stack = parsed if isinstance(parsed, list) else [parsed]
        while stack:
            obj = stack.pop(0)
            if isinstance(obj, dict):
                items.append(obj)
                graph = obj.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
            elif isinstance(obj, list):
                stack.extend(obj)
    return items


def jsonld_article_data(soup: BeautifulSoup) -> dict:
    for obj in extract_json_ld(soup):
        typ = obj.get("@type", "")
        types = typ if isinstance(typ, list) else [typ]
        if any(str(t).lower() in {"newsarticle", "article", "blogposting"} for t in types):
            return obj
    return {}


def text_from_jsonld_body(soup: BeautifulSoup, title: str = "") -> list[str]:
    obj = jsonld_article_data(soup)
    body = obj.get("articleBody") or obj.get("description") or ""
    if not body:
        return []
    # Divide por saltos o por frases largas.
    parts = [p.strip() for p in re.split(r"\n{2,}|\r{2,}", body) if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"])", body) if len(p.strip()) > 40]
    return clean_paragraphs(parts, title=title, allow_loose=True)


def node_score(node) -> int:
    if not node:
        return 0
    text = clean_spaces(node.get_text(" ", strip=True))
    p_count = len(node.find_all(["p", "h2", "h3", "li"]))
    return min(len(text), 8000) + p_count * 300


def find_article_node(soup: BeautifulSoup):
    candidates = []
    for selector in ARTICLE_SELECTORS:
        try:
            candidates.extend(soup.select(selector))
        except Exception:
            continue
    if soup.body:
        candidates.append(soup.body)
    if not candidates:
        return soup
    return max(candidates, key=node_score)


def extract_image_from_jsonld(soup: BeautifulSoup, page_url: str) -> str | None:
    obj = jsonld_article_data(soup)
    image = obj.get("image")
    if isinstance(image, str):
        return absolute_url(page_url, image)
    if isinstance(image, list) and image:
        first = image[0]
        if isinstance(first, str):
            return absolute_url(page_url, first)
        if isinstance(first, dict) and first.get("url"):
            return absolute_url(page_url, first.get("url"))
    if isinstance(image, dict):
        return absolute_url(page_url, image.get("url") or image.get("contentUrl"))
    return None


def extract_image(soup: BeautifulSoup, page_url: str) -> str | None:
    image = get_meta(soup, "og:image", "twitter:image", "twitter:image:src", "image")
    if image:
        return absolute_url(page_url, image)
    image = extract_image_from_jsonld(soup, page_url)
    if image:
        return image
    article = find_article_node(soup)
    if article:
        for img in article.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or img.get("data-original")
            if src:
                return absolute_url(page_url, src)
    return None


def extract_paragraphs_from_node(node, soup: BeautifulSoup, title: str = "") -> list[str]:
    # Mini limpiador inteligente local: quita publicidad, relacionados, botones, redes, newsletter, menús y texto repetido.
    paragraphs = extract_clean_text_blocks(node, title=title)
    if len(paragraphs) >= 2:
        return paragraphs[:80]

    # Fallback 1: JSON-LD articleBody/description.
    paragraphs = text_from_jsonld_body(soup, title=title)
    if len(paragraphs) >= 2:
        return paragraphs[:80]

    # Fallback 2: extracción más suave desde body, útil cuando el HTML no usa <article> o usa clases raras.
    fallback_node = soup.body or soup
    paragraphs = extract_loose_text_blocks(fallback_node, title=title)
    return paragraphs[:80]


def extract_tags(soup: BeautifulSoup) -> list[str]:
    tags: list[str] = []
    keywords = get_meta(soup, "keywords", "news_keywords")
    if keywords:
        for part in re.split(r"[,;|]", keywords):
            value = clean_spaces(part)
            if value:
                tags.append(value)
    for meta in soup.find_all("meta", property="article:tag"):
        value = clean_spaces(meta.get("content", ""))
        if value:
            tags.append(value)
    for obj in extract_json_ld(soup):
        kws = obj.get("keywords")
        if isinstance(kws, str):
            tags.extend([clean_spaces(x) for x in re.split(r"[,;|]", kws) if clean_spaces(x)])
        elif isinstance(kws, list):
            tags.extend([clean_spaces(str(x)) for x in kws if clean_spaces(str(x))])
    for a in soup.select("a[rel~='tag'], .tags a, .tagcloud a, .entry-tags a, .post-tags a"):
        value = clean_spaces(a.get_text(" ", strip=True))
        if value:
            tags.append(value)
    clean_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        tag = clean_tag_name(tag)
        key = tag.lower()
        if not tag or len(tag) < 3 or key in seen:
            continue
        if any(bad in key for bad in ["publicidad", "whatsapp", "facebook", "twitter", "instagram", "newsletter"]):
            continue
        seen.add(key)
        clean_tags.append(tag)
    return clean_tags[:12]



def _extract_strings_from_obj(obj, out: list[str], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()
            if isinstance(value, str):
                val = html.unescape(value)
                if (key_l in {"articlebody", "body", "content", "contenido", "nota", "text", "description", "descripcion"} or len(val) > 450) and len(val) > 250:
                    out.append(val)
            else:
                _extract_strings_from_obj(value, out, depth + 1)
    elif isinstance(obj, list):
        for value in obj:
            _extract_strings_from_obj(value, out, depth + 1)


def _text_to_candidate_paragraphs(raw: str, title: str = "") -> list[str]:
    if not raw:
        return []
    raw = html.unescape(raw)
    if "<" in raw and ">" in raw:
        raw = BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)
    raw = clean_text_global(raw)
    # Divide por saltos; si viene en una sola línea, divide por oraciones largas.
    parts = [p.strip() for p in re.split(r"\n{1,}|\r{1,}", raw) if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"])", raw) if len(p.strip()) > 35]
    return clean_paragraphs(parts, title=title, allow_loose=True)


def extract_script_text_candidates(soup: BeautifulSoup, title: str = "") -> list[str]:
    """Extrae cuerpo desde JSON-LD, __NEXT_DATA__, Nuxt u otros scripts con estado.

    Varios sitios modernos no dejan el texto en <p>, sino en JSON dentro de <script>.
    """
    candidates: list[str] = []
    for script in soup.find_all("script"):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw or len(raw) < 300:
            continue
        parsed_ok = False
        if raw.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(raw)
                _extract_strings_from_obj(parsed, candidates)
                parsed_ok = True
            except Exception:
                pass
        if not parsed_ok:
            # Fallback regex para articleBody/content embebido.
            for pattern in [r'"articleBody"\s*:\s*"(.*?)"\s*,\s*"', r'"content"\s*:\s*"(.*?)"\s*,\s*"', r'"descripcion"\s*:\s*"(.*?)"\s*,\s*"']:
                for match in re.finditer(pattern, raw, flags=re.S):
                    value = match.group(1)
                    try:
                        value = bytes(value, "utf-8").decode("unicode_escape")
                    except Exception:
                        pass
                    if len(value) > 250:
                        candidates.append(value)
    best: list[str] = []
    for candidate in candidates:
        parts = _text_to_candidate_paragraphs(candidate, title=title)
        if len(parts) > len(best):
            best = parts
    return best[:80]


def extract_raw_paragraphs_soft(soup: BeautifulSoup, title: str = "") -> list[str]:
    """Fallback suave: toma <p> crudos antes de que el limpiador elimine nodos.

    Sirve para sitios como Luz Noticias cuando el selector principal queda vacío.
    """
    raw_parts: list[str] = []
    for p in soup.find_all(["p", "h2", "h3"]):
        text = clean_text_global(p.get_text(" ", strip=True))
        if len(text) >= 35:
            raw_parts.append(text)
    return clean_paragraphs(raw_parts, title=title, allow_loose=True)[:80]


def extract_site_specific_paragraphs(soup: BeautifulSoup, page_url: str, title: str = "") -> list[str]:
    url_l = (page_url or "").lower()
    # Orden: scripts modernos -> p crudos -> extracción laxa de body.
    if "luznoticias.mx" in url_l or "lineadirectaportal.com" in url_l:
        paragraphs = extract_script_text_candidates(soup, title=title)
        if len(paragraphs) >= 2:
            return paragraphs
        paragraphs = extract_raw_paragraphs_soft(soup, title=title)
        if len(paragraphs) >= 2:
            return paragraphs
    paragraphs = extract_script_text_candidates(soup, title=title)
    if len(paragraphs) >= 2:
        return paragraphs
    return []


def fetch_full_article(url: str) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    raw_soup = BeautifulSoup(resp.text, "html.parser")
    soup = BeautifulSoup(resp.text, "html.parser")
    title = get_meta(soup, "og:title", "twitter:title")
    if not title:
        obj = jsonld_article_data(soup)
        title = clean_spaces(obj.get("headline") or obj.get("name") or "")
    if not title and soup.title:
        title = clean_spaces(soup.title.get_text(" ", strip=True))
    description = get_meta(soup, "og:description", "description", "twitter:description")
    node = find_article_node(soup)
    strip_junk_nodes(node)
    paragraphs = extract_paragraphs_from_node(node, soup=soup, title=title or "")
    if len(paragraphs) < 2:
        paragraphs = extract_site_specific_paragraphs(raw_soup, url, title=title or "") or paragraphs
    # Si solo hay un párrafo muy largo, intenta dividirlo por oraciones para no rechazar contenido válido.
    if len(paragraphs) == 1 and len(paragraphs[0]) > 450:
        split_parts = _text_to_candidate_paragraphs(paragraphs[0], title=title or "")
        if len(split_parts) >= 2:
            paragraphs = split_parts
    image = extract_image(soup, url)
    published_dt = extract_date(soup)
    tags = extract_tags(soup)
    return {
        "title": clean_text_global(title or ""),
        "description": clean_text_global(description or ""),
        "paragraphs": paragraphs,
        "text": "\n\n".join(paragraphs),
        "image": image,
        "published_dt": published_dt,
        "tags": tags,
    }
