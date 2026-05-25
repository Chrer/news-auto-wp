from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .database import init_db, latest
from .scheduler import start_scheduler, scheduled_job
from .publisher import run_once
from .wordpress import WordPressClient
from .config import (
    RUN_ON_START, CHECK_INTERVAL_MINUTES, WORDPRESS_URL, WORDPRESS_STATUS,
    COPY_FULL_ARTICLE, PARAPHRASE_ARTICLE, UPLOAD_FEATURED_IMAGE
)

app = FastAPI(title="News Auto WordPress Full", version="2.0.0")


@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()
    if RUN_ON_START:
        scheduled_job()


@app.get("/")
def home():
    return {
        "status": "ok",
        "site": WORDPRESS_URL,
        "publish_status": WORDPRESS_STATUS,
        "check_interval_minutes": CHECK_INTERVAL_MINUTES,
        "copy_full_article": COPY_FULL_ARTICLE,
        "paraphrase_article": PARAPHRASE_ARTICLE,
        "upload_featured_image": UPLOAD_FEATURED_IMAGE,
        "message": "Automatizador de noticias activo",
    }


@app.api_route("/run-now", methods=["GET", "POST"])
def run_now():
    return run_once()


@app.get("/latest")
def latest_posts():
    return {
        "items": [
            {
                "title": row[0],
                "source": row[1],
                "original_url": row[2],
                "wordpress_post_id": row[3],
                "created_at": row[4],
            }
            for row in latest()
        ]
    }


@app.get("/test-wordpress")
def test_wordpress():
    try:
        wp = WordPressClient()
        user = wp.test_connection()
        return {"connected": True, "wordpress_user": user.get("name"), "id": user.get("id")}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"connected": False, "error": str(exc)})
