import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.weekly_cycle import decide_cycle


def utc(year: int, month: int, day: int, hour: int = 5) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


class WeeklyCycleUAT(unittest.TestCase):
    def test_scheduled_tuesday_starts_predictions_and_closes_previous_week(self):
        decision = decide_cycle(utc(2026, 9, 8), "schedule")
        self.assertEqual(decision.mode, "prediction")
        self.assertTrue(decision.close_previous_week)

    def test_scheduled_wednesday_thursday_friday_are_prediction_mornings(self):
        for day in (9, 10, 11):
            with self.subTest(day=day):
                decision = decide_cycle(utc(2026, 9, day), "schedule")
                self.assertEqual(decision.mode, "prediction")
                self.assertFalse(decision.close_previous_week)

    def test_delayed_friday_schedule_cannot_reopen_frozen_predictions(self):
        friday_evening = utc(2026, 9, 11, 17)
        self.assertEqual(decide_cycle(friday_evening, "schedule").mode, "frozen")

    def test_scheduled_saturday_sunday_monday_are_evaluation_only(self):
        for day in (12, 13, 14):
            with self.subTest(day=day):
                self.assertEqual(decide_cycle(utc(2026, 9, day), "schedule").mode, "evaluation")

    def test_push_never_recalculates_predictions(self):
        for day in range(8, 15):
            with self.subTest(day=day):
                self.assertEqual(decide_cycle(utc(2026, 9, day), "push").mode, "publish_only")

    def test_manual_prediction_is_limited_to_tuesday_thursday(self):
        for day in (8, 9, 10):
            with self.subTest(day=day):
                self.assertEqual(decide_cycle(utc(2026, 9, day), "workflow_dispatch").mode, "prediction")
        self.assertEqual(decide_cycle(utc(2026, 9, 11), "workflow_dispatch").mode, "frozen")

    def test_manual_weekend_and_monday_only_evaluate(self):
        for day in (12, 13, 14):
            with self.subTest(day=day):
                self.assertEqual(decide_cycle(utc(2026, 9, day), "workflow_dispatch").mode, "evaluation")

    def test_workflow_has_one_morning_schedule_and_separate_mode_steps(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/update-data.yml").read_text(encoding="utf-8")

        self.assertIn('cron: "0 8 * * *"', workflow)
        self.assertNotIn('cron: "0 18 * *', workflow)
        self.assertIn("if: steps.cycle.outputs.mode == 'prediction'", workflow)
        self.assertIn("if: steps.cycle.outputs.mode == 'evaluation'", workflow)
        self.assertIn("python scripts/evaluate_results.py --archive", workflow)


if __name__ == "__main__":
    unittest.main()
