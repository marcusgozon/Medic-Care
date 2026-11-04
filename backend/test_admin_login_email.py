import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from backend import app as mediccare


class AdminLoginEmailTests(unittest.TestCase):
    def setUp(self):
        self.client = mediccare.app.test_client()
        self.admin = {
            "uid": 987654,
            "password_hash": generate_password_hash("ValidPass123"),
            "profile": {"role": "admin"},
        }
        mediccare.pending_signups.pop("admin_admin@example.com", None)
        mediccare.login_mail_limiter.reset(self.admin["uid"])
        mediccare.admin_login_mail_limiter.reset(self.admin["uid"])
        mediccare.login_limiter.reset("127.0.0.1|admin@example.com")
        self.store_patch = patch.object(mediccare.store, "get_by_login", return_value=self.admin)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)

    def tearDown(self):
        mediccare.pending_signups.pop("admin_admin@example.com", None)
        mediccare.login_mail_limiter.reset(self.admin["uid"])
        mediccare.admin_login_mail_limiter.reset(self.admin["uid"])

    def login(self):
        return self.client.post(
            "/api/admin/login",
            json={"id": "admin@example.com", "password": "ValidPass123"},
        )

    @patch.object(mediccare, "send_email", return_value=False)
    def test_delivery_failure_does_not_create_verification_challenge(self, _send_email):
        response = self.login()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"ok": False, "error": "email_unavailable"})
        self.assertNotIn("admin_admin@example.com", mediccare.pending_signups)

    @patch.object(mediccare, "send_email", return_value=True)
    def test_successful_delivery_allows_code_verification(self, _send_email):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["needs_verification"])
        code = mediccare.pending_signups["admin_admin@example.com"]["code"]

        response = self.client.post(
            "/api/admin/verify",
            json={"id": "admin@example.com", "code": code},
        )

        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertTrue(session["is_admin"])

    @patch.object(mediccare, "send_email", return_value=True)
    def test_patient_email_limit_does_not_block_admin_code(self, send_email):
        for _ in range(mediccare.login_mail_limiter.limit):
            mediccare.login_mail_limiter.hit(self.admin["uid"])

        response = self.login()

        self.assertEqual(response.status_code, 200)
        send_email.assert_called_once()


if __name__ == "__main__":
    unittest.main()
