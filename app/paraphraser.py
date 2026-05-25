from __future__ import annotations
import re
from .text_utils import clean_text_global

REPLACEMENTS = [
    (r"\bseñaló\b", "indicó"),
    (r"\binformó\b", "dio a conocer"),
    (r"\bexplicó\b", "detalló"),
    (r"\bde acuerdo con\b", "según"),
    (r"\bmanifestó\b", "expresó"),
    (r"\bafirmó\b", "aseguró"),
    (r"\bagregó\b", "añadió"),
    (r"\bdebido a\b", "a causa de"),
    (r"\bpor lo que\b", "por ello"),
    (r"\bactualmente\b", "en la actualidad"),
    (r"\bademás\b", "también"),
    (r"\btras\b", "después de"),
    (r"\bantes de\b", "previo a"),
    (r"\bcon el objetivo de\b", "con la finalidad de"),
]

OPENERS = [
    "En este contexto, ",
    "De acuerdo con la información disponible, ",
    "Como parte de los datos reportados, ",
    "Sobre este tema, ",
    "En relación con el caso, ",
]


def _replace_outside_quotes(text: str) -> str:
    parts = re.split(r'("[^"]*"|“[^”]*”|«[^»]*»)', text)
    out = []
    for part in parts:
        if not part:
            continue
        if part.startswith(('"', '“', '«')):
            out.append(part)
            continue
        new = part
        for pattern, repl in REPLACEMENTS:
            new = re.sub(pattern, repl, new, flags=re.IGNORECASE)
        out.append(new)
    return "".join(out)


def paraphrase_paragraph(paragraph: str, index: int = 0) -> str:
    p = clean_text_global(paragraph)
    if not p:
        return ""
    p = _replace_outside_quotes(p)
    if index > 0 and len(p) > 120 and not p.lower().startswith(("en ", "de ", "según", "como ")):
        p = OPENERS[index % len(OPENERS)] + p[0].lower() + p[1:]
    return p


def paraphrase_text(paragraphs: list[str]) -> list[str]:
    return [clean_text_global(paraphrase_paragraph(p, i)) for i, p in enumerate(paragraphs) if clean_text_global(p)]
