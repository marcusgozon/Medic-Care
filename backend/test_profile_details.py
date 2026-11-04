import unittest
from unittest.mock import patch

from backend import app as mediccare


class FakeStore:
    def __init__(self):
        self.details = {
            "altPhone": "",
            "address": "",
            "gender": "",
            "bdayMonth": None,
            "bdayDay": None,
            "bdayYear": None,
        }
        self.user = {
            "uid": 12002,
            "id": "patient@example.com",
            "profile": {"status": "active"},
            "data": {"appointments": [], "profileExtra": self.details},
        }

    def get(self, uid):
        return self.user if uid == self.user["uid"] else None

    def save_profile_details(self, uid, details):
        if uid != self.user["uid"]:
            return False
        self.details = details
        self.user["data"]["profileExtra"] = details
        return True


class ProfileDetailsTests(unittest.TestCase):
    def setUp(self):
        self.client = mediccare.app.test_client()
        self.fake_store = FakeStore()
        self.store_patch = patch.object(mediccare, "store", self.fake_store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        with self.client.session_transaction() as session:
            session["uid"] = self.fake_store.user["uid"]

    def test_current_user_endpoint_returns_guest_state_without_authentication(self):
        with self.client.session_transaction() as session:
            session.clear()

        response = self.client.get("/api/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "user": None})

    def test_saves_and_returns_persistent_profile_details(self):
        details = {
            "altPhone": "09123456789",
            "address": "123 Sample Street",
            "gender": "Prefer Not To Say",
            "bdayMonth": 2,
            "bdayDay": 28,
            "bdayYear": 1995,
        }
        response = self.client.put("/api/data/profileExtra", json={"value": details})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["value"], details)

        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["data"]["profileExtra"], details)

    def test_rejects_invalid_birth_date_without_saving(self):
        details = {
            "altPhone": "",
            "address": "",
            "gender": "",
            "bdayMonth": 2,
            "bdayDay": 30,
            "bdayYear": 1995,
        }
        response = self.client.put("/api/data/profileExtra", json={"value": details})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_birth_date")
        self.assertEqual(self.fake_store.details["address"], "")

    def test_rejects_invalid_gender(self):
        response = self.client.put(
            "/api/data/profileExtra",
            json={"value": {
                "altPhone": "",
                "address": "",
                "gender": "Other",
                "bdayMonth": None,
                "bdayDay": None,
                "bdayYear": None,
            }},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_gender")


if __name__ == "__main__":
    unittest.main()
