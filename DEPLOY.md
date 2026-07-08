# Desplegar la app para todo el equipo (Render + Postgres gratis)

Esta guía deja la app corriendo en un link único (ej.
`https://xseed-followups.onrender.com`) donde cada recruiter entra con su
propia cuenta de Google y ve solo sus propios candidatos.

Vas a necesitar crear 3 cuentas gratuitas (no piden tarjeta): **GitHub**,
**Neon** (base de datos) y **Render** (hosting).

---

## Paso 0 — Antes de empezar

Ya deberías tener, de la app local:
- El proyecto (esta carpeta `candidate-followup-app-team`).
- Tu `credentials.json` de Google Cloud (si no lo tenés todavía, mirá el
  Paso 1).

**Importante:** `credentials.json` NUNCA se sube a GitHub — es secreto. En
Render se carga de otra forma (Paso 4).

---

## Paso 1 — Ajustar el proyecto de Google Cloud

Si ya seguiste el README de la versión local, reutilizá el mismo proyecto de
Google Cloud. Si no, primero creá uno (ver README.md, Paso 2, secciones 1-4).

1. Entrá a [Google Cloud Console](https://console.cloud.google.com/) → tu
   proyecto → **APIs y servicios → Credenciales**.
2. Abrí tu "ID de cliente de OAuth" y en **URI de redireccionamiento
   autorizados** agregá (sin borrar la de localhost):
   ```
   https://TU-APP.onrender.com/oauth2callback
   ```
   (vas a saber el nombre final `TU-APP` recién en el Paso 5 — podés volver
   a este paso después para completarlo).
3. Andá a **Pantalla de consentimiento OAuth → Usuarios de prueba** y
   agregá el email de Google de **cada persona del equipo** que va a usar
   la app (hasta 100 personas sin necesitar verificación de Google).

> Nota sobre el modo "prueba": como la app no está verificada por Google,
> cada usuario va a tener que volver a conectar su cuenta cada 7 días (el
> token expira). Es una limitación de Google, no de la app — alcanza con
> tocar "Conectar Google Calendar" de nuevo cuando pida reconectar. Si en
> el futuro quieren evitar esto, hay que pasar la app por el proceso de
> verificación de Google (requiere política de privacidad y dominio
> propio).

---

## Paso 2 — Crear la base de datos gratis (Neon)

1. Entrá a [neon.tech](https://neon.tech) y creá una cuenta gratis.
2. Creá un proyecto nuevo (cualquier nombre, ej. `xseed-followups`).
3. En el dashboard del proyecto, copiá el **Connection string** (empieza
   con `postgresql://...`). Guardalo, lo vas a usar en el Paso 5.

---

## Paso 3 — Subir el código a GitHub

1. Entrá a [github.com](https://github.com) y creá una cuenta gratis (si no
   tenés).
2. Creá un repositorio nuevo, privado, por ejemplo `candidate-followups`.
3. Subí todos los archivos de esta carpeta **excepto** `credentials.json` y
   `followups.db` (el `.gitignore` ya los excluye si usás Git; si subís
   manualmente por la web de GitHub, simplemente no arrastres esos dos
   archivos).

---

## Paso 4 — Crear el servicio en Render

1. Entrá a [render.com](https://render.com) y creá una cuenta gratis
   (podés entrar directo con GitHub).
2. **New → Web Service** → elegí el repositorio `candidate-followups`.
3. Configuración:
   - **Runtime:** Python 3.
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** (se completa solo desde el `Procfile`: `gunicorn app:app`)
   - **Instance Type:** Free.
4. En **Environment → Environment Variables**, agregá:
   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | el connection string de Neon (Paso 2) |
   | `REDIRECT_URI` | `https://TU-APP.onrender.com/oauth2callback` |
   | `FLASK_ENV` | `production` |
   | `FLASK_SECRET_KEY` | cualquier texto largo y random (ej. generalo en [randomkeygen.com](https://randomkeygen.com)) |
5. En **Environment → Secret Files**, agregá un archivo:
   - **Filename:** `credentials.json`
   - **Contents:** pegá el contenido completo del `credentials.json` que
     descargaste de Google Cloud.
6. Hacé clic en **Create Web Service**. Render va a instalar todo y
   levantar la app — tarda 2-3 minutos la primera vez.
7. Cuando termine, vas a ver la URL real de tu app (ej.
   `https://candidate-followups-xyz.onrender.com`). Copiala.

---

## Paso 5 — Cerrar el círculo

1. Volvé a Google Cloud Console (Paso 1) y reemplazá `TU-APP.onrender.com`
   por la URL real que te dio Render, tanto en:
   - La variable de entorno `REDIRECT_URI` en Render, y
   - El "URI de redireccionamiento autorizado" en Google Cloud.
   Tienen que ser **exactamente iguales**, con `/oauth2callback` al final.
2. En Render, si cambiaste alguna variable de entorno, la app se reinicia
   sola.

---

## Paso 6 — Probarla

1. Compartí el link de Render con el equipo (ej. por Slack).
2. Cada persona entra, hace clic en "Conectar Google Calendar" y usa **su
   propia cuenta** (tiene que ser una de las que agregaste como "usuario de
   prueba" en el Paso 1.3, si no Google le va a bloquear el acceso).
3. Cada una va a ver únicamente sus propios candidatos.

---

## Nota sobre el plan gratuito de Render

El plan free "duerme" la app después de 15 minutos sin uso, y tarda unos 20-30
segundos en volver a arrancar la primera vez que alguien entra después de
eso. Es normal, no es un error. Si en algún momento eso molesta, se puede
pasar a un plan pago (~7 USD/mes) para que quede siempre activa.
