from __future__ import annotations
import re
from bs4 import BeautifulSoup
from .text_utils import decode_entities

# Selectores comunes de bloques que no forman parte de la nota.
REMOVE_SELECTORS = [
    "script", "style", "noscript", "iframe", "svg", "form", "button", "input", "select",
    "nav", "header", "footer", "aside",
    ".sharedaddy", ".share", ".shares", ".social", ".social-share", ".share-buttons", ".addtoany_share_save_container",
    ".comments", "#comments", ".comment", ".comment-respond",
    ".related", ".related-posts", ".post-related", ".td-related-title", ".yarpp-related", ".jp-relatedposts",
    ".advertisement", ".ads", ".ad", ".ad-container", ".banner", ".publicidad", ".google-auto-placed",
    ".newsletter", ".subscribe", ".suscripcion", ".mailchimp", ".wp-block-jetpack-subscriptions",
    ".breadcrumb", ".breadcrumbs", ".author-box", ".byline", ".menu", ".sidebar", ".widget",
    ".wp-block-buttons", ".wp-block-button", ".wp-block-embed", ".embed", ".video-embed",
    ".tags", ".tagcloud", ".entry-tags", ".post-tags", ".cat-links",
    "[class*='advert']", "[id*='advert']", "[class*='ads']", "[id*='ads']",
    "[class*='share']", "[id*='share']", "[class*='social']", "[id*='social']",
    "[class*='related']", "[id*='related']", "[class*='newsletter']", "[id*='newsletter']",
]

# Frases que cortan/descartan bloques de basura.
BAD_PHRASES = [
    "lee también", "también lee", "leer también", "también te podría interesar", "te puede interesar", "te podría interesar",
    "te recomendamos", "notas relacionadas", "historias relacionadas", "más noticias", "mas noticias",
    "más información", "mas información", "contenido relacionado", "sigue leyendo",
    "publicidad", "anuncio", "contenido patrocinado", "patrocinado", "comunicado patrocinado",
    "síguenos", "siguenos", "google discover", "google search", "whatsapp", "telegram", "facebook", "instagram", "x.com", "twitter", "youtube", "tiktok",
    "suscríbete", "suscribete", "newsletter", "recibe las noticias", "boletín", "boletin", "activa las notificaciones",
    "comparte esta noticia", "comparte", "compartir", "haz clic", "da clic", "click aquí", "click aqui",
    "comentarios", "deja tu comentario", "iniciar sesión", "iniciar sesion", "registrarse", "cookie", "cookies",
    "todos los derechos reservados", "copyright", "fuente:", "leer nota completa", "ver publicación original",
    "acerca de nosotros", "luz noticias forma parte", "correo:", "teléfono:", "telefono:", "etiquetas:",
]

STOP_SECTION_PHRASES = [
    "te puede interesar", "te podría interesar", "también te podría interesar", "más noticias de", "mas noticias de",
    "notas relacionadas", "etiquetas:", "acerca de nosotros", "©", "derechos reservados",
]

BAD_LINE_PATTERNS = [
    r"^\s*(foto|imagen|crédito|credito|captura|cortesía|cortesia)\s*[:：-]",
    r"^\s*(redacción|redaccion|editorial)\s*[:：-]?\s*$",
    r"^\s*(local|nacional|internacional|policiaca|economía|economia|opinión|opinion|sinaloa|norte|sur|centro)\s*$",
    r"^\s*(mira también|lee además|además lee)\b",
    r"^\s*a-aa\+\s*$",
    r"^\s*[-–—•*]+\s*$",
]


def clean_spaces(text: str) -> str:
    return decode_entities(text or "")


def strip_junk_nodes(node) -> None:
    if not node:
        return
    for selector in REMOVE_SELECTORS:
        try:
            for bad in node.select(selector):
                bad.decompose()
        except Exception:
            continue


def should_stop_at(text: str) -> bool:
    low = clean_spaces(text).lower()
    return any(phrase in low for phrase in STOP_SECTION_PHRASES)


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
    # En H2/H3 se permiten subtítulos cortos.
    if tag_name == "p" and len(text) < 28:
        return True

    # Elimina texto con URLs o apariencia de navegación.
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


def clean_paragraphs(raw_paragraphs: list[str], title: str = "", allow_loose: bool = False) -> list[str]:
    cleaned = []
    for p in raw_paragraphs:
        p = clean_spaces(p)
        if not p:
            continue
        if should_stop_at(p):
            break
        if allow_loose:
            # Filtro más suave para fallback: elimina basura obvia, pero no borra párrafos reales.
            low = p.lower()
            if any(phrase in low for phrase in BAD_PHRASES):
                continue
            if len(p) < 28:
                continue
            cleaned.append(p)
        else:
            if looks_like_junk(p):
                continue
            cleaned.append(p)
    return dedupe_paragraphs(cleaned, title=title)


def extract_clean_text_blocks(node, title: str = "") -> list[str]:
    strip_junk_nodes(node)
    paragraphs: list[str] = []
    for tag in node.find_all(["p", "h2", "h3", "li"], recursive=True):
        links = tag.find_all("a")
        text = clean_spaces(tag.get_text(" ", strip=True))
        if not text:
            continue
        if should_stop_at(text):
            break
        if links and len(links) >= 2 and len(text) < 180:
            continue
        if looks_like_junk(text, tag.name):
            continue
        paragraphs.append(text)
    return dedupe_paragraphs(paragraphs, title=title)


def extract_loose_text_blocks(node, title: str = "") -> list[str]:
    """Fallback: usa p/h2/h3/li/div con filtro suave cuando el selector principal no funciona."""
    strip_junk_nodes(node)
    raw: list[str] = []
    for tag in node.find_all(["p", "h2", "h3", "li", "div"], recursive=True):
        # Evita divs enormes que contienen toda la página duplicada.
        text = clean_spaces(tag.get_text(" ", strip=True))
        if not text:
            continue
        if len(text) > 1200:
            continue
        if should_stop_at(text):
            break
        raw.append(text)
    return clean_paragraphs(raw, title=title, allow_loose=True)


def clean_html_fragment(html: str, title: str = "") -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    strip_junk_nodes(soup)
    return extract_clean_text_blocks(soup, title=title)
