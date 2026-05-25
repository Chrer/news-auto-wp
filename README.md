# News Auto WordPress Full

Sistema automático para sitios propios/autorizados. Lee feeds, abre cada nota, extrae el cuerpo completo, aplica una paráfrasis básica sin API de IA, sube la imagen destacada a WordPress y publica automáticamente.

## Importante
Usa este modo solamente con sitios tuyos o con autorización para reutilizar contenido e imágenes.

## Variables de entorno en Render

```env
WORDPRESS_URL
WORDPRESS_USER=
WORDPRESS_APP_PASSWORD=TU_APPLICATION_PASSWORD
WORDPRESS_STATUS=publish
RUN_ON_START=true
CHECK_INTERVAL_MINUTES=30
MAX_POSTS_PER_RUN=8
COPY_FULL_ARTICLE=true
PARAPHRASE_ARTICLE=true
UPLOAD_FEATURED_IMAGE=true
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
- `/run-now` ejecuta revisión manual. Acepta GET y POST.
- `/latest` últimas notas procesadas.

## Qué cambió en esta versión

- `/run-now` funciona desde navegador.
- Mensajes de error de WordPress más claros.
- Extrae cuerpo completo de la nota desde el HTML.
- Paráfrasis básica sin API de IA.
- Extrae imagen OpenGraph o primera imagen del artículo.
- Sube la imagen a WordPress y la asigna como imagen destacada.
