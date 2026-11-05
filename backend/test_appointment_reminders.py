import unittest
from datetime import date, datetime, timedelta

from backend.reminders import MANILA_TIMEZONE, appointment_start, is_due_for_reminder


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

    def test_reminder_window_is_one_hour(self):
        appointment = appointment_start("2026-11-05", "9:00AM - 10:00AM")
        now = appointment - timedelta(hours=1)
        self.assertTrue(is_due_for_reminder(appointment, now))
        self.assertFalse(is_due_for_reminder(appointment, now - timedelta(seconds=1)))
        self.assertFalse(is_due_for_reminder(appointment, appointment + timedelta(seconds=1)))


if __name__ == "__main__":
    unittest.main()
