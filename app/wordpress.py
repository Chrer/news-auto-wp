from __future__ import annotations
from pathlib import Path
from urllib.parse import urlparse
import requests
from requests.auth import HTTPBasicAuth
from slugify import slugify
from .config import WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_APP_PASSWORD, USER_AGENT, REQUEST_TIMEOUT


class WordPressClient:
    def __init__(self):
        if not WORDPRESS_USER or not WORDPRESS_APP_PASSWORD:
            raise RuntimeError("Faltan WORDPRESS_USER o WORDPRESS_APP_PASSWORD en variables de entorno")
        self.base = f"{WORDPRESS_URL}/wp-json/wp/v2"
        self.auth = HTTPBasicAuth(WORDPRESS_USER, WORDPRESS_APP_PASSWORD.replace(" ", ""))
        self.headers = {"User-Agent": USER_AGENT}

    def _request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base}/{endpoint.lstrip('/')}"
        resp = requests.request(method, url, auth=self.auth, headers=self.headers, timeout=REQUEST_TIMEOUT, **kwargs)
        if resp.status_code in (401, 403):
            raise RuntimeError(
                "WordPress rechazó la conexión. Revisa WORDPRESS_USER, WORDPRESS_APP_PASSWORD y permisos del usuario. "
                f"Código: {resp.status_code}. Respuesta: {resp.text[:300]}"
            )
        resp.raise_for_status()
        if not resp.text:
            return {}
        return resp.json()

    def get_or_create_category_id(self, name: str) -> int | None:
        if not name:
            return None
        slug = slugify(name)
        found = self._request("GET", "categories", params={"slug": slug, "per_page": 1})
        if found:
            return found[0]["id"]
        found = self._request("GET", "categories", params={"search": name, "per_page": 5})
        for category in found:
            if category.get("name", "").strip().lower() == name.strip().lower():
                return category["id"]
        created = self._request("POST", "categories", json={"name": name, "slug": slug})
        return created.get("id")

    def upload_media(self, image_url: str, alt_text: str = "") -> int | None:
        if not image_url:
            return None
        headers = {"User-Agent": USER_AGENT}
        img_resp = requests.get(image_url, headers=headers, timeout=REQUEST_TIMEOUT)
        img_resp.raise_for_status()
        content_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
        if not content_type.startswith("image/"):
            return None
        parsed = urlparse(image_url)
        filename = Path(parsed.path).name or "imagen-noticia.jpg"
        if "." not in filename:
            ext = content_type.split("/")[-1].replace("jpeg", "jpg")
            filename = f"imagen-noticia.{ext}"
        media_headers = {
            "User-Agent": USER_AGENT,
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type,
        }
        url = f"{self.base}/media"
        resp = requests.post(url, auth=self.auth, headers=media_headers, data=img_resp.content, timeout=60)
        if resp.status_code in (401, 403):
            raise RuntimeError("WordPress rechazó la subida de imagen. Revisa permisos para subir medios.")
        resp.raise_for_status()
        media = resp.json()
        media_id = media.get("id")
        if media_id and alt_text:
            try:
                self._request("POST", f"media/{media_id}", json={"alt_text": alt_text[:250]})
            except Exception:
                pass
        return media_id

    def create_post(self, title: str, content: str, category_name: str, status: str = "publish", excerpt: str | None = None, featured_media: int | None = None):
        category_id = self.get_or_create_category_id(category_name)
        payload = {
            "title": title,
            "content": content,
            "status": status,
            "slug": slugify(title)[:70],
        }
        if category_id:
            payload["categories"] = [category_id]
        if excerpt:
            payload["excerpt"] = excerpt[:250]
        if featured_media:
            payload["featured_media"] = featured_media
        return self._request("POST", "posts", json=payload)

    def test_connection(self):
        return self._request("GET", "users/me")
