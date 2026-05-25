# News Auto WordPress V6

Versión combinada: elimina El País, desactiva el filtro de fecha y conserva el arreglo para subida de imágenes 406.

## Reglas incluidas

- No descarta por fecha.
- No descarta por “sin fecha de publicación verificable”.
- No incluye fuentes de El País.
- Si no puede extraer o subir imagen, no publica esa noticia y busca otra.
- Copia/parafrasea el artículo completo de las fuentes configuradas.
- `/run-now` funciona con GET y POST.

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
INCLUDE_SOURCE_LINK=true
```

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
