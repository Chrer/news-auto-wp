from __future__ import annotations
from datetime import datetime, timezone
from html import escape
from .config import (
    MIN_SUMMARY_LENGTH, MAX_POSTS_PER_RUN, WORDPRESS_STATUS, load_yaml_config,
    COPY_FULL_ARTICLE, PARAPHRASE_ARTICLE, UPLOAD_FEATURED_IMAGE, INCLUDE_SOURCE_LINK,
    REQUIRE_IMAGE, MAX_ARTICLE_AGE_HOURS, SKIP_UNDATED_ARTICLES, MIN_PARAGRAPHS_FULL_ARTICLE, DATE_FILTER_ENABLED
)
from .database import already_processed, mark_processed
from .feeds import read_feed
from .article import fetch_full_article
from .paraphraser import paraphrase_text
from .wordpress import WordPressClient


def choose_category(item: dict, cfg: dict) -> str:
    text = f"{item.get('title','')} {item.get('summary','')}",
    text = " ".join(text).lower()
    for rule in cfg.get("category_rules", []):
        for kw in rule.get("keywords", []):
            if kw.lower() in text:
                return rule["category"]
    return item.get("default_category") or cfg.get("site", {}).get("default_category", "Nacional")


def get_source_status(item: dict, cfg: dict) -> str:
    return item.get("source_status") or cfg.get("site", {}).get("default_status") or WORDPRESS_STATUS


def article_is_recent(published_dt: datetime | None, max_hours: int = 24) -> tuple[bool, str]:
    # Filtro de fecha desactivado por defecto en esta versión.
    # Así no se descartan noticias por "sin fecha" ni por "noticia antigua".
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
        if p.strip():
            blocks.append(f"<p>{escape(p.strip())}</p>")
    # No se agrega bloque visible de fuente original dentro del contenido.
    # La URL original se conserva internamente en la base de datos para evitar duplicados.
    return "\n".join(blocks)


def build_summary_content(item: dict, cfg: dict) -> str:
    site_cfg = cfg.get("site", {})
    summary = item.get("summary") or "Consulta la información completa en la fuente original."
    template = site_cfg.get("post_template") or "<p>{summary}</p><p>Fuente: {source_name}</p><p>{original_url}</p>"
    return template.format(
        title=escape(item["title"]),
        summary=escape(summary),
        source_name=escape(item.get("source_name", "Fuente original")),
        original_url=escape(item["url"]),
        published=escape(item.get("published", "")),
    )


def prepare_item_content(item: dict, cfg: dict) -> tuple[str, str, str | None, datetime | None]:
    """Regresa title, content, image_url, published_dt."""
    image_url = item.get("image")
    published_dt = item.get("published_dt")
    should_copy_full = COPY_FULL_ARTICLE and item.get("source_full_article", True)
    if should_copy_full:
        article = fetch_full_article(item["url"])
        if article.get("title"):
            item["title"] = article["title"]
        if article.get("description") and not item.get("summary"):
            item["summary"] = article["description"]
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
    return item["title"], build_summary_content(item, cfg), image_url, published_dt


def run_once() -> dict:
    cfg = load_yaml_config()
    wp = WordPressClient()
    published = []
    skipped = []
    errors = []

    for source in cfg.get("sources", []):
        try:
            items = read_feed(source)
        except Exception as exc:
            errors.append({"source": source.get("name"), "error": str(exc)})
            continue

        for item in items:
            if len(published) >= MAX_POSTS_PER_RUN:
                break
            if already_processed(item["url"]):
                skipped.append({"title": item["title"], "reason": "duplicada"})
                continue
            if not COPY_FULL_ARTICLE and len(item.get("summary", "")) < MIN_SUMMARY_LENGTH:
                skipped.append({"title": item["title"], "reason": "resumen muy corto"})
                continue

            try:
                category = choose_category(item, cfg)
                status = get_source_status(item, cfg)
                title, content, image_url, published_dt = prepare_item_content(item, cfg)

                recent_ok, recent_reason = article_is_recent(published_dt, MAX_ARTICLE_AGE_HOURS)
                if not recent_ok:
                    skipped.append({"title": title, "reason": recent_reason})
                    continue

                media_id = None
                if UPLOAD_FEATURED_IMAGE:
                    if not image_url:
                        if REQUIRE_IMAGE:
                            skipped.append({"title": title, "reason": "sin imagen extraíble"})
                            continue
                    else:
                        try:
                            media_id = wp.upload_media(image_url, alt_text=title)
                        except Exception as exc:
                            if REQUIRE_IMAGE:
                                skipped.append({"title": title, "reason": f"falló subida de imagen: {exc}"})
                                continue
                            errors.append({"title": title, "warning": f"imagen no subida: {exc}"})
                        if REQUIRE_IMAGE and not media_id:
                            skipped.append({"title": title, "reason": "imagen inválida o no descargable"})
                            continue

                # Publica inmediatamente esta noticia válida antes de seguir buscando.
                post = wp.create_post(
                    title=title,
                    content=content,
                    category_name=category,
                    status=status,
                    excerpt=item.get("summary", ""),
                    featured_media=media_id,
                    tags=item.get("tags") or [],
                )
                mark_processed(item["url"], title, item.get("source_name", ""), post.get("id"), status)
                published.append({
                    "title": title,
                    "category": category,
                    "status": status,
                    "wp_id": post.get("id"),
                    "link": post.get("link"),
                    "featured_media": media_id,
                })
            except Exception as exc:
                errors.append({"title": item.get("title"), "url": item.get("url"), "error": str(exc)})

    return {"published": published, "skipped": skipped[:50], "errors": errors}
