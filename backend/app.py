import hashlib
import json
import os
import re
import secrets
import string
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import pymysql
import requests
from PIL import Image, UnidentifiedImageError
from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, request, send_from_directory, session
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
ALLOWED_DATA = {"appointments": list, "profileExtra": dict}
MAX_APPOINTMENTS = 500
MAX_DATA_BYTES = 1_000_000
MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
MAX_PROFILE_PHOTO_PIXELS = 16_000_000
PROFILE_PHOTO_FORMATS = {"JPEG", "PNG", "WEBP"}
SESSION_DAYS = 30
VERIFY_WINDOW = 600
LOGIN_LINK_MINUTES = 15
RESET_TOKEN_MINUTES = 30
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
STATIC_EXTENSIONS = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp"}

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "noreply@mediccare.com")
pending_signups = {}

@contextmanager
def db_cursor():
    try:
        connection = pymysql.connect(
            **DB_CONFIG,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
    except pymysql.MySQLError as error:
        print("\nMYSQL CONNECTION ERROR")
        print(error)
        print("\n")
        raise DatabaseUnavailable from error
    try:
        with connection.cursor() as cursor:
            yield cursor
        connection.commit()
    except pymysql.MySQLError as error:
        connection.rollback()
        print("\nMYSQL QUERY ERROR")
        print(error)
        print("\n")
        raise DatabaseUnavailable from error
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

def as_text(value, limit):
    return str(value if value is not None else "")[:limit]

def as_date(value):
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
        as_text(appointment.get("status") or "Pending", 20),
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
    def _profile_details(self, cursor, user_id):
        cursor.execute(
            "SELECT alt_phone, address, gender, bday_month, bday_day, bday_year "
            "FROM user_profile_details WHERE user_id=%s",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return {
                "altPhone": "",
                "address": "",
                "gender": "",
                "bdayMonth": None,
                "bdayDay": None,
                "bdayYear": None,
            }
        return {
            "altPhone": row["alt_phone"],
            "address": row["address"],
            "gender": row["gender"],
            "bdayMonth": row["bday_month"],
            "bdayDay": row["bday_day"],
            "bdayYear": row["bday_year"],
        }

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
                "role": row.get("role", "user"),
                "status": row.get("status", "active"),
            },
            "data": {
                "appointments": self._appointments(cursor, row["id"]),
                "profileExtra": self._profile_details(cursor, row["id"]),
            },
            "created_at": to_epoch(row["created_at"]),
        }

    def get(self, uid):
        ensure_profile_details_table()
        with db_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id=%s", (uid,))
            row = cursor.fetchone()
            return self._user_doc(cursor, row) if row else None

    def get_by_login(self, login_id):
        ensure_profile_details_table()
        with db_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE login_id=%s", (login_id,))
            row = cursor.fetchone()
            return self._user_doc(cursor, row) if row else None

    def create(self, login_id, doc):
        profile = doc.get("profile") or {}
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO users (login_id, password_hash, name, email, phone, code, role, status)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    login_id,
                    doc["password_hash"],
                    as_text(profile.get("name"), 200),
                    as_text(profile.get("email"), 254),
                    as_text(profile.get("phone"), 30),
                    as_text(profile.get("code") or "+63", 8),
                    as_text(profile.get("role") or "user", 20),
                    as_text(profile.get("status") or "active", 20),
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
            for column, limit in (("name", 200), ("email", 254), ("phone", 30), ("code", 8), ("role", 20), ("status", 20)):
                if column in profile:
                    sets.append(f"{column}=%s")
                    params.append(as_text(profile[column], limit))
        if not sets:
            return True
        params.append(uid)
        with db_cursor() as cursor:
            cursor.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=%s", tuple(params))
            if cursor.rowcount > 0:
                return True
            cursor.execute("SELECT 1 FROM users WHERE id=%s", (uid,))
            return cursor.fetchone() is not None

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

    def save_profile_details(self, uid, details):
        ensure_profile_details_table()
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_profile_details "
                "(user_id, alt_phone, address, gender, bday_month, bday_day, bday_year) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE alt_phone=VALUES(alt_phone), "
                "address=VALUES(address), gender=VALUES(gender), "
                "bday_month=VALUES(bday_month), bday_day=VALUES(bday_day), "
                "bday_year=VALUES(bday_year)",
                (
                    uid,
                    details["altPhone"],
                    details["address"],
                    details["gender"],
                    details["bdayMonth"],
                    details["bdayDay"],
                    details["bdayYear"],
                ),
            )
        return True

