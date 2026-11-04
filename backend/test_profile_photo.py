import io
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from PIL import Image

from backend import app as mediccare


class FakeStore:
    def __init__(self, users):
        self.users = users

    def get(self, uid):
        return self.users.get(uid)


class FakePhotoCursor:
    def __init__(self, photos):
        self.photos = photos
        self.result = None

    def execute(self, query, params=None):
        if query.startswith("SELECT image_data, mime_type FROM profile_photos"):
            self.result = self.photos.get(params[0])
        elif query.startswith("INSERT INTO profile_photos"):
            self.photos[params[0]] = {"image_data": params[1], "mime_type": params[2]}
        elif query.startswith("DELETE FROM profile_photos"):
            self.photos.pop(params[0], None)

    def fetchone(self):
        return self.result


class ProfilePhotoTests(unittest.TestCase):
    def setUp(self):
        self.client = mediccare.app.test_client()
        self.users = {
            uid: {
                "uid": uid,
                "id": f"patient{uid}@example.com",
                "profile": {"status": "active"},
                "data": {},
            }
            for uid in (1, 2)
        }
        self.photos = {}
        self.store_patch = patch.object(mediccare, "store", FakeStore(self.users))
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.table_patch = patch.object(mediccare, "ensure_profile_photos_table")
        self.table_patch.start()
        self.addCleanup(self.table_patch.stop)

        @contextmanager
        def fake_db_cursor():
            yield FakePhotoCursor(self.photos)

        self.db_patch = patch.object(mediccare, "db_cursor", fake_db_cursor)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def set_user(self, uid):
        with self.client.session_transaction() as session:
            session["uid"] = uid

    @staticmethod
    def image_bytes():
        image = Image.new("RGB", (32, 24), color=(20, 100, 220))
        output = io.BytesIO()
        image.save(output, format="JPEG")
        return output.getvalue()

    def test_photo_requires_authentication(self):
        response = self.client.get("/api/profile/photo")
        self.assertEqual(response.status_code, 401)

    def test_upload_requires_custom_request_header(self):
        self.set_user(1)
        response = self.client.post(
            "/api/profile/photo",
            data={"photo": (io.BytesIO(self.image_bytes()), "avatar.jpg")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.get_json()["error"], "request_header_required")

    def test_upload_and_retrieve_photo_only_for_owner(self):
        self.set_user(1)
        response = self.client.post(
            "/api/profile/photo",
            data={"photo": (io.BytesIO(self.image_bytes()), "avatar.jpg")},
            content_type="multipart/form-data",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

        response = self.client.get("/api/profile/photo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.data, self.photos[1]["image_data"])

        self.set_user(2)
        response = self.client.get("/api/profile/photo")
        self.assertEqual(response.status_code, 404)

    def test_rejects_corrupt_image(self):
        self.set_user(1)
        response = self.client.post(
            "/api/profile/photo",
            data={"photo": (io.BytesIO(b"not an image"), "avatar.png")},
            content_type="multipart/form-data",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_image")

    def test_rejects_photo_over_size_limit(self):
        self.set_user(1)
        response = self.client.post(
            "/api/profile/photo",
            data={"photo": (io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)), "avatar.jpg")},
            content_type="multipart/form-data",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["error"], "photo_too_large")
        response.close()

    def test_delete_removes_only_current_users_photo(self):
        self.photos[1] = {"image_data": b"first", "mime_type": "image/jpeg"}
        self.photos[2] = {"image_data": b"second", "mime_type": "image/jpeg"}
        self.set_user(1)

        response = self.client.delete("/api/profile/photo")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(1, self.photos)
        self.assertIn(2, self.photos)

    def test_admin_can_view_a_patient_photo(self):
        self.photos[1] = {"image_data": b"photo-bytes", "mime_type": "image/jpeg"}
        with self.client.session_transaction() as session:
            session["uid"] = 2
            session["is_admin"] = True

        response = self.client.get("/api/admin/users/1/photo")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.data, b"photo-bytes")

    def test_patient_cannot_view_another_users_photo(self):
        self.set_user(2)
        response = self.client.get("/api/admin/users/1/photo")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
