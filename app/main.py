from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from .database import init_db, latest
from .scheduler import start_scheduler, scheduled_job
from .publisher import run_once
from .wordpress import WordPressClient
from .config import (
    RUN_ON_START, CHECK_INTERVAL_MINUTES, WORDPRESS_URL, WORDPRESS_STATUS,
    COPY_FULL_ARTICLE, PARAPHRASE_ARTICLE, UPLOAD_FEATURED_IMAGE, REQUIRE_IMAGE,
    MAX_ARTICLE_AGE_HOURS, DATE_FILTER_ENABLED, SMART_CLEAN_CONTENT, INCLUDE_SOURCE_LINK
)

app = FastAPI(title="News Auto WordPress Full", version="10.0.0")


@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()
    if RUN_ON_START:
        scheduled_job()


@app.api_route("/", methods=["GET", "HEAD"])
def home():
    data = {
        "status": "ok",
        "site": WORDPRESS_URL,
        "default_publish_status": WORDPRESS_STATUS,
        "check_interval_minutes": CHECK_INTERVAL_MINUTES,
        "copy_full_article": COPY_FULL_ARTICLE,
        "paraphrase_article": PARAPHRASE_ARTICLE,
        "upload_featured_image": UPLOAD_FEATURED_IMAGE,
        "require_image": REQUIRE_IMAGE,
        "date_filter_enabled": DATE_FILTER_ENABLED,
        "smart_clean_content": SMART_CLEAN_CONTENT,
        "include_source_link": INCLUDE_SOURCE_LINK,
        "tags_to_wordpress": True,
        "duplicate_protection": "url+title+slug+wordpress",
        "source_strategy": "round_robin",
        "html_entities_decoded": True,
        "utf8_global_cleaning": True,
        "mojibake_repair": True,
        "message": "Automatizador de noticias activo",
    }
    return data


@app.api_route("/run-now", methods=["GET", "POST"])
def run_now():
    return run_once()


@app.api_route("/run-now", methods=["HEAD"])
def run_now_head():
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