_notifications_table_ready = False
_notifications_table_lock = threading.Lock()
_profile_photos_table_ready = False
_profile_photos_table_lock = threading.Lock()
_profile_details_table_ready = False
_profile_details_table_lock = threading.Lock()

def ensure_notifications_table():
    global _notifications_table_ready
    with _notifications_table_lock:
        if _notifications_table_ready:
            return
        with db_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    user_id INT UNSIGNED NOT NULL,
                    appointment_id INT UNSIGNED NULL,
                    type VARCHAR(50) NOT NULL,
                    doctor_name VARCHAR(200) NOT NULL DEFAULT '',
                    appointment_date DATE NULL,
                    appointment_time VARCHAR(40) NOT NULL DEFAULT '',
                    reason VARCHAR(500) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    read_at DATETIME NULL,
                    PRIMARY KEY (id),
                    KEY idx_notifications_user_read_created (user_id, read_at, created_at),
                    CONSTRAINT fk_notifications_user
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='notifications' AND COLUMN_NAME='reason'"
            )
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE notifications ADD COLUMN reason VARCHAR(500) NOT NULL DEFAULT ''")
        _notifications_table_ready = True

def ensure_profile_photos_table():
    global _profile_photos_table_ready
    with _profile_photos_table_lock:
        if _profile_photos_table_ready:
            return
        with db_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profile_photos (
                    user_id INT UNSIGNED NOT NULL,
                    image_data MEDIUMBLOB NOT NULL,
                    mime_type VARCHAR(32) NOT NULL,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id),
                    CONSTRAINT fk_profile_photos_user
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        _profile_photos_table_ready = True

def ensure_profile_details_table():
    global _profile_details_table_ready
    with _profile_details_table_lock:
        if _profile_details_table_ready:
            return
        with db_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profile_details (
                    user_id INT UNSIGNED NOT NULL,
                    alt_phone VARCHAR(30) NOT NULL DEFAULT '',
                    address VARCHAR(500) NOT NULL DEFAULT '',
                    gender VARCHAR(30) NOT NULL DEFAULT '',
                    bday_month TINYINT UNSIGNED NULL,
                    bday_day TINYINT UNSIGNED NULL,
                    bday_year SMALLINT UNSIGNED NULL,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id),
                    CONSTRAINT fk_user_profile_details_user
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        _profile_details_table_ready = True

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
    MAX_CONTENT_LENGTH=MAX_PROFILE_PHOTO_BYTES + 64 * 1024,
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
    return isinstance(v, int) and not isinstance(v, bool)

def is_text(v, max_len):
    return isinstance(v, str) and len(v) <= max_len

def valid_appointment(a):
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
        session.clear()
        return None
    doc = store.get(uid)
    if doc is None or doc["profile"].get("status") == "banned":
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
        "role": p.get("role", "user"),
        "status": p.get("status", "active"),
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
admin_login_mail_limiter = RateLimiter(limit=5, window=3600)
login_limiter = RateLimiter(limit=5, window=300)
signup_limiter = RateLimiter(limit=20, window=3600)
reset_limiter = RateLimiter(limit=5, window=3600)
reset_try_limiter = RateLimiter(limit=10, window=600)

