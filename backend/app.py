import hashlib
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash


load_dotenv(Path(__file__).with_name(".env"))


class DatabaseUnavailable(Exception):
    pass


def env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "medic_care"),
    "charset": "utf8mb4",
}
LOGIN_EMAIL_VERIFICATION = env_flag("LOGIN_EMAIL_VERIFICATION", True)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
APPOINTMENT_STATUSES = {"pending", "confirmed", "cancelled", "completed"}
ALLOWED_DATA = {"appointments": list}
MAX_APPOINTMENTS = 500
MAX_DATA_BYTES = 1_000_000
SESSION_DAYS = 30
VERIFY_WINDOW = 600
LOGIN_LINK_MINUTES = 15
RESET_TOKEN_MINUTES = 30
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
STATIC_EXTENSIONS = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp"}


@contextmanager
def db_cursor():
    """Open one MySQL connection, hand out a cursor, and always close it again."""
    try:
        connection = pymysql.connect(
            **DB_CONFIG,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
    except pymysql.MySQLError as error:
        raise DatabaseUnavailable from error
    try:
        with connection.cursor() as cursor:
            yield cursor
        connection.commit()
    except pymysql.MySQLError as error:
        connection.rollback()
        raise DatabaseUnavailable from error
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def as_text(value, limit):
    """Coerce anything to a string that fits a VARCHAR(limit) column."""
    return str(value if value is not None else "")[:limit]


def as_date(value):
    """Return a YYYY-MM-DD string when it looks like a date, otherwise NULL."""
    text = str(value or "").strip()
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None


def to_epoch(value):
    return int(value.timestamp()) if isinstance(value, datetime) else 0


def from_epoch(value):
    return datetime.fromtimestamp(float(value))


def appointment_row(uid, appointment):
    patient = appointment.get("patient") if isinstance(appointment.get("patient"), dict) else {}
    return (
        uid,
        int(appointment.get("id") or 0),
        as_text(appointment.get("doctor"), 100),
        as_text(appointment.get("doctorName"), 200),
        as_text(appointment.get("spec"), 200),
        as_text(appointment.get("service"), 300),
        as_text(appointment.get("specific"), 300),
        as_text(appointment.get("status") or "Confirmed", 20),
        as_date(appointment.get("date")),
        as_text(appointment.get("time"), 40),
        as_text(patient.get("first"), 100),
        as_text(patient.get("middle"), 100),
        as_text(patient.get("last"), 100),
        as_text(patient.get("suffix"), 20),
        as_date(patient.get("dob")),
        as_text(patient.get("sex"), 20),
        as_text(patient.get("phone"), 30),
        as_text(patient.get("email"), 254),
    )


class Store:
    """All MySQL access lives here, so the routes below stay readable."""

    def _appointments(self, cursor, user_id):
        cursor.execute("SELECT * FROM appointments WHERE user_id=%s ORDER BY id", (user_id,))
        return [
            {
                "id": row["client_id"],
                "doctor": row["doctor"],
                "doctorName": row["doctor_name"],
                "spec": row["spec"],
                "service": row["service"],
                "specific": row["specific_service"],
                "status": row["status"],
                "date": row["appt_date"].isoformat() if row["appt_date"] else "",
                "time": row["appt_time"],
                "patient": {
                    "first": row["patient_first"],
                    "middle": row["patient_middle"],
                    "last": row["patient_last"],
                    "suffix": row["patient_suffix"],
                    "dob": row["patient_dob"].isoformat() if row["patient_dob"] else "",
                    "sex": row["patient_sex"],
                    "phone": row["patient_phone"],
                    "email": row["patient_email"],
                },
            }
            for row in cursor.fetchall()
        ]

    def _user_doc(self, cursor, row):
        return {
            "uid": row["id"],
            "id": row["login_id"],
            "password_hash": row["password_hash"],
            "profile": {
                "name": row["name"],
                "email": row["email"],
                "phone": row["phone"],
                "code": row["code"],
            },
            "data": {"appointments": self._appointments(cursor, row["id"])},
            "created_at": to_epoch(row["created_at"]),
        }

    def get(self, uid):
        with db_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id=%s", (uid,))
            row = cursor.fetchone()
            return self._user_doc(cursor, row) if row else None

    def get_by_login(self, login_id):
        with db_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE login_id=%s", (login_id,))
            row = cursor.fetchone()
            return self._user_doc(cursor, row) if row else None

    def create(self, login_id, doc):
        """Insert a new account. Returns its id, or None when the e-mail is taken."""
        profile = doc.get("profile") or {}
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO users (login_id, password_hash, name, email, phone, code)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    login_id,
                    doc["password_hash"],
                    as_text(profile.get("name"), 200),
                    as_text(profile.get("email"), 254),
                    as_text(profile.get("phone"), 30),
                    as_text(profile.get("code") or "+63", 8),
                ),
            )
            if not cursor.rowcount:
                return None
            return cursor.lastrowid

    def update(self, uid, fields):
        sets, params = [], []
        if "password_hash" in fields:
            sets.append("password_hash=%s")
            params.append(str(fields["password_hash"]))
        profile = fields.get("profile")
        if isinstance(profile, dict):
            for column, limit in (("name", 200), ("email", 254), ("phone", 30), ("code", 8)):
                if column in profile:
                    sets.append(f"{column}=%s")
                    params.append(as_text(profile[column], limit))
        if not sets:
            return True
        params.append(uid)
        with db_cursor() as cursor:
            cursor.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=%s", tuple(params))
            return cursor.rowcount > 0

    def delete(self, uid):
        with db_cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id=%s", (uid,))

    def get_reset(self, token_hash):
        with db_cursor() as cursor:
            cursor.execute("SELECT * FROM password_resets WHERE token_hash=%s", (token_hash,))
            row = cursor.fetchone()
            return {"uid": row["user_id"], "exp": to_epoch(row["expires_at"])} if row else None

    def put_reset(self, token_hash, doc):
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (%s, %s, %s)"
                " ON DUPLICATE KEY UPDATE user_id=VALUES(user_id), expires_at=VALUES(expires_at)",
                (token_hash, doc["uid"], from_epoch(doc["exp"])),
            )

    def delete_reset(self, token_hash):
        with db_cursor() as cursor:
            cursor.execute("DELETE FROM password_resets WHERE token_hash=%s", (token_hash,))

    def get_challenge(self, token_hash):
        with db_cursor() as cursor:
            cursor.execute("SELECT * FROM login_challenges WHERE token_hash=%s", (token_hash,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "uid": row["user_id"],
                "exp": to_epoch(row["expires_at"]),
                "confirmed": bool(row["confirmed"]),
            }

    def put_challenge(self, token_hash, doc):
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO login_challenges (token_hash, user_id, expires_at, confirmed)"
                " VALUES (%s, %s, %s, 0)"
                " ON DUPLICATE KEY UPDATE user_id=VALUES(user_id),"
                " expires_at=VALUES(expires_at), confirmed=0",
                (token_hash, doc["uid"], from_epoch(doc["exp"])),
            )

    def confirm_challenge(self, token_hash):
        with db_cursor() as cursor:
            cursor.execute("UPDATE login_challenges SET confirmed=1 WHERE token_hash=%s", (token_hash,))
            return cursor.rowcount > 0

    def delete_challenge(self, token_hash):
        with db_cursor() as cursor:
            cursor.execute("DELETE FROM login_challenges WHERE token_hash=%s", (token_hash,))

    def claim_slot(self, slot_key, uid):
        """Take a doctor/date/time slot. True when it is free or already ours."""
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO appointment_slots (slot_key, user_id) VALUES (%s, %s)",
                (slot_key, uid),
            )
            if cursor.rowcount:
                return True
            cursor.execute("SELECT user_id FROM appointment_slots WHERE slot_key=%s", (slot_key,))
            row = cursor.fetchone()
            return bool(row and row["user_id"] == uid)

    def release_slot(self, slot_key, uid):
        with db_cursor() as cursor:
            cursor.execute(
                "DELETE FROM appointment_slots WHERE slot_key=%s AND user_id=%s",
                (slot_key, uid),
            )

    def save_appointments(self, uid, appointments):
        """Replace this patient's appointment list with exactly what was sent."""
        with db_cursor() as cursor:
            cursor.execute("DELETE FROM appointments WHERE user_id=%s", (uid,))
            if appointments:
                cursor.executemany(
                    "INSERT INTO appointments (user_id, client_id, doctor, doctor_name, spec, service,"
                    " specific_service, status, appt_date, appt_time, patient_first, patient_middle,"
                    " patient_last, patient_suffix, patient_dob, patient_sex, patient_phone,"
                    " patient_email)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [appointment_row(uid, appointment) for appointment in appointments],
                )


