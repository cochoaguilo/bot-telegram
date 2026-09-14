# Bot de Telegram → Google Sheets (local, multi-usuario)

Corre en tu PC. Cada usuario que hable con el bot puede autorizar con su Google y que
automáticamente se cree una Sheet en su cuenta — sin intervención manual, sin compartir
hojas.

## Requisitos

- Python 3.11+
- Proyecto de Google Cloud con **Google Sheets API** y **Google Drive API** habilitadas.
- OAuth credential con pantalla de consentimiento en modo *Testing*.

## Setup

### 1. Google Cloud Console

1. Crea un proyecto o reutiliza uno existente.
2. Habilita **Google Sheets API** y **Google Drive API**.
3. Crea una **pantalla de consentimiento OAuth**:
   - Tipo: *Externo*
   - Estado: *Testing*
4. En **Credenciales**, crea un **ID de cliente de OAuth** (tipo *Aplicación web*):
   - URIs de redirección: `http://localhost:5000/oauth/callback`
5. Copia el **Client ID** y **Client Secret**.

### 2. Variables de entorno

Genera la clave de cifrado:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copia `.env.example` a `.env` y rellena:

```
TELEGRAM_TOKEN=<tu_token_de_BotFather>
GOOGLE_CLIENT_ID=<del_paso_1>
GOOGLE_CLIENT_SECRET=<del_paso_1>
BASE_URL=http://localhost:5000
TOKEN_ENCRYPTION_KEY=<salida_del_comando_arriba>
```

### 3. Instala dependencias

```bash
pip install -r requirements.txt
```

### 4. Arranca el bot

```bash
python -m bot.main
```

Debe salir:

```
Base de datos inicializada
Bot escuchando (long-polling). Ctrl+C para parar.
```

### 5. Agregar usuarios (test users)

Para que alguien pueda autorizar con Google, debe estar en la lista de *usuarios de prueba*
de la pantalla de consentimiento OAuth:

1. Google Cloud Console → proyecto → Pantalla de consentimiento OAuth
2. *Usuarios de prueba* → *Agregar usuarios*
3. Pega el email de Google de cada usuario que vaya a probar

Sin esto, Google bloquea la autorización.

## Uso

1. Usuario nuevo en Telegram envía `/start` → bot muestra un botón "Autorizar con Google".
2. Usuario toca el botón, autoriza (si está en la lista de test users).
3. Bot crea automáticamente una Sheet y avisa con el link.
4. Usuario envía `/config` para elegir columnas; a partir de ahí, cada mensaje se guarda.

### Comandos

- `/start` — Autorizar y configurar.
- `/config` — Elegir columnas (Fecha, Hora, Usuario, Texto, Adjuntos, etc.).
- `/estado` — Ver columnas activas y el link a la hoja.

### Columnas disponibles

Fecha, Hora, Plataforma, Chat ID, Chat, Usuario, User ID, Tipo, Texto, Adjunto, Message ID.

### Expansión de filas

- **Una fila por línea**: si el mensaje tiene 3 líneas, se guardan como 3 filas.
- **Una fila por adjunto**: fotos, documentos, videos, etc. cada uno en su fila.
- El primer adjunto viaja en la fila del texto; los demás salen en filas propias.

## Archivos locales

- `bot.db` — Base de datos SQLite con usuarios, tokens OAuth (cifrados) y config.
- `config.json` — **Descartado** (ahora todo está en la DB).

## Troubleshooting

### "Invalid state" en OAuth

Revisá que BASE_URL en `.env` coincida con la URI de redirección en Google Cloud.

### "Token expirado" al guardar

Los refresh tokens se regeneran automáticamente. Si ocurre algo raro, el usuario puede
hacer `/start` de nuevo.

### La DB está corrupta

Borra `bot.db` y reinicia el bot. Cada usuario tendrá que hacer `/start` de nuevo.

## Escalado futuro

Si en el futuro quieres pasar a cloud (24/7 sin tu PC):
- El código está diseñado para funcionar con webhook también.
- Solo cambiarías `bot/main.py` para usar `bot/server.py` + FastAPI.
- Toda la lógica de DB, OAuth y Sheets seguiría funcionando igual.
