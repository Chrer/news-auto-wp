from __future__ import annotations
import html
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from slugify import slugify

TRACKING_PARAMS_PREFIXES = ("utm_",)
TRACKING_PARAMS = {"fbclid", "gclid", "wbraid", "gbraid", "mc_cid", "mc_eid", "spm", "ref", "ref_src"}

# Reemplazos comunes de mojibake UTF-8/Windows-1252 que aparecen cuando una web declara mal su encoding.
MOJIBAKE_REPLACEMENTS = {
    "Ã¡": "á", "Ã©": "é", "Ã­": "í", "Ã³": "ó", "Ãº": "ú", "Ã±": "ñ", "Ã¼": "ü",
    "Ã": "Á", "Ã‰": "É", "Ã": "Í", "Ã“": "Ó", "Ãš": "Ú", "Ã‘": "Ñ", "Ãœ": "Ü",
    "Â¿": "¿", "Â¡": "¡", "Â°": "°", "Âº": "º", "Âª": "ª", "Â·": "·", "Â": "",
    "â€œ": "“", "â€": "”", "â€˜": "‘", "â€™": "’", "â€š": "‚", "â€˜": "‘",
    "â€“": "–", "â€”": "—", "â€¦": "…", "â€¢": "•", "â„¢": "™", "â‚¬": "€",
    "�": "",
}

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
WEIRD_SPACES = {
    "\xa0": " ", "\u1680": " ", "\u180e": " ", "\u2000": " ", "\u2001": " ", "\u2002": " ",
    "\u2003": " ", "\u2004": " ", "\u2005": " ", "\u2006": " ", "\u2007": " ", "\u2008": " ",
    "\u2009": " ", "\u200a": " ", "\u202f": " ", "\u205f": " ", "\u3000": " ",
}


def _fix_mojibake(text: str) -> str:
    if not text:
        return ""
    value = text
    # Intento conservador: solo intenta latin1->utf8 si hay señales claras de mojibake.
    if any(marker in value for marker in ("Ã", "Â", "â€", "â€“", "â€”", "â€¦")):
        try:
            candidate = value.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            # Acepta el candidato si reduce marcadores sospechosos y conserva suficiente texto.
            bad_before = sum(value.count(m) for m in ("Ã", "Â", "â"))
            bad_after = sum(candidate.count(m) for m in ("Ã", "Â", "â"))
            if candidate and len(candidate) >= max(4, int(len(value) * 0.65)) and bad_after <= bad_before:
                value = candidate
        except Exception:
            pass
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        value = value.replace(bad, good)
    return value


def clean_text_global(value: str | None, *, single_line: bool = True) -> str:
    """Limpieza global final para texto antes de publicarlo.

    Corrige entidades HTML (&ntilde;), mojibake frecuente (aÃ±o), caracteres invisibles,
    espacios raros y normaliza Unicode a NFC. Es segura para títulos, párrafos, etiquetas,
    extractos, slugs y nombres de archivo.
    """
    if value is None:
        return ""
    text = str(value)

    # Decodifica entidades HTML repetidas: &amp;ntilde; -> &ntilde; -> ñ.
    for _ in range(4):
        new = html.unescape(text)
        if new == text:
            break
        text = new

    text = _fix_mojibake(text)
    text = unicodedata.normalize("NFC", text)

    for bad, good in WEIRD_SPACES.items():
        text = text.replace(bad, good)
    text = ZERO_WIDTH_RE.sub("", text)
    text = CONTROL_CHARS_RE.sub("", text)

    # Normaliza comillas/guiones sin perder signos del español.
    text = text.replace("´", "'").replace("`", "'")
    text = text.replace("﹘", "-").replace("－", "-")

    if single_line:
        text = re.sub(r"\s+", " ", text).strip()
    else:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def decode_entities(value: str | None) -> str:
    return clean_text_global(value, single_line=True)


def clean_spaces(value: str | None) -> str:
    return clean_text_global(value, single_line=True)


def clean_paragraph_text(value: str | None) -> str:
    return clean_text_global(value, single_line=False)


def clean_tag_name(value: str | None) -> str:
    text = clean_text_global(value, single_line=True)
    text = re.sub(r"^[#\s]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;|/")
    return text[:50]


def canonical_url(url: str | None) -> str:
    if not url:
        return ""
    url = clean_text_global(url, single_line=True)
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query_pairs = []
    for k, v in parse_qsl(parts.query, keep_blank_values=False):
        kl = k.lower()
        if kl in TRACKING_PARAMS or any(kl.startswith(prefix) for prefix in TRACKING_PARAMS_PREFIXES):
            continue
        query_pairs.append((k, v))
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def title_key(title: str | None) -> str:
    text = clean_text_global(title, single_line=True).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9ñ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:220]


def safe_slug(title: str | None) -> str:
    slug = slugify(clean_text_global(title, single_line=True))[:70].strip("-")
    return slug or "noticia"
