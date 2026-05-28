"""Ejecuta una revisión/publicación una sola vez.
Uso: python run_once.py
"""
from app.database import init_db
from app.publisher import run_once

if __name__ == "__main__":
    init_db()
    result = run_once()
    print(result)
