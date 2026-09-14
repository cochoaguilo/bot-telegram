"""Comandos y flujo principal del bot."""

from __future__ import annotations

import asyncio
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from . import config as cfgmod
from . import oauth, sheets
from . import db
from .extract import construir_filas

log = logging.getLogger(__name__)

OPCIONES = (
    ("dividir_lineas", "Una fila por linea"),
    ("fila_por_adjunto", "Una fila por adjunto"),
)


def _teclado(cfg: dict) -> InlineKeyboardMarkup:
    """Genera el teclado de /config."""
    filas = []
    activos = set(cfg.get("campos", cfgmod.DEFAULTS["campos"]))

    for campo in cfgmod.CAMPOS:
        marca = "✅" if campo.clave in activos else "⬜"
        filas.append(
            [
                InlineKeyboardButton(
                    f"{marca} {campo.etiqueta}", callback_data=f"campo:{campo.clave}"
                )
            ]
        )

    for clave, etiqueta in OPCIONES:
        marca = "✅" if cfg.get(clave, cfgmod.DEFAULTS.get(clave)) else "⬜"
        filas.append(
            [InlineKeyboardButton(f"{marca} {etiqueta}", callback_data=f"opcion:{clave}")]
        )

    filas.append([InlineKeyboardButton("💾 Guardar y cerrar", callback_data="cerrar")])
    return InlineKeyboardMarkup(filas)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    if not u:
        return

    usuario_db = db.usuario(u.id)
    if usuario_db and usuario_db.get("sheet_id"):
        await update.message.reply_text(
            "Bienvenido de nuevo. Mandame cualquier mensaje y lo guardo en tu Google Sheet.\n\n"
            f"Tu user ID: `{u.id}`\n\n"
            "Comandos: /config /estado",
            parse_mode="Markdown",
        )
    else:
        url_auth = oauth.url_autorizacion(u.id)
        await update.message.reply_text(
            "Hola. Para empezar, necesito que autorices el acceso a tu Google.\n\n"
            "Toca el botón de abajo:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Autorizar con Google", url=url_auth)]]
            ),
        )


async def config_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    if not u:
        return

    usuario_db = db.usuario(u.id)
    if not usuario_db or not usuario_db.get("sheet_id"):
        await update.message.reply_text("Primero necesitas /start para autorizar.")
        return

    # Arma la config desde la DB con defaults
    cfg = {
        "campos": (
            cfgmod.CAMPOS_POR_CLAVE[c].clave
            for c in (
                usuario_db.get("campos")
                and __import__("json").loads(usuario_db.get("campos")) or cfgmod.DEFAULTS["campos"]
            )
            if c in cfgmod.CAMPOS_POR_CLAVE
        ),
        "dividir_lineas": usuario_db.get("dividir_lineas", cfgmod.DEFAULTS["dividir_lineas"]),
        "fila_por_adjunto": usuario_db.get("fila_por_adjunto", cfgmod.DEFAULTS["fila_por_adjunto"]),
    }
    cfg["campos"] = list(cfg["campos"])
    if not cfg["campos"]:
        cfg["campos"] = list(cfgmod.DEFAULTS["campos"])

    await update.message.reply_text(
        "Elige que columnas quieres guardar:",
        reply_markup=_teclado(cfg),
    )


async def config_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    u = update.effective_user
    if not u:
        await query.answer("Error: sin usuario", show_alert=True)
        return

    usuario_db = db.usuario(u.id)
    if not usuario_db or not usuario_db.get("sheet_id"):
        await query.answer("Necesitas /start primero", show_alert=True)
        return

    dato = query.data
    cfg = {
        "campos": list(__import__("json").loads(usuario_db.get("campos", "[]")) or cfgmod.DEFAULTS["campos"]),
        "dividir_lineas": usuario_db.get("dividir_lineas", cfgmod.DEFAULTS["dividir_lineas"]),
        "fila_por_adjunto": usuario_db.get("fila_por_adjunto", cfgmod.DEFAULTS["fila_por_adjunto"]),
    }

    if dato == "cerrar":
        await query.answer("Guardado")
        # Sincroniza la cabecera en la hoja
        try:
            creds = oauth.credenciales_de(u.id)
            if creds:
                await asyncio.to_thread(
                    sheets.sincronizar_cabecera,
                    creds,
                    usuario_db["sheet_id"],
                    cfg["campos"],
                )
        except Exception:
            log.exception("Error sincronizando cabecera")
        columnas = ", ".join(cfgmod.cabeceras(cfg["campos"]))
        await query.edit_message_text(f"Configuracion guardada.\nColumnas: {columnas}")
        return

    tipo, _, clave = dato.partition(":")
    if tipo == "campo":
        if clave in cfg["campos"]:
            cfg["campos"].remove(clave)
        else:
            cfg["campos"].append(clave)
        cfg["campos"] = [c for c in cfgmod.CAMPOS if c.clave in cfg["campos"]]
        cfg["campos"] = [c.clave for c in cfg["campos"]]
        if not cfg["campos"]:
            cfg["campos"] = ["texto"]
    elif tipo == "opcion":
        cfg[clave] = not cfg.get(clave, False)

    db.set_config(u.id, **cfg)
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=_teclado(cfg))


async def estado_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    if not u:
        return

    usuario_db = db.usuario(u.id)
    if not usuario_db or not usuario_db.get("sheet_id"):
        await update.message.reply_text("Primero necesitas /start para autorizar.")
        return

    campos_list = __import__("json").loads(usuario_db.get("campos", "[]")) or cfgmod.DEFAULTS["campos"]
    opciones = "\n".join(
        f"- {etiqueta}: {'si' if usuario_db.get(c, cfgmod.DEFAULTS.get(c)) else 'no'}"
        for c, etiqueta in OPCIONES
    )
    sheet_url = f"https://docs.google.com/spreadsheets/d/{usuario_db['sheet_id']}"
    await update.message.reply_text(
        f"Columnas: {', '.join(cfgmod.cabeceras(campos_list))}\n"
        f"{opciones}\n{sheet_url}"
    )


async def guardar_mensaje(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    u = update.effective_user
    if not msg or not u:
        return

    usuario_db = db.usuario(u.id)
    if not usuario_db or not usuario_db.get("sheet_id"):
        await msg.reply_text("Primero necesitas /start para autorizar.")
        return

    # Arma la config
    cfg = {
        "campos": __import__("json").loads(usuario_db.get("campos", "[]")) or cfgmod.DEFAULTS["campos"],
        "dividir_lineas": usuario_db.get("dividir_lineas", cfgmod.DEFAULTS["dividir_lineas"]),
        "fila_por_adjunto": usuario_db.get("fila_por_adjunto", cfgmod.DEFAULTS["fila_por_adjunto"]),
    }

    try:
        filas = await construir_filas(msg, cfg)
        if not filas:
            return

        creds = oauth.credenciales_de(u.id)
        if not creds:
            await msg.reply_text("❌ No pude obtener tus credenciales de Google.")
            return

        await asyncio.to_thread(
            sheets.sincronizar_cabecera, creds, usuario_db["sheet_id"], cfg["campos"]
        )
        await asyncio.to_thread(
            sheets.append, creds, usuario_db["sheet_id"], filas
        )
    except Exception as e:
        log.exception("Error guardando mensaje")
        await msg.reply_text(f"❌ No pude guardarlo: {e}")
        return

    await msg.reply_text(f"✅ {len(filas)} fila(s) guardada(s)")
