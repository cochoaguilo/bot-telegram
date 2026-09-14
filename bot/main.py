"""Entrypoint del bot para ejecución local con long-polling."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from . import db, handlers

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")


def validar() -> None:
    """Valida que estén las variables requeridas."""
    reqs = [
        "TELEGRAM_TOKEN",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "BASE_URL",
        "TOKEN_ENCRYPTION_KEY",
    ]
    faltan = [r for r in reqs if not os.getenv(r)]
    if faltan:
        print("Faltan variables en .env:")
        for f in faltan:
            print(f"  - {f}")
        print("\nCopia .env.example a .env y rellena los valores.")
        sys.exit(1)


def main() -> None:
    """Arranca el bot con long-polling en local."""
    load_dotenv()
    validar()

    # Inicializa la DB
    db.inicializar()
    log.info("Base de datos inicializada")

    # Construye la Application
    app = Application.builder().token(os.environ["TELEGRAM_TOKEN"]).build()

    # Registra handlers
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("config", handlers.config_cmd))
    app.add_handler(CommandHandler("estado", handlers.estado_cmd))
    app.add_handler(CallbackQueryHandler(handlers.config_callback))
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, handlers.guardar_mensaje)
    )

    log.info("Bot escuchando (long-polling). Ctrl+C para parar.")
    # Configura Windows event loop si es necesario (igual que antes)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Arranca con polling
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
