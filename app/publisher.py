from __future__ import annotations
from html import escape
from .config import (
    MIN_SUMMARY_LENGTH, MAX_POSTS_PER_RUN, WORDPRESS_STATUS, load_yaml_config,
    COPY_FULL_ARTICLE, PARAPHRASE_ARTICLE, UPLOAD_FEATURED_IMAGE, INCLUDE_SOURCE_LINK
)
from .database import already_processed, mark_processed
from .feeds import read_feed
from .article import fetch_full_article
from .paraphraser import paraphrase_text
from .wordpress import WordPressClient


def choose_category(item: dict, cfg: dict) -> str:
    text = f"{item.get('title','')} {item.get('summary','')}".lower()
    for rule in cfg.get("category_rules", []):
        for kw in rule.get("keywords", []):
            if kw.lower() in text:
                return rule["category"]
    return item.get("default_category") or cfg.get("site", {}).get("default_category", "Nacional")


def build_full_content(item: dict, paragraphs: list[str]) -> str:
    blocks = []
    for p in paragraphs:
        if p.strip():
            blocks.append(f"<p>{escape(p.strip())}</p>")
    if INCLUDE_SOURCE_LINK:
        blocks.append("<hr />")
        blocks.append(f"<p><strong>Fuente original:</strong> {escape(item.get('source_name', 'Fuente'))}</p>")
        blocks.append(f'<p><a href="{escape(item["url"])}" target="_blank" rel="nofollow noopener">Ver publicación original</a></p>')
    return "
".join(blocks)


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


def prepare_item_content(item: dict, cfg: dict) -> tuple[str, str, str | None]:
    """Regresa title, content, image_url."""
    image_url = item.get("image")
    if COPY_FULL_ARTICLE:
        article = fetch_full_article(item["url"])
        if article.get("title"):
            item["title"] = article["title"]
        if article.get("description") and not item.get("summary"):
            item["summary"] = article["description"]
        if article.get("image"):
            image_url = article["image"]
        paragraphs = article.get("paragraphs") or []
        if PARAPHRASE_ARTICLE:
            paragraphs = paraphrase_text(paragraphs)
        if paragraphs:
            return item["title"], build_full_content(item, paragraphs), image_url
    return item["title"], build_summary_content(item, cfg), image_url


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
                title, content, image_url = prepare_item_content(item, cfg)
                media_id = None
                image_error = None
                if UPLOAD_FEATURED_IMAGE and image_url:
                    try:
                        media_id = wp.upload_media(image_url, alt_text=title)
                    except Exception as exc:
                        image_error = str(exc)
                post = wp.create_post(
                    title=title,
                    content=content,
                    category_name=category,
                    status=WORDPRESS_STATUS,
                    excerpt=item.get("summary", ""),
                    featured_media=media_id,
                )
                mark_processed(item["url"], title, item.get("source_name", ""), post.get("id"))
                published_item = {"title": title, "category": category, "wp_id": post.get("id"), "link": post.get("link"), "featured_media": media_id}
                if image_error:
                    published_item["image_warning"] = image_error
                published.append(published_item)
            except Exception as exc:
                errors.append({"title": item.get("title"), "url": item.get("url"), "error": str(exc)})

    return {"published": published, "skipped": skipped[:20], "errors": errors}
