"""Reset optional consensus input after a new weekly coupon is created."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSENSUS = ROOT / "data/consensus.csv"
EXTERNAL = ROOT / "data/external_predictions.csv"
FIELDS = [
    "match_no",
    "sportoto_1_pct", "sportoto_x_pct", "sportoto_2_pct",
    "nesine_1_pct", "nesine_x_pct", "nesine_2_pct",
    "bilyoner_1_pct", "bilyoner_x_pct", "bilyoner_2_pct",
    "misli_1_pct", "misli_x_pct", "misli_2_pct",
    "hedef15_1_pct", "hedef15_x_pct", "hedef15_2_pct",
    "model_a_name", "model_a_1_pct", "model_a_x_pct", "model_a_2_pct",
    "model_b_name", "model_b_1_pct", "model_b_x_pct", "model_b_2_pct",
    "model_c_name", "model_c_1_pct", "model_c_x_pct", "model_c_2_pct",
    "source_updated_at",
    "site_pick", "site_note",
    "external_sites_1_pct", "external_sites_x_pct", "external_sites_2_pct",
    "external_source_count", "external_numeric_source_count",
    "external_pick_1_pct", "external_pick_x_pct", "external_pick_2_pct",
    "external_top_signal", "external_agreement_pct", "external_source_names",
    "external_comment_summary", "external_updated_at",
]
EXTERNAL_FIELDS = [
    "week_id", "match_no", "source_name", "source_type", "pick",
    "prob_1_pct", "prob_x_pct", "prob_2_pct", "confidence_pct",
    "comment_summary", "source_url", "source_published_at", "collected_at",
]


def main() -> None:
    CONSENSUS.parent.mkdir(parents=True, exist_ok=True)
    with CONSENSUS.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for number in range(1, 16):
            writer.writerow({"match_no": str(number)})
    with EXTERNAL.open("w", newline="", encoding="utf-8") as file:
        csv.DictWriter(file, fieldnames=EXTERNAL_FIELDS, lineterminator="\n").writeheader()
    print("data/consensus.csv ve data/external_predictions.csv sıfırlandı.")


if __name__ == "__main__":
    main()
