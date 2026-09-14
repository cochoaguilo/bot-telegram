"""Autenticación OAuth con Google."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from .db import (
    guardar_token_cifrado,
    obtener_token_descifrado,
    usuario,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def url_autorizacion(telegram_id: int) -> str:
    """Devuelve la URL de autorización de Google para este usuario de Telegram."""
    flow = Flow.from_client_config(
        {
            "installed": {
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [os.environ["BASE_URL"] + "/oauth/callback"],
            }
        },
        scopes=SCOPES,
    )
    # Fuerza que Google devuelva siempre un refresh_token, incluso si el usuario ya autorizó
    flow.code_challenge_method = None  # No PKCE; no es necesario aquí
    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", state=str(telegram_id)
    )
    return auth_url


def intercambiar_code(code: str) -> Credentials:
    """Intercambia el code de Google por Credentials (access + refresh token)."""
    flow = Flow.from_client_config(
        {
            "installed": {
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [os.environ["BASE_URL"] + "/oauth/callback"],
            }
        },
        scopes=SCOPES,
    )
    flow.fetch_token(code=code)
    return flow.credentials


def credenciales_de(telegram_id: int) -> Credentials | None:
    """Obtiene las Credentials para este usuario, refrescando si expiró."""
    u = usuario(telegram_id)
    if not u or not u.get("refresh_token"):
        return None

    refresh = obtener_token_descifrado(telegram_id, "refresh_token")
    access = obtener_token_descifrado(telegram_id, "access_token")
    expiry_str = u.get("token_expiry")

    expiry = None
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str)
        except ValueError:
            expiry = None

    creds = Credentials(
        token=access,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    if expiry:
        creds.expiry = expiry

    # Si expiró, refresca
    if creds.expired and refresh:
        req = Request()
        creds.refresh(req)
        # Persiste el nuevo access_token
        guardar_token_cifrado(telegram_id, "access_token", creds.token)
        # Actualiza la expiry
        if creds.expiry:
            from .db import crear_o_actualizar
            crear_o_actualizar(telegram_id, token_expiry=creds.expiry.isoformat())

    return creds
