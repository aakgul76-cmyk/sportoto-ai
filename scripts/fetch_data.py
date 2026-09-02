"""Build Spor Toto model predictions from provider data."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import statistics
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
FOOTBALL_DATA_API = "https://api.football-data.org/v4"
API_FOOTBALL_API = "https://v3.football.api-sports.io"
MIN_API_INTERVAL_SECONDS = 10.0  # En fazla 6 istek/dakika; API-Football 10/dakika sinirindan guvenli uzaklik.
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 60.0
API_FOOTBALL_MIN_DAILY_REMAINING = 10
_last_api_request_at = 0.0
_api_football_disabled_reason: str | None = None

LEAGUE_CODES = {
    "süper lig": "TSL",
    "bundesliga": "BL1",
    "ligue 1": "FL1",
    "premier league": "PL",
    "la liga": "PD",
    "serie a": "SA",
}

API_FOOTBALL_LEAGUES = {
    "süper lig": 203,
    "premier league": 39,
    "la liga": 140,
    "serie a": 135,
    "bundesliga": 78,
    "ligue 1": 61,
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


def football_data_get(path: str, token: str, **params) -> dict:
    for attempt in range(3):
        wait_for_api_slot()
        response = requests.get(
            FOOTBALL_DATA_API + path,
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


def api_football_get(path: str, key: str, **params) -> list:
    global _api_football_disabled_reason
    if _api_football_disabled_reason:
        raise RuntimeError(_api_football_disabled_reason)

    for attempt in range(3):
        wait_for_api_slot()
        response = requests.get(
            API_FOOTBALL_API + path,
            headers={"x-apisports-key": key},
            params=params,
            timeout=45,
        )
        if response.status_code == 429 and attempt < 2:
            time.sleep(retry_after_seconds(response))
            continue
        if not response.ok:
            detail = response_error_detail(response)
            raise RuntimeError(
                f"API-Football HTTP {response.status_code} {path}: {detail}"
            )
        payload = response.json()
        if payload.get("errors"):
            detail = json.dumps(payload["errors"], ensure_ascii=False)
            raise RuntimeError(f"API-Football {path}: {detail[:500]}")
        daily_remaining = response.headers.get("x-ratelimit-requests-remaining")
        try:
            if daily_remaining is not None and int(daily_remaining) <= API_FOOTBALL_MIN_DAILY_REMAINING:
                _api_football_disabled_reason = (
                    "API-Football gunluk kota korumasi: "
                    f"kalan istek {daily_remaining}; yeni istekler durduruldu."
                )
                raise RuntimeError(_api_football_disabled_reason)
        except ValueError:
            pass
        return payload.get("response", [])
    raise RuntimeError(f"API-Football yanit vermedi: {path}")


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
                payload = football_data_get(f"/competitions/{code}/matches", token, season=season)
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


def api_football_league_id(match: dict) -> int | None:
    return API_FOOTBALL_LEAGUES.get(match["league"].lower())


def api_football_season(match: dict) -> int:
    match_date = datetime.fromisoformat(match["date"]).date()
    return match_date.year if match_date.month >= 7 else match_date.year - 1


def latest_allowed_api_football_season(error: Exception) -> int | None:
    """Extract the newest season offered by an API-Football plan error."""
    match = re.search(r"try from\s+(\d{4})\s+to\s+(\d{4})", str(error), re.IGNORECASE)
    return int(match.group(2)) if match else None


def api_football_fixture_as_match(item: dict) -> dict | None:
    fixture = item.get("fixture", {})
    teams = item.get("teams", {})
    goals = item.get("goals", {})
    home = teams.get("home", {})
    away = teams.get("away", {})
    if not fixture.get("id") or not home.get("id") or not away.get("id"):
        return None
    status_short = fixture.get("status", {}).get("short")
    is_finished = status_short in {"FT", "AET", "PEN"}
    return {
        "id": fixture["id"],
        "utcDate": fixture.get("date", ""),
        "status": "FINISHED" if is_finished else status_short or "TIMED",
        "homeTeam": {"id": home["id"], "name": home.get("name", "")},
        "awayTeam": {"id": away["id"], "name": away.get("name", "")},
        "score": {
            "fullTime": {
                "home": goals.get("home") if is_finished else None,
                "away": goals.get("away") if is_finished else None,
            }
        },
    }


def api_football_fixture_score(match: dict, item: dict) -> float:
    teams = item.get("teams", {})
    return (
        similarity(match["home"], teams.get("home", {}).get("name", ""))
        + similarity(match["away"], teams.get("away", {}).get("name", ""))
    ) / 2


def assign_api_football_fixture(match: dict, item: dict, score: float, source: str) -> None:
    fixture = item.get("fixture", {})
    match["api_football_fixture_id"] = fixture.get("id")
    match["api_football_match_score"] = round(score, 3)
    match["api_football_fixture_source"] = source


def fetch_api_football_season_fixtures(
    matches: list[dict], key: str
) -> tuple[dict[str, list], dict[str, int], dict[str, str]]:
    errors: dict[str, str] = {}
    data: dict[str, list] = {}
    source_seasons: dict[str, int] = {}
    league_requests = sorted(
        {
            (api_football_league_id(match), api_football_season(match), match["league"].lower())
            for match in matches
            if api_football_league_id(match)
        }
    )
    for league_id, season, league_name in league_requests:
        requested_season = season
        try:
            fixtures = api_football_get(
                "/fixtures",
                key,
                league=league_id,
                season=season,
                timezone="Europe/Istanbul",
            )
        except (requests.RequestException, RuntimeError) as error:
            errors[f"api_football_season:{league_name}:{season}"] = str(error)
            fallback_season = latest_allowed_api_football_season(error)
            if fallback_season is None or fallback_season == season:
                continue
            try:
                fixtures = api_football_get(
                    "/fixtures",
                    key,
                    league=league_id,
                    season=fallback_season,
                    timezone="Europe/Istanbul",
                )
                season = fallback_season
            except (requests.RequestException, RuntimeError) as fallback_error:
                errors[f"api_football_season:{league_name}:{fallback_season}"] = str(fallback_error)
                continue
        converted = [
            converted
            for item in fixtures
            if (converted := api_football_fixture_as_match(item)) is not None
        ]
        target_key = f"{league_id}:{requested_season}"
        data[target_key] = converted
        source_seasons[target_key] = season

        for match in matches:
            if api_football_league_id(match) != league_id or api_football_season(match) != requested_season:
                continue
            ranked = [
                (api_football_fixture_score(match, item), item)
                for item in fixtures
                if item.get("fixture", {}).get("date", "")[:10] == match["date"][:10]
            ]
            best_score, best = max(ranked, default=(0, None), key=lambda entry: entry[0])
            if best is not None and best_score >= 0.55 and not match.get("api_football_fixture_id"):
                assign_api_football_fixture(match, best, best_score, "league_season")
    return data, source_seasons, errors


def resolve_api_football_fixtures(
    matches: list[dict], key: str
) -> tuple[dict[str, str], dict[str, list], dict[str, int]]:
    errors: dict[str, str] = {}
    by_date: dict[str, list[dict]] = {}
    for match in matches:
        by_date.setdefault(match["date"][:10], []).append(match)

    for date, dated_matches in by_date.items():
        try:
            fixtures = api_football_get("/fixtures", key, date=date, timezone="Europe/Istanbul")
        except (requests.RequestException, RuntimeError) as error:
            errors[f"fixtures:{date}"] = str(error)
            continue

        for match in dated_matches:
            ranked = [(api_football_fixture_score(match, item), item) for item in fixtures]
            best_score, best = max(ranked, default=(0, None), key=lambda entry: entry[0])
            if best is None or best_score < 0.55:
                match["api_football_error"] = "API-Football fixture eslesmesi bulunamadi"
                match["api_football_fixture_id"] = None
            else:
                assign_api_football_fixture(match, best, best_score, "date")

    season_data, source_seasons, season_errors = fetch_api_football_season_fixtures(matches, key)
    errors.update(season_errors)
    return errors, season_data, source_seasons


def median_odds(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def collect_api_football_odds(payload: list) -> tuple[dict, dict[str, list[float]]]:
    buckets = {
        "1": [], "X": [], "2": [], "kg_var": [], "kg_yok": [],
        "o15": [], "u15": [], "o25": [], "u25": [],
    }
    correct_scores: dict[str, list[float]] = {}
    for item in payload:
        for bookmaker in item.get("bookmakers", []):
            for bet in bookmaker.get("bets", []):
                name = bet.get("name", "").lower()
                for value in bet.get("values", []):
                    label = str(value.get("value", "")).strip()
                    try:
                        odd = float(value.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    low = label.lower()
                    if "match winner" in name:
                        key = {"home": "1", "draw": "X", "away": "2", "1": "1", "x": "X", "2": "2"}.get(low)
                        if key:
                            buckets[key].append(odd)
                    elif "both teams" in name:
                        if low in ("yes", "var"):
                            buckets["kg_var"].append(odd)
                        elif low in ("no", "yok"):
                            buckets["kg_yok"].append(odd)
                    elif "over/under" in name or "goals over" in name:
                        compact = low.replace(" ", "")
                        for line, suffix in (("1.5", "15"), ("2.5", "25")):
                            if line in compact and compact.startswith("over"):
                                buckets["o" + suffix].append(odd)
                            if line in compact and compact.startswith("under"):
                                buckets["u" + suffix].append(odd)
                    elif "correct score" in name:
                        score = label.replace(":", "-").replace(" ", "")
                        if "-" in score and all(part.isdigit() for part in score.split("-", 1)):
                            correct_scores.setdefault(score, []).append(odd)
    markets = {
        "1x2": {"1": median_odds(buckets["1"]), "X": median_odds(buckets["X"]), "2": median_odds(buckets["2"])},
        "btts": {"yes": median_odds(buckets["kg_var"]), "no": median_odds(buckets["kg_yok"])},
        "over_under": {
            "1.5": {"over": median_odds(buckets["o15"]), "under": median_odds(buckets["u15"])},
            "2.5": {"over": median_odds(buckets["o25"]), "under": median_odds(buckets["u25"])},
        },
    }
    return markets, correct_scores


def devig(odds: list[float | None]) -> list[float] | None:
    if any(not odd or odd <= 1 for odd in odds):
        return None
    inverse = [1 / odd for odd in odds]
    total = sum(inverse)
    return [value / total for value in inverse]


def odds_distribution(markets: dict) -> dict:
    probabilities = devig([markets["1x2"][key] for key in ("1", "X", "2")])
    if not probabilities:
        return {}
    return {
        symbol: round(probability * 100, 1)
        for symbol, probability in zip(("1", "X", "2"), probabilities)
    }


def poisson_scores_from_market(markets: dict) -> list[tuple[str, float]]:
    target_1x2 = devig([markets["1x2"][key] for key in ("1", "X", "2")])
    target_ou = devig([markets["over_under"]["2.5"]["over"], markets["over_under"]["2.5"]["under"]])
    if not target_1x2:
        return []
    best = None
    for home_i in range(4, 81):
        home_lam = home_i / 20
        for away_i in range(4, 81):
            away_lam = away_i / 20
            grid = {
                (home, away): poisson(home_lam, home) * poisson(away_lam, away)
                for home in range(7) for away in range(7)
            }
            outcomes = [
                sum(p for (home, away), p in grid.items() if home > away),
                sum(p for (home, away), p in grid.items() if home == away),
                sum(p for (home, away), p in grid.items() if home < away),
            ]
            error = sum((outcomes[index] - target_1x2[index]) ** 2 for index in range(3))
            if target_ou:
                over = sum(p for (home, away), p in grid.items() if home + away >= 3)
                error += (over - target_ou[0]) ** 2
            if best is None or error < best[0]:
                best = (error, grid)
    return sorted(
        ((f"{home}-{away}", probability) for (home, away), probability in best[1].items()),
        key=lambda entry: entry[1],
        reverse=True,
    )[:3]


def market_score_predictions(markets: dict, correct: dict[str, list[float]]) -> tuple[list[dict], str]:
    if correct:
        probabilities = {score: 1 / median_odds(values) for score, values in correct.items()}
        total = sum(probabilities.values())
        ranked = sorted(
            ((score, value / total) for score, value in probabilities.items()),
            key=lambda entry: entry[1],
            reverse=True,
        )[:3]
        source = "api_football_correct_score_odds"
    else:
        ranked = poisson_scores_from_market(markets)
        source = "api_football_poisson_from_market_odds"
    return (
        [{"score": score, "percentage": round(probability * 100, 1)} for score, probability in ranked],
        source,
    )


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
    api_football_key = os.getenv("API_FOOTBALL_KEY")
    if not token and not api_football_key:
        raise SystemExit("FOOTBALL_DATA_TOKEN veya API_FOOTBALL_KEY GitHub Secret bulunamadi.")
    matches = load_inputs()
    competition_data: dict[str, list] = {}
    api_football_season_data: dict[str, list] = {}
    api_football_source_seasons: dict[str, int] = {}
    fetch_errors: dict[str, str] = {}
    if token:
        competition_data, fetch_errors = fetch_competitions(matches, token)
    else:
        fetch_errors["football-data.org"] = "FOOTBALL_DATA_TOKEN yok; football-data modeli atlandi."

    if api_football_key:
        (
            api_football_errors,
            api_football_season_data,
            api_football_source_seasons,
        ) = resolve_api_football_fixtures(matches, api_football_key)
        fetch_errors.update(api_football_errors)
    else:
        fetch_errors["API-Football"] = "API_FOOTBALL_KEY yok; oran/fixture sağlayıcısı atlandi."

    for match in matches:
        code = LEAGUE_CODES.get(match["league"].lower())
        match["model_1x2"] = {}
        match["model_score_predictions"] = []
        match["model_markets"] = {}
        match["market_odds"] = {}
        match["market_score_predictions"] = []
        match["market_status"] = "unavailable_without_odds_provider"
        match["model_internal_alignment"] = {"status": "unavailable"}
        if code and competition_data:
            candidates = competition_data.get(code, [])
            fixture = find_fixture(match, candidates)
            fixture_match_type = "exact_date_and_teams"
            if not fixture:
                fixture = infer_fixture_from_teams(match, candidates)
                fixture_match_type = "teams_from_competition_history"
            if fixture:
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
            else:
                match["data_error"] = "football-data.org fikstur eslesmesi bulunamadi"
        elif not code:
            match["data_error"] = "Lig kodu tanimli degil"

        if not match["model_1x2"] and api_football_season_data:
            league_id = api_football_league_id(match)
            season = api_football_season(match)
            season_key = f"{league_id}:{season}"
            candidates = api_football_season_data.get(season_key, [])
            source_season = api_football_source_seasons.get(season_key, season)
            fixture = find_fixture(match, candidates)
            fixture_match_type = "api_football_exact_date_and_teams"
            if not fixture:
                fixture = infer_fixture_from_teams(match, candidates)
                fixture_match_type = "api_football_teams_from_season_history"
            if fixture:
                history = finished_before(candidates, fixture)
                home_lambda, away_lambda, sample = expected_goals(fixture, history)
                one_x_two, scores, markets = model_distribution(home_lambda, away_lambda)
                match["api_football_history_match_id"] = fixture["id"]
                match["api_football_history_status"] = fixture.get("status")
                match["fixture_match_type"] = fixture_match_type
                match["model_1x2"] = one_x_two
                match["model_score_predictions"] = scores
                match["score_predictions"] = scores
                match["score_model"] = "poisson_from_api_football_season_history"
                match["model_markets"] = markets
                match["model_sample"] = sample | {
                    "provider": "api_football",
                    "source_season": source_season,
                    "target_season": season,
                }
                if source_season != season:
                    match["model_warning"] = (
                        f"API-Football Free plan nedeniyle {source_season} sezonu "
                        "tarihsel yedek veri olarak kullanildi; güncel form değildir."
                    )
                match["model_internal_alignment"] = alignment(one_x_two, scores, match["narrow_pick"])
                match.pop("data_error", None)

        fixture_id = match.get("api_football_fixture_id")
        if api_football_key and fixture_id:
            try:
                markets, correct = collect_api_football_odds(api_football_get("/odds", api_football_key, fixture=fixture_id))
            except (requests.RequestException, RuntimeError) as error:
                match["api_football_error"] = str(error)
                markets, correct = {}, {}
            if markets:
                odds_1x2 = odds_distribution(markets)
                scores, source = market_score_predictions(markets, correct)
                match["market_odds"] = markets
                match["market_1x2"] = odds_1x2
                match["market_score_predictions"] = scores
                match["market_status"] = "ready" if odds_1x2 else "odds_without_1x2"
                if odds_1x2:
                    # API-Football restore edildiginde piyasa olasiligini karar politikasina
                    # besle; football-data.org TSL 403 gibi bosluklari kapatir.
                    match["model_1x2"] = odds_1x2
                    match["model_score_predictions"] = scores
                    match["score_predictions"] = scores
                    match["score_model"] = source
                    match["model_markets"] = markets
                    match["model_internal_alignment"] = alignment(odds_1x2, scores, match["narrow_pick"])
                    match.pop("data_error", None)

    def columns(field: str) -> int:
        result = 1
        for match in matches:
            result *= sum(symbol in match[field] for symbol in ("1", "X", "2"))
        return result

    model_count = sum(bool(match["model_score_predictions"]) for match in matches)
    if model_count == 0:
        print("Hic model uretilemedi. Saglayici hatalari:", flush=True)
        print(json.dumps(fetch_errors, ensure_ascii=False, indent=2), flush=True)
        raise SystemExit(
            "Veri kalite korumasi: 0/15 model uretildi; mevcut yayin korunuyor."
        )

    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "Europe/Istanbul",
        "count": len(matches),
        "source": "api_football_market_odds_plus_football_data_history",
        "wide_columns": columns("wide_pick"),
        "narrow_columns": columns("narrow_pick"),
        "fetch_errors": fetch_errors,
        "matches": matches,
    }
    for path in OUTPUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Veri modeli tamamlandi: {len(matches)} mac, {model_count} model.")


if __name__ == "__main__":
    main()