store = Store()

app = Flask(__name__, static_folder=None)

secret = os.getenv("SECRET_KEY")
if not secret:
    secret = secrets.token_hex(32)

app.config.update(
    SECRET_KEY=secret,
    SESSION_COOKIE_NAME="medic_care_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=env_flag("SESSION_COOKIE_SECURE"),
    PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)

if env_flag("TRUST_PROXY"):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def normalize(raw):
    return str(raw or "").strip().lower()


def valid_id(login_id):
    return len(login_id) <= 254 and bool(EMAIL_RE.match(login_id))


def valid_password(pw):
    return (
        isinstance(pw, str)
        and 8 <= len(pw) <= 128
        and re.search(r"[A-Za-z]", pw) is not None
        and re.search(r"\d", pw) is not None
    )


def is_int(v):
    """True only for real integers (bool is a subclass of int, so exclude it)."""
    return isinstance(v, int) and not isinstance(v, bool)


def is_text(v, max_len):
    return isinstance(v, str) and len(v) <= max_len


def valid_appointment(a):
    """Type-check one appointment record coming from the browser."""
    if not isinstance(a, dict):
        return False
    if "id" in a and not is_int(a["id"]):
        return False
    for field, limit in (("doctor", 100), ("doctorName", 200), ("spec", 200), ("service", 300),
                         ("specific", 300), ("date", 10), ("time", 40), ("status", 20)):
        if field in a and not is_text(a[field], limit):
            return False
    if "status" in a and a["status"].lower() not in APPOINTMENT_STATUSES:
        return False
    if "date" in a and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a["date"]):
        return False
    if "patient" in a and not isinstance(a["patient"], dict):
        return False
    return True


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def fail(error=None, status=400, **extra):
    payload = {"ok": False}
    if error:
        payload["error"] = error
    payload.update(extra)
    return jsonify(payload), status


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    if not is_int(uid):
        # A session cookie left over from the old Firestore version: just drop it.
        session.clear()
        return None
    doc = store.get(uid)
    if doc is None:
        session.clear()
        return None
    return uid, doc


