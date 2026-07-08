"""
Candidate Follow-up Tracker — versión equipo (multi-usuario)
--------------------------------------------------------------
Cada persona se loguea con su propia cuenta de Google. Cada una ve
únicamente sus propias entrevistas y follow-ups. Pensada para desplegarse
en un solo lugar (ej. Render) y que todo el equipo entre por el mismo link.

Local (desarrollo):
    pip install -r requirements.txt
    python app.py
    -> http://localhost:5000

Producción: ver DEPLOY.md
"""

import os
import re
import json
from datetime import datetime, timedelta, timezone

from flask import Flask, request, redirect, session, jsonify, render_template
from dateutil import parser as dateparser

from flask_sqlalchemy import SQLAlchemy

from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:5000/oauth2callback")

# Para desarrollo local sobre http:// (en producción Render sirve https, así
# que esto no aplica ahí).
if os.environ.get("FLASK_ENV", "development") != "production":
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

# Formato esperado de los títulos de entrevista: "Puesto (Siglas) - Nombre del candidato"
EVENT_TITLE_PATTERN = re.compile(r"^\s*(?P<position>.+?)\s*\((?P<company>[^)]+)\)\s*-\s*(?P<candidate>.+?)\s*$")

DAYS_FIRST_REMINDER = 7
DAYS_BETWEEN_REMINDERS = 7
SYNC_LOOKBACK_DAYS = 180

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

db_url = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'followups.db')}")
# Render/Heroku/Neon entregan "postgres://" o "postgresql://". Usamos pg8000
# (driver 100% Python) en vez de psycopg2 para evitar problemas de
# compatibilidad binaria con versiones nuevas de Python.
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
elif db_url.startswith("postgresql://") and "+pg8000" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
db = SQLAlchemy(app)


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class Credential(db.Model):
    __tablename__ = "credentials"
    user_email = db.Column(db.String(255), primary_key=True)
    token_json = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)


class Interview(db.Model):
    __tablename__ = "interviews"
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(255), nullable=False, index=True)
    event_id = db.Column(db.String(255), nullable=False)
    candidate_name = db.Column(db.String(255), nullable=False)
    position = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(255), nullable=False)
    interview_datetime = db.Column(db.DateTime, nullable=False)
    attendees = db.Column(db.Text)
    next_reminder_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (db.UniqueConstraint("user_email", "event_id", name="uq_user_event"),)


class FollowupHistory(db.Model):
    __tablename__ = "followup_history"
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(255), nullable=False, index=True)
    event_id = db.Column(db.String(255), nullable=False)
    candidate_name = db.Column(db.String(255), nullable=False)
    position = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(255), nullable=False)
    interview_datetime = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=False)


def init_db():
    with app.app_context():
        db.create_all()


# ---------------------------------------------------------------------------
# Auth con Google (por usuario)
# ---------------------------------------------------------------------------

def current_user_email():
    return session.get("user_email")


def login_required_api(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user_email():
            return jsonify({"error": "not_logged_in"}), 401
        return fn(*args, **kwargs)

    return wrapper


def save_credentials_for_user(email, creds: Credentials):
    row = Credential.query.get(email)
    if not row:
        row = Credential(user_email=email)
        db.session.add(row)
    row.token_json = creds.to_json()
    row.updated_at = datetime.now(timezone.utc)
    db.session.commit()


def load_credentials_for_user(email):
    row = Credential.query.get(email)
    if not row:
        return None
    creds = Credentials.from_authorized_user_info(json.loads(row.token_json), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            save_credentials_for_user(email, creds)
        except Exception:
            return None
    return creds


@app.route("/api/auth/me")
def auth_me():
    email = current_user_email()
    if not email:
        return jsonify({"logged_in": False})
    creds = load_credentials_for_user(email)
    return jsonify({"logged_in": True, "email": email, "connected": bool(creds and creds.valid)})


@app.route("/login")
def login():
    if not os.path.exists(CREDENTIALS_FILE):
        return (
            "Falta credentials.json en el servidor. Revisá DEPLOY.md / README.",
            500,
        )
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent select_account",
    )
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth2callback():
    state = session.get("oauth_state")
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES, state=state, redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    # Identificamos al usuario a través de su calendario principal: el "id"
    # del calendario "primary" es justamente su dirección de Gmail/Workspace.
    service = build("calendar", "v3", credentials=creds)
    primary = service.calendars().get(calendarId="primary").execute()
    email = primary["id"]

    save_credentials_for_user(email, creds)
    session["user_email"] = email
    session.permanent = True
    return redirect("/")


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user_email", None)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Sincronización con Google Calendar
# ---------------------------------------------------------------------------

def parse_event_title(summary: str):
    if not summary:
        return None
    m = EVENT_TITLE_PATTERN.match(summary)
    if not m:
        return None
    return {
        "position": m.group("position").strip(),
        "company": m.group("company").strip(),
        "candidate": m.group("candidate").strip(),
    }


def fetch_calendar_events(creds: Credentials):
    service = build("calendar", "v3", credentials=creds)
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=SYNC_LOOKBACK_DAYS)).isoformat()
    time_max = now.isoformat()

    events = []
    page_token = None
    while True:
        resp = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=250,
                pageToken=page_token,
            )
            .execute()
        )
        events.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return events


