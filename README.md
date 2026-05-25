# News Auto WordPress V3

Sistema automático para WordPress con extracción de artículo completo para fuentes autorizadas, paráfrasis básica sin API de IA, imagen destacada obligatoria y estados por fuente.

## Reglas incluidas

- Solo procesa noticias publicadas hace menos de 24 horas.
- Si no puede extraer o subir imagen, no publica esa noticia y busca otra.
- Publica inmediatamente cada noticia válida durante la revisión.
- Las fuentes con `status: publish` se publican directo.
- Las fuentes con `status: draft`, como El País, se guardan como borrador.
- `/run-now` funciona con GET, POST y HEAD.

## Variables en Render

```env
WORDPRESS_URL=
WORDPRESS_USER=
WORDPRESS_APP_PASSWORD=TU_APPLICATION_PASSWORD
WORDPRESS_STATUS=publish
RUN_ON_START=false
CHECK_INTERVAL_MINUTES=5
MAX_POSTS_PER_RUN=8
COPY_FULL_ARTICLE=true
PARAPHRASE_ARTICLE=true
UPLOAD_FEATURED_IMAGE=true
REQUIRE_IMAGE=true
MAX_ARTICLE_AGE_HOURS=24
SKIP_UNDATED_ARTICLES=true
INCLUDE_SOURCE_LINK=true
```

## Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Rutas

- `/` estado del sistema.
- `/test-wordpress` prueba conexión con WordPress.
- `/run-now` ejecuta revisión manual.
- `/latest` últimas notas procesadas.
