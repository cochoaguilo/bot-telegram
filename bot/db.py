"""Base de datos SQLite para usuarios y tokens OAuth."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bot.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

_cipher = None


def _get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        key = os.environ.get("TOKEN_ENCRYPTION_KEY", "").encode()
        if not key:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY no definida en .env")
        _cipher = Fernet(key)
    return _cipher


def _cifrar(texto: str) -> str:
    return _get_cipher().encrypt(texto.encode()).decode()


def _descifrar(texto: str) -> str:
    return _get_cipher().decrypt(texto.encode()).decode()


@contextmanager
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


def inicializar() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                telegram_id INTEGER PRIMARY KEY,
                sheet_id TEXT,
                refresh_token TEXT,
                access_token TEXT,
                token_expiry TEXT,
                campos TEXT,
                dividir_lineas INTEGER,
                fila_por_adjunto INTEGER
            )
        """)
        c.commit()


def usuario(telegram_id: int) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM usuarios WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    if not row:
        return None
    return dict(row)


def crear_o_actualizar(telegram_id: int, **campos: Any) -> None:
    # Cifra los tokens
    if "refresh_token" in campos and campos["refresh_token"]:
        campos["refresh_token"] = _cifrar(campos["refresh_token"])
    if "access_token" in campos and campos["access_token"]:
        campos["access_token"] = _cifrar(campos["access_token"])

    # Serializa JSON si es necesario
    if "campos" in campos and isinstance(campos["campos"], list):
        campos["campos"] = json.dumps(campos["campos"])

    with _conn() as c:
        # Verifica si existe
        existe = c.execute(
            "SELECT 1 FROM usuarios WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()

        if existe:
            set_clause = ", ".join(f"{k} = ?" for k in campos.keys())
            vals = list(campos.values()) + [telegram_id]
            c.execute(f"UPDATE usuarios SET {set_clause} WHERE telegram_id = ?", vals)
        else:
            placeholders = ", ".join("?" * (len(campos) + 1))
            cols = "telegram_id, " + ", ".join(campos.keys())
            vals = [telegram_id] + list(campos.values())
            c.execute(
                f"INSERT INTO usuarios ({cols}) VALUES ({placeholders})", vals
            )
        c.commit()


def set_config(telegram_id: int, **campos: Any) -> None:
    """Actualiza solo los campos de config, no los tokens."""
    permitidos = {"campos", "dividir_lineas", "fila_por_adjunto"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if campos:
        crear_o_actualizar(telegram_id, **campos)


def obtener_token_descifrado(telegram_id: int, tipo: str) -> str | None:
    """Obtiene refresh_token o access_token descifrado."""
    u = usuario(telegram_id)
    if not u or not u.get(tipo):
        return None
    try:
        return _descifrar(u[tipo])
    except Exception:
        return None


def guardar_token_cifrado(telegram_id: int, tipo: str, valor: str) -> None:
    """Guarda refresh_token o access_token cifrados."""
    crear_o_actualizar(telegram_id, **{tipo: valor})
