# News Auto WP V19 Render sin panel + autores por categoría

Versión diseñada para Render, sin panel visual.

## Funciones principales

- Publicación automática en WordPress.
- Categorías corregidas por `target_category`.
- Autores por categoría mediante `category_authors` en `config.yaml`.
- Endpoint `/api/wp-authors` para listar IDs de usuarios/autores de WordPress.
- Ejecución de todas las fuentes, por fuente o por categoría.
- Limpieza de contenido basura, UTF-8 y entidades HTML.
- Limpieza de `Al momento` y `Lee ahora:`.
- Imagen obligatoria y subida de imagen destacada.
- Control de duplicados por URL/título/slug/WordPress.

## Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Variables de entorno en Render

```env
WORDPRESS_URL=https://enriquevirgen.com
WORDPRESS_USER=TU_USUARIO_API
WORDPRESS_APP_PASSWORD=TU_APPLICATION_PASSWORD
WORDPRESS_STATUS=publish
RUN_ON_START=false
CHECK_INTERVAL_MINUTES=5
MAX_POSTS_PER_RUN=1
COPY_FULL_ARTICLE=true
PARAPHRASE_ARTICLE=true
PARAPHRASE_MODE=coherent
UPLOAD_FEATURED_IMAGE=true
REQUIRE_IMAGE=true
INCLUDE_SOURCE_LINK=false
SMART_CLEAN_CONTENT=true
DATE_FILTER_ENABLED=false
```

## Autores por categoría

Edita `config.yaml` en GitHub:

```yaml
category_authors:
  "Política": 4
  "Ciencia y Tecnología": 5
  "Policiaca": 6
  "Deportes": 7
  "Economía": 8
  "Nacional": 2
  "Internacional": 2
  "Sinaloa": 2
  "Clima": 2
  "Opinión": 2
```

El sistema usa este orden:

1. `author_id` de la fuente, si existe.
2. `category_authors[target_category]`.
3. Usuario conectado por la API de WordPress.

## Endpoints

- `/` estado general.
- `/run-now` ejecutar todo.
- `/api/run-now-background` ejecutar todo en segundo plano.
- `/api/run-source/{source_id}` ejecutar una fuente.
- `/api/run-category/{target_category}` ejecutar una categoría.
- `/api/wp-authors` listar autores/usuarios de WordPress.
- `/api/last-run` ver último proceso.
- `/api/sources` ver fuentes.
- `/latest` ver últimas procesadas.
- `/test-wordpress` probar conexión.