def clean_profile(profile):
    p = profile if isinstance(profile, dict) else {}
    return {
        "name": p.get("name", ""),
        "email": p.get("email", ""),
        "phone": p.get("phone", ""),
        "code": p.get("code", "+63"),
    }


class RateLimiter:
    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self._hits = {}
        self._lock = threading.Lock()

    def _recent(self, key):
        now = time.time()
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def blocked(self, key):
        with self._lock:
            return len(self._recent(key)) >= self.limit

    def hit(self, key):
        with self._lock:
            hits = self._recent(key)
            hits.append(time.time())
            self._hits[key] = hits

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)


login_mail_limiter = RateLimiter(limit=5, window=3600)
login_limiter = RateLimiter(limit=5, window=300)
signup_limiter = RateLimiter(limit=20, window=3600)
reset_limiter = RateLimiter(limit=5, window=3600)
reset_try_limiter = RateLimiter(limit=10, window=600)

@app.before_request
def require_json_for_changes():
    if request.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if not request.is_json:
            return fail("json_required", 415)

@app.after_request
def add_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp

@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return fail("not_found", 404)
    return "Not found", 404

@app.errorhandler(413)
def too_large(_):
    return fail("too_large", 413)

@app.errorhandler(500)
def server_error(_):
    return fail("server_error", 500)

@app.errorhandler(DatabaseUnavailable)
def database_down(error):
    return fail("database_unavailable", 503)

@app.get("/api/health")
def health():
    return jsonify(ok=True)

@app.get("/api/me")
def me():
    found = current_user()
    if not found:
        return jsonify(ok=False, user=None), 401
    _, doc = found
    return jsonify(ok=True, user={
        "id": doc["id"],
        "profile": clean_profile(doc.get("profile")),
        "data": doc.get("data", {}),
    })

