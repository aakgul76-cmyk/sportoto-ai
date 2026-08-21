"""Elle girilen Spor Toto kuponunu web paneli icin JSON'a donusturur."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COUPON_PATH = PROJECT_ROOT / "data" / "coupon.csv"
JSON_PATH = PROJECT_ROOT / "data" / "matches.json"
SITE_JSON_PATH = PROJECT_ROOT / "docs" / "data" / "matches.json"


def load_coupon() -> list[dict]:
    if not COUPON_PATH.exists():
        raise SystemExit("data/coupon.csv bulunamadi.")

    matches = []
    with COUPON_PATH.open(newline="", encoding="utf-8-sig") as file:
        for row_number, row in enumerate(csv.DictReader(file), start=2):
            home = (row.get("home") or "").strip()
            away = (row.get("away") or "").strip()
            if not home and not away:
                continue
            if not home or not away:
                raise SystemExit(f"coupon.csv satir {row_number}: home ve away zorunludur.")

            matches.append(
                {
                    "fixture_id": (row.get("match_no") or str(len(matches) + 1)).strip(),
                    "date": (row.get("date") or "").strip() or None,
                    "status": "NS",
                    "league": (row.get("league") or "Spor Toto").strip(),
                    "country": (row.get("country") or "").strip(),
                    "home": home,
                    "away": away,
                    "wide_pick": (row.get("wide_pick") or "").strip(),
                    "narrow_pick": (row.get("narrow_pick") or "").strip(),
                }
            )

    return matches


def save_outputs(matches: list[dict]) -> None:
    def column_count(field: str) -> int:
        total = 1
        for match in matches:
            pick = match.get(field, "")
            total *= max(1, sum(symbol in pick for symbol in ("1", "X", "2")))
        return total

    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "Europe/Istanbul",
        "count": len(matches),
        "source": "manual_coupon",
        "wide_columns": column_count("wide_pick"),
        "narrow_columns": column_count("narrow_pick"),
        "matches": matches,
    }

    for path in (JSON_PATH, SITE_JSON_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main() -> None:
    matches = load_coupon()
    save_outputs(matches)
    print(f"Tamamlandi: kupondaki {len(matches)} mac panele aktarildi.")


if __name__ == "__main__":
    main()
