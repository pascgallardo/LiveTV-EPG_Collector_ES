"""Tests for scripts/madrid_noon_gate.py.

These cover the daylight saving behaviour that a plain UTC cron cannot express.
"""
import importlib.util
import pathlib
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "madrid_noon_gate.py"


def load_gate_module():
    spec = importlib.util.spec_from_file_location("madrid_noon_gate", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_gate_module()


def utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestIsMadridNoon(unittest.TestCase):
    def test_winter_time_is_utc_plus_one(self):
        # January: mainland Spain is CET, so noon is 11:00 UTC.
        self.assertTrue(gate.is_madrid_noon(utc(2026, 1, 15, 11, 0)))

    def test_summer_time_is_utc_plus_two(self):
        # July: mainland Spain is CEST, so noon is 10:00 UTC.
        self.assertTrue(gate.is_madrid_noon(utc(2026, 7, 15, 10, 0)))

    def test_rejects_the_other_candidate_hour(self):
        # In July, 11:00 UTC is 13:00 in Madrid.
        self.assertFalse(gate.is_madrid_noon(utc(2026, 7, 15, 11, 0)))
        # In January, 10:00 UTC is 11:00 in Madrid.
        self.assertFalse(gate.is_madrid_noon(utc(2026, 1, 15, 10, 0)))

    def test_rejects_hours_around_noon(self):
        self.assertFalse(gate.is_madrid_noon(utc(2026, 1, 15, 9, 0)))
        self.assertFalse(gate.is_madrid_noon(utc(2026, 1, 15, 12, 0)))
        self.assertFalse(gate.is_madrid_noon(utc(2026, 7, 15, 9, 0)))
        self.assertFalse(gate.is_madrid_noon(utc(2026, 7, 15, 12, 0)))

    def test_accepts_a_short_delay_but_not_a_stale_run(self):
        self.assertTrue(gate.is_madrid_noon(utc(2026, 1, 15, 11, 20)))
        self.assertFalse(gate.is_madrid_noon(utc(2026, 1, 15, 11, 45)))

    def test_spring_transition_day(self):
        # 2026-03-29: Madrid switches from CET to CEST at 02:00 local (01:00 UTC).
        self.assertTrue(gate.is_madrid_noon(utc(2026, 3, 29, 10, 0)))
        self.assertFalse(gate.is_madrid_noon(utc(2026, 3, 29, 11, 0)))

    def test_autumn_transition_day(self):
        # 2026-10-25: Madrid switches from CEST to CET at 03:00 local (01:00 UTC).
        self.assertTrue(gate.is_madrid_noon(utc(2026, 10, 25, 11, 0)))
        self.assertFalse(gate.is_madrid_noon(utc(2026, 10, 25, 10, 0)))

    def test_exactly_one_candidate_hour_matches_per_season(self):
        for month, expected_hour in ((1, 11), (7, 10)):
            matches = [
                hour for hour in (10, 11)
                if gate.is_madrid_noon(utc(2026, month, 15, hour))
            ]
            self.assertEqual(matches, [expected_hour])

    def test_defaults_to_the_current_time(self):
        self.assertIsInstance(gate.is_madrid_noon(), bool)

    def test_exactly_one_candidate_runs_each_day_of_the_year(self):
        # The workflow schedules 10:00 and 11:00 UTC. On every single day of 2026 and
        # 2027 exactly one of them must be noon in Madrid, otherwise the collector
        # would either run twice a day or not at all.
        candidates = (10, 11)
        for year in (2026, 2027):
            day = datetime(year, 1, 1, tzinfo=timezone.utc)
            while day.year == year:
                matches = [h for h in candidates if gate.is_madrid_noon(day.replace(hour=h))]
                self.assertEqual(len(matches), 1, f"{day.date()} matched {matches}")
                day += timedelta(days=1)

    def test_naive_datetime_is_interpreted_as_utc(self):
        # The result must not depend on the machine's local timezone.
        self.assertTrue(gate.is_madrid_noon(datetime(2026, 1, 15, 11, 0)))
        self.assertFalse(gate.is_madrid_noon(datetime(2026, 1, 15, 10, 0)))


if __name__ == "__main__":
    unittest.main()
