"""Servidor HTTP que atiende el callback de OAuth de Google."""

from __future__ import annotations

import asyncio
import logging
import threading

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from . import db, oauth, sheets

log = logging.getLogger(__name__)

app = FastAPI()

_bot = None
_loop: asyncio.AbstractEventLoop | None = None


def configurar(bot, loop: asyncio.AbstractEventLoop) -> None:
    """Guarda la referencia al bot y a su event loop para poder avisarle al usuario."""
    global _bot, _loop
    _bot = bot
    _loop = loop


@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(request: Request) -> str:
    error = request.query_params.get("error")
    if error:
        return f"<h1>Autorización cancelada</h1><p>{error}</p>"

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return "<h1>Error</h1><p>Faltan parámetros en la respuesta de Google.</p>"

    telegram_id = int(state)

    try:
        creds = await asyncio.to_thread(oauth.intercambiar_code, code)
        sheet_id = await asyncio.to_thread(
            sheets.crear_hoja, creds, f"Bot Telegram - {telegram_id}"
        )
        db.crear_o_actualizar(
            telegram_id,
            sheet_id=sheet_id,
            refresh_token=creds.refresh_token,
            access_token=creds.token,
            token_expiry=creds.expiry.isoformat() if creds.expiry else None,
        )
    except Exception:
        log.exception("Error procesando el callback de OAuth")
        return (
            "<h1>Error</h1>"
            "<p>No pude completar la autorización. Volvé a intentar con /start.</p>"
        )

    _avisar(telegram_id)
    return "<h1>Listo</h1><p>Ya podés volver a Telegram.</p>"


def _avisar(telegram_id: int) -> None:
    """Manda un mensaje de confirmación al usuario en Telegram."""
    if not _bot or not _loop:
        return
    asyncio.run_coroutine_threadsafe(
        _bot.send_message(
            chat_id=telegram_id,
            text="✅ Autorización completa. Ya podés mandarme mensajes o usar /config.",
        ),
        _loop,
    )


def iniciar_en_hilo(host: str, port: int) -> threading.Thread:
    """Arranca el servidor FastAPI en un hilo aparte (daemon)."""
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    return hilo
