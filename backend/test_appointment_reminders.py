import unittest
from datetime import date, datetime

from backend.reminders import MANILA_TIMEZONE, appointment_start


class AppointmentReminderTests(unittest.TestCase):
    def test_parses_morning_slot_start(self):
        self.assertEqual(
            appointment_start(date(2026, 11, 5), "8:00AM - 9:00AM"),
            datetime(2026, 11, 5, 8, 0, tzinfo=MANILA_TIMEZONE),
        )

    def test_parses_afternoon_slot_start_with_spaces(self):
        self.assertEqual(
            appointment_start("2026-11-05", " 3:00 PM - 4:00 PM"),
            datetime(2026, 11, 5, 15, 0, tzinfo=MANILA_TIMEZONE),
        )

    def test_rejects_invalid_slot(self):
        with self.assertRaises(ValueError):
            appointment_start("2026-11-05", "after lunch")


if __name__ == "__main__":
    unittest.main()
