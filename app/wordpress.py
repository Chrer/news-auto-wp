from __future__ import annotations
from pathlib import Path
from urllib.parse import urlparse
import requests
import hashlib
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

    def get_or_create_tag_ids(self, names: list[str] | None) -> list[int]:
        ids: list[int] = []
        if not names:
            return ids
        seen: set[str] = set()
        for name in names[:12]:
            name = (name or "").strip()[:50]
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            slug = slugify(name)[:60]
            try:
                found = self._request("GET", "tags", params={"slug": slug, "per_page": 1})
                if found:
                    ids.append(found[0]["id"])
                    continue
                found = self._request("GET", "tags", params={"search": name, "per_page": 5})
                matched = None
                for tag in found:
                    if tag.get("name", "").strip().lower() == key:
                        matched = tag.get("id")
                        break
                if matched:
                    ids.append(matched)
                    continue
                created = self._request("POST", "tags", json={"name": name, "slug": slug})
                if created.get("id"):
                    ids.append(created["id"])
            except Exception:
                # Si no se pudo crear alguna etiqueta, no se detiene la publicación.
                continue
        return ids

    def upload_media(self, image_url: str, alt_text: str = "") -> int | None:
        """
        Descarga una imagen remota y la sube a WordPress.

        Esta versión evita errores 406 comunes en hosting compartido/ModSecurity:
        - no usa el nombre original de la imagen, porque a veces trae caracteres raros o querystrings;
        - normaliza el nombre del archivo;
        - agrega Accept;
        - intenta primero subida binaria estándar y luego multipart/form-data como respaldo.
        """
        if not image_url:
            return None

        image_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": WORDPRESS_URL,
        }

        img_resp = requests.get(image_url, headers=image_headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        img_resp.raise_for_status()

        content_type = (img_resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            return None

        if content_type in ("image/jpeg", "image/jpg"):
            ext = "jpg"
            content_type = "image/jpeg"
        elif content_type == "image/png":
            ext = "png"
        elif content_type == "image/webp":
            ext = "webp"
        elif content_type == "image/gif":
            ext = "gif"
        else:
            # Evita formatos problemáticos como svg/avif/heic si WordPress o el hosting los rechaza.
            return None

        image_bytes = img_resp.content
        if not image_bytes or len(image_bytes) < 500:
            return None

        file_hash = hashlib.sha1((image_url + str(len(image_bytes))).encode("utf-8")).hexdigest()[:12]
        filename = f"noticia-{file_hash}.{ext}"
        url = f"{self.base}/media"

        # Intento 1: subida binaria recomendada por WordPress REST API.
        media_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type,
        }

        resp = requests.post(
            url,
            auth=self.auth,
            headers=media_headers,
            data=image_bytes,
            timeout=90,
        )

        # Intento 2: algunos hostings bloquean el modo binario y aceptan multipart/form-data.
        if resp.status_code == 406:
            resp = requests.post(
                url,
                auth=self.auth,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                files={"file": (filename, image_bytes, content_type)},
                timeout=90,
            )

        if resp.status_code in (401, 403):
            raise RuntimeError(
                "WordPress rechazó la subida de imagen. Revisa permisos del usuario para subir medios. "
                f"Código: {resp.status_code}. Respuesta: {resp.text[:300]}"
            )

        if resp.status_code >= 400:
            raise RuntimeError(
                f"falló subida de imagen: {resp.status_code} {resp.reason} para {url}. "
                f"Respuesta WordPress: {resp.text[:500]}"
            )

        media = resp.json()
        media_id = media.get("id")
        if media_id and alt_text:
            try:
                self._request("POST", f"media/{media_id}", json={"alt_text": alt_text[:250]})
            except Exception:
                pass
        return media_id

    def create_post(self, title: str, content: str, category_name: str, status: str = "publish", excerpt: str | None = None, featured_media: int | None = None, tags: list[str] | None = None):
        category_id = self.get_or_create_category_id(category_name)
        tag_ids = self.get_or_create_tag_ids(tags)
        payload = {
            "title": title,
            "content": content,
            "status": status,
            "slug": slugify(title)[:70],
        }
        if category_id:
            payload["categories"] = [category_id]
        if tag_ids:
            payload["tags"] = tag_ids
        if excerpt:
            payload["excerpt"] = excerpt[:250]
        if featured_media:
            payload["featured_media"] = featured_media
        return self._request("POST", "posts", json=payload)

    def test_connection(self):
        return self._request("GET", "users/me")
