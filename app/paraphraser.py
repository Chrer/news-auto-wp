from __future__ import annotations
import re
from .text_utils import clean_text_global

"""
Parafraseador local conservador.

Objetivo: mejorar variación sin perder coherencia.
No usa IA ni APIs. No cambia citas textuales, cifras, nombres propios ni orden lógico.
La estrategia es ligera:
- conserva el primer párrafo casi intacto;
- reemplaza conectores y verbos comunes solo fuera de comillas;
- evita modificar párrafos con muchas cifras o nombres propios;
- agrega transiciones suaves solo cuando el párrafo no inicia con conector;
- valida longitud para no publicar texto roto.
"""

REPLACEMENTS = [
    (r"\bseñaló\b", "indicó"),
    (r"\binformó\b", "dio a conocer"),
    (r"\bexplicó\b", "detalló"),
    (r"\bmanifestó\b", "expresó"),
    (r"\bafirmó\b", "aseguró"),
    (r"\bagregó\b", "añadió"),
    (r"\bde acuerdo con\b", "según"),
    (r"\bdebido a\b", "a causa de"),
    (r"\bpor lo que\b", "por ello"),
    (r"\bcon el objetivo de\b", "con la finalidad de"),
    (r"\bactualmente\b", "en la actualidad"),
    (r"\bademás\b", "también"),
]

OPENERS = [
    "En ese sentido, ",
    "Sobre este tema, ",
    "De igual manera, ",
    "Como parte de la información, ",
    "En relación con el caso, ",
]

CONNECTOR_STARTS = (
    "en ", "de ", "según", "como ", "además", "también", "por ", "sin ", "con ",
    "durante", "mientras", "tras", "después", "ante", "para", "al ", "la ", "el ", "los ", "las "
)

QUOTE_PATTERN = re.compile(r'("[^"]*"|“[^”]*”|«[^»]*»)')


def _looks_sensitive_to_change(text: str) -> bool:
    """Evita tocar párrafos donde una sustitución puede afectar precisión."""
    if len(re.findall(r"\d", text)) >= 6:
        return True
    # Muchos nombres propios seguidos: mejor no forzar cambios.
    proper_words = re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b", text)
    if len(proper_words) >= 8:
        return True
    return False


def _replace_outside_quotes(text: str) -> str:
    parts = QUOTE_PATTERN.split(text)
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        if QUOTE_PATTERN.fullmatch(part):
            out.append(part)
            continue
        new = part
        if not _looks_sensitive_to_change(new):
            for pattern, repl in REPLACEMENTS:
                new = re.sub(pattern, repl, new, flags=re.IGNORECASE)
        out.append(new)
    return "".join(out)


def _add_light_transition(p: str, index: int) -> str:
    if index < 2:
        return p
    if len(p) < 140:
        return p
    low = p.lower().strip()
    if low.startswith(CONNECTOR_STARTS):
        return p
    opener = OPENERS[index % len(OPENERS)]
    return opener + p[0].lower() + p[1:]


def _valid_after_change(original: str, changed: str) -> str:
    """Si el resultado parece dañado, conserva el original."""
    original = clean_text_global(original)
    changed = clean_text_global(changed)
    if not changed:
        return original
    # Si perdió demasiado texto, conserva original.
    if len(changed) < max(40, len(original) * 0.65):
        return original
    # Si quedaron caracteres sospechosos de plantillas/código, conserva original.
    if any(x in changed for x in ["{{", "}}", "undefined", "function(", "window."]):
        return original
    return changed


def paraphrase_paragraph(paragraph: str, index: int = 0, mode: str = "coherent") -> str:
    original = clean_text_global(paragraph)
    if not original:
        return ""
    if mode in ("off", "none", "false"):
        return original
    # Modo light: solo limpieza, casi sin cambios.
    if mode == "light":
        return original
    changed = _replace_outside_quotes(original)
    changed = _add_light_transition(changed, index)
    return _valid_after_change(original, changed)


def paraphrase_text(paragraphs: list[str], mode: str = "coherent") -> list[str]:
    result: list[str] = []
    for i, p in enumerate(paragraphs):
        cleaned = clean_text_global(p)
        if not cleaned:
            continue
        result.append(paraphrase_paragraph(cleaned, i, mode=mode))
    return result
