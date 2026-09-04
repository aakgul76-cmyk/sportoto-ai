import csv
import sys
import tempfile
import types
import unittest
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


def model_match(match_no: int) -> dict:
    return {
        "match_no": str(match_no),
        "model_1x2": {"1": 60.0, "X": 25.0, "2": 15.0},
        "model_score_predictions": [{"score": "1-0", "percentage": 15.0}],
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def enrich_with_predictions(prediction_rows: list[dict], missing_match: int | None = None) -> dict:
    matches = [model_match(number) for number in range(1, 16)]
    if missing_match:
        matches[missing_match - 1]["model_1x2"] = {}
        matches[missing_match - 1]["model_score_predictions"] = []
    with tempfile.TemporaryDirectory() as directory:
        prediction_path = Path(directory) / "predictions.csv"
        consensus_path = Path(directory) / "consensus.csv"
        write_csv(
            prediction_path,
            ["match_no", "narrow_pick", "wide_pick", "narrow_reason", "wide_reason"],
            prediction_rows,
        )
        write_csv(consensus_path, ["match_no"], [{"match_no": str(number)} for number in range(1, 16)])
        with patch.object(policy, "PRED", prediction_path), patch.object(policy, "CONS", consensus_path):
            return policy.enrich({"source": "uat", "matches": matches})


def blank_predictions(count: int = 15) -> list[dict]:
    return [{"match_no": str(number)} for number in range(1, count + 1)]


class CouponIntegrityUAT(unittest.TestCase):
    def test_automatic_coupon_is_valid_and_wide_contains_narrow(self):
        document = enrich_with_predictions(blank_predictions())

        self.assertEqual(document["narrow_strategy"]["validation"]["status"], "valid")
        self.assertIn(document["narrow_columns"], {128, 256})
        self.assertTrue(document["coupon_validation"]["narrow_playable"])
        self.assertEqual(document["wide_strategy"]["validation"]["status"], "valid")
        self.assertEqual(document["wide_columns"], 2048)
        for match in document["matches"]:
            self.assertTrue(set(match["narrow_pick"]).issubset(set(match["wide_pick"])))
            self.assertNotEqual(match["narrow_pick"], "1X2")
            self.assertNotEqual(match["wide_pick"], "1X2")

    def test_nine_manual_narrow_doubles_are_invalid_not_rewritten(self):
        predictions = blank_predictions()
        for row in predictions[:9]:
            row.update({"narrow_pick": "1X", "narrow_reason": "UAT manuel tercihi"})

        document = enrich_with_predictions(predictions)
        validation = document["narrow_strategy"]["validation"]

        self.assertEqual([match["narrow_pick"] for match in document["matches"][:9]], ["1X"] * 9)
        self.assertEqual(document["narrow_columns"], 512)
        self.assertEqual(validation["status"], "invalid")
        self.assertFalse(validation["playable"])
        self.assertIn("narrow_double_count", {error["code"] for error in validation["errors"]})

    def test_twelve_manual_wide_doubles_are_invalid_not_rewritten(self):
        predictions = blank_predictions()
        for row in predictions[:12]:
            row.update({"wide_pick": "1X", "wide_reason": "UAT manuel tercihi"})

        document = enrich_with_predictions(predictions)
        validation = document["wide_strategy"]["validation"]

        self.assertEqual([match["wide_pick"] for match in document["matches"][:12]], ["1X"] * 12)
        self.assertEqual(document["wide_columns"], 4096)
        self.assertEqual(validation["status"], "invalid")
        self.assertFalse(validation["final"])
        self.assertIn("wide_column_limit", {error["code"] for error in validation["errors"]})

    def test_manual_wide_that_omits_narrow_is_preserved_and_invalid(self):
        predictions = blank_predictions()
        predictions[0].update({
            "narrow_pick": "1X",
            "narrow_reason": "UAT dar tercihi",
            "wide_pick": "X2",
            "wide_reason": "UAT geniş tercihi",
        })

        document = enrich_with_predictions(predictions)
        first = document["matches"][0]
        validation = document["wide_strategy"]["validation"]

        self.assertEqual(first["narrow_pick"], "1X")
        self.assertEqual(first["wide_pick"], "X2")
        self.assertEqual(validation["status"], "invalid")
        self.assertIn("wide_missing_narrow_pick", {error["code"] for error in validation["errors"]})

    def test_manual_wide_single_is_never_silently_upgraded(self):
        predictions = blank_predictions()
        predictions[0].update({"wide_pick": "X", "wide_reason": "UAT manuel geniş teki"})

        document = enrich_with_predictions(predictions)

        self.assertEqual(document["matches"][0]["wide_pick"], "X")
        self.assertEqual(document["matches"][0]["wide_pick_origin"], "manual_wide")
        self.assertEqual(document["wide_strategy"]["validation"]["status"], "invalid")

    def test_all_manual_wide_singles_are_preserved_without_crashing(self):
        predictions = blank_predictions()
        for row in predictions:
            row.update({"wide_pick": "1", "wide_reason": "UAT manuel geniş teki"})

        document = enrich_with_predictions(predictions)

        self.assertEqual([match["wide_pick"] for match in document["matches"]], ["1"] * 15)
        self.assertEqual(document["wide_columns"], 1)
        self.assertEqual(document["wide_strategy"]["validation"]["status"], "invalid")

    def test_manual_triple_invalidates_only_coupon_not_other_match_decisions(self):
        baseline = enrich_with_predictions(blank_predictions())
        predictions = blank_predictions()
        predictions[0].update({"narrow_pick": "1X2", "narrow_reason": "UAT geçersiz tercihi"})

        document = enrich_with_predictions(predictions)

        self.assertEqual(document["matches"][0]["requested_manual_narrow_pick"], "1X2")
        self.assertEqual(document["matches"][0]["manual_narrow_audit"]["status"], "rejected_invalid_pick")
        self.assertEqual(document["narrow_strategy"]["validation"]["status"], "invalid")
        self.assertEqual(
            [match["decision"] for match in document["matches"][1:]],
            [match["decision"] for match in baseline["matches"][1:]],
        )

    def test_malformed_manual_pick_is_rejected_instead_of_filtered(self):
        predictions = blank_predictions()
        predictions[0].update({"narrow_pick": "abc1", "narrow_reason": "UAT bozuk giriş"})

        document = enrich_with_predictions(predictions)

        self.assertEqual(document["matches"][0]["requested_manual_narrow_pick"], "ABC1")
        self.assertEqual(document["matches"][0]["manual_narrow_audit"]["status"], "rejected_invalid_pick")
        self.assertEqual(document["narrow_strategy"]["validation"]["status"], "invalid")

    def test_missing_model_makes_coupon_incomplete_not_invalid(self):
        document = enrich_with_predictions(blank_predictions(), missing_match=15)

        self.assertEqual(document["narrow_strategy"]["validation"]["status"], "incomplete")
        self.assertEqual(document["wide_strategy"]["validation"]["status"], "incomplete")
        self.assertEqual(document["coupon_validation"]["status"], "incomplete")
        self.assertFalse(document["coupon_validation"]["narrow_playable"])
        self.assertEqual(document["decision_coverage"]["pending_match_nos"], ["15"])

    def test_wide_cannot_be_final_when_its_narrow_base_is_missing(self):
        predictions = blank_predictions()
        predictions[14].update({
            "wide_pick": "X2",
            "wide_reason": "UAT yalnız geniş tercihi",
        })

        document = enrich_with_predictions(predictions, missing_match=15)

        self.assertEqual(document["matches"][14]["narrow_pick"], "")
        self.assertEqual(document["matches"][14]["wide_pick"], "X2")
        self.assertEqual(document["wide_strategy"]["validation"]["status"], "incomplete")
        self.assertFalse(document["coupon_validation"]["wide_virtual_final"])

    def test_fourteen_rows_publish_as_incomplete_not_valid(self):
        matches = [model_match(number) for number in range(1, 15)]
        with tempfile.TemporaryDirectory() as directory:
            prediction_path = Path(directory) / "predictions.csv"
            consensus_path = Path(directory) / "consensus.csv"
            write_csv(prediction_path, ["match_no"], blank_predictions(14))
            write_csv(consensus_path, ["match_no"], blank_predictions(14))
            with patch.object(policy, "PRED", prediction_path), patch.object(policy, "CONS", consensus_path):
                document = policy.enrich({"source": "uat", "matches": matches})

        self.assertEqual(len(document["matches"]), 14)
        self.assertEqual(document["narrow_strategy"]["validation"]["status"], "incomplete")
        self.assertEqual(document["wide_strategy"]["validation"]["status"], "incomplete")
        self.assertIn("15", document["narrow_strategy"]["validation"]["incomplete_match_nos"])
        self.assertIn("15", document["decision_coverage"]["pending_match_nos"])


if __name__ == "__main__":
    unittest.main()
