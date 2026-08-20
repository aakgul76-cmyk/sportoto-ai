"""API-Football'dan yaklasan maclari alip JSON ve CSV olarak kaydeder."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


API_URL = "https://v3.football.api-sports.io/fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = PROJECT_ROOT / "data" / "matches.json"
CSV_PATH = PROJECT_ROOT / "data" / "matches.csv"
SITE_JSON_PATH = PROJECT_ROOT / "docs" / "data" / "matches.json"

# Spor Toto kuponlarinda sik kullanilan liglerin API-Football kimlikleri.
LEAGUES = {
    203: "Turkiye Super Lig",
    204: "Turkiye 1. Lig",
    39: "England Premier League",
    40: "England Championship",
    41: "England League One",
    78: "Germany Bundesliga",
    79: "Germany 2. Bundesliga",
    135: "Italy Serie A",
    136: "Italy Serie B",
    140: "Spain La Liga",
    141: "Spain Segunda Division",
    61: "France Ligue 1",
    62: "France Ligue 2",
    88: "Netherlands Eredivisie",
    94: "Portugal Primeira Liga",
    144: "Belgium Pro League",
    179: "Scotland Premiership",
}


def coupon_dates() -> list:
    """Aktif veya siradaki Spor Toto donemini Cuma-Pazartesi olarak verir."""
    istanbul_time = timezone(timedelta(hours=3))
    today = datetime.now(istanbul_time).date()
    friday_offset = {0: -3, 1: 3, 2: 2, 3: 1, 4: 0, 5: -1, 6: -2}
    friday = today + timedelta(days=friday_offset[today.weekday()])
    return [friday + timedelta(days=day) for day in range(4)]


def fetch_upcoming_matches(api_key: str, limit: int = 500) -> tuple[list[dict], str | None]:
    target_dates = {match_date.isoformat() for match_date in coupon_dates()}
    today = datetime.now(timezone(timedelta(hours=3))).date()
    season = today.year if today.month >= 7 else today.year - 1
    raw_fixtures = []
    remaining = None
    successful_requests = 0
    errors = []

    for league_id, league_name in LEAGUES.items():
        response = requests.get(
            API_URL,
            headers={"x-apisports-key": api_key},
            params={
                "league": league_id,
                "season": season,
                "timezone": "Europe/Istanbul",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("errors"):
            errors.append(f"{league_name}: {payload['errors']}")
            continue

        successful_requests += 1
        raw_fixtures.extend(
            item
            for item in payload.get("response", [])
            if item.get("fixture", {}).get("date", "")[:10] in target_dates
        )
        remaining = response.headers.get("x-ratelimit-requests-remaining")

    if successful_requests == 0:
        raise RuntimeError("Lig verileri alinamadi: " + " | ".join(errors))

    for error in errors:
        print(f"Uyari: {error}")

    matches = []
    fixtures = sorted(
        raw_fixtures,
        key=lambda item: item.get("fixture", {}).get("date", ""),
    )
    for item in fixtures[:limit]:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        matches.append(
            {
                "fixture_id": fixture.get("id"),
                "date": fixture.get("date"),
                "status": fixture.get("status", {}).get("short"),
                "league": league.get("name"),
                "country": league.get("country"),
                "home": teams.get("home", {}).get("name"),
                "away": teams.get("away", {}).get("name"),
            }
        )

    return matches, remaining


def save_outputs(matches: list[dict], remaining: str | None) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    document = {
        "generated_at": generated_at,
        "timezone": "Europe/Istanbul",
        "count": len(matches),
        "api_requests_remaining": remaining,
        "matches": matches,
    }

    for path in (JSON_PATH, SITE_JSON_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    columns = ["fixture_id", "date", "status", "league", "country", "home", "away"]
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(matches)


def main() -> None:
    api_key = os.getenv("API_FOOTBALL_KEY")
    if not api_key:
        raise SystemExit(
            "API_FOOTBALL_KEY bulunamadi. GitHub Secret veya ortam degiskeni ekleyin."
        )

    matches, remaining = fetch_upcoming_matches(api_key)
    save_outputs(matches, remaining)
    print(f"Tamamlandi: {len(matches)} mac kaydedildi.")


if __name__ == "__main__":
    main()
