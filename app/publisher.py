from __future__ import annotations
from datetime import datetime, timezone
from html import escape
from itertools import zip_longest
from .config import (
    MIN_SUMMARY_LENGTH, MAX_POSTS_PER_RUN, WORDPRESS_STATUS, load_yaml_config,
    COPY_FULL_ARTICLE, PARAPHRASE_ARTICLE, UPLOAD_FEATURED_IMAGE,
    REQUIRE_IMAGE, MAX_ARTICLE_AGE_HOURS, SKIP_UNDATED_ARTICLES, MIN_PARAGRAPHS_FULL_ARTICLE, DATE_FILTER_ENABLED
)
from .database import already_processed, mark_processed
from .feeds import read_feed
from .article import fetch_full_article
from .paraphraser import paraphrase_text
from .wordpress import WordPressClient
from .text_utils import decode_entities, canonical_url, clean_text_global


def choose_category(item: dict, cfg: dict) -> str:
    text = f"{item.get('title','')} {item.get('summary','')}"
    text = decode_entities(text).lower()
    for rule in cfg.get("category_rules", []):
        for kw in rule.get("keywords", []):
            if kw.lower() in text:
                return rule["category"]
    return item.get("default_category") or cfg.get("site", {}).get("default_category", "Nacional")


def get_source_status(item: dict, cfg: dict) -> str:
    return item.get("source_status") or cfg.get("site", {}).get("default_status") or WORDPRESS_STATUS


def article_is_recent(published_dt: datetime | None, max_hours: int = 24) -> tuple[bool, str]:
    # En la versión estable el filtro de fecha está desactivado por defecto.
    if not DATE_FILTER_ENABLED:
        return True, "filtro de fecha desactivado"
    if not published_dt:
        if SKIP_UNDATED_ARTICLES:
            return False, "sin fecha de publicación verificable"
        return True, "fecha no disponible, permitido por configuración"
    now = datetime.now(timezone.utc)
    age_hours = (now - published_dt.astimezone(timezone.utc)).total_seconds() / 3600
    if age_hours < 0:
        return True, "fecha futura o reciente"
    if max_hours and age_hours > max_hours:
        return False, f"noticia antigua: {age_hours:.1f} horas"
    return True, f"reciente: {age_hours:.1f} horas"


def build_full_content(item: dict, paragraphs: list[str]) -> str:
    blocks = []
    for p in paragraphs:
        p = clean_text_global(p)
        if p:
            blocks.append(f"<p>{escape(p)}</p>")
    # No se agrega fuente visible dentro del contenido.
    return "\n".join(blocks)


def build_summary_content(item: dict, cfg: dict) -> str:
    site_cfg = cfg.get("site", {})
    summary = clean_text_global(item.get("summary") or "Consulta la información completa en la fuente original.")
    template = site_cfg.get("post_template") or "<p>{summary}</p>"
    return template.format(
        title=escape(decode_entities(item["title"])),
        summary=escape(summary),
        source_name=escape(decode_entities(item.get("source_name", "Fuente original"))),
        original_url=escape(item["url"]),
        published=escape(decode_entities(item.get("published", ""))),
    )


def prepare_item_content(item: dict, cfg: dict) -> tuple[str, str, str | None, datetime | None]:
    """Regresa title, content, image_url, published_dt."""
    image_url = item.get("image")
    published_dt = item.get("published_dt")
    should_copy_full = COPY_FULL_ARTICLE and item.get("source_full_article", True)
    if should_copy_full:
        article = fetch_full_article(item["url"])
        if article.get("title"):
            item["title"] = clean_text_global(article["title"])
        else:
            item["title"] = clean_text_global(item["title"])
        if article.get("description") and not item.get("summary"):
            item["summary"] = clean_text_global(article["description"])
        if article.get("image"):
            image_url = article["image"]
        if article.get("published_dt"):
            published_dt = article["published_dt"]
        article_tags = article.get("tags") or []
        if article_tags:
            item["tags"] = list(dict.fromkeys((item.get("tags") or []) + article_tags))[:12]
        paragraphs = article.get("paragraphs") or []
        if len(paragraphs) < MIN_PARAGRAPHS_FULL_ARTICLE:
            raise RuntimeError(f"no se pudo extraer cuerpo completo suficiente: {len(paragraphs)} párrafos")
        if PARAPHRASE_ARTICLE:
            paragraphs = paraphrase_text(paragraphs)
        return item["title"], build_full_content(item, paragraphs), image_url, published_dt
    item["title"] = clean_text_global(item["title"])
    return item["title"], build_summary_content(item, cfg), image_url, published_dt


def interleave_sources(source_items: list[tuple[dict, list[dict]]]):
    """Mezcla fuentes para que no se quede solo en la primera, por ejemplo Luz Noticias."""
    lists = [items for _, items in source_items]
    sources = [source for source, _ in source_items]
    for group in zip_longest(*lists):
        for idx, item in enumerate(group):
            if item is not None:
                yield sources[idx], item


