"""Catalogo de campos y persistencia de preferencias por chat."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Callable

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


@dataclass(frozen=True)
class Campo:
    clave: str
    etiqueta: str
    extraer: Callable[[dict[str, Any]], str]


# Cada extractor recibe el `ctx` que arma extract.construir_filas: un dict plano con los
# datos ya resueltos del mensaje (incluida la linea o el adjunto de ESTA fila concreta).
CAMPOS: tuple[Campo, ...] = (
    Campo("fecha", "Fecha", lambda c: c["fecha"]),
    Campo("hora", "Hora", lambda c: c["hora"]),
    Campo("plataforma", "Plataforma", lambda c: c["plataforma"]),
    Campo("chat_id", "Chat ID", lambda c: str(c["chat_id"])),
    Campo("chat_nombre", "Chat", lambda c: c["chat_nombre"]),
    Campo("usuario", "Usuario", lambda c: c["usuario"]),
    Campo("user_id", "User ID", lambda c: str(c["user_id"])),
    Campo("tipo", "Tipo", lambda c: c["tipo"]),
    Campo("texto", "Texto", lambda c: c["texto"]),
    Campo("adjunto_url", "Adjunto", lambda c: c["adjunto_url"]),
    Campo("message_id", "Message ID", lambda c: str(c["message_id"])),
)

CAMPOS_POR_CLAVE: dict[str, Campo] = {c.clave: c for c in CAMPOS}

DEFAULTS: dict[str, Any] = {
    "campos": ["fecha", "hora", "usuario", "texto", "adjunto_url"],
    "hoja": "Mensajes",
    "dividir_lineas": True,
    "fila_por_adjunto": True,
}


def cargar() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        # Un config corrupto no debe tumbar el bot: se vuelve a los defaults.
        return {}


def guardar(data: dict[str, Any]) -> None:
    """Escritura atomica para no dejar el JSON a medias si se corta el proceso."""
    carpeta = os.path.dirname(CONFIG_PATH)
    fd, tmp = tempfile.mkstemp(dir=carpeta, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def config_de_chat(chat_id: int) -> dict[str, Any]:
    guardado = cargar().get(str(chat_id), {})
    cfg = dict(DEFAULTS)
    cfg.update(guardado)
    # Descarta claves de campos que ya no existan en el catalogo.
    cfg["campos"] = [c for c in cfg["campos"] if c in CAMPOS_POR_CLAVE]
    if not cfg["campos"]:
        cfg["campos"] = list(DEFAULTS["campos"])
    return cfg


def escribir_config_de_chat(chat_id: int, cfg: dict[str, Any]) -> None:
    data = cargar()
    data[str(chat_id)] = cfg
    guardar(data)


def toggle_campo(chat_id: int, clave: str) -> dict[str, Any]:
    """Activa o desactiva un campo, conservando el orden del catalogo."""
    cfg = config_de_chat(chat_id)
    activos = set(cfg["campos"])
    if clave in activos:
        activos.discard(clave)
    else:
        activos.add(clave)
    if not activos:  # nunca dejar la hoja sin columnas
        activos = {"texto"}
    cfg["campos"] = [c.clave for c in CAMPOS if c.clave in activos]
    escribir_config_de_chat(chat_id, cfg)
    return cfg


def toggle_opcion(chat_id: int, clave: str) -> dict[str, Any]:
    cfg = config_de_chat(chat_id)
    cfg[clave] = not cfg.get(clave, False)
    escribir_config_de_chat(chat_id, cfg)
    return cfg


def set_hoja(chat_id: int, nombre: str) -> dict[str, Any]:
    cfg = config_de_chat(chat_id)
    cfg["hoja"] = nombre
    escribir_config_de_chat(chat_id, cfg)
    return cfg


def cabeceras(campos: list[str]) -> list[str]:
    return [CAMPOS_POR_CLAVE[c].etiqueta for c in campos]
