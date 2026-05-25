from __future__ import annotations
import re
from bs4 import BeautifulSoup

# Selectores comunes de bloques que no forman parte de la nota.
REMOVE_SELECTORS = [
    "script", "style", "noscript", "iframe", "svg", "form", "button", "input", "select",
    "nav", "header", "footer", "aside",
    ".sharedaddy", ".share", ".shares", ".social", ".social-share", ".share-buttons", ".addtoany_share_save_container",
    ".comments", "#comments", ".comment", ".comment-respond",
    ".related", ".related-posts", ".post-related", ".td-related-title", ".yarpp-related", ".jp-relatedposts",
    ".advertisement", ".ads", ".ad", ".ad-container", ".banner", ".publicidad", ".google-auto-placed",
    ".newsletter", ".subscribe", ".suscripcion", ".mailchimp", ".wp-block-jetpack-subscriptions",
    ".breadcrumb", ".breadcrumbs", ".author-box", ".author", ".byline", ".menu", ".sidebar", ".widget",
    ".wp-block-buttons", ".wp-block-button", ".wp-block-embed", ".embed", ".video-embed",
    ".tags", ".tagcloud", ".entry-tags", ".post-tags", ".cat-links",
    "[class*='advert']", "[id*='advert']", "[class*='ads']", "[id*='ads']",
    "[class*='share']", "[id*='share']", "[class*='social']", "[id*='social']",
    "[class*='related']", "[id*='related']", "[class*='newsletter']", "[id*='newsletter']",
]

BAD_PHRASES = [
    "lee también", "también lee", "leer también", "te puede interesar", "te recomendamos", "notas relacionadas",
    "historias relacionadas", "más noticias", "más información", "contenido relacionado", "sigue leyendo",
    "publicidad", "anuncio", "contenido patrocinado", "patrocinado", "comunicado patrocinado",
    "síguenos", "siguenos", "whatsapp", "telegram", "facebook", "instagram", "x.com", "twitter", "youtube", "tiktok",
    "suscríbete", "suscribete", "newsletter", "recibe las noticias", "boletín", "boletin", "activa las notificaciones",
    "comparte esta noticia", "comparte", "compartir", "haz clic", "da clic", "click aquí", "click aqui",
    "comentarios", "deja tu comentario", "iniciar sesión", "iniciar sesion", "registrarse", "cookie", "cookies",
    "todos los derechos reservados", "copyright", "fuente:", "leer nota completa", "ver publicación original",
]

BAD_LINE_PATTERNS = [
    r"^\s*(foto|imagen|crédito|credito|captura|cortesía|cortesia)\s*[:：-]",
    r"^\s*(redacción|redaccion|editorial)\s*[:：-]?\s*$",
    r"^\s*(local|nacional|internacional|policiaca|economía|economia|opinión|opinion)\s*$",
    r"^\s*(mira también|lee además|además lee)\b",
    r"^\s*[-–—•]+\s*$",
]


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def strip_junk_nodes(node) -> None:
    if not node:
        return
    for selector in REMOVE_SELECTORS:
        try:
            for bad in node.select(selector):
                bad.decompose()
        except Exception:
            continue


def looks_like_junk(text: str, tag_name: str = "p") -> bool:
    text = clean_spaces(text)
    if not text:
        return True
    low = text.lower()

    if any(phrase in low for phrase in BAD_PHRASES):
        return True

    for pattern in BAD_LINE_PATTERNS:
        if re.search(pattern, low, flags=re.I):
            return True

    # Líneas demasiado cortas normalmente son botones, menús o etiquetas sueltas.
    if tag_name == "p" and len(text) < 35:
        return True

    # Elimina texto con demasiadas URLs o apariencia de navegación.
    if low.count("http") >= 1 or low.count("www.") >= 1:
        return True

    words = re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ]+", text)
    if len(words) <= 4 and tag_name in {"p", "li", "div"}:
        return True

    # Elimina líneas con exceso de símbolos típicas de botones o widgets.
    symbol_count = len(re.findall(r"[|•·→»#@]", text))
    if symbol_count >= 3 and len(words) < 18:
        return True

    return False


def dedupe_paragraphs(paragraphs: list[str], title: str = "") -> list[str]:
    title_key = clean_spaces(title).lower()
    seen: set[str] = set()
    clean: list[str] = []
    for p in paragraphs:
        p = clean_spaces(p)
        if not p:
            continue
        key = re.sub(r"\W+", " ", p.lower()).strip()
        if not key or key in seen:
            continue
        if title_key and key == re.sub(r"\W+", " ", title_key).strip():
            continue
        seen.add(key)
        clean.append(p)
    return clean


def clean_paragraphs(raw_paragraphs: list[str], title: str = "") -> list[str]:
    cleaned = []
    for p in raw_paragraphs:
        p = clean_spaces(p)
        if looks_like_junk(p):
            continue
        cleaned.append(p)
    return dedupe_paragraphs(cleaned, title=title)


def extract_clean_text_blocks(node, title: str = "") -> list[str]:
    strip_junk_nodes(node)
    paragraphs: list[str] = []
    for tag in node.find_all(["p", "h2", "h3", "li"], recursive=True):
        # descarta nodos que solo son links/botones
        links = tag.find_all("a")
        text = clean_spaces(tag.get_text(" ", strip=True))
        if not text:
            continue
        if links and len(links) >= 2 and len(text) < 180:
            continue
        if looks_like_junk(text, tag.name):
            continue
        paragraphs.append(text)
    return dedupe_paragraphs(paragraphs, title=title)


def clean_html_fragment(html: str, title: str = "") -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    strip_junk_nodes(soup)
    return extract_clean_text_blocks(soup, title=title)
