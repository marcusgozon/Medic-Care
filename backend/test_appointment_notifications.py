import unittest
from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import patch

from backend import app as mediccare


class FakeStore:
    def __init__(self, doc):
        self.doc = doc
        self.saved_appointments = None

    def get(self, uid):
        return self.doc if uid == self.doc["uid"] else None

    def claim_slot(self, slot_key, uid):
        return True

    def release_slot(self, slot_key, uid):
        return None

    def save_appointments(self, uid, appointments):
        self.saved_appointments = appointments


class FakeCursor:
    def __init__(self, appointment=None, conflict=None, notifications=None, unread_count=0):
        self.appointment = appointment
        self.conflict = conflict
        self.notifications = notifications or []
        self.unread_count = unread_count
        self.result = None
        self.rowcount = 0
        self.updated_status = None
        self.inserted_notification = None

    def execute(self, query, params=None):
        if query.startswith("SELECT * FROM appointments"):
            self.result = self.appointment
        elif query.startswith("SELECT id FROM appointments"):
            self.result = self.conflict
        elif query.startswith("UPDATE appointments SET status"):
            self.updated_status = params[0]
            self.rowcount = 1
        elif query.startswith("INSERT INTO notifications"):
            self.inserted_notification = params
        elif query.startswith("SELECT id, type, doctor_name"):
            self.result = self.notifications
        elif query.startswith("SELECT COUNT(*) AS unread_count"):
            self.result = {"unread_count": self.unread_count}
        elif query.startswith("UPDATE notifications SET read_at"):
            self.rowcount = 1
        elif query.startswith("SELECT id FROM notifications"):
            self.result = {"id": params[0]}

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result or []


