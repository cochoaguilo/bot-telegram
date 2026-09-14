"""Convierte un mensaje de Telegram en una o varias filas para la hoja."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Message

from .config import CAMPOS_POR_CLAVE

log = logging.getLogger(__name__)


def _nombre_usuario(msg: Message) -> str:
    u = msg.from_user
    if u is None:
        return ""
    if u.username:
        return f"@{u.username}"
    return " ".join(p for p in (u.first_name, u.last_name) if p)


def _nombre_chat(msg: Message) -> str:
    c = msg.chat
    return c.title or " ".join(p for p in (c.first_name, c.last_name) if p) or str(c.id)


def _adjuntos(msg: Message) -> list[tuple[str, str]]:
    """Devuelve [(tipo, file_id)] de los adjuntos del mensaje."""
    salida: list[tuple[str, str]] = []
    if msg.photo:
        # PTB ordena las PhotoSize de menor a mayor: la ultima es la mejor resolucion.
        salida.append(("foto", msg.photo[-1].file_id))
    for tipo, obj in (
        ("documento", msg.document),
        ("video", msg.video),
        ("audio", msg.audio),
        ("voz", msg.voice),
        ("nota_video", msg.video_note),
        ("sticker", msg.sticker),
        ("animacion", msg.animation),
    ):
        if obj is not None:
            salida.append((tipo, obj.file_id))
    return salida


def _tipo_mensaje(msg: Message, adjuntos: list[tuple[str, str]]) -> str:
    if adjuntos:
        return adjuntos[0][0]
    if msg.location:
        return "ubicacion"
    if msg.contact:
        return "contacto"
    return "texto"


def _cuerpos(msg: Message, dividir: bool) -> list[str]:
    texto = msg.text or msg.caption or ""
    if msg.location:
        texto = texto or f"{msg.location.latitude},{msg.location.longitude}"
    if msg.contact:
        texto = texto or f"{msg.contact.first_name} {msg.contact.phone_number}"
    if not texto:
        return []
    if not dividir:
        return [texto]
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    return lineas or [texto]


async def construir_filas(msg: Message, cfg: dict[str, Any]) -> list[list[str]]:
    """Proyecta el mensaje sobre los campos activos, expandiendo en varias filas."""
    adjuntos = _adjuntos(msg)
    cuerpos = _cuerpos(msg, cfg.get("dividir_lineas", True))
    fecha_local = msg.date.astimezone()

    base = {
        "fecha": fecha_local.strftime("%Y-%m-%d"),
        "hora": fecha_local.strftime("%H:%M:%S"),
        "plataforma": "Telegram",
        "chat_id": msg.chat.id,
        "chat_nombre": _nombre_chat(msg),
        "usuario": _nombre_usuario(msg),
        "user_id": msg.from_user.id if msg.from_user else "",
        "tipo": _tipo_mensaje(msg, adjuntos),
        "message_id": msg.message_id,
    }

    # Resolver las URLs de descarga una sola vez por adjunto.
    urls: list[tuple[str, str]] = []
    for tipo, file_id in adjuntos:
        try:
            fichero = await msg.get_bot().get_file(file_id)
            urls.append((tipo, fichero.file_path or ""))
        except Exception:
            log.exception("No se pudo resolver el adjunto %s", file_id)
            urls.append((tipo, "(no disponible)"))

    if not cfg.get("fila_por_adjunto", True):
        urls = urls[:1]

    # Una fila por cuerpo y una por adjunto. Para no duplicar el texto, el primer
    # adjunto viaja en la primera fila de texto y el resto salen en filas propias.
    contextos: list[dict[str, Any]] = []
    for i, cuerpo in enumerate(cuerpos):
        ctx = dict(base, texto=cuerpo, adjunto_url="")
        if i == 0 and urls:
            ctx["tipo"], ctx["adjunto_url"] = urls[0]
        contextos.append(ctx)

    restantes = urls[1:] if cuerpos else urls
    for tipo, url in restantes:
        contextos.append(dict(base, texto="", tipo=tipo, adjunto_url=url))

    if not contextos:
        return []

    return [
        [CAMPOS_POR_CLAVE[clave].extraer(ctx) for clave in cfg["campos"]]
        for ctx in contextos
    ]
