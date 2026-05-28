from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import JSONResponse, Response

from .config import (
    CHECK_INTERVAL_MINUTES,
    COPY_FULL_ARTICLE,
    DATE_FILTER_ENABLED,
    INCLUDE_SOURCE_LINK,
    MAX_ARTICLE_AGE_HOURS,
    PARAPHRASE_ARTICLE,
    PARAPHRASE_MODE,
    REQUIRE_IMAGE,
    RUN_ON_START,
    SMART_CLEAN_CONTENT,
    UPLOAD_FEATURED_IMAGE,
    WORDPRESS_STATUS,
    WORDPRESS_URL,
)
from .database import init_db, latest
from .publisher import run_once
from .scheduler import scheduled_job, start_scheduler
from .wordpress import WordPressClient
from .publisher import load_yaml_config, available_categories

app = FastAPI(title="News Auto WordPress Render API", version="19.0.0")

LAST_RUN = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "mode": None,
    "source_id": None,
    "target_category": None,
    "result": None,
    "error": None,
    "events": [],
    "current_step": None,
    "current_source": None,
    "current_title": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _push_event(event: dict):
    event = dict(event or {})
    event["time"] = _now()
    LAST_RUN["events"].append(event)
    LAST_RUN["events"] = LAST_RUN["events"][-150:]
    LAST_RUN["current_step"] = event.get("step") or LAST_RUN.get("current_step")
    if event.get("source"):
        LAST_RUN["current_source"] = event.get("source")
    if event.get("title"):
        LAST_RUN["current_title"] = event.get("title")


def _execute(source_id: Optional[str] = None, target_category: Optional[str] = None, mode: str = "all"):
    if LAST_RUN.get("running"):
        return {
            "status": "busy",
            "message": "Ya hay una revisión en ejecución. Consulta /api/last-run.",
            "last_run": LAST_RUN,
        }

    LAST_RUN.update(
        {
            "running": True,
            "started_at": _now(),
            "finished_at": None,
            "mode": mode,
            "source_id": source_id,
            "target_category": target_category,
            "result": None,
            "error": None,
            "events": [],
            "current_step": "iniciando",
            "current_source": None,
            "current_title": None,
        }
    )
    _push_event({"step": "iniciando", "mode": mode, "source_id": source_id, "target_category": target_category})

    try:
        result = run_once(source_id=source_id, target_category=target_category, progress_callback=_push_event)
        LAST_RUN["result"] = result
        _push_event(
            {
                "step": "finalizado",
                "published": len((result or {}).get("published", [])),
                "skipped": len((result or {}).get("skipped", [])),
                "errors": len((result or {}).get("errors", [])),
            }
        )
        return result
    except Exception as exc:
        LAST_RUN["error"] = str(exc)
        LAST_RUN["result"] = {"published": [], "skipped": [], "errors": [{"error": str(exc)}]}
        _push_event({"step": "error_general", "error": str(exc)})
        return LAST_RUN["result"]
    finally:
        LAST_RUN["running"] = False
        LAST_RUN["finished_at"] = _now()


def _execute_background(source_id: Optional[str] = None, target_category: Optional[str] = None, mode: str = "all"):
    _execute(source_id=source_id, target_category=target_category, mode=mode)


@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()
    if RUN_ON_START:
        scheduled_job()


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    if False:
        return Response(status_code=200)
    cfg = load_yaml_config()
    return {
        "status": "ok",
        "service": "news-auto-wp-render-api",
        "version": "19.0.0",
        "site": WORDPRESS_URL,
        "default_publish_status": WORDPRESS_STATUS,
        "check_interval_minutes": CHECK_INTERVAL_MINUTES,
        "copy_full_article": COPY_FULL_ARTICLE,
        "paraphrase_article": PARAPHRASE_ARTICLE,
        "paraphrase_mode": PARAPHRASE_MODE,
        "upload_featured_image": UPLOAD_FEATURED_IMAGE,
        "require_image": REQUIRE_IMAGE,
        "date_filter_enabled": DATE_FILTER_ENABLED,
        "smart_clean_content": SMART_CLEAN_CONTENT,
        "include_source_link": INCLUDE_SOURCE_LINK,
        "tags_to_wordpress": True,
        "duplicate_protection": "url+title+slug+wordpress",
        "source_strategy": "round_robin",
        "single_target_category_publish": True,
        "category_pipeline_fixed": True,
        "available_categories": available_categories(cfg),
        "web_panel": False,
        "render_optimized": True,
        "category_authors_enabled": True,
        "category_authors": cfg.get("category_authors", {}),
        "endpoints": {
            "run_all_sync": "/run-now",
            "run_all_background": "/api/run-now-background",
            "run_source_sync": "/api/run-source/{source_id}",
            "run_category_sync": "/api/run-category/{target_category}",
            "last_run": "/api/last-run",
            "latest": "/latest",
            "sources": "/api/sources",
            "test_wordpress": "/test-wordpress",
            "wp_authors": "/api/wp-authors",
            "health": "/health",
        },
        "message": "Automatizador de noticias activo para Render, sin panel visual.",
    }


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "healthy", "running": LAST_RUN.get("running"), "time": _now()}