class AppointmentNotificationTests(unittest.TestCase):
    def setUp(self):
        self.client = mediccare.app.test_client()
        self.user_doc = {
            "uid": 12001,
            "id": "patient@example.com",
            "profile": {"status": "active"},
            "data": {"appointments": []},
        }
        self.fake_store = FakeStore(self.user_doc)
        self.store_patch = patch.object(mediccare, "store", self.fake_store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)

    def set_user_session(self):
        with self.client.session_transaction() as session:
            session["uid"] = self.user_doc["uid"]

    def set_admin_session(self):
        with self.client.session_transaction() as session:
            session["is_admin"] = True

    @patch.object(mediccare, "db_cursor")
    def test_new_booking_is_pending_even_if_client_sends_confirmed(self, db_cursor):
        appointment = {
            "id": 1,
            "doctorName": "Dr. Example",
            "date": "2026-11-06",
            "time": "8:00AM - 9:00AM",
            "status": "Confirmed",
        }
        self.set_user_session()

        response = self.client.put(
            "/api/data/appointments",
            json={"value": [appointment]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_store.saved_appointments[0]["status"], "Pending")
        db_cursor.assert_not_called()

    @patch.object(mediccare, "db_cursor")
    def test_rescheduling_a_confirmed_booking_requires_new_approval(self, db_cursor):
        self.user_doc["data"]["appointments"] = [{
            "id": 1,
            "doctorName": "Dr. Example",
            "date": "2026-11-06",
            "time": "8:00AM - 9:00AM",
            "status": "Confirmed",
        }]
        self.set_user_session()
        response = self.client.put(
            "/api/data/appointments",
            json={"value": [{
                "id": 1,
                "doctorName": "Dr. Example",
                "date": "2026-11-07",
                "time": "8:00AM - 9:00AM",
                "status": "Confirmed",
            }]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_store.saved_appointments[0]["status"], "Pending")
        db_cursor.assert_not_called()

    @patch.object(mediccare, "db_cursor")
    def test_existing_pending_booking_cannot_be_confirmed_by_patient(self, db_cursor):
        self.user_doc["data"]["appointments"] = [{
            "id": 1,
            "doctorName": "Dr. Example",
            "date": "2026-11-06",
            "time": "8:00AM - 9:00AM",
            "status": "Pending",
        }]
        self.set_user_session()
        response = self.client.put(
            "/api/data/appointments",
            json={"value": [{
                "id": 1,
                "doctorName": "Dr. Example",
                "date": "2026-11-06",
                "time": "8:00AM - 9:00AM",
                "status": "Confirmed",
            }]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_store.saved_appointments[0]["status"], "Pending")
        db_cursor.assert_not_called()

    def admin_cursor_context(self, cursor):
        @contextmanager
        def fake_db_cursor():
            yield cursor
        return fake_db_cursor

    def pending_appointment(self):
        return {
            "id": 81,
            "client_id": 4,
            "user_id": self.user_doc["uid"],
            "status": "Pending",
            "doctor_name": "Dr. Example",
            "appt_date": date(2026, 11, 6),
            "appt_time": "8:00AM - 9:00AM",
        }

    def test_admin_confirmation_creates_a_persistent_notification(self):
        cursor = FakeCursor(appointment=self.pending_appointment())
        self.set_admin_session()
        with patch.object(mediccare, "db_cursor", self.admin_cursor_context(cursor)):
            response = self.client.put(
                "/api/admin/appointments/81",
                json={"status": "Confirmed"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(cursor.updated_status, "Confirmed")
        self.assertEqual(cursor.inserted_notification, (
            self.user_doc["uid"],
            4,
            "appointment_confirmed",
            "Dr. Example",
            date(2026, 11, 6),
            "8:00AM - 9:00AM",
            "",
        ))

    def test_admin_denial_creates_a_patient_notification(self):
        cursor = FakeCursor(appointment=self.pending_appointment())
        self.set_admin_session()
        with patch.object(mediccare, "db_cursor", self.admin_cursor_context(cursor)):
            response = self.client.put(
                "/api/admin/appointments/81",
                json={"status": "Cancelled", "reason": "The doctor is unavailable at this time."},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(cursor.updated_status, "Cancelled")
        self.assertEqual(cursor.inserted_notification, (
            self.user_doc["uid"],
            4,
            "appointment_unavailable",
            "Dr. Example",
            date(2026, 11, 6),
            "8:00AM - 9:00AM",
            "The doctor is unavailable at this time.",
        ))

    def test_admin_denial_requires_a_reason(self):
        cursor = FakeCursor(appointment=self.pending_appointment())
        self.set_admin_session()
        with patch.object(mediccare, "db_cursor", self.admin_cursor_context(cursor)):
            response = self.client.put(
                "/api/admin/appointments/81",
                json={"status": "Cancelled", "reason": "   "},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "reason_required")
        self.assertIsNone(cursor.updated_status)
        self.assertIsNone(cursor.inserted_notification)

    def test_admin_cannot_confirm_an_occupied_schedule(self):
        cursor = FakeCursor(
            appointment=self.pending_appointment(),
            conflict={"id": 82},
        )
        self.set_admin_session()
        with patch.object(mediccare, "db_cursor", self.admin_cursor_context(cursor)):
            response = self.client.put(
                "/api/admin/appointments/81",
                json={"status": "Confirmed"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "slot_unavailable")
        self.assertIsNone(cursor.updated_status)
        self.assertIsNone(cursor.inserted_notification)

    def test_user_can_fetch_and_mark_only_owned_notifications(self):
        cursor = FakeCursor(
            notifications=[{
                "id": 21,
                "type": "appointment_confirmed",
                "doctor_name": "Dr. Example",
                "appointment_date": date(2026, 11, 6),
                "appointment_time": "8:00AM - 9:00AM",
                "reason": "The doctor is unavailable at this time.",
                "created_at": datetime(2026, 11, 5, 12, 0),
                "read_at": None,
            }],
            unread_count=1,
        )
        self.set_user_session()
        with patch.object(mediccare, "db_cursor", self.admin_cursor_context(cursor)):
            response = self.client.get("/api/notifications")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["unread_count"], 1)
        self.assertEqual(response.get_json()["notifications"][0]["date"], "2026-11-06")
        self.assertEqual(response.get_json()["notifications"][0]["reason"], "The doctor is unavailable at this time.")

        with patch.object(mediccare, "db_cursor", self.admin_cursor_context(cursor)):
            response = self.client.post("/api/notifications/21/read", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(cursor.rowcount, 1)


if __name__ == "__main__":
    unittest.main()
