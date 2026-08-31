"""Reset optional consensus input after a new weekly coupon is created."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSENSUS = ROOT / "data/consensus.csv"
FIELDS = [
    "match_no",
    "sportoto_1_pct", "sportoto_x_pct", "sportoto_2_pct",
    "nesine_1_pct", "nesine_x_pct", "nesine_2_pct",
    "bilyoner_1_pct", "bilyoner_x_pct", "bilyoner_2_pct",
    "misli_1_pct", "misli_x_pct", "misli_2_pct",
    "hedef15_1_pct", "hedef15_x_pct", "hedef15_2_pct",
    "site_pick", "site_note",
]


def main() -> None:
    CONSENSUS.parent.mkdir(parents=True, exist_ok=True)
    with CONSENSUS.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for number in range(1, 16):
            writer.writerow({"match_no": str(number)})
    print("data/consensus.csv sıfırlandı.")


if __name__ == "__main__":
    main()
