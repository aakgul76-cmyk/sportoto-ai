import unittest
from copy import deepcopy
from datetime import datetime, timezone

from scripts.evaluate_results import assessment, evaluate_document, is_completed_week


def match(number: int, home: str, away: str, date: str, narrow: str, wide: str) -> dict:
    return {
        "match_no": str(number),
        "date": date,
        "home": home,
        "away": away,
        "narrow_pick": narrow,
        "wide_pick": wide,
        "model_1x2": {"1": 50.0, "X": 30.0, "2": 20.0},
        "decision": {"status": "ready", "model_single": "1", "model_double": "1X"},
    }


def fixture(identifier: int, home: str, away: str, status: str, home_goals=None, away_goals=None) -> dict:
    return {
        "fixture": {"id": identifier, "status": {"short": status}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": home_goals, "away": away_goals},
    }


class ResultEvaluationUAT(unittest.TestCase):
    def setUp(self):
        self.document = {
            "generated_at": "2026-09-11T05:05:00+00:00",
            "matches": [
                match(1, "Alpha", "Beta", "2026-09-11T20:00:00+03:00", "1X", "1X"),
                match(2, "Gamma", "Delta", "2026-09-12T20:00:00+03:00", "1", "12"),
            ],
        }

    def test_results_are_added_without_changing_frozen_predictions(self):
        before = deepcopy(self.document["matches"])
        fixtures = {
            "2026-09-11": [fixture(101, "Alpha", "Beta", "FT", 1, 1)],
            "2026-09-12": [fixture(102, "Gamma", "Delta", "NS")],
        }

        evaluated = evaluate_document(self.document, fixtures)

        for index, original in enumerate(before):
            unchanged = {
                key: value for key, value in evaluated["matches"][index].items()
                if key != "result_analysis"
            }
            self.assertEqual(unchanged, original)
        first = evaluated["matches"][0]["result_analysis"]
        self.assertEqual(first["outcome"], "X")
        self.assertTrue(first["narrow_hit"])
        self.assertTrue(first["wide_hit"])
        self.assertEqual(first["assessment"], "correct_main_decision")
        self.assertEqual(evaluated["matches"][1]["result_analysis"]["status"], "pending")
        self.assertTrue(evaluated["weekly_cycle"]["predictions_frozen"])

    def test_result_assessment_uses_the_decision_policy_categories(self):
        self.assertEqual(assessment(True, True), "correct_main_decision")
        self.assertEqual(assessment(False, True), "narrowing_or_risk_budget_error")
        self.assertEqual(assessment(False, False), "analysis_or_model_error")
        self.assertEqual(assessment(True, False), "wide_distribution_error")
        self.assertEqual(assessment(None, False), "not_evaluable")

    def test_finished_match_without_prediction_is_not_counted_as_a_miss(self):
        document = deepcopy(self.document)
        document["matches"][0]["narrow_pick"] = ""
        document["matches"][0]["wide_pick"] = ""
        evaluated = evaluate_document(
            document,
            {"2026-09-11": [fixture(101, "Alpha", "Beta", "FT", 0, 1)]},
        )

        result = evaluated["matches"][0]["result_analysis"]
        self.assertIsNone(result["narrow_hit"])
        self.assertIsNone(result["wide_hit"])
        self.assertEqual(result["assessment"], "not_evaluable")
        self.assertEqual(evaluated["result_evaluation"]["narrow_evaluated_count"], 0)
        self.assertEqual(evaluated["result_evaluation"]["wide_evaluated_count"], 0)
        self.assertEqual(evaluated["result_evaluation"]["assessment_counts"]["analysis_or_model_error"], 0)

    def test_missing_result_is_unavailable_without_touching_prediction(self):
        after_week = datetime(2026, 9, 15, 8, tzinfo=timezone.utc)
        evaluated = evaluate_document(self.document, {}, now=after_week)
        self.assertEqual(evaluated["result_evaluation"]["unavailable_count"], 2)
        self.assertEqual(evaluated["matches"][0]["model_1x2"], self.document["matches"][0]["model_1x2"])

    def test_future_matches_are_pending_without_result_request(self):
        saturday_morning = datetime(2026, 9, 12, 5, tzinfo=timezone.utc)
        evaluated = evaluate_document(self.document, {}, now=saturday_morning)
        self.assertEqual(evaluated["matches"][1]["result_analysis"]["status"], "pending")
        self.assertIn("2", evaluated["result_evaluation"]["pending_match_nos"])

    def test_finished_result_is_not_lost_when_provider_later_fails(self):
        first = evaluate_document(
            self.document,
            {"2026-09-11": [fixture(101, "Alpha", "Beta", "FT", 2, 0)]},
        )
        saved = deepcopy(first["matches"][0]["result_analysis"])

        second = evaluate_document(first, {}, {"API-Football": "temporary failure"})

        self.assertEqual(second["matches"][0]["result_analysis"], saved)
        self.assertEqual(second["result_evaluation"]["completed_match_nos"], ["1"])

    def test_only_past_coupon_can_replace_last_week_archive(self):
        tuesday = datetime(2026, 9, 15, 8, tzinfo=timezone.utc)
        self.assertTrue(is_completed_week(self.document, tuesday))
        future = deepcopy(self.document)
        future["matches"][1]["date"] = "2026-09-18T20:00:00+03:00"
        self.assertFalse(is_completed_week(future, tuesday))


if __name__ == "__main__":
    unittest.main()
