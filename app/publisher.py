from __future__ import annotations
from html import escape
from .config import MIN_SUMMARY_LENGTH, MAX_POSTS_PER_RUN, WORDPRESS_STATUS, load_yaml_config
from .database import already_processed, mark_processed
from .feeds import read_feed
from .wordpress import WordPressClient


def choose_category(item: dict, cfg: dict) -> str:
    text = f"{item.get('title','')} {item.get('summary','')}".lower()
    for rule in cfg.get("category_rules", []):
        for kw in rule.get("keywords", []):
            if kw.lower() in text:
                return rule["category"]
    return item.get("default_category") or cfg.get("site", {}).get("default_category", "Nacional")


def build_content(item: dict, cfg: dict) -> str:
    site_cfg = cfg.get("site", {})
    summary = item.get("summary") or "Consulta la información completa en la fuente original."
    image_html = ""
    if site_cfg.get("include_external_image_in_content") and item.get("image"):
        image_html = f'<p><img src="{escape(item["image"])}" alt="{escape(item["title"])}" /></p>\n'
    template = site_cfg.get("post_template") or "<p>{summary}</p><p>Fuente: {source_name}</p><p>{original_url}</p>"
    content = template.format(
        title=escape(item["title"]),
        summary=escape(summary),
        source_name=escape(item.get("source_name", "Fuente original")),
        original_url=escape(item["url"]),
        published=escape(item.get("published", "")),
    )
    return image_html + content


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
            if len(item.get("summary", "")) < MIN_SUMMARY_LENGTH:
                skipped.append({"title": item["title"], "reason": "resumen muy corto"})
                continue

            try:
                category = choose_category(item, cfg)
                content = build_content(item, cfg)
                post = wp.create_post(
                    title=item["title"],
                    content=content,
                    category_name=category,
                    status=WORDPRESS_STATUS,
                    excerpt=item.get("summary", ""),
                )
                mark_processed(item["url"], item["title"], item.get("source_name", ""), post.get("id"))
                published.append({"title": item["title"], "category": category, "wp_id": post.get("id"), "link": post.get("link")})
            except Exception as exc:
                errors.append({"title": item["title"], "error": str(exc)})

    return {"published": published, "skipped": skipped[:20], "errors": errors}
