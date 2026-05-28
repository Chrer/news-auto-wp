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
from .text_utils import decode_entities, canonical_url, clean_text_global, safe_slug


def _split_categories(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace("|", ",").split(",")
    cleaned = []
    for cat in raw:
        cat = clean_text_global(str(cat)).strip()
        if cat and cat not in cleaned:
            cleaned.append(cat)
    return cleaned


def choose_categories(item: dict, cfg: dict) -> list[str]:
    """Publica en UNA categoría destino.

    La categoría de extracción controla de qué sección se lee contenido.
    La categoría destino controla dónde se publica en WordPress.
    Esta función evita el error de publicar una entrada en todas las categorías del panel.
    """
    return [normalize_target_category(item, cfg)]

def source_identifier(source: dict) -> str:
    return source.get("id") or safe_slug(source.get("name") or source.get("home_url") or "fuente")


def available_categories(cfg: dict) -> list[str]:
    cats = cfg.get("available_categories") or []
    if not cats:
        cats = [
            "Ciencia y Tecnología", "Clima", "Deportes", "Economía", "Internacional",
            "Nacional", "Opinión", "Policiaca", "Política", "Sinaloa"
        ]
    return [clean_text_global(str(c)).strip() for c in cats if clean_text_global(str(c)).strip()]


def infer_category_from_text(item: dict, cfg: dict) -> str | None:
    text = clean_text_global(" ".join([
        str(item.get("title") or ""),
        str(item.get("summary") or ""),
        " ".join([str(x) for x in (item.get("tags") or [])]),
        str(item.get("source_name") or ""),
        str(item.get("url") or ""),
    ])).lower()
    best = None
    best_score = 0
    for rule in cfg.get("category_rules", []) or []:
        cat = clean_text_global(str(rule.get("category") or "")).strip()
        score = 0
        for kw in rule.get("keywords", []) or []:
            kw = clean_text_global(str(kw)).lower().strip()
            if kw and kw in text:
                score += 1
        if score > best_score:
            best_score = score
            best = cat
    return best if best_score > 0 else None


def normalize_target_category(item: dict, cfg: dict) -> str:
    allowed = available_categories(cfg)
    allowed_map = {c.lower(): c for c in allowed}
    target = clean_text_global(str(item.get("target_category") or item.get("default_category") or "")).strip()
    # Si el destino viene vacío o raro, intenta inferirlo por palabras clave.
    if not target or target.lower() not in allowed_map:
        if cfg_bool(cfg, "infer_category_if_unclear", True):
            inferred = infer_category_from_text(item, cfg)
            if inferred:
                target = inferred
    if target.lower() in allowed_map:
        return allowed_map[target.lower()]
    default = clean_text_global(str(cfg.get("site", {}).get("default_category", "Nacional"))).strip()
    return allowed_map.get(default.lower(), default or "Nacional")

# Compatibilidad con versiones anteriores.
def choose_category(item: dict, cfg: dict) -> str:
    return choose_categories(item, cfg)[0]


def get_source_status(item: dict, cfg: dict) -> str:
    return item.get("source_status") or cfg.get("site", {}).get("default_status") or WORDPRESS_STATUS


def normalize_category_key(name: str) -> str:
    return clean_text_global(str(name or "")).strip().lower()


def choose_author_id(categories: list[str], item: dict, cfg: dict) -> int | None:
    """Elige autor de WordPress según la categoría destino.

    Prioridad:
    1. author_id definido directamente en la fuente.
    2. category_authors[target_category] en config.yaml.
    3. None: WordPress usará el usuario conectado por la API.
    """
    source_author = item.get("source_author_id") or item.get("author_id")
    if source_author:
        try:
            return int(source_author)
        except Exception:
            pass

    mapping = cfg.get("category_authors") or {}
    normalized = {normalize_category_key(k): v for k, v in mapping.items()}
    for category in categories or []:
        value = normalized.get(normalize_category_key(category))
        if value is not None and str(value).strip() != "":
            try:
                return int(value)
            except Exception:
                continue
    return None


def cfg_bool(cfg: dict, key: str, default: bool) -> bool:
    rules = cfg.get("runtime_rules", {}) or {}
    if key in rules:
        return bool(rules.get(key))
    return default


def cfg_str(cfg: dict, key: str, default: str) -> str:
    rules = cfg.get("runtime_rules", {}) or {}
    value = rules.get(key, default)
    return str(value if value is not None else default)


def cfg_int(cfg: dict, key: str, default: int) -> int:
    rules = cfg.get("runtime_rules", {}) or {}
    try:
        value = rules.get(key, default)
        return int(value) if value is not None else default
    except Exception:
        return default


def article_is_recent(published_dt: datetime | None, max_hours: int = 24, date_filter_enabled: bool | None = None) -> tuple[bool, str]:
    # En la versión estable el filtro de fecha está desactivado por defecto.
    active = DATE_FILTER_ENABLED if date_filter_enabled is None else date_filter_enabled
    if not active:
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
        if cfg_bool(cfg, "paraphrase_article", PARAPHRASE_ARTICLE):
            paragraphs = paraphrase_text(paragraphs, mode=cfg_str(cfg, "paraphrase_mode", "coherent"))
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


def run_once(source_id: str | None = None, target_category: str | None = None, progress_callback=None) -> dict:
    cfg = load_yaml_config()
    def progress(step: str, **data):
        if progress_callback:
            try:
                progress_callback({"step": step, **data})
            except Exception:
                pass
    progress("inicio", source_id=source_id, target_category=target_category)
    wp = WordPressClient()
    max_posts_per_run = cfg_int(cfg, "max_posts_per_run", MAX_POSTS_PER_RUN)
    require_image = cfg_bool(cfg, "require_image", REQUIRE_IMAGE)
    upload_featured_image = cfg_bool(cfg, "upload_featured_image", UPLOAD_FEATURED_IMAGE)
    published: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    source_report: dict[str, dict] = {}

    source_items: list[tuple[dict, list[dict]]] = []
    allowed_categories = available_categories(cfg)
    selected_source_id = safe_slug(source_id or "") if source_id else None
    selected_category = clean_text_global(target_category or "").lower() if target_category else None

    for source in cfg.get("sources", []):
        name = source.get("name", "Fuente")
        sid = source_identifier(source)
        source_target = clean_text_global(str(source.get("target_category") or source.get("category") or "")).lower()

        if selected_source_id and sid != selected_source_id:
            continue
        if selected_category and source_target != selected_category:
            continue

        try:
            progress("leyendo_fuente", source=name, source_id=sid, target_category=source.get("target_category") or source.get("category"), extraction_category=source.get("extraction_category"))
            items = read_feed(source)
            source_report[name] = {"id": sid, "extraction_category": source.get("extraction_category"), "target_category": source.get("target_category") or source.get("category"), "found": len(items), "published": 0, "skipped": 0, "errors": 0}
            progress("fuente_leida", source=name, found=len(items))
            source_items.append((source, items))
        except Exception as exc:
            source_report[name] = {"id": sid, "extraction_category": source.get("extraction_category"), "target_category": source.get("target_category") or source.get("category"), "found": 0, "published": 0, "skipped": 0, "errors": 1}
            progress("error_fuente", source=name, error=str(exc))
            errors.append({"source": name, "error": str(exc)})

    for source, item in interleave_sources(source_items):
        if len(published) >= max_posts_per_run:
            break
        source_name = item.get("source_name") or source.get("name", "Fuente")
        item["url"] = canonical_url(item.get("url"))
        item["title"] = clean_text_global(item.get("title"))
        item["summary"] = clean_text_global(item.get("summary"))
        if source.get("author_id") is not None:
            item["source_author_id"] = source.get("author_id")

        progress("revisando_noticia", source=source_name, title=item.get("title"), target_category=item.get("target_category"))
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
            categories = choose_categories(item, cfg)
            status = get_source_status(item, cfg)
            progress("extrayendo_articulo", source=source_name, title=item.get("title"), categories=categories)
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

            recent_ok, recent_reason = article_is_recent(published_dt, MAX_ARTICLE_AGE_HOURS, cfg_bool(cfg, "date_filter_enabled", DATE_FILTER_ENABLED))
            if not recent_ok:
                skipped.append({"title": title, "source": source_name, "reason": recent_reason})
                source_report[source_name]["skipped"] += 1
                continue

            media_id = None
            if upload_featured_image:
                if not image_url:
                    if require_image:
                        skipped.append({"title": title, "source": source_name, "reason": "sin imagen extraíble"})
                        source_report[source_name]["skipped"] += 1
                        continue
                else:
                    try:
                        progress("subiendo_imagen", source=source_name, title=title)
                        media_id = wp.upload_media(image_url, alt_text=title)
                    except Exception as exc:
                        if require_image:
                            skipped.append({"title": title, "source": source_name, "reason": f"falló subida de imagen: {exc}"})
                            source_report[source_name]["skipped"] += 1
                            continue
                        errors.append({"title": title, "source": source_name, "warning": f"imagen no subida: {exc}"})
                    if require_image and not media_id:
                        skipped.append({"title": title, "source": source_name, "reason": "imagen inválida o no descargable"})
                        source_report[source_name]["skipped"] += 1
                        continue

            author_id = choose_author_id(categories, item, cfg)
            progress("publicando_wordpress", source=source_name, title=title, categories=categories, status=status, author_id=author_id)
            post = wp.create_post(
                title=title,
                content=content,
                category_name=categories,
                status=status,
                excerpt=item.get("summary", ""),
                featured_media=media_id,
                tags=item.get("tags") or [],
                author_id=author_id,
            )
            mark_processed(item["url"], title, source_name, post.get("id"), status)
            source_report[source_name]["published"] += 1
            progress("publicada", source=source_name, title=title, categories=categories, wp_id=post.get("id"), author_id=author_id)
            published.append({
                "title": title,
                "source": source_name,
                "categories": categories,
                "status": status,
                "wp_id": post.get("id"),
                "link": post.get("link"),
                "featured_media": media_id,
                "author_id": author_id,
            })
        except Exception as exc:
            progress("error_noticia", source=source_name, title=item.get("title"), error=str(exc))
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
            "La categoría de extracción y la categoría destino están separadas. No se asignan todas las categorías del panel.",
            f"Categorías válidas: {', '.join(allowed_categories)}",
            "Autores por categoría activos mediante category_authors en config.yaml. Prioridad: source.author_id > category_authors > usuario API.",
            "Puede ejecutarse todo, una fuente específica o una categoría destino específica desde API/cron.",
        ],
    }
