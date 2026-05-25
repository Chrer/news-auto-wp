# News Auto WordPress sin IA

Sistema automático para leer noticias desde RSS o feeds detectados, crear entradas cortas con fuente original y publicarlas directamente en WordPress.

## Importante
Este sistema no usa API de IA. Publica título, resumen del feed, fuente y enlace original. No copia el cuerpo completo de la noticia.

## Instalación local

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y coloca tu Application Password de WordPress.

## Ejecutar

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abre:

```text
http://localhost:8000
```

## Publicación automática

Por defecto revisa fuentes cada 30 minutos y publica directo con `WORDPRESS_STATUS=publish`.

## Deploy en Render

1. Sube este proyecto a GitHub.
2. En Render crea un `Web Service`.
3. Build command:
   ```bash
   pip install -r requirements.txt
   ```
4. Start command:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
5. Agrega variables de entorno:
   - WORDPRESS_URL
   - WORDPRESS_USER
   - WORDPRESS_APP_PASSWORD
   - WORDPRESS_STATUS=publish
   - CHECK_INTERVAL_MINUTES=30

## Deploy en VPS

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip -y
git clone TU_REPOSITORIO news-auto-wp
cd news-auto-wp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Para producción, usa systemd o supervisor.