@app.before_request
def require_json_for_changes():
    if request.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.path == "/api/profile/photo" and request.method == "POST":
            if request.headers.get("X-Requested-With") != "XMLHttpRequest":
                return fail("request_header_required", 415)
        if request.path != "/api/profile/photo" and not request.is_json:
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
def server_error(error):
    import traceback
    traceback.print_exc()
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
        return jsonify(ok=True, user=None)
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

    code = ''.join(secrets.choice(string.digits) for _ in range(6))
    pending_signups[login_id] = {
        "code": code,
        "exp": time.time() + 600,
        "name": name,
        "password_hash": generate_password_hash(password)
    }

    sent = send_email(login_id, "Your Medic Care Verification Code", f"Your verification code is: {code}\n\nThis code expires in 10 minutes.")
    
    if not sent:
        if not BREVO_API_KEY and not os.getenv("SMTP_HOST"):
             return jsonify(ok=True, needs_verification=True) 
        return fail("email_unavailable", 503)

    return jsonify(ok=True, needs_verification=True), 200

@app.post("/api/signup/verify")
def verify_signup():
    data = body()
    login_id = normalize(data.get("id"))
    user_code = data.get("code")

    record = pending_signups.get(login_id)
    
    if not record or record["exp"] < time.time():
        return fail("expired_code", 400)

    if record["code"] != user_code:
        return fail("invalid_code", 400)
        
    doc = {
        "password_hash": record["password_hash"],
        "profile": {
            "name": record["name"],
            "email": login_id,
            "phone": "",
            "code": "+63",
            "role": "user",
            "status": "active"
        },
    }
    
    uid = store.create(login_id, doc)
    if uid is None:
        return fail("exists", 409)
        
    del pending_signups[login_id]
    session.clear()
    session["uid"] = uid
    session.permanent = True
    return jsonify(ok=True), 201

@app.post("/api/admin/login")
def admin_login():
    data = body()
    login_id = normalize(data.get("id"))
    password = data.get("password")

    key = f"{request.remote_addr or '?'}|{login_id}"
    if login_limiter.blocked(key):
        return fail("too_many", 429)

    doc = store.get_by_login(login_id)

    if not doc or not check_password_hash(doc["password_hash"], password):
        login_limiter.hit(key)
        return fail("invalid_credentials", 401)

    if doc["profile"].get("role") != "admin":
        return fail("not_admin", 403)

    login_limiter.reset(key)
    uid = doc["uid"]
    if admin_login_mail_limiter.blocked(uid):
        return fail("too_many", 429)

    code = ''.join(secrets.choice(string.digits) for _ in range(6))
    admin_login_mail_limiter.hit(uid)
    try:
        sent = send_email(login_id, "Admin Login Code", f"Your admin login code is: {code}")
    except Exception as error:
        app.logger.warning("Admin login email delivery failed: %s", type(error).__name__)
        sent = False

    if not sent:
        pending_signups.pop(f"admin_{login_id}", None)
        return fail("email_unavailable", 503)

    pending_signups[f"admin_{login_id}"] = {
        "code": code,
        "exp": time.time() + 600,
        "uid": uid,
        "email": login_id
    }

    return jsonify(ok=True, needs_verification=True)

@app.post("/api/admin/verify")
def admin_verify():
    data = body()
    login_id = normalize(data.get("id"))
    user_code = data.get("code")
    
    record = pending_signups.get(f"admin_{login_id}")
    
    if not record or record["exp"] < time.time():
        return fail("expired_code", 400)
    if record["code"] != user_code:
        return fail("invalid_code", 400)
        
    session.clear()
    session["uid"] = record["uid"]
    session["is_admin"] = True
    session.permanent = True
    del pending_signups[f"admin_{login_id}"]
    
    return jsonify(ok=True)

@app.get("/api/admin/users")
def admin_get_users():
    if not session.get("is_admin"):
        return fail("unauthorized", 401)
        
    with db_cursor() as cursor:
        cursor.execute("SELECT id, login_id, name, email, phone, role, status, created_at FROM users")
        users = cursor.fetchall()
        for u in users:
            u["created_at"] = u["created_at"].strftime("%Y-%m-%d") if u["created_at"] else ""
            u["role"] = u.get("role", "user")
            u["status"] = u.get("status", "active")
        return jsonify(ok=True, users=users)

