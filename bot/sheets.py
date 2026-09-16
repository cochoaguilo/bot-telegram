"""Cliente de Google Sheets API v4."""

from __future__ import annotations

import logging
import time

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from .config import cabeceras

log = logging.getLogger(__name__)

TIMEOUT = 30


class SheetsError(RuntimeError):
    """Error al hablar con Google Sheets."""


def _reintentar(fn, intentos: int = 3):
    """Reintento con backoff ante rate limits y errores temporales."""
    for i in range(intentos):
        try:
            return fn()
        except HttpError as e:
            codigo = e.resp.status
            if codigo not in (429, 500, 502, 503, 504) or i == intentos - 1:
                raise SheetsError(f"Google Sheets respondio HTTP {codigo}") from e
            espera = 2 ** i
            log.warning("HTTP %s, reintento en %ss", codigo, espera)
            time.sleep(espera)


def crear_hoja(creds: Credentials, titulo: str) -> str:
    """Crea una Google Sheet nueva. Devuelve el spreadsheetId."""
    service = build("sheets", "v4", credentials=creds)
    try:
        resultado = _reintentar(
            lambda: service.spreadsheets()
            .create(body={"properties": {"title": titulo}})
            .execute()
        )
        return resultado["spreadsheetId"]
    except SheetsError:
        raise
    except Exception as e:
        raise SheetsError(f"No pude crear la hoja: {e}") from e


def sincronizar_cabecera(creds: Credentials, sheet_id: str, campos: list[str]) -> bool:
    """Reescribe la fila 1 si no coincide. Devuelve True si cambio."""
    service = build("sheets", "v4", credentials=creds)
    esperada = cabeceras(campos)

    try:
        # Lee la fila 1
        resultado = _reintentar(
            lambda: service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="A1:Z1")
            .execute()
        )
        actual = resultado.get("values", [[]])[0]
    except SheetsError:
        raise
    except Exception:
        # Si no existe o hay error, asume que hay que escribir
        actual = []

    # Compara
    if actual == esperada:
        return False

    # Reescribe la cabecera + formatea
    try:
        _reintentar(
            lambda: service.spreadsheets()
            .values()
            .update(
                spreadsheetId=sheet_id,
                range="A1",
                valueInputOption="USER_ENTERED",
                body={"values": [esperada]},
            )
            .execute()
        )
        # Congela la fila 1 y la pone en negrita
        _reintentar(
            lambda: service.spreadsheets()
            .batchUpdate(
                spreadsheetId=sheet_id,
                body={
                    "requests": [
                        {
                            "updateSheetProperties": {
                                "fields": "gridProperties.frozenRowCount",
                                "properties": {
                                    "gridProperties": {"frozenRowCount": 1}
                                },
                            }
                        },
                        {
                            "repeatCell": {
                                "range": {
                                    "sheetId": 0,
                                    "startRowIndex": 0,
                                    "endRowIndex": 1,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": len(esperada),
                                },
                                "cell": {
                                    "userEnteredFormat": {"textFormat": {"bold": True}}
                                },
                                "fields": "userEnteredFormat.textFormat",
                            }
                        },
                    ]
                },
            )
            .execute()
        )
        return True
    except SheetsError:
        raise
    except Exception as e:
        raise SheetsError(f"No pude actualizar la cabecera: {e}") from e


def append(creds: Credentials, sheet_id: str, filas: list[list[str]]) -> None:
    """Añade filas a partir de la ultima fila."""
    if not filas:
        return

    service = build("sheets", "v4", credentials=creds)
    try:
        _reintentar(
            lambda: service.spreadsheets()
            .values()
            .append(
                spreadsheetId=sheet_id,
                range="A1",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": filas},
            )
            .execute()
        )
    except SheetsError:
        raise
    except Exception as e:
        raise SheetsError(f"No pude guardar las filas: {e}") from e
