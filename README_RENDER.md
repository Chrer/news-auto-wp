# News Auto WP V20 - Render sin panel

Versión optimizada para Render.

## Cambios V20

- Corrige categorías duplicadas por feeds generales.
- Detecta categoría real desde la URL de la noticia.
- Evita procesar la misma URL varias veces en una sola ejecución.
- Añade extractor especial para Luz Noticias y Línea Directa con fallback desde JSON/scripts.
- Mantiene autores por categoría (`category_authors`).
- Mantiene limpieza UTF-8, limpieza de basura, etiquetas como tags, imagen obligatoria y paráfrasis coherente.

## Endpoints

- `/` estado
- `/run-now` ejecutar todo
- `/api/run-category/{categoria}` ejecutar categoría
- `/api/run-source/{source_id}` ejecutar fuente
- `/api/last-run` ver proceso
- `/api/wp-authors` ver IDs de autores WordPress

## Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Las credenciales deben configurarse en Render > Environment. El archivo `.env` incluido es solo para referencia/local; no lo subas a repositorios públicos.
