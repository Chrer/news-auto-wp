# News Auto WordPress V7

Sistema automático para fuentes propias/autorizadas.

## Cambios V7

- Elimina basura del artículo antes de publicar: publicidad, menús, redes sociales, newsletter, relacionados, botones, comentarios y bloques repetidos.
- Ya no agrega el bloque visible de “Fuente original” dentro de la nota.
- Extrae etiquetas del feed o del HTML y las crea/asigna como **etiquetas de WordPress**.
- Las etiquetas no se agregan como texto dentro de la publicación.
- Mantiene imagen obligatoria y corrección de subida de imagen 406.
- Sin filtro de fecha y sin fuentes de El País.

## Variables recomendadas

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
SKIP_UNDATED_ARTICLES=false
INCLUDE_SOURCE_LINK=false
SMART_CLEAN_CONTENT=true
```

## Rutas

- `/` estado del sistema
- `/test-wordpress` prueba conexión con WordPress
- `/run-now` ejecuta revisión manual
- `/latest` últimas publicaciones procesadas