def _naive_utc(dt):
    """SQLite/Postgres DateTime columns aquí se guardan naive-UTC."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@app.route("/api/sync", methods=["POST"])
@login_required_api
def sync():
    email = current_user_email()
    creds = load_credentials_for_user(email)
    if not creds or not creds.valid:
        return jsonify({"error": "not_connected"}), 401

    try:
        events = fetch_calendar_events(creds)
    except Exception as e:
        return jsonify({"error": "calendar_error", "detail": str(e)}), 502

    now = datetime.now(timezone.utc)
    inserted = 0
    matched = 0

    existing_ids = {
        row.event_id
        for row in Interview.query.filter_by(user_email=email).with_entities(Interview.event_id)
    }

    for event in events:
        summary = event.get("summary", "")
        end = event.get("end", {})
        end_raw = end.get("dateTime") or end.get("date")
        if not end_raw:
            continue
        try:
            end_dt = dateparser.isoparse(end_raw)
        except Exception:
            continue
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        if end_dt > now:
            continue  # todavía no terminó

        parsed = parse_event_title(summary)
        if not parsed:
            continue
        matched += 1

        if event["id"] in existing_ids:
            continue  # ya está en seguimiento, no reseteamos su ciclo

        start = event.get("start", {})
        start_raw = start.get("dateTime") or start.get("date")
        try:
            start_dt = dateparser.isoparse(start_raw)
        except Exception:
            start_dt = end_dt
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        attendees = [
            {"email": a.get("email"), "name": a.get("displayName", a.get("email"))}
            for a in event.get("attendees", [])
            if a.get("email")
        ]

        next_reminder = start_dt + timedelta(days=DAYS_FIRST_REMINDER)

        db.session.add(
            Interview(
                user_email=email,
                event_id=event["id"],
                candidate_name=parsed["candidate"],
                position=parsed["position"],
                company=parsed["company"],
                interview_datetime=_naive_utc(start_dt),
                attendees=json.dumps(attendees),
                next_reminder_date=_naive_utc(next_reminder),
                created_at=_naive_utc(datetime.now(timezone.utc)),
            )
        )
        inserted += 1

    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "events_seen": len(events),
            "matched_interviews": matched,
            "new_tracked": inserted,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
    )


# ---------------------------------------------------------------------------
# Follow-ups: pendientes / historial / completar (scoped por usuario)
# ---------------------------------------------------------------------------

def row_to_pending(row, today):
    interview_dt = row.interview_datetime.replace(tzinfo=timezone.utc)
    next_reminder = row.next_reminder_date.replace(tzinfo=timezone.utc)
    days_elapsed = (today.date() - interview_dt.date()).days
    weeks_overdue = max(0, (today.date() - next_reminder.date()).days // 7)
    return {
        "event_id": row.event_id,
        "candidate_name": row.candidate_name,
        "position": row.position,
        "company": row.company,
        "interview_datetime": interview_dt.isoformat(),
        "attendees": json.loads(row.attendees or "[]"),
        "days_elapsed": days_elapsed,
        "weeks_overdue": weeks_overdue,
        "next_reminder_date": next_reminder.isoformat(),
    }


@app.route("/api/followups/pending")
@login_required_api
def followups_pending():
    email = current_user_email()
    today = datetime.now(timezone.utc)
    rows = Interview.query.filter_by(user_email=email).all()
    pending = [r for r in rows if r.next_reminder_date.replace(tzinfo=timezone.utc) <= today]
    pending.sort(key=lambda r: r.next_reminder_date)
    return jsonify([row_to_pending(r, today) for r in pending])


@app.route("/api/followups/upcoming")
@login_required_api
def followups_upcoming():
    email = current_user_email()
    today = datetime.now(timezone.utc)
    rows = Interview.query.filter_by(user_email=email).all()
    upcoming = [r for r in rows if r.next_reminder_date.replace(tzinfo=timezone.utc) > today]
    upcoming.sort(key=lambda r: r.next_reminder_date)
    return jsonify([row_to_pending(r, today) for r in upcoming])


@app.route("/api/followups/history")
@login_required_api
def followups_history():
    email = current_user_email()
    rows = (
        FollowupHistory.query.filter_by(user_email=email)
        .order_by(FollowupHistory.completed_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "event_id": r.event_id,
                "candidate_name": r.candidate_name,
                "position": r.position,
                "company": r.company,
                "interview_datetime": r.interview_datetime.replace(tzinfo=timezone.utc).isoformat(),
                "completed_at": r.completed_at.replace(tzinfo=timezone.utc).isoformat(),
            }
            for r in rows
        ]
    )


@app.route("/api/followups/<event_id>/complete", methods=["POST"])
@login_required_api
def complete_followup(event_id):
    email = current_user_email()
    row = Interview.query.filter_by(user_email=email, event_id=event_id).first()
    if not row:
        return jsonify({"error": "not_found"}), 404

    now = datetime.now(timezone.utc)
    db.session.add(
        FollowupHistory(
            user_email=email,
            event_id=row.event_id,
            candidate_name=row.candidate_name,
            position=row.position,
            company=row.company,
            interview_datetime=row.interview_datetime,
            completed_at=_naive_utc(now),
        )
    )

    next_reminder = now + timedelta(days=DAYS_BETWEEN_REMINDERS)
    row.next_reminder_date = _naive_utc(next_reminder)
    db.session.commit()

    return jsonify({"ok": True, "next_reminder_date": next_reminder.isoformat()})


# ---------------------------------------------------------------------------
# Vista principal
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