@app.post("/api/signup")
def signup():
    ip = request.remote_addr or "unknown"
    if signup_limiter.blocked(ip):
        return fail("too_many", 429)

    data = body()
    login_id = normalize(data.get("id"))
    password = data.get("password")
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    name = str(profile.get("name", "")).strip()

    if not name or len(name) > 200:
        return fail("invalid_name")
    if not valid_id(login_id):
        return fail("invalid_id")
    if not valid_password(password):
        return fail("weak_password")

    signup_limiter.hit(ip)

    doc = {
        "password_hash": generate_password_hash(password),
        "profile": {
            "name": name,
            "email": login_id,
            "phone": "",
            "code": "+63",
        },
    }
    if store.create(login_id, doc) is None:
        return fail("exists", 409)
    return jsonify(ok=True, id=login_id), 201


@app.post("/api/verify")
def verify():
    data = body()
    login_id = normalize(data.get("id"))
    password = data.get("password")
    if not login_id or not isinstance(password, str):
        return fail(reason="bad", status=400)
    key = f"{request.remote_addr}|{login_id}"
    if login_limiter.blocked(key):
        return fail(reason="too_many", status=429)

    doc = store.get_by_login(login_id)
    if doc is None:
        login_limiter.hit(key)
        return fail(reason="not_found", status=404)
    if not check_password_hash(doc.get("password_hash", ""), password):
        login_limiter.hit(key)
        return fail("bad", 401)
    login_limiter.reset(key)

    uid = doc["uid"]
    if LOGIN_EMAIL_VERIFICATION:
        th, error = issue_login_link(uid, login_id)
        if error:
            session.pop("verified", None)
            return fail(error, 503 if error == "email_unavailable" else 429)
        session["verified"] = {"uid": uid, "t": time.time(), "th": th}
        return jsonify(ok=True, id=login_id, needs_email=True, email=mask_email(login_id))
    session["verified"] = {"uid": uid, "t": time.time()}
    return jsonify(ok=True, id=login_id, needs_email=False)


@app.post("/api/login")
def login():
    verified = session.get("verified") or {}
    uid = verified.get("uid")
    th = verified.get("th")
    window = LOGIN_LINK_MINUTES * 60 if th else VERIFY_WINDOW
    if not uid or time.time() - verified.get("t", 0) > window:
        session.pop("verified", None)
        return fail("not_verified", 401)
    if th:
        challenge = store.get_challenge(th)
        if not challenge or challenge.get("uid") != uid or challenge.get("exp", 0) < time.time():
            session.pop("verified", None)
            return fail("not_verified", 401)
        if not challenge.get("confirmed"):
            return fail("email_not_confirmed", 401)
        store.delete_challenge(th)
    doc = store.get(uid)
    if doc is None:
        session.clear()
        return fail("not_found", 404)
    asked = normalize(body().get("id"))
    if asked and asked != normalize(doc.get("id")):
        return fail("not_verified", 403)
    session.clear()
    session["uid"] = uid
    session.permanent = True
    return jsonify(ok=True)

def mask_email(email):
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"

def issue_login_link(uid, email):
    if login_mail_limiter.blocked(uid):
        return None, "too_many"
    login_mail_limiter.hit(uid)
    old = (session.get("verified") or {}).get("th")
    if old:
        store.delete_challenge(old)
    token = secrets.token_urlsafe(32)
    th = token_hash(token)
    store.put_challenge(th, {"uid": uid, "exp": time.time() + LOGIN_LINK_MINUTES * 60, "confirmed": False})
    base = os.getenv("PUBLIC_URL", request.host_url).rstrip("/")
    link = f"{base}/confirm-login.html?token={token}"
    try:
        sent = send_email(
            email,
            "Confirm your Medic Care login",
            f"Someone is logging in to your Medic Care account. If this is you, open this link "
            f"(valid for {LOGIN_LINK_MINUTES} minutes):\n\n{link}\n\n"
            "If this was not you, ignore this email and change your password.",
        )
    except Exception:
        store.delete_challenge(th)
        return None, "email_unavailable"
    if not sent:
        if env_flag("FLASK_DEBUG"):
            return th, None
        store.delete_challenge(th)
        return None, "email_unavailable"
    return th, None

