"""Update match-result analysis without recalculating frozen predictions."""

from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

try:
    from scripts.fetch_data import api_football_fixture_score, api_football_get
except ModuleNotFoundError:  # Direct execution: python scripts/evaluate_results.py
    from fetch_data import api_football_fixture_score, api_football_get

ROOT = Path(__file__).resolve().parents[1]
MATCH_FILES = (ROOT / "data/matches.json", ROOT / "docs/data/matches.json")
ARCHIVE_FILES = (
    ROOT / "data/last_week_evaluation.json",
    ROOT / "docs/data/last_week_evaluation.json",
)
FINISHED_STATUSES = {"FT", "AET", "PEN"}
ISTANBUL = ZoneInfo("Europe/Istanbul")


def result_symbol(home: int, away: int) -> str:
    return "1" if home > away else "X" if home == away else "2"


def assessment(narrow_hit: bool | None, wide_hit: bool | None) -> str:
    if narrow_hit is None or wide_hit is None:
        return "not_evaluable"
    if narrow_hit and wide_hit:
        return "correct_main_decision"
    if not narrow_hit and wide_hit:
        return "narrowing_or_risk_budget_error"
    if not narrow_hit and not wide_hit:
        return "analysis_or_model_error"
    return "wide_distribution_error"


def fixture_for_match(match: dict, fixtures: list[dict]) -> tuple[dict | None, float]:
    ranked = [(api_football_fixture_score(match, item), item) for item in fixtures]
    score, fixture = max(ranked, default=(0.0, None), key=lambda entry: entry[0])
    return (fixture, score) if fixture is not None and score >= 0.55 else (None, score)


def evaluate_document(
    document: dict,
    fixtures_by_date: dict[str, list[dict]],
    errors: dict | None = None,
    now: datetime | None = None,
) -> dict:
    result = deepcopy(document)
    completed = []
    pending = []
    unavailable = []
    narrow_hits = []
    wide_hits = []
    assessment_counts = {
        "correct_main_decision": 0,
        "narrowing_or_risk_budget_error": 0,
        "analysis_or_model_error": 0,
        "wide_distribution_error": 0,
        "not_evaluable": 0,
    }
    narrow_evaluated = []
    wide_evaluated = []
    current = now or datetime.now(timezone.utc)
    evaluated_at = current.astimezone(timezone.utc).isoformat()
    local_today = current.astimezone(ISTANBUL).date()

    for match in result.get("matches", []):
        match_no = str(match.get("match_no") or "?")
        previous = match.get("result_analysis", {})
        if previous.get("status") == "finished":
            completed.append(match_no)
            if previous.get("narrow_hit"):
                narrow_hits.append(match_no)
            if previous.get("wide_hit"):
                wide_hits.append(match_no)
            if previous.get("narrow_hit") is not None:
                narrow_evaluated.append(match_no)
            if previous.get("wide_hit") is not None:
                wide_evaluated.append(match_no)
            category = previous.get("assessment") or assessment(
                previous.get("narrow_hit"), previous.get("wide_hit")
            )
            assessment_counts[category] = assessment_counts.get(category, 0) + 1
            continue
        fixture, match_score = fixture_for_match(match, fixtures_by_date.get(match.get("date", "")[:10], []))
        if fixture is None:
            try:
                match_date = datetime.fromisoformat(match["date"]).astimezone(ISTANBUL).date()
            except (KeyError, TypeError, ValueError):
                match_date = None
            if match_date is not None and match_date >= local_today:
                match["result_analysis"] = {
                    "status": "pending",
                    "fixture_status": "not_finished",
                    "evaluated_at": evaluated_at,
                }
                pending.append(match_no)
                continue
            match["result_analysis"] = {
                "status": "unavailable",
                "evaluated_at": evaluated_at,
                "reason": "Sonuç fikstürü eşleştirilemedi.",
            }
            unavailable.append(match_no)
            continue

        fixture_data = fixture.get("fixture", {})
        status = fixture_data.get("status", {}).get("short", "")
        goals = fixture.get("goals", {})
        if status not in FINISHED_STATUSES or goals.get("home") is None or goals.get("away") is None:
            match["result_analysis"] = {
                "status": "pending",
                "fixture_status": status or "unknown",
                "fixture_id": fixture_data.get("id"),
                "match_score": round(match_score, 3),
                "evaluated_at": evaluated_at,
            }
            pending.append(match_no)
            continue

        home_goals = int(goals["home"])
        away_goals = int(goals["away"])
        outcome = result_symbol(home_goals, away_goals)
        narrow_pick = match.get("narrow_pick") or ""
        wide_pick = match.get("wide_pick") or ""
        narrow_hit = outcome in narrow_pick if narrow_pick else None
        wide_hit = outcome in wide_pick if wide_pick else None
        category = assessment(narrow_hit, wide_hit)
        match["result_analysis"] = {
            "status": "finished",
            "fixture_status": status,
            "fixture_id": fixture_data.get("id"),
            "match_score": round(match_score, 3),
            "score": f"{home_goals}-{away_goals}",
            "outcome": outcome,
            "narrow_hit": narrow_hit,
            "wide_hit": wide_hit,
            "assessment": category,
            "evaluated_at": evaluated_at,
        }
        completed.append(match_no)
        if narrow_hit is not None:
            narrow_evaluated.append(match_no)
        if wide_hit is not None:
            wide_evaluated.append(match_no)
        if narrow_hit is True:
            narrow_hits.append(match_no)
        if wide_hit is True:
            wide_hits.append(match_no)
        assessment_counts[category] += 1

    total = len(result.get("matches", []))
    result["weekly_cycle"] = {
        "mode": "evaluation",
        "predictions_frozen": True,
        "evaluated_at": evaluated_at,
    }
    result["result_evaluation"] = {
        "status": "complete" if len(completed) == total and total == 15 else "partial",
        "total_matches": total,
        "completed_count": len(completed),
        "pending_count": len(pending),
        "unavailable_count": len(unavailable),
        "completed_match_nos": completed,
        "pending_match_nos": pending,
        "unavailable_match_nos": unavailable,
        "narrow_hit_count": len(narrow_hits),
        "wide_hit_count": len(wide_hits),
        "narrow_evaluated_count": len(narrow_evaluated),
        "wide_evaluated_count": len(wide_evaluated),
        "narrow_evaluated_match_nos": narrow_evaluated,
        "wide_evaluated_match_nos": wide_evaluated,
        "narrow_hit_match_nos": narrow_hits,
        "wide_hit_match_nos": wide_hits,
        "assessment_counts": assessment_counts,
        "errors": errors or {},
    }
    return result


