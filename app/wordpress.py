from __future__ import annotations
import requests
from requests.auth import HTTPBasicAuth
from slugify import slugify
from .config import WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_APP_PASSWORD, USER_AGENT


class WordPressClient:
    def __init__(self):
        if not WORDPRESS_USER or not WORDPRESS_APP_PASSWORD:
            raise RuntimeError("Faltan WORDPRESS_USER o WORDPRESS_APP_PASSWORD en .env")
        self.base = f"{WORDPRESS_URL}/wp-json/wp/v2"
        self.auth = HTTPBasicAuth(WORDPRESS_USER, WORDPRESS_APP_PASSWORD.replace(" ", ""))
        self.headers = {"User-Agent": USER_AGENT}

    def _request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base}/{endpoint.lstrip('/')}"
        resp = requests.request(method, url, auth=self.auth, headers=self.headers, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_or_create_category_id(self, name: str) -> int | None:
        if not name:
            return None
        slug = slugify(name)
        found = self._request("GET", "categories", params={"slug": slug, "per_page": 1})
        if found:
            return found[0]["id"]
        # Fallback: search by visible name
        found = self._request("GET", "categories", params={"search": name, "per_page": 5})
        for category in found:
            if category.get("name", "").strip().lower() == name.strip().lower():
                return category["id"]
        created = self._request("POST", "categories", json={"name": name, "slug": slug})
        return created.get("id")

    def create_post(self, title: str, content: str, category_name: str, status: str = "publish", excerpt: str | None = None):
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
        return self._request("POST", "posts", json=payload)

    def test_connection(self):
        return self._request("GET", "users/me")