@app.post("/api/confirm-login")
def confirm_login():
    ip = request.remote_addr or "?"
    if reset_try_limiter.blocked(ip):
        return fail("too_many", 429)
    reset_try_limiter.hit(ip)
    token = body().get("token")
    if not isinstance(token, str) or not token:
        return fail("invalid_token", 400)
    th = token_hash(token)
    challenge = store.get_challenge(th)
    if not challenge or challenge.get("exp", 0) < time.time():
        return fail("invalid_token", 400)
    store.confirm_challenge(th)
    return jsonify(ok=True)

@app.get("/api/login-status")
def login_status():
    th = (session.get("verified") or {}).get("th")
    if not th:
        return jsonify(ok=True, confirmed=False, expired=True)
    challenge = store.get_challenge(th)
    if not challenge or challenge.get("exp", 0) < time.time():
        return jsonify(ok=True, confirmed=False, expired=True)
    return jsonify(ok=True, confirmed=bool(challenge.get("confirmed")), expired=False)

@app.post("/api/login/resend")
def login_resend():
    verified = session.get("verified") or {}
    uid = verified.get("uid")
    if not uid or not verified.get("th") or time.time() - verified.get("t", 0) > LOGIN_LINK_MINUTES * 60:
        return fail("not_verified", 401)
    doc = store.get(uid)
    if not doc:
        return fail("not_verified", 401)
    th, error = issue_login_link(uid, doc["id"])
    if error:
        return fail(error, 503 if error == "email_unavailable" else 429)
    session["verified"] = {"uid": uid, "t": time.time(), "th": th}
    return jsonify(ok=True)

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

def validate_profile_patch(patch):
    out = {}
    if "name" in patch:
        name = str(patch["name"] or "").strip()
        if not name or len(name) > 200:
            return None, "invalid_name"
        out["name"] = name
    if "email" in patch:
        email = str(patch["email"] or "").strip().lower()
        if email and (len(email) > 254 or not EMAIL_RE.match(email)):
            return None, "invalid_email"
        out["email"] = email
    if "phone" in patch:
        phone = str(patch["phone"] or "").strip()
        if len(phone) > 30 or not re.fullmatch(r"[0-9+\-().\s]*", phone):
            return None, "invalid_phone"
        out["phone"] = phone
    if "code" in patch:
        code = str(patch["code"] or "").strip()
        if not re.fullmatch(r"\+?\d{1,4}", code):
            return None, "invalid_code"
        out["code"] = code
    return out, None

@app.put("/api/profile")
def save_profile():
    found = current_user()
    if not found:
        return fail("unauthorized", 401)
    uid, doc = found
    fields, error = validate_profile_patch(body())
    if error:
        return fail(error)
    profile = {**clean_profile(doc.get("profile")), **fields}
    store.update(uid, {"profile": profile})
    return jsonify(ok=True, profile=profile)

@app.post("/api/password/check")
def password_check():
    found = current_user()
    if not found:
        return fail("unauthorized", 401)
    uid, doc = found
    password = body().get("password")
    key = f"pw|{uid}"
    if login_limiter.blocked(key):
        return fail("too_many", 429)
    if not isinstance(password, str) or not check_password_hash(doc["password_hash"], password):
        login_limiter.hit(key)
        return fail("bad", 401)
    login_limiter.reset(key)
    session["pw_ok"] = time.time()
    return jsonify(ok=True)

@app.put("/api/password")
def password_change():
    found = current_user()
    if not found:
        return fail("unauthorized", 401)
    uid, _ = found
    if time.time() - session.get("pw_ok", 0) > VERIFY_WINDOW:
        return fail("current_password_required", 403)
    password = body().get("password")
    if not valid_password(password):
        return fail("weak_password")
    store.update(uid, {"password_hash": generate_password_hash(password)})
    session.pop("pw_ok", None)
    return jsonify(ok=True)

@app.delete("/api/account")
def delete_account():
    found = current_user()
    if not found:
        return fail("unauthorized", 401)
    uid, _ = found
    store.delete(uid)
    session.clear()
    return jsonify(ok=True)

