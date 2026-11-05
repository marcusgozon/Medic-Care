import re
import sys
from datetime import date, datetime, timedelta, timezone

from backend.app import (
    app,
    db_cursor,
    ensure_notifications_table,
    send_email,
)

MANILA_TIMEZONE = timezone(timedelta(hours=8), "Asia/Manila")
REMINDER_WINDOW = timedelta(minutes=30)
START_TIME_RE = re.compile(r"^\s*(\d{1,2}:\d{2}\s*[APap][Mm])")


def appointment_start(appointment_date, appointment_time):
    if isinstance(appointment_date, datetime):
        appointment_date = appointment_date.date()
    elif isinstance(appointment_date, str):
        appointment_date = date.fromisoformat(appointment_date)
    if not isinstance(appointment_date, date):
        raise ValueError("Invalid appointment date.")

    match = START_TIME_RE.match(str(appointment_time or ""))
    if not match:
        raise ValueError("Invalid appointment time.")
    start_time = datetime.strptime(match.group(1).replace(" ", "").upper(), "%I:%M%p").time()
    return datetime.combine(appointment_date, start_time, MANILA_TIMEZONE)


def ensure_appointment_reminders_table():
    ensure_notifications_table()
    with db_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointment_reminders (
                user_id INT UNSIGNED NOT NULL,
                client_id INT NOT NULL,
                appointment_date DATE NOT NULL,
                appointment_time VARCHAR(40) NOT NULL,
                email_sent_at DATETIME NULL,
                claim_until DATETIME NULL,
                notification_created_at DATETIME NULL,
                PRIMARY KEY (user_id, client_id),
                KEY idx_appointment_reminders_claim (claim_until),
                CONSTRAINT fk_appointment_reminders_user
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)


def _claim_reminder(user_id, client_id, appointment):
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO appointment_reminders
                (user_id, client_id, appointment_date, appointment_time)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                email_sent_at=IF(
                    appointment_date<>VALUES(appointment_date)
                    OR appointment_time<>VALUES(appointment_time),
                    NULL, email_sent_at
                ),
                claim_until=IF(
                    appointment_date<>VALUES(appointment_date)
                    OR appointment_time<>VALUES(appointment_time),
                    NULL, claim_until
                ),
                notification_created_at=IF(
                    appointment_date<>VALUES(appointment_date)
                    OR appointment_time<>VALUES(appointment_time),
                    NULL, notification_created_at
                ),
                appointment_date=VALUES(appointment_date),
                appointment_time=VALUES(appointment_time)
        """, (
            user_id,
            client_id,
            appointment["appt_date"],
            appointment["appt_time"],
        ))
        cursor.execute(
            "UPDATE appointment_reminders SET claim_until=DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 10 MINUTE) "
            "WHERE user_id=%s AND client_id=%s AND email_sent_at IS NULL "
            "AND (claim_until IS NULL OR claim_until < CURRENT_TIMESTAMP)",
            (user_id, client_id),
        )
        if not cursor.rowcount:
            return False

        cursor.execute(
            "SELECT notification_created_at FROM appointment_reminders "
            "WHERE user_id=%s AND client_id=%s FOR UPDATE",
            (user_id, client_id),
        )
        reminder = cursor.fetchone()
        if reminder["notification_created_at"] is None:
            cursor.execute(
                "INSERT INTO notifications "
                "(user_id, appointment_id, type, doctor_name, appointment_date, appointment_time) "
                "VALUES (%s, %s, 'appointment_reminder', %s, %s, %s)",
                (
                    user_id,
                    client_id,
                    appointment["doctor_name"],
                    appointment["appt_date"],
                    appointment["appt_time"],
                ),
            )
            cursor.execute(
                "UPDATE appointment_reminders SET notification_created_at=CURRENT_TIMESTAMP "
                "WHERE user_id=%s AND client_id=%s",
                (user_id, client_id),
            )
    return True


def _finish_reminder(user_id, client_id, sent):
    with db_cursor() as cursor:
        if sent:
            cursor.execute(
                "UPDATE appointment_reminders SET email_sent_at=CURRENT_TIMESTAMP, claim_until=NULL "
                "WHERE user_id=%s AND client_id=%s",
                (user_id, client_id),
            )
        else:
            cursor.execute(
                "UPDATE appointment_reminders SET claim_until=NULL "
                "WHERE user_id=%s AND client_id=%s AND email_sent_at IS NULL",
                (user_id, client_id),
            )


def process_due_appointment_reminders(now=None):
    now = now or datetime.now(MANILA_TIMEZONE)
    if now.tzinfo is None:
        raise ValueError("The reminder worker requires a timezone-aware current time.")
    now = now.astimezone(MANILA_TIMEZONE)
    ensure_appointment_reminders_table()

    with db_cursor() as cursor:
        cursor.execute(
            "SELECT a.user_id, a.client_id, a.appt_date, a.appt_time, a.doctor_name, u.login_id "
            "FROM appointments a JOIN users u ON u.id=a.user_id "
            "WHERE a.status='Confirmed' AND a.appt_date BETWEEN %s AND %s",
            (now.date(), (now + REMINDER_WINDOW).date()),
        )
        appointments = cursor.fetchall()

    sent_count = 0
    for appointment in appointments:
        try:
            starts_at = appointment_start(appointment["appt_date"], appointment["appt_time"])
        except (TypeError, ValueError):
            app.logger.warning(
                "Skipping appointment reminder with an invalid schedule (user %s, appointment %s).",
                appointment["user_id"],
                appointment["client_id"],
            )
            continue
        if not now <= starts_at <= now + REMINDER_WINDOW:
            continue

        user_id = appointment["user_id"]
        client_id = appointment["client_id"]
        if not _claim_reminder(user_id, client_id, appointment):
            continue

        message = (
            f"Reminder: your appointment with {appointment['doctor_name']} starts within the next 30 minutes.\n"
            f"Date: {appointment['appt_date'].isoformat()}\n"
            f"Time: {appointment['appt_time']}\n\n"
            "Please arrive on time. If you can no longer attend, contact the clinic."
        )
        try:
            sent = send_email(
                appointment["login_id"],
                "Medic Care Appointment Reminder",
                message,
            )
        except Exception as error:
            app.logger.warning("Appointment reminder email failed: %s", type(error).__name__)
            sent = False

        _finish_reminder(user_id, client_id, sent)
        if sent:
            sent_count += 1
        else:
            app.logger.warning(
                "Could not send appointment reminder (user %s, appointment %s).",
                user_id,
                client_id,
            )
    return sent_count


def main():
    try:
        sent_count = process_due_appointment_reminders()
    except Exception:
        app.logger.exception("Appointment reminder job failed.")
        return 1
    print(f"Appointment reminder job completed; sent {sent_count} email(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
