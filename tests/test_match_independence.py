import csv
import json
import sys
import tempfile
import types
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = types.SimpleNamespace(
        Response=object,
        RequestException=Exception,
        get=None,
    )

from scripts import apply_decision_policy as policy
from scripts.apply_decision_policy import decision_coverage
from scripts.fetch_data import annotate_model_availability, has_complete_model, publish_match_results


def ready_match(match_no: int) -> dict:
    return {
        "match_no": str(match_no),
        "wide_pick": "1X",
        "narrow_pick": "1",
        "model_1x2": {"1": 50.0, "X": 30.0, "2": 20.0},
        "model_score_predictions": [{"score": "1-0", "percentage": 12.0}],
        "decision": {"status": "ready"},
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def enrich_with_rows(matches: list[dict], prediction_rows: list[dict], consensus_rows: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        prediction_path = Path(directory) / "predictions.csv"
        consensus_path = Path(directory) / "consensus.csv"
        write_csv(
            prediction_path,
            ["match_no", "narrow_pick", "wide_pick", "narrow_reason", "wide_reason"],
            prediction_rows,
        )
        write_csv(
            consensus_path,
            ["match_no", "model_a_name", "model_a_1_pct", "model_a_x_pct", "model_a_2_pct"],
            consensus_rows,
        )
        annotate_model_availability(matches)
        with patch.object(policy, "PRED", prediction_path), patch.object(policy, "CONS", consensus_path):
            return policy.enrich({"source": "uat", "matches": matches})


class MatchIndependenceUAT(unittest.TestCase):
    def test_14_ready_models_are_published_and_only_missing_match_is_marked(self):
        matches = [ready_match(number) for number in range(1, 16)]
        original_first_model = deepcopy(matches[0]["model_1x2"])
        matches[8]["model_1x2"] = {}
        matches[8]["model_score_predictions"] = []

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "matches.json"
            document = publish_match_results(matches, {}, outputs=(output,))
            published = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(document["model_coverage"]["status"], "partial")
        self.assertEqual(document["model_coverage"]["ready_count"], 14)
        self.assertEqual(document["model_coverage"]["unavailable_match_nos"], ["9"])
        self.assertEqual(published["matches"][0]["model_1x2"], original_first_model)
        self.assertEqual(published["matches"][0]["model_status"], "ready")
        self.assertEqual(published["matches"][8]["model_status"], "unavailable")

    def test_zero_models_are_reported_per_match_instead_of_blocking_publication(self):
        matches = [ready_match(number) for number in range(1, 16)]
        for match in matches:
            match["model_1x2"] = {}
            match["model_score_predictions"] = []

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "matches.json"
            document = publish_match_results(matches, {}, outputs=(output,))
            self.assertTrue(output.exists())

        self.assertEqual(document["model_coverage"]["status"], "unavailable")
        self.assertEqual(document["model_coverage"]["unavailable_count"], 15)

    def test_missing_model_does_not_cancel_manual_match_decision(self):
        matches = [ready_match(number) for number in range(1, 16)]
        matches[8]["model_1x2"] = {}
        matches[8]["model_score_predictions"] = []
        matches[8]["decision"] = {"status": "unavailable"}
        matches[8]["narrow_pick"] = "X2"
        matches[8]["wide_pick"] = "X2"

        coverage = decision_coverage(matches)

        self.assertEqual(matches[8]["decision_status"], "manual_ready")
        self.assertEqual(coverage["manual_only_match_nos"], ["9"])
        self.assertEqual(coverage["ready_count"], 15)
        self.assertEqual(coverage["pending_count"], 0)
        self.assertEqual(coverage["status"], "complete")

    def test_one_pending_match_does_not_change_other_match_decisions(self):
        matches = [ready_match(number) for number in range(1, 16)]
        expected_picks = [(match["narrow_pick"], match["wide_pick"]) for match in matches[:14]]
        matches[14]["decision"] = {"status": "unavailable"}
        matches[14]["narrow_pick"] = ""
        matches[14]["wide_pick"] = ""

        coverage = decision_coverage(matches)

        actual_picks = [(match["narrow_pick"], match["wide_pick"]) for match in matches[:14]]
        self.assertEqual(actual_picks, expected_picks)
        self.assertEqual(coverage["pending_match_nos"], ["15"])
        self.assertEqual(coverage["narrow_ready_count"], 14)
        self.assertEqual(coverage["wide_ready_count"], 14)

    def test_wide_only_manual_pick_is_partial_not_ready(self):
        matches = [ready_match(number) for number in range(1, 16)]
        matches[8]["decision"] = {"status": "unavailable"}
        matches[8]["narrow_pick"] = ""
        matches[8]["wide_pick"] = "X2"

        coverage = decision_coverage(matches)

        self.assertEqual(matches[8]["decision_status"], "partial")
        self.assertEqual(coverage["partial_match_nos"], ["9"])
        self.assertEqual(coverage["incomplete_match_nos"], ["9"])
        self.assertEqual(coverage["ready_count"], 14)
        self.assertEqual(coverage["status"], "partial")

    def test_enrich_keeps_other_match_decisions_when_one_model_is_missing(self):
        complete_matches = [ready_match(number) for number in range(1, 16)]
        partial_matches = deepcopy(complete_matches)
        partial_matches[14]["model_1x2"] = {}
        partial_matches[14]["model_score_predictions"] = []
        blank_predictions = [{"match_no": str(number)} for number in range(1, 16)]
        blank_consensus = [{"match_no": str(number)} for number in range(1, 16)]

        complete = enrich_with_rows(complete_matches, blank_predictions, blank_consensus)
        partial = enrich_with_rows(partial_matches, blank_predictions, blank_consensus)

        complete_decisions = [match["decision"] for match in complete["matches"][:14]]
        partial_decisions = [match["decision"] for match in partial["matches"][:14]]
        self.assertEqual(partial_decisions, complete_decisions)
        self.assertEqual(partial["decision_coverage"]["pending_match_nos"], ["15"])

    def test_enrich_accepts_manual_decision_for_match_without_api_model(self):
        matches = [ready_match(number) for number in range(1, 16)]
        matches[14]["model_1x2"] = {}
        matches[14]["model_score_predictions"] = []
        predictions = [{"match_no": str(number)} for number in range(1, 15)] + [{
            "match_no": "15",
            "narrow_pick": "X2",
            "wide_pick": "X2",
            "narrow_reason": "Uzman değerlendirmesi",
            "wide_reason": "Uzman değerlendirmesi",
        }]
        consensus = [{"match_no": str(number)} for number in range(1, 16)]

        enriched = enrich_with_rows(matches, predictions, consensus)

        self.assertEqual(enriched["matches"][14]["model_status"], "unavailable")
        self.assertEqual(enriched["matches"][14]["decision_status"], "manual_ready")
        self.assertEqual(enriched["decision_coverage"]["ready_count"], 15)

    def test_enrich_accepts_external_model_for_match_without_api_model(self):
        matches = [ready_match(number) for number in range(1, 16)]
        matches[14]["model_1x2"] = {}
        matches[14]["model_score_predictions"] = []
        predictions = [{"match_no": str(number)} for number in range(1, 16)]
        consensus = [{"match_no": str(number)} for number in range(1, 15)] + [{
            "match_no": "15",
            "model_a_name": "uat_external_model",
            "model_a_1_pct": "55",
            "model_a_x_pct": "25",
            "model_a_2_pct": "20",
        }]

        enriched = enrich_with_rows(matches, predictions, consensus)

        self.assertEqual(enriched["matches"][14]["model_status"], "unavailable")
        self.assertEqual(enriched["matches"][14]["decision_status"], "ready")
        self.assertEqual(enriched["matches"][14]["decision"]["distribution_source"], "external_models")
        self.assertEqual(enriched["decision_coverage"]["ready_count"], 15)

    def test_malformed_probability_distribution_marks_only_that_match_unavailable(self):
        match = ready_match(1)
        match["model_1x2"] = {"1": 50.0, "X": 30.0}
        self.assertFalse(has_complete_model(match))


if __name__ == "__main__":
    unittest.main()