def run_once() -> dict:
    cfg = load_yaml_config()
    wp = WordPressClient()
    published: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    source_report: dict[str, dict] = {}

    source_items: list[tuple[dict, list[dict]]] = []
    for source in cfg.get("sources", []):
        name = source.get("name", "Fuente")
        try:
            items = read_feed(source)
            source_report[name] = {"found": len(items), "published": 0, "skipped": 0, "errors": 0}
            source_items.append((source, items))
        except Exception as exc:
            source_report[name] = {"found": 0, "published": 0, "skipped": 0, "errors": 1}
            errors.append({"source": name, "error": str(exc)})

    for source, item in interleave_sources(source_items):
        if len(published) >= MAX_POSTS_PER_RUN:
            break
        source_name = item.get("source_name") or source.get("name", "Fuente")
        item["url"] = canonical_url(item.get("url"))
        item["title"] = clean_text_global(item.get("title"))
        item["summary"] = clean_text_global(item.get("summary"))

        if already_processed(item["url"], item.get("title")):
            skipped.append({"title": item["title"], "source": source_name, "reason": "duplicada en registro local"})
            source_report[source_name]["skipped"] += 1
            continue
        if wp.post_exists(item.get("title", "")):
            mark_processed(item["url"], item.get("title", ""), source_name, None, "duplicada_wp")
            skipped.append({"title": item["title"], "source": source_name, "reason": "duplicada en WordPress"})
            source_report[source_name]["skipped"] += 1
            continue
        if not COPY_FULL_ARTICLE and len(item.get("summary", "")) < MIN_SUMMARY_LENGTH:
            skipped.append({"title": item["title"], "source": source_name, "reason": "resumen muy corto"})
            source_report[source_name]["skipped"] += 1
            continue

        try:
            category = choose_category(item, cfg)
            status = get_source_status(item, cfg)
            title, content, image_url, published_dt = prepare_item_content(item, cfg)

            # Revisa duplicado otra vez por si el título cambió al abrir el artículo completo.
            if already_processed(item["url"], title):
                skipped.append({"title": title, "source": source_name, "reason": "duplicada después de extraer artículo"})
                source_report[source_name]["skipped"] += 1
                continue
            if wp.post_exists(title):
                mark_processed(item["url"], title, source_name, None, "duplicada_wp")
                skipped.append({"title": title, "source": source_name, "reason": "duplicada en WordPress"})
                source_report[source_name]["skipped"] += 1
                continue

            recent_ok, recent_reason = article_is_recent(published_dt, MAX_ARTICLE_AGE_HOURS)
            if not recent_ok:
                skipped.append({"title": title, "source": source_name, "reason": recent_reason})
                source_report[source_name]["skipped"] += 1
                continue

            media_id = None
            if UPLOAD_FEATURED_IMAGE:
                if not image_url:
                    if REQUIRE_IMAGE:
                        skipped.append({"title": title, "source": source_name, "reason": "sin imagen extraíble"})
                        source_report[source_name]["skipped"] += 1
                        continue
                else:
                    try:
                        media_id = wp.upload_media(image_url, alt_text=title)
                    except Exception as exc:
                        if REQUIRE_IMAGE:
                            skipped.append({"title": title, "source": source_name, "reason": f"falló subida de imagen: {exc}"})
                            source_report[source_name]["skipped"] += 1
                            continue
                        errors.append({"title": title, "source": source_name, "warning": f"imagen no subida: {exc}"})
                    if REQUIRE_IMAGE and not media_id:
                        skipped.append({"title": title, "source": source_name, "reason": "imagen inválida o no descargable"})
                        source_report[source_name]["skipped"] += 1
                        continue

            post = wp.create_post(
                title=title,
                content=content,
                category_name=category,
                status=status,
                excerpt=item.get("summary", ""),
                featured_media=media_id,
                tags=item.get("tags") or [],
            )
            mark_processed(item["url"], title, source_name, post.get("id"), status)
            source_report[source_name]["published"] += 1
            published.append({
                "title": title,
                "source": source_name,
                "category": category,
                "status": status,
                "wp_id": post.get("id"),
                "link": post.get("link"),
                "featured_media": media_id,
            })
        except Exception as exc:
            errors.append({"title": item.get("title"), "source": source_name, "url": item.get("url"), "error": str(exc)})
            source_report[source_name]["errors"] += 1

    return {
        "published": published,
        "skipped": skipped[:80],
        "errors": errors[:80],
        "source_report": source_report,
        "notes": [
            "Filtro de fecha desactivado por defecto.",
            "Duplicados revisados por URL canónica, título normalizado, slug local y posts existentes en WordPress.",
            "Fuentes mezcladas en round-robin para evitar que una sola fuente monopolice la ejecución.",
        ],
    }
