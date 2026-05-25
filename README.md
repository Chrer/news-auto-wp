# News Auto WordPress V9 Estable

Versión corregida para el automatizador de noticias de `enriquevirgen.com`.

## Cambios principales

- Corrige entidades HTML como `&ntilde;` para publicar `ñ`, acentos y signos correctamente.
- No agrega bloque visible de fuente original dentro de la noticia.
- Extrae etiquetas y las agrega como etiquetas de WordPress, no dentro del texto.
- Mantiene imagen obligatoria: si no puede extraer/subir imagen, no publica esa noticia.
- Elimina El País del `config.yaml`.
- Desactiva filtro de fecha: no descarta por fecha antigua ni por falta de fecha verificable.
- Agrega protección fuerte de duplicados:
  - URL original,
  - URL canónica sin parámetros de tracking,
  - título normalizado,
  - slug local,
  - búsqueda en WordPress antes de publicar.
- Procesa fuentes en modo round-robin para no quedarse solo con una fuente.
- Devuelve `source_report` en `/run-now` para ver cuántas noticias encontró/publicó/saltó por fuente.
- Mantiene fallback de extracción para evitar errores de `0 párrafos`.
- Mantiene fallback de subida de imagen para evitar errores 406 comunes en hosting compartido.

## Variables recomendadas en Render

```env
WORDPRESS_URL=https://enriquevirgen.com
WORDPRESS_USER=qwerty123321
WORDPRESS_APP_PASSWORD=TU_APPLICATION_PASSWORD
WORDPRESS_STATUS=publish
RUN_ON_START=false
CHECK_INTERVAL_MINUTES=5
MAX_POSTS_PER_RUN=1
COPY_FULL_ARTICLE=true
PARAPHRASE_ARTICLE=true
UPLOAD_FEATURED_IMAGE=true
REQUIRE_IMAGE=true
DATE_FILTER_ENABLED=false
MAX_ARTICLE_AGE_HOURS=0
SKIP_UNDATED_ARTICLES=false
SMART_CLEAN_CONTENT=true
INCLUDE_SOURCE_LINK=false
MIN_PARAGRAPHS_FULL_ARTICLE=2
REQUEST_TIMEOUT=30
```

## Rutas

- `/` estado del sistema.
- `/test-wordpress` prueba conexión con WordPress.
- `/run-now` ejecuta revisión manual.
- `/latest` muestra últimos registros procesados.

## Deploy

1. Sube estos archivos a GitHub reemplazando los anteriores.
2. No subas `.env` con contraseñas reales.
3. En Render usa: `Manual Deploy → Clear build cache & deploy`.
4. Revisa `/` y confirma que muestre:
   - `duplicate_protection`
   - `source_strategy: round_robin`
   - `html_entities_decoded: true`

## V10 - Limpieza global UTF-8

Esta versión agrega una capa final de limpieza de caracteres antes de publicar:

- Decodifica entidades HTML repetidas: `&ntilde;`, `&aacute;`, `&amp;ntilde;`, etc.
- Repara mojibake común: `aÃ±o` → `año`, `â€œ` → `“`, `â€“` → `–`.
- Elimina caracteres invisibles y espacios raros: `\u200b`, `\ufeff`, `&nbsp;`, etc.
- Normaliza Unicode con NFC para evitar caracteres combinados extraños.
- Aplica limpieza a títulos, párrafos, extractos, etiquetas, slugs, alt text e imágenes.

En `/` debe verse:

```json
"utf8_global_cleaning": true,
"mojibake_repair": true
```
