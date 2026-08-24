"""Build Spor Toto model predictions from football-data.org match history."""

from __future__ import annotations

import csv
import json
import math
import os
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
COUPON = ROOT / "data/coupon.csv"
PREDICTIONS = ROOT / "data/predictions.csv"
OUTPUTS = (ROOT / "data/matches.json", ROOT / "docs/data/matches.json")
API = "https://api.football-data.org/v4"
MIN_API_INTERVAL_SECONDS = 6.2  # En fazla 9.67 istek/dakika (10/dakika sinirinin altinda).
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 60.0
_last_api_request_at = 0.0

LEAGUE_CODES = {
    "süper lig": "TSL",
    "bundesliga": "BL1",
    "ligue 1": "FL1",
    "premier league": "PL",
    "la liga": "PD",
    "serie a": "SA",
}


def wait_for_api_slot() -> None:
    """Serialize provider calls and keep them below the free-plan minute limit."""
    global _last_api_request_at
    elapsed = time.monotonic() - _last_api_request_at
    if elapsed < MIN_API_INTERVAL_SECONDS:
        time.sleep(MIN_API_INTERVAL_SECONDS - elapsed)
    _last_api_request_at = time.monotonic()


def retry_after_seconds(response: requests.Response) -> float:
    try:
        return max(float(response.headers.get("Retry-After", "")), MIN_API_INTERVAL_SECONDS)
    except (TypeError, ValueError):
        return DEFAULT_RATE_LIMIT_BACKOFF_SECONDS


def response_error_detail(response: requests.Response) -> str:
    """Return a bounded provider error without exposing request credentials."""
    try:
        payload = response.json()
        detail = json.dumps(payload, ensure_ascii=False)
    except ValueError:
        detail = response.text.strip() or response.reason or "bos yanit"
    return detail[:500]


def api_get(path: str, token: str, **params) -> dict:
    for attempt in range(3):
        wait_for_api_slot()
        response = requests.get(
            API + path,
            headers={"X-Auth-Token": token},
            params=params,
            timeout=45,
        )
        if response.status_code == 429 and attempt < 2:
            time.sleep(retry_after_seconds(response))
            continue
        if not response.ok:
            detail = response_error_detail(response)
            raise RuntimeError(
                f"football-data.org HTTP {response.status_code} {path}: {detail}"
            )
        return response.json()
    raise RuntimeError(f"football-data.org yanit vermedi: {path}")


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    replacements = {
        "olympique de marseille": "marseille",
        "olympique marseille": "marseille",
        "basaksehir fk": "istanbul basaksehir",
        "istanbul basaksehir fk": "istanbul basaksehir",
        "corum fk": "corum",
        "erzurumspor fk": "erzurum",
    }
    value = replacements.get(value, value)
    for word in ("fk", "sk", "spor", "sportif", "faaliyetler", "tumosan", "corendon", "arca"):
        value = value.replace(word, " ")
    return " ".join(value.split())


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalized(left), normalized(right)).ratio()


def load_inputs() -> list[dict]:
    with PREDICTIONS.open(newline="", encoding="utf-8-sig") as file:
        picks = {row["match_no"].strip(): row for row in csv.DictReader(file)}
    matches = []
    with COUPON.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            number = row["match_no"].strip()
            prediction = picks[number]
            matches.append({
                "match_no": number,
                "date": row["date"].strip(),
                "league": row["league"].strip(),
                "country": row["country"].strip(),
                "home": row["home"].strip(),
                "away": row["away"].strip(),
                "wide_pick": prediction["wide_pick"].strip().replace("0", "X"),
                "narrow_pick": prediction["narrow_pick"].strip().replace("0", "X"),
            })
    if len(matches) != 15:
        raise SystemExit(f"Kuponda 15 yerine {len(matches)} mac bulundu.")
    return matches


def fetch_competitions(matches: list[dict], token: str) -> tuple[dict[str, list], dict[str, str]]:
    codes = sorted({LEAGUE_CODES.get(match["league"].lower()) for match in matches} - {None})
    data: dict[str, list] = {}
    errors: dict[str, str] = {}
    for code in codes:
        combined = []
        for season in (2025, 2026):
            try:
                payload = api_get(f"/competitions/{code}/matches", token, season=season)
                combined.extend(payload.get("matches", []))
            except (requests.RequestException, RuntimeError) as error:
                errors[f"{code}:{season}"] = str(error)
        data[code] = combined
    return data, errors