def fetch_results(
    document: dict,
    key: str,
    now: datetime | None = None,
) -> tuple[dict[str, list[dict]], dict[str, str]]:
    fixtures_by_date = {}
    errors = {}
    local_today = (now or datetime.now(ISTANBUL)).astimezone(ISTANBUL).date()
    dates = sorted({
        match.get("date", "")[:10]
        for match in document.get("matches", [])
        if match.get("date") and datetime.fromisoformat(match["date"]).astimezone(ISTANBUL).date() <= local_today
    })
    for date in dates:
        try:
            fixtures_by_date[date] = api_football_get(
                "/fixtures", key, date=date, timezone="Europe/Istanbul"
            )
        except (requests.RequestException, RuntimeError) as error:
            fixtures_by_date[date] = []
            errors[date] = str(error)
    return fixtures_by_date, errors


def is_completed_week(document: dict, now: datetime | None = None) -> bool:
    """Only archive a coupon whose last scheduled match is before local today."""
    local_today = (now or datetime.now(ISTANBUL)).astimezone(ISTANBUL).date()
    dates = []
    for match in document.get("matches", []):
        try:
            dates.append(datetime.fromisoformat(match["date"]).astimezone(ISTANBUL).date())
        except (KeyError, TypeError, ValueError):
            return False
    return bool(dates) and max(dates) < local_today


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    source = next((path for path in MATCH_FILES if path.exists()), None)
    if source is None:
        if args.archive:
            print("Kapatılacak önceki hafta verisi yok; yeni hafta tahmini devam edebilir.")
            return
        raise SystemExit("Dondurulmuş matches.json bulunamadı; sonuç değerlendirmesi atlandı.")
    document = json.loads(source.read_text(encoding="utf-8"))
    if args.archive and not is_completed_week(document):
        print("Mevcut JSON yeni haftaya ait; geçen hafta arşivi değiştirilmedi.")
        return
    key = os.getenv("API_FOOTBALL_KEY", "")
    fixtures, errors = fetch_results(document, key) if key else ({}, {"API-Football": "Secret yok."})
    evaluated = evaluate_document(document, fixtures, errors)
    for path in MATCH_FILES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evaluated, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.archive:
        for path in ARCHIVE_FILES:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(evaluated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "Sonuç değerlendirmesi tamamlandı: "
        f"{evaluated['result_evaluation']['completed_count']}/{evaluated['result_evaluation']['total_matches']} maç."
    )


if __name__ == "__main__":
    main()