@app.api_route("/run-now", methods=["GET", "POST"])
def run_now():
    """Ejecución sincrónica para cron-job.org o pruebas directas."""
    return _execute(mode="all")


@app.api_route("/run-now", methods=["HEAD"])
def run_now_head():
    return Response(status_code=200)


@app.api_route("/api/run-now-background", methods=["GET", "POST"])
def run_now_background(background_tasks: BackgroundTasks):
    if LAST_RUN.get("running"):
        return {"status": "busy", "message": "Ya hay una revisión en ejecución.", "last_run": LAST_RUN}
    background_tasks.add_task(_execute_background, None, None, "all-background")
    return {"status": "started", "message": "Revisión iniciada en segundo plano. Consulta /api/last-run."}


@app.api_route("/api/run-source/{source_id}", methods=["GET", "POST"])
def run_source(source_id: str):
    return _execute(source_id=source_id, mode="source")


@app.api_route("/api/run-category/{target_category}", methods=["GET", "POST"])
def run_category(target_category: str):
    return _execute(target_category=target_category, mode="category")


@app.api_route("/api/run-source-background/{source_id}", methods=["GET", "POST"])
def run_source_background(source_id: str, background_tasks: BackgroundTasks):
    if LAST_RUN.get("running"):
        return {"status": "busy", "message": "Ya hay una revisión en ejecución.", "last_run": LAST_RUN}
    background_tasks.add_task(_execute_background, source_id, None, "source-background")
    return {"status": "started", "source_id": source_id, "message": "Revisión de fuente iniciada en segundo plano."}


@app.api_route("/api/run-category-background/{target_category}", methods=["GET", "POST"])
def run_category_background(target_category: str, background_tasks: BackgroundTasks):
    if LAST_RUN.get("running"):
        return {"status": "busy", "message": "Ya hay una revisión en ejecución.", "last_run": LAST_RUN}
    background_tasks.add_task(_execute_background, None, target_category, "category-background")
    return {"status": "started", "target_category": target_category, "message": "Revisión de categoría iniciada en segundo plano."}


@app.api_route("/api/last-run", methods=["GET", "HEAD"])
def last_run():
    return LAST_RUN


@app.api_route("/api/sources", methods=["GET", "HEAD"])
def sources():
    cfg = load_yaml_config()
    return {"sources": cfg.get("sources", []), "available_categories": available_categories(cfg)}


@app.api_route("/api/wp-authors", methods=["GET"])
def wp_authors():
    try:
        wp = WordPressClient()
        return {"authors": wp.list_authors()}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "authors": [],
                "error": str(exc),
                "hint": "La Application Password debe pertenecer a un usuario con permiso para listar usuarios. Si falla, revisa manualmente los IDs en WordPress > Usuarios.",
            },
        )


@app.api_route("/api/wp-authors", methods=["HEAD"])
def wp_authors_head():
    return Response(status_code=200)


@app.api_route("/latest", methods=["GET", "HEAD"])
def latest_posts():
    return {
        "items": [
            {
                "title": row[0],
                "source": row[1],
                "original_url": row[2],
                "wordpress_post_id": row[3],
                "wordpress_status": row[4],
                "created_at": row[5],
            }
            for row in latest()
        ]
    }


@app.api_route("/test-wordpress", methods=["GET"])
def test_wordpress():
    try:
        wp = WordPressClient()
        user = wp.test_connection()
        return {"connected": True, "wordpress_user": user.get("name"), "id": user.get("id")}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"connected": False, "error": str(exc)})


@app.api_route("/test-wordpress", methods=["HEAD"])
def test_wordpress_head():
    return Response(status_code=200)