def find_fixture(match: dict, candidates: list) -> dict | None:
    target_date = datetime.fromisoformat(match["date"]).astimezone(timezone.utc)
    ranked = []
    for item in candidates:
        try:
            item_date = datetime.fromisoformat(item["utcDate"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if abs((item_date - target_date).total_seconds()) > 36 * 3600:
            continue
        score = (
            similarity(match["home"], item.get("homeTeam", {}).get("name", ""))
            + similarity(match["away"], item.get("awayTeam", {}).get("name", ""))
        ) / 2
        ranked.append((score, item))
    best_score, best = max(ranked, default=(0, None), key=lambda entry: entry[0])
    return best if best is not None and best_score >= 0.55 else None


def infer_fixture_from_teams(match: dict, candidates: list) -> dict | None:
    teams = {}
    for item in candidates:
        for side in ("homeTeam", "awayTeam"):
            team = item.get(side, {})
            if team.get("id") and team.get("name"):
                teams[team["id"]] = team
    home_score, home_team = max(
        ((similarity(match["home"], team["name"]), team) for team in teams.values()),
        default=(0, None),
        key=lambda entry: entry[0],
    )
    away_score, away_team = max(
        ((similarity(match["away"], team["name"]), team) for team in teams.values()),
        default=(0, None),
        key=lambda entry: entry[0],
    )
    if home_team is None or away_team is None or home_score < 0.55 or away_score < 0.55:
        return None
    target_date = datetime.fromisoformat(match["date"]).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "id": None,
        "utcDate": target_date,
        "status": "COUPON_ONLY",
        "homeTeam": home_team,
        "awayTeam": away_team,
    }


def finished_before(candidates: list, fixture: dict) -> list[dict]:
    cutoff = fixture.get("utcDate", "")
    result = []
    for item in candidates:
        score = item.get("score", {}).get("fullTime", {})
        if (
            item.get("status") == "FINISHED"
            and item.get("utcDate", "") < cutoff
            and score.get("home") is not None
            and score.get("away") is not None
        ):
            result.append(item)
    return result


def average(values: list[float], fallback: float) -> float:
    return sum(values) / len(values) if values else fallback


def shrink(value: float, sample: int, baseline: float) -> float:
    weight = sample / (sample + 5)
    return value * weight + baseline * (1 - weight)


def expected_goals(fixture: dict, history: list[dict]) -> tuple[float, float, dict]:
    league_home = []
    league_away = []
    for item in history:
        score = item["score"]["fullTime"]
        league_home.append(float(score["home"]))
        league_away.append(float(score["away"]))
    home_base = average(league_home, 1.45)
    away_base = average(league_away, 1.15)
    home_id = fixture["homeTeam"]["id"]
    away_id = fixture["awayTeam"]["id"]
    home_for, home_against, away_for, away_against = [], [], [], []
    for item in history:
        score = item["score"]["fullTime"]
        if item["homeTeam"]["id"] == home_id:
            home_for.append(float(score["home"]))
            home_against.append(float(score["away"]))
        if item["awayTeam"]["id"] == away_id:
            away_for.append(float(score["away"]))
            away_against.append(float(score["home"]))
    home_attack = shrink(average(home_for[-10:], home_base), len(home_for[-10:]), home_base)
    away_defence = shrink(average(away_against[-10:], home_base), len(away_against[-10:]), home_base)
    away_attack = shrink(average(away_for[-10:], away_base), len(away_for[-10:]), away_base)
    home_defence = shrink(average(home_against[-10:], away_base), len(home_against[-10:]), away_base)
    home_lambda = max(0.2, min(3.8, (home_attack + away_defence) / 2))
    away_lambda = max(0.2, min(3.8, (away_attack + home_defence) / 2))
    sample = {
        "league_matches": len(history),
        "home_home_matches": len(home_for),
        "away_away_matches": len(away_for),
        "expected_home_goals": round(home_lambda, 3),
        "expected_away_goals": round(away_lambda, 3),
    }
    return home_lambda, away_lambda, sample


def poisson(lam: float, goals: int) -> float:
    return math.exp(-lam) * lam**goals / math.factorial(goals)


def model_distribution(home_lambda: float, away_lambda: float) -> tuple[dict, list[dict], dict]:
    grid = {
        (home, away): poisson(home_lambda, home) * poisson(away_lambda, away)
        for home in range(8) for away in range(8)
    }
    total = sum(grid.values())
    grid = {score: probability / total for score, probability in grid.items()}
    home_win = sum(p for (h, a), p in grid.items() if h > a)
    draw = sum(p for (h, a), p in grid.items() if h == a)
    away_win = sum(p for (h, a), p in grid.items() if h < a)
    btts_yes = sum(p for (h, a), p in grid.items() if h > 0 and a > 0)
    over_15 = sum(p for (h, a), p in grid.items() if h + a >= 2)
    over_25 = sum(p for (h, a), p in grid.items() if h + a >= 3)
    one_x_two = {"1": round(home_win * 100, 1), "X": round(draw * 100, 1), "2": round(away_win * 100, 1)}
    markets = {
        "btts": {"yes": round(btts_yes * 100, 1), "no": round((1 - btts_yes) * 100, 1)},
        "over_under": {
            "1.5": {"over": round(over_15 * 100, 1), "under": round((1 - over_15) * 100, 1)},
            "2.5": {"over": round(over_25 * 100, 1), "under": round((1 - over_25) * 100, 1)},
        },
    }
    scores = sorted(grid.items(), key=lambda entry: entry[1], reverse=True)[:3]
    predictions = [{"score": f"{h}-{a}", "percentage": round(p * 100, 1)} for (h, a), p in scores]
    return one_x_two, predictions, markets


def result_symbol(score: str) -> str:
    home, away = (int(value) for value in score.split("-", 1))
    return "1" if home > away else "X" if home == away else "2"


def alignment(one_x_two: dict, scores: list[dict], narrow_pick: str) -> dict:
    if not one_x_two or not scores:
        return {"status": "unavailable"}
    model_pick = max(one_x_two, key=one_x_two.get)
    score_results = [result_symbol(item["score"]) for item in scores]
    matching_scores = sum(result == model_pick for result in score_results)
    coupon_match = model_pick in narrow_pick
    status = "aligned" if matching_scores == 3 and coupon_match else "partial" if matching_scores and coupon_match else "divergent"
    return {
        "status": status,
        "model_pick": model_pick,
        "score_results": score_results,
        "matching_scores": matching_scores,
        "coupon_match": coupon_match,
    }


def main() -> None:
    token = os.getenv("FOOTBALL_DATA_TOKEN")
    if not token:
        raise SystemExit("FOOTBALL_DATA_TOKEN GitHub Secret bulunamadi.")
    matches = load_inputs()
    competition_data, fetch_errors = fetch_competitions(matches, token)
    for match in matches:
        code = LEAGUE_CODES.get(match["league"].lower())
        match["model_1x2"] = {}
        match["model_score_predictions"] = []
        match["model_markets"] = {}
        match["market_odds"] = {}
        match["market_score_predictions"] = []
        match["market_status"] = "unavailable_without_odds_provider"
        match["model_internal_alignment"] = {"status": "unavailable"}
        if not code:
            match["data_error"] = "Lig kodu tanimli degil"
            continue
        candidates = competition_data.get(code, [])
        fixture = find_fixture(match, candidates)
        fixture_match_type = "exact_date_and_teams"
        if not fixture:
            fixture = infer_fixture_from_teams(match, candidates)
            fixture_match_type = "teams_from_competition_history"
        if not fixture:
            match["data_error"] = "football-data.org fikstur eslesmesi bulunamadi"
            continue
        history = finished_before(candidates, fixture)
        home_lambda, away_lambda, sample = expected_goals(fixture, history)
        one_x_two, scores, markets = model_distribution(home_lambda, away_lambda)
        match["football_data_match_id"] = fixture["id"]
        match["football_data_status"] = fixture.get("status")
        match["fixture_match_type"] = fixture_match_type
        match["model_1x2"] = one_x_two
        match["model_score_predictions"] = scores
        match["score_predictions"] = scores
        match["score_model"] = "poisson_from_football_data_history"
        match["model_markets"] = markets
        match["model_sample"] = sample
        match["model_internal_alignment"] = alignment(one_x_two, scores, match["narrow_pick"])

    def columns(field: str) -> int:
        result = 1
        for match in matches:
            result *= sum(symbol in match[field] for symbol in ("1", "X", "2"))
        return result

    model_count = sum(bool(match["model_score_predictions"]) for match in matches)
    if model_count == 0:
        print("football-data.org hic model uretemedi. Saglayici hatalari:", flush=True)
        print(json.dumps(fetch_errors, ensure_ascii=False, indent=2), flush=True)
        raise SystemExit(
            "Veri kalite korumasi: 0/15 model uretildi; mevcut yayin korunuyor."
        )

    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "Europe/Istanbul",
        "count": len(matches),
        "source": "football_data_history_model",
        "wide_columns": columns("wide_pick"),
        "narrow_columns": columns("narrow_pick"),
        "fetch_errors": fetch_errors,
        "matches": matches,
    }
    for path in OUTPUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"football-data.org tamamlandi: {len(matches)} mac, {model_count} model.")


if __name__ == "__main__":
    main()

