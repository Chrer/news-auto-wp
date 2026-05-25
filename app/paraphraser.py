from __future__ import annotations
import re

REPLACEMENTS = [
    (r"señaló", "indicó"),
    (r"informó", "dio a conocer"),
    (r"explicó", "detalló"),
    (r"de acuerdo con", "según"),
    (r"manifestó", "expresó"),
    (r"afirmó", "aseguró"),
    (r"agregó", "añadió"),
    (r"debido a", "a causa de"),
    (r"por lo que", "por ello"),
    (r"actualmente", "en la actualidad"),
    (r"además", "también"),
    (r"tras", "después de"),
    (r"antes de", "previo a"),
    (r"con el objetivo de", "con la finalidad de"),
]

OPENERS = [
    "En este contexto, ",
    "De acuerdo con la información disponible, ",
    "Como parte de los datos reportados, ",
    "Sobre este tema, ",
    "En relación con el caso, ",
]


def _replace_outside_quotes(text: str) -> str:
    # Evita modificar citas entre comillas dobles o latinas.
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
    p = paragraph.strip()
    if not p:
        return ""
    p = _replace_outside_quotes(p)
    # Cambia un poco la estructura en párrafos largos, sin tocar cifras/nombres.
    if index > 0 and len(p) > 120 and not p.lower().startswith(("en ", "de ", "según", "como ")):
        p = OPENERS[index % len(OPENERS)] + p[0].lower() + p[1:]
    return p


def paraphrase_text(paragraphs: list[str]) -> list[str]:
    return [paraphrase_paragraph(p, i) for i, p in enumerate(paragraphs) if p.strip()]
