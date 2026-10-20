import datetime as dt
import unittest

from hackathon_maintenance import execution_plan


class ScheduleTests(unittest.TestCase):
    def plan(self, timestamp, event="schedule", mode="full"):
        return execution_plan(event, mode, dt.datetime.fromisoformat(timestamp))

    def test_daily_run_is_light(self):
        plan = self.plan("2026-10-21T01:17:00+00:00")
        self.assertTrue(plan["health"])
        self.assertTrue(plan["light_tests"])
        self.assertFalse(plan["full_matrix"])
        self.assertFalse(plan["acceptance"])

    def test_october_25_reuses_existing_matrix(self):
        plan = self.plan("2026-10-25T01:17:00+00:00")
        self.assertTrue(plan["full_matrix"])
        self.assertTrue(plan["health"])
        self.assertFalse(plan["light_tests"])
        self.assertFalse(plan["acceptance"])

    def test_october_28_runs_one_acceptance_without_duplicate_matrix(self):
        plan = self.plan("2026-10-28T01:17:00+00:00")
        self.assertTrue(plan["acceptance"])
        self.assertTrue(plan["health"])
        self.assertFalse(plan["light_tests"])
        self.assertFalse(plan["full_matrix"])

    def test_deadline_is_shanghai_midnight_not_utc_midnight(self):
        self.assertTrue(self.plan("2026-10-31T15:59:59+00:00")["health"])
        expired = self.plan("2026-10-31T16:00:00+00:00")
        self.assertTrue(all(not expired[key] for key in
                            ("health", "light_tests", "full_matrix", "acceptance")))

    def test_delayed_and_future_year_schedule_never_tests(self):
        for timestamp in ("2026-11-01T01:17:00+00:00", "2027-10-28T01:17:00+00:00"):
            with self.subTest(timestamp=timestamp):
                plan = self.plan(timestamp)
                self.assertFalse(any(plan[key] for key in
                                     ("health", "light_tests", "full_matrix", "acceptance")))

    def test_manual_full_remains_available_after_contest(self):
        plan = self.plan("2026-11-02T00:00:00+00:00", "workflow_dispatch", "full")
        self.assertTrue(plan["acceptance"])
        self.assertFalse(plan["full_matrix"])
        self.assertFalse(plan["light_tests"])

    def test_manual_health_exercises_the_daily_path(self):
        plan = self.plan("2026-10-20T00:00:00+00:00", "workflow_dispatch", "health")
        self.assertTrue(plan["health"])
        self.assertTrue(plan["light_tests"])
        self.assertFalse(plan["acceptance"])

    def test_push_keeps_original_ci(self):
        plan = self.plan("2026-11-02T00:00:00+00:00", "push")
        self.assertTrue(plan["full_matrix"])
        self.assertFalse(plan["health"])
        self.assertFalse(plan["acceptance"])

    def test_before_monitoring_window_is_inactive(self):
        self.assertFalse(self.plan("2026-10-19T00:00:00+00:00")["health"])


if __name__ == "__main__":
    unittest.main()
