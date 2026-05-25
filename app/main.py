from fastapi import FastAPI
from .database import init_db, latest
from .scheduler import start_scheduler, scheduled_job
from .publisher import run_once
from .wordpress import WordPressClient
from .config import RUN_ON_START, CHECK_INTERVAL_MINUTES, WORDPRESS_URL, WORDPRESS_STATUS

app = FastAPI(title="News Auto WordPress sin IA", version="1.0.0")


@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()
    if RUN_ON_START:
        # Ejecuta una revisión inicial al encender el hosting.
        scheduled_job()


@app.get("/")
def home():
    return {
        "status": "ok",
        "site": WORDPRESS_URL,
        "publish_status": WORDPRESS_STATUS,
        "check_interval_minutes": CHECK_INTERVAL_MINUTES,
        "message": "Automatizador de noticias activo",
    }


@app.post("/run-now")
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
    wp = WordPressClient()
    user = wp.test_connection()
    return {"connected": True, "wordpress_user": user.get("name"), "id": user.get("id")}
