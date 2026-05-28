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
    # Línea Directa suele incluir un bloque lateral/sección llamado "Al momento".
    # Estos selectores ayudan a quitarlo cuando aparece con clase o id descriptivo.
    "[class*='momento']", "[id*='momento']",
]

# Frases que cortan/descartan bloques de basura.
BAD_PHRASES = [
    "lee ahora", "lee ahora:", "lee ahora :", "lee también", "también lee", "leer también", "también te podría interesar", "te puede interesar", "te podría interesar",
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
    "lee ahora", "lee ahora:", "lee ahora :", "te puede interesar", "te podría interesar", "también te podría interesar", "más noticias de", "mas noticias de",
    "notas relacionadas", "etiquetas:", "acerca de nosotros", "©", "derechos reservados",
]

BAD_LINE_PATTERNS = [
    r"^\s*(foto|imagen|crédito|credito|captura|cortesía|cortesia)\s*[:：-]",
    r"^\s*(redacción|redaccion|editorial)\s*[:：-]?\s*$",
    r"^\s*(local|nacional|internacional|policiaca|economía|economia|opinión|opinion|sinaloa|norte|sur|centro)\s*$",
    r"^\s*(lee ahora|mira también|lee además|además lee)\b",
    r"^\s*al momento\s*$",
    r"^\s*a-aa\+\s*$",
    r"^\s*[-–—•*]+\s*$",
]


def clean_spaces(text: str) -> str:
    return decode_entities(text or "")




def _norm_for_junk(text: str) -> str:
    text = clean_spaces(text).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _link_count(node) -> int:
    try:
        return len(node.find_all("a"))
    except Exception:
        return 0


def _text_len(node) -> int:
    try:
        return len(clean_spaces(node.get_text(" ", strip=True)))
    except Exception:
        return 0


def remove_al_momento_sections(node) -> None:
    """Elimina el bloque 'Al momento' de Línea Directa sin tocar el cuerpo real de la nota.

    Estrategia:
    - Si hay clases/ids con 'momento', ya se eliminan por REMOVE_SELECTORS.
    - Si el encabezado visible dice exactamente 'Al momento', se sube a un contenedor cercano
      que tenga varios enlaces, típico de módulos laterales/listados de últimas noticias.
    - Si no hay contenedor claro, solo elimina el encabezado.
    """
    if not node:
        return
    try:
        candidates = node.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "span", "p", "div"])
    except Exception:
        return

    for tag in list(candidates):
        if not getattr(tag, "parent", None):
            continue
        own_text = _norm_for_junk(tag.get_text(" ", strip=True))
        if own_text != "al momento":
            continue

        container = tag
        # Sube pocos niveles buscando un módulo compacto con varias ligas.
        for _ in range(5):
            parent = container.parent
            if not parent or getattr(parent, "name", "") in {"body", "html", "article", "main"}:
                break
            parent_text_len = _text_len(parent)
            parent_links = _link_count(parent)
            class_id = " ".join(parent.get("class", []) if hasattr(parent, "get") else []) + " " + str(parent.get("id", "") if hasattr(parent, "get") else "")
            class_id = class_id.lower()

            if (
                parent_links >= 2
                and parent_text_len <= 7000
                and (
                    "momento" in class_id
                    or "ultim" in class_id
                    or "latest" in class_id
                    or "sidebar" in class_id
                    or "widget" in class_id
                    or "module" in class_id
                    or "bloque" in class_id
                    or "section" in class_id
                    or parent_links >= 4
                )
            ):
                container = parent
            else:
                break

        try:
            container.decompose()
        except Exception:
            try:
                tag.decompose()
            except Exception:
                pass


def remove_lee_ahora_sections(node) -> None:
    """Elimina bloques 'Lee ahora:' de Línea Directa y Luz Noticias.

    Muchas veces esta sección aparece como una línea con un enlace relacionado y el título
    de otra nota. Se elimina el contenedor cercano si parece módulo/enlace; si no, elimina
    la línea y el siguiente elemento corto relacionado.
    """
    if not node:
        return
    try:
        candidates = node.find_all(["p", "div", "span", "strong", "b", "h2", "h3", "h4", "li"])
    except Exception:
        return
    pattern = re.compile(r"^\s*(lee\s+ahora\s*:?)\s*$|^\s*lee\s+ahora\s*[:：]", re.I)
    for tag in list(candidates):
        if not getattr(tag, "parent", None):
            continue
        text = _norm_for_junk(tag.get_text(" ", strip=True))
        if not pattern.search(text):
            continue
        container = tag
        # Busca un contenedor pequeño con enlaces, típico de recomendación.
        for _ in range(4):
            parent = container.parent
            if not parent or getattr(parent, "name", "") in {"body", "html", "article", "main"}:
                break
            parent_text_len = _text_len(parent)
            parent_links = _link_count(parent)
            class_id = " ".join(parent.get("class", []) if hasattr(parent, "get") else []) + " " + str(parent.get("id", "") if hasattr(parent, "get") else "")
            class_id = class_id.lower()
            if parent_links >= 1 and parent_text_len <= 1200 and (
                "related" in class_id or "recomend" in class_id or "nota" in class_id or "link" in class_id or parent_links >= 1
            ):
                container = parent
            else:
                break
        try:
            # Si no se encontró contenedor claro, borra también el siguiente hermano corto.
            if container is tag:
                nxt = tag.find_next_sibling()
                if nxt and _text_len(nxt) < 350:
                    nxt.decompose()
            container.decompose()
        except Exception:
            try:
                tag.decompose()
            except Exception:
                pass

def strip_junk_nodes(node) -> None:
    if not node:
        return
    for selector in REMOVE_SELECTORS:
        try:
            for bad in node.select(selector):
                bad.decompose()
        except Exception:
            continue
    remove_al_momento_sections(node)
    remove_lee_ahora_sections(node)


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
