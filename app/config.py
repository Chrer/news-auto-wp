import os
from pathlib import Path
from dotenv import load_dotenv
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


WORDPRESS_URL = os.getenv("WORDPRESS_URL", "https://enriquevirgen.com").rstrip("/")
WORDPRESS_USER = os.getenv("WORDPRESS_USER", "")
WORDPRESS_APP_PASSWORD = os.getenv("WORDPRESS_APP_PASSWORD", "")
WORDPRESS_STATUS = os.getenv("WORDPRESS_STATUS", "publish")

RUN_ON_START = env_bool("RUN_ON_START", False)
CHECK_INTERVAL_MINUTES = env_int("CHECK_INTERVAL_MINUTES", 5)
MAX_POSTS_PER_RUN = env_int("MAX_POSTS_PER_RUN", 8)
MIN_SUMMARY_LENGTH = env_int("MIN_SUMMARY_LENGTH", 20)
MIN_PARAGRAPHS_FULL_ARTICLE = env_int("MIN_PARAGRAPHS_FULL_ARTICLE", 3)

COPY_FULL_ARTICLE = env_bool("COPY_FULL_ARTICLE", True)
PARAPHRASE_ARTICLE = env_bool("PARAPHRASE_ARTICLE", True)
UPLOAD_FEATURED_IMAGE = env_bool("UPLOAD_FEATURED_IMAGE", True)
REQUIRE_IMAGE = env_bool("REQUIRE_IMAGE", True)
MAX_ARTICLE_AGE_HOURS = env_int("MAX_ARTICLE_AGE_HOURS", 0)  # 0 = filtro de fecha desactivado
SKIP_UNDATED_ARTICLES = env_bool("SKIP_UNDATED_ARTICLES", False)
DATE_FILTER_ENABLED = env_bool("DATE_FILTER_ENABLED", False)
INCLUDE_SOURCE_LINK = env_bool("INCLUDE_SOURCE_LINK", True)

USER_AGENT = os.getenv("USER_AGENT", "NewsAutoBot/3.0 (+https://enriquevirgen.com)")
REQUEST_TIMEOUT = env_int("REQUEST_TIMEOUT", 25)


def load_yaml_config() -> dict:
    path = BASE_DIR / "config.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