@app.put("/api/data/<key>")
def save_data(key):
    found = current_user()
    if not found:
        return fail("unauthorized", 401)
    uid, doc = found
    expected = ALLOWED_DATA.get(key)
    if expected is None:
        return fail("invalid_key", 400)
    value = body().get("value")
    if not isinstance(value, expected):
        return fail("invalid_value", 400)
    if key == "appointments":
        if len(value) > MAX_APPOINTMENTS or not all(valid_appointment(a) for a in value):
            return fail("invalid_value", 400)
    if len(json.dumps(value)) > MAX_DATA_BYTES:
        return fail("too_large", 413)
    if key == "appointments":
        old_keys = slot_keys((doc.get("data") or {}).get("appointments"))
        new_keys = slot_keys(value)
        claimed = []
        for k in new_keys - old_keys:
            if not store.claim_slot(k, uid):
                for done in claimed:
                    store.release_slot(done, uid)
                return fail("slot_taken", 409)
            claimed.append(k)
        store.save_appointments(uid, value)
        for k in old_keys - new_keys:
            store.release_slot(k, uid)
    return jsonify(ok=True)

def slot_keys(appointments):
    keys = set()
    for a in appointments if isinstance(appointments, list) else []:
        if not isinstance(a, dict) or str(a.get("status", "")).lower() == "cancelled":
            continue
        doctor, date, slot = (str(a.get(f, "")).strip() for f in ("doctorName", "date", "time"))
        if doctor and date and slot:
            keys.add(hashlib.sha256(f"{doctor}|{date}|{slot}".encode("utf-8")).hexdigest())
    return keys

def send_email(to, subject, text):
    import smtplib
    import ssl
    from email.message import EmailMessage
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("RESET_EMAIL_FROM", user or "")
    if not all((host, user, password, sender)):
        return False
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, sender, to
    message.set_content(text)
    port = int(os.getenv("SMTP_PORT", "587"))
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as smtp:
            smtp.login(user, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls(context=context)
            smtp.login(user, password)
            smtp.send_message(message)
    return True

def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

@app.post("/api/forgot-password")
def forgot_password():
    ip = request.remote_addr or "?"
    if reset_limiter.blocked(ip):
        return fail("too_many", 429)
    email = body().get("email")
    if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()):
        return fail("invalid_email")
    email = email.strip().lower()
    reset_limiter.hit(ip)
    account = store.get_by_login(email)
    if account is None:
        return jsonify(ok=True)
    uid = account["uid"]
    token = secrets.token_urlsafe(32)
    store.put_reset(token_hash(token), {"uid": uid, "exp": time.time() + RESET_TOKEN_MINUTES * 60})
    base = os.getenv("PUBLIC_URL", request.host_url).rstrip("/")
    link = f"{base}/reset-password.html?token={token}"
    try:
        sent = send_email(
            email,
            "Reset your Medic Care password",
            f"Use this link to reset your Medic Care password (valid for {RESET_TOKEN_MINUTES} minutes):\n\n"
            f"{link}\n\nIf you did not request this, you can ignore this email.",
        )
    except Exception:
        return fail("reset_unavailable", 503)
    if not sent:
        if env_flag("FLASK_DEBUG"):
            return jsonify(ok=True)
        return fail("reset_unavailable", 503)
    return jsonify(ok=True)

@app.post("/api/reset-password")
def reset_password():
    ip = request.remote_addr or "?"
    if reset_try_limiter.blocked(ip):
        return fail("too_many", 429)
    reset_try_limiter.hit(ip)
    data = body()
    token, password = data.get("token"), data.get("password")
    if not isinstance(token, str) or not token:
        return fail("invalid_token", 400)
    if not valid_password(password):
        return fail("weak_password")
    th = token_hash(token)
    record = store.get_reset(th)
    if not record or record.get("exp", 0) < time.time():
        if record:
            store.delete_reset(th)
        return fail("invalid_token", 400)
    if not store.update(record["uid"], {"password_hash": generate_password_hash(password)}):
        store.delete_reset(th)
        return fail("invalid_token", 400)
    store.delete_reset(th)
    session.clear()
    return jsonify(ok=True)

@app.get("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:filename>")
def site_file(filename):
    path = Path(filename)
    if any(part.startswith(".") for part in path.parts) or path.suffix.lower() not in STATIC_EXTENSIONS:
        abort(404)
    resp = send_from_directory(FRONTEND_DIR, filename)
    if path.suffix.lower() in (".html", ".js"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp

if __name__ == "__main__":
    port: int = int(os.environ.get("PORT", "10000"))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=env_flag("FLASK_DEBUG")
    )
