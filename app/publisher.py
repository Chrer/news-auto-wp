from __future__ import annotations
from html import escape
from .config import (
    MIN_SUMMARY_LENGTH, MAX_POSTS_PER_RUN, WORDPRESS_STATUS, load_yaml_config,
    COPY_FULL_ARTICLE, PARAPHRASE_ARTICLE, UPLOAD_FEATURED_IMAGE, INCLUDE_SOURCE_LINK,
    REQUIRE_IMAGE, MIN_PARAGRAPHS_FULL_ARTICLE
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


def build_full_content(item: dict, paragraphs: list[str]) -> str:
    blocks = []
    for p in paragraphs:
        if p.strip():
            blocks.append(f"<p>{escape(p.strip())}</p>")
    if INCLUDE_SOURCE_LINK:
        blocks.append("<hr />")
        blocks.append(f"<p><strong>Fuente original:</strong> {escape(item.get('source_name', 'Fuente'))}</p>")
        blocks.append(f'<p><a href="{escape(item["url"])}" target="_blank" rel="nofollow noopener">Ver publicación original</a></p>')
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

                # Regla de fecha desactivada: se permite publicar aunque no exista fecha verificable.

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