@app.put("/api/admin/users/<int:uid>")
def admin_update_user(uid):
    if not session.get("is_admin"):
        return fail("unauthorized", 401)

    data = body()
    name = data.get("name")
    email = data.get("email")
    role = data.get("role")

    if role not in ["user", "admin"]:
        return fail("invalid_role", 400)

    profile = {}
    if name: profile["name"] = name
    if email: profile["email"] = email
    if role: profile["role"] = role

    if profile:
        store.update(uid, {"profile": profile})
    return jsonify(ok=True)

@app.put("/api/admin/users/<int:uid>/status")
def admin_update_user_status(uid):
    if not session.get("is_admin"):
        return fail("unauthorized", 401)
        
    new_status = body().get("status")
    if new_status not in ["active", "banned"]:
        return fail("invalid_status", 400)
        
    with db_cursor() as cursor:
        cursor.execute("UPDATE users SET status=%s WHERE id=%s", (new_status, uid))
        return jsonify(ok=True)

@app.delete("/api/admin/users/<int:uid>")
def admin_delete_user(uid):
    if not session.get("is_admin"):
        return fail("unauthorized", 401)
    store.delete(uid)
    return jsonify(ok=True)

@app.get("/api/admin/appointments")
def admin_get_appointments():
    if not session.get("is_admin"):
        return fail("unauthorized", 401)
        
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT a.*, u.name as patient_name, u.login_id as patient_email 
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            ORDER BY a.appt_date DESC, a.id DESC
        """)
        rows = cursor.fetchall()
        
        appointments = []
        for row in rows:
            appointments.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "patient_name": row["patient_name"],
                "patient_email": row["patient_email"],
                "doctor_name": row["doctor_name"],
                "spec": row["spec"],
                "service": row["service"],
                "specific_service": row["specific_service"],
                "date": row["appt_date"].isoformat() if row["appt_date"] else "",
                "time": row["appt_time"],
                "status": row["status"],
                "patient_first": row["patient_first"],
                "patient_middle": row["patient_middle"],
                "patient_last": row["patient_last"],
                "patient_suffix": row["patient_suffix"],
                "patient_dob": row["patient_dob"].isoformat() if row["patient_dob"] else "",
                "patient_sex": row["patient_sex"],
                "patient_phone": row["patient_phone"]
            })
        return jsonify(ok=True, appointments=appointments)

@app.put("/api/admin/appointments/<int:appt_id>")
def admin_update_appointment(appt_id):
    if not session.get("is_admin"):
        return fail("unauthorized", 401)

    new_status = body().get("status")
    if new_status not in ["Pending", "Confirmed", "Completed", "Cancelled"]:
        return fail("invalid_status", 400)
    reason = body().get("reason", "")
    if not isinstance(reason, str):
        return fail("invalid_reason", 400)
    reason = reason.strip()
    if len(reason) > 500:
        return fail("invalid_reason", 400)

    ensure_notifications_table()
    with db_cursor() as cursor:
        cursor.execute("SELECT * FROM appointments WHERE id=%s FOR UPDATE", (appt_id,))
        appointment = cursor.fetchone()
        if not appointment:
            return fail("appointment_not_found", 404)

        old_status = appointment["status"]
        allowed_transitions = {
            "Pending": {"Confirmed", "Cancelled"},
            "Confirmed": {"Completed", "Cancelled"},
            "Completed": set(),
            "Cancelled": set(),
        }
        if new_status == old_status:
            return jsonify(ok=True)
        if new_status not in allowed_transitions.get(old_status, set()):
            return fail("invalid_status_transition", 409)
        if old_status == "Pending" and new_status == "Cancelled" and not reason:
            return fail("reason_required", 400)

        if new_status == "Confirmed":
            cursor.execute(
                "SELECT id FROM appointments WHERE doctor_name=%s AND appt_date=%s AND appt_time=%s"
                " AND status IN ('Pending', 'Confirmed') AND id<>%s LIMIT 1 FOR UPDATE",
                (
                    appointment["doctor_name"],
                    appointment["appt_date"],
                    appointment["appt_time"],
                    appt_id,
                ),
            )
            if cursor.fetchone():
                return fail("slot_unavailable", 409)

        cursor.execute("UPDATE appointments SET status=%s WHERE id=%s", (new_status, appt_id))
        if new_status == "Confirmed":
            notification_type = "appointment_confirmed"
        elif old_status == "Pending":
            notification_type = "appointment_unavailable"
        elif new_status == "Cancelled":
            notification_type = "appointment_cancelled"
        else:
            notification_type = None
        if notification_type:
            cursor.execute(
                "INSERT INTO notifications "
                "(user_id, appointment_id, type, doctor_name, appointment_date, appointment_time, reason) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    appointment["user_id"],
                    appointment["client_id"],
                    notification_type,
                    appointment["doctor_name"],
                    appointment["appt_date"],
                    appointment["appt_time"],
                    reason if notification_type == "appointment_unavailable" else "",
                ),
            )
        if new_status == "Cancelled":
            slot_key = hashlib.sha256(
                f"{appointment['doctor_name']}|{appointment['appt_date'].isoformat() if appointment['appt_date'] else ''}|"
                f"{appointment['appt_time']}".encode("utf-8")
            ).hexdigest()
            cursor.execute(
                "DELETE FROM appointment_slots WHERE slot_key=%s AND user_id=%s",
                (slot_key, appointment["user_id"]),
            )
        return jsonify(ok=True)

@app.delete("/api/admin/appointments/<int:appt_id>")
def admin_delete_appointment(appt_id):
    if not session.get("is_admin"):
        return fail("unauthorized", 401)
        
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM appointments WHERE id=%s", (appt_id,))
        return jsonify(ok=True)

@app.get("/api/notifications")
def get_notifications():
    found = current_user()
    if not found:
        return fail("unauthorized", 401)
    uid, _ = found
    ensure_notifications_table()
    with db_cursor() as cursor:
        cursor.execute(
            "SELECT id, type, doctor_name, appointment_date, appointment_time, reason, created_at, read_at "
            "FROM notifications WHERE user_id=%s ORDER BY id DESC LIMIT 50",
            (uid,),
        )
        notifications = [
            {
                "id": row["id"],
                "type": row["type"],
                "doctor_name": row["doctor_name"],
                "date": row["appointment_date"].isoformat() if row["appointment_date"] else "",
                "time": row["appointment_time"],
                "reason": row["reason"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                "read": row["read_at"] is not None,
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            "SELECT COUNT(*) AS unread_count FROM notifications WHERE user_id=%s AND read_at IS NULL",
            (uid,),
        )
        unread_count = cursor.fetchone()["unread_count"]
    return jsonify(ok=True, notifications=notifications, unread_count=unread_count)

@app.post("/api/notifications/<int:notification_id>/read")
def mark_notification_read(notification_id):
    found = current_user()
    if not found:
        return fail("unauthorized", 401)
    uid, _ = found
    ensure_notifications_table()
    with db_cursor() as cursor:
        cursor.execute(
            "UPDATE notifications SET read_at=COALESCE(read_at, CURRENT_TIMESTAMP) "
            "WHERE id=%s AND user_id=%s",
            (notification_id, uid),
        )
        if not cursor.rowcount:
            cursor.execute(
                "SELECT id FROM notifications WHERE id=%s AND user_id=%s",
                (notification_id, uid),
            )
            if not cursor.fetchone():
                return fail("notification_not_found", 404)
    return jsonify(ok=True)

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
    
    if doc["profile"].get("status") == "banned":
        return fail("account_banned", 403)

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
    
    if doc["profile"].get("status") == "banned":
        session.clear()
        return fail("account_banned", 403)

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
    resp = jsonify(ok=True)
    resp.set_cookie(
        "medic_care_session", 
        "", 
        expires=0, 
        path="/", 
        httponly=True, 
        samesite="Lax", 
        secure=env_flag("SESSION_COOKIE_SECURE")
    )
    return resp

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

def validate_profile_details(details):
    alt_phone = details.get("altPhone", "")
    address = details.get("address", "")
    gender = details.get("gender", "")
    if not isinstance(alt_phone, str) or len(alt_phone) > 30 or not re.fullmatch(r"[0-9+\-().\s]*", alt_phone):
        return None, "invalid_alt_phone"
    if not isinstance(address, str) or len(address) > 500:
        return None, "invalid_address"
    if gender not in ("", "Male", "Female", "Prefer Not To Say"):
        return None, "invalid_gender"

    month = details.get("bdayMonth")
    day = details.get("bdayDay")
    year = details.get("bdayYear")
    birth_date = (month, day, year)
    if all(value is None for value in birth_date):
        pass
    elif not all(is_int(value) for value in birth_date):
        return None, "invalid_birth_date"
    else:
        try:
            parsed = datetime(year, month, day).date()
        except ValueError:
            return None, "invalid_birth_date"
        if parsed > datetime.now().date():
            return None, "invalid_birth_date"

    return {
        "altPhone": alt_phone.strip(),
        "address": address.strip(),
        "gender": gender,
        "bdayMonth": month,
        "bdayDay": day,
        "bdayYear": year,
    }, None

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
    if not store.update(uid, {"profile": profile}):
        return fail("profile_not_saved", 500)
    return jsonify(ok=True, profile=profile)

def normalize_profile_photo(image_bytes):
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format not in PROFILE_PHOTO_FORMATS:
                return None, "unsupported_image_type"
            if image.width * image.height > MAX_PROFILE_PHOTO_PIXELS:
                return None, "image_dimensions_too_large"
            image.verify()

        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
            output = BytesIO()
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            if has_alpha:
                image.convert("RGBA").save(output, format="PNG", optimize=True)
                mime_type = "image/png"
            else:
                image.convert("RGB").save(output, format="JPEG", quality=85, optimize=True)
                mime_type = "image/jpeg"
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError, ValueError):
        return None, "invalid_image"

    normalized = output.getvalue()
    if len(normalized) > MAX_PROFILE_PHOTO_BYTES:
        return None, "photo_too_large"
    return (normalized, mime_type), None

@app.route("/api/profile/photo", methods=["GET", "POST", "DELETE"])
def profile_photo():
    found = current_user()
    if not found:
        return fail("unauthorized", 401)
    uid, _ = found
    ensure_profile_photos_table()

    if request.method == "GET":
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT image_data, mime_type FROM profile_photos WHERE user_id=%s",
                (uid,),
            )
            photo = cursor.fetchone()
        if not photo:
            return fail("photo_not_found", 404)
        if photo["mime_type"] not in ("image/jpeg", "image/png"):
            app.logger.error("Invalid stored profile photo MIME type for user %s", uid)
            return fail("invalid_stored_photo", 500)
        return Response(photo["image_data"], mimetype=photo["mime_type"])

    if request.method == "DELETE":
        with db_cursor() as cursor:
            cursor.execute("DELETE FROM profile_photos WHERE user_id=%s", (uid,))
        return jsonify(ok=True)

    photo_file = request.files.get("photo")
    if photo_file is None:
        return fail("photo_required")
    image_bytes = photo_file.stream.read(MAX_PROFILE_PHOTO_BYTES + 1)
    if len(image_bytes) > MAX_PROFILE_PHOTO_BYTES:
        return fail("photo_too_large", 413)
    normalized, error = normalize_profile_photo(image_bytes)
    if error:
        return fail(error, 413 if error == "photo_too_large" else 400)
    image_data, mime_type = normalized
    with db_cursor() as cursor:
        cursor.execute(
            "INSERT INTO profile_photos (user_id, image_data, mime_type) "
            "VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE "
            "image_data=VALUES(image_data), mime_type=VALUES(mime_type), "
            "updated_at=CURRENT_TIMESTAMP",
            (uid, image_data, mime_type),
        )
    return jsonify(ok=True, photo="/api/profile/photo")

@app.get("/api/admin/users/<int:uid>/photo")
def admin_user_photo(uid):
    if not session.get("is_admin"):
        return fail("unauthorized", 401)
    ensure_profile_photos_table()
    with db_cursor() as cursor:
        cursor.execute(
            "SELECT image_data, mime_type FROM profile_photos WHERE user_id=%s",
            (uid,),
        )
        photo = cursor.fetchone()
    if not photo:
        return fail("photo_not_found", 404)
    if photo["mime_type"] not in ("image/jpeg", "image/png"):
        app.logger.error("Invalid stored profile photo MIME type for user %s", uid)
        return fail("invalid_stored_photo", 500)
    return Response(photo["image_data"], mimetype=photo["mime_type"])

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
    if key == "profileExtra":
        details, error = validate_profile_details(value)
        if error:
            return fail(error, 400)
        store.save_profile_details(uid, details)
        return jsonify(ok=True, value=details)
    if key == "appointments":
        if len(value) > MAX_APPOINTMENTS or not all(valid_appointment(a) for a in value):
            return fail("invalid_value", 400)
        old_appointments = (doc.get("data") or {}).get("appointments", [])
        old_by_id = {a.get("id"): a for a in old_appointments if isinstance(a, dict)}
        seen_ids = set()
        normalized_appointments = []
        for appointment in value:
            appointment = dict(appointment)
            appointment_id = appointment.get("id")
            if appointment_id in seen_ids:
                return fail("invalid_value", 400)
            seen_ids.add(appointment_id)
            previous = old_by_id.get(appointment_id)
            if previous is None:
                appointment["status"] = "Pending"
            else:
                schedule_changed = any(
                    appointment.get(field) != previous.get(field)
                    for field in ("doctorName", "date", "time")
                )
                requested_status = str(appointment.get("status", "")).lower()
                previous_status = str(previous.get("status", "Pending"))
                if previous_status in {"Cancelled", "Completed"} and (
                    schedule_changed or requested_status != previous_status.lower()
                ):
                    return fail("invalid_value", 400)
                if requested_status == "cancelled" and previous_status not in {"Cancelled", "Completed"}:
                    appointment["status"] = "Cancelled"
                elif schedule_changed:
                    appointment["status"] = "Pending"
                else:
                    appointment["status"] = previous_status
            normalized_appointments.append(appointment)
        value = normalized_appointments

        active_slots = [
            hashlib.sha256(
                f"{appointment.get('doctorName', '').strip()}|{appointment.get('date', '').strip()}|"
                f"{appointment.get('time', '').strip()}".encode("utf-8")
            ).hexdigest()
            for appointment in value
            if str(appointment.get("status", "")).lower() != "cancelled"
            and appointment.get("doctorName")
            and appointment.get("date")
            and appointment.get("time")
        ]
        if len(active_slots) != len(set(active_slots)):
            return fail("slot_taken", 409)
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
    if BREVO_API_KEY:
        try:
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "accept": "application/json",
                "api-key": BREVO_API_KEY,
                "content-type": "application/json"
            }
            payload = {
                "sender": {"name": "Medic Care", "email": BREVO_SENDER_EMAIL},
                "to": [{"email": to}],
                "subject": subject,
                "textContent": text
            }
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code in [200, 201, 202]:
                return True
            app.logger.warning("Brevo email request rejected with HTTP %s", response.status_code)
        except Exception as e:
            app.logger.warning("Brevo email request failed: %s", type(e).__name__)

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

@app.get("/admin")
def admin_portal():
    resp = send_from_directory(FRONTEND_DIR / "pages", "admin.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

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