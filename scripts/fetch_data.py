"""Spor Toto kuponunu API-Football oranlariyla zenginlestirir."""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
COUPON = ROOT / "data/coupon.csv"
PREDICTIONS = ROOT / "data/predictions.csv"
OUTPUTS = (ROOT / "data/matches.json", ROOT / "docs/data/matches.json")
API = "https://v3.football.api-sports.io"


def api_get(path: str, key: str, **params) -> list:
    response = requests.get(
        API + path,
        headers={"x-apisports-key": key},
        params=params,
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"API-Football {path}: {payload['errors']}")
    return payload.get("response", [])


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    for word in ("fk", "sk", "spor", "sportif", "faaliyetler", "tumosan", "corendon"):
        value = value.lower().replace(word, " ")
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


def resolve_fixtures(matches: list[dict], key: str) -> None:
    by_date = {}
    for match in matches:
        by_date.setdefault(match["date"][:10], []).append(match)
    for date, dated_matches in by_date.items():
        try:
            fixtures = api_get("/fixtures", key, date=date, timezone="Europe/Istanbul")
        except RuntimeError as error:
            for match in dated_matches:
                match["api_error"] = str(error)
                match["api_fixture_id"] = None
            continue
        for match in dated_matches:
            candidates = []
            for item in fixtures:
                teams = item.get("teams", {})
                score = (
                    similarity(match["home"], teams.get("home", {}).get("name", ""))
                    + similarity(match["away"], teams.get("away", {}).get("name", ""))
                ) / 2
                candidates.append((score, item))
            best_score, best = max(candidates, default=(0, None), key=lambda x: x[0])
            if best is None or best_score < 0.55:
                match["api_error"] = "API-Football fixture eslesmesi bulunamadi"
                match["api_fixture_id"] = None
            else:
                match["api_fixture_id"] = best["fixture"]["id"]
                match["api_match_score"] = round(best_score, 3)


def median_odds(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def collect_odds(payload: list) -> tuple[dict, dict[str, list[float]]]:
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
                        if key: buckets[key].append(odd)
                    elif "both teams" in name:
                        if low in ("yes", "var"): buckets["kg_var"].append(odd)
                        elif low in ("no", "yok"): buckets["kg_yok"].append(odd)
                    elif "over/under" in name or "goals over" in name:
                        compact = low.replace(" ", "")
                        for line, suffix in (("1.5", "15"), ("2.5", "25")):
                            if line in compact and compact.startswith("over"): buckets["o" + suffix].append(odd)
                            if line in compact and compact.startswith("under"): buckets["u" + suffix].append(odd)
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


def poisson(lam: float, goals: int) -> float:
    return math.exp(-lam) * lam**goals / math.factorial(goals)


def poisson_scores(markets: dict) -> list[tuple[str, float]]:
    target_1x2 = devig([markets["1x2"][key] for key in ("1", "X", "2")])
    target_ou = devig([markets["over_under"]["2.5"]["over"], markets["over_under"]["2.5"]["under"]])
    if not target_1x2:
        return []
    best = None
    for home_i in range(4, 81):
        home_lam = home_i / 20
        for away_i in range(4, 81):
            away_lam = away_i / 20
            grid = {(h, a): poisson(home_lam, h) * poisson(away_lam, a) for h in range(7) for a in range(7)}
            outcomes = [sum(p for (h, a), p in grid.items() if h > a), sum(p for (h, a), p in grid.items() if h == a), sum(p for (h, a), p in grid.items() if h < a)]
            error = sum((outcomes[i] - target_1x2[i]) ** 2 for i in range(3))
            if target_ou:
                over = sum(p for (h, a), p in grid.items() if h + a >= 3)
                error += (over - target_ou[0]) ** 2
            if best is None or error < best[0]:
                best = (error, grid)
    return sorted(((f"{h}-{a}", p) for (h, a), p in best[1].items()), key=lambda x: x[1], reverse=True)[:3]


def score_predictions(markets: dict, correct: dict[str, list[float]]) -> tuple[list[dict], str]:
    if correct:
        probabilities = {score: 1 / median_odds(values) for score, values in correct.items()}
        total = sum(probabilities.values())
        ranked = sorted(((score, value / total) for score, value in probabilities.items()), key=lambda x: x[1], reverse=True)[:3]
        source = "correct_score_odds"
    else:
        ranked = poisson_scores(markets)
        source = "poisson_from_market_odds"
    return ([{"score": score, "percentage": round(probability * 100, 1)} for score, probability in ranked], source)


def main() -> None:
    key = os.getenv("API_FOOTBALL_KEY")
    if not key:
        raise SystemExit("API_FOOTBALL_KEY GitHub Secret bulunamadi.")
    matches = load_inputs()
    resolve_fixtures(matches, key)
    for match in matches:
        fixture_id = match.get("api_fixture_id")
        if fixture_id:
            try:
                odds_payload = api_get("/odds", key, fixture=fixture_id)
                markets, correct = collect_odds(odds_payload)
                scores, source = score_predictions(markets, correct)
                match["market_odds"] = markets
                match["score_predictions"] = scores
                match["score_model"] = source if scores else "odds_unavailable"
            except (RuntimeError, requests.RequestException) as error:
                match["api_error"] = str(error)
                match["market_odds"] = {}
                match["score_predictions"] = []
                match["score_model"] = "odds_unavailable"
        else:
            match["market_odds"] = {}
            match["score_predictions"] = []
            match["score_model"] = "unavailable"
    def columns(field: str) -> int:
        result = 1
        for match in matches:
            result *= sum(symbol in match[field] for symbol in ("1", "X", "2"))
        return result
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "Europe/Istanbul",
        "count": len(matches),
        "source": "statistical_model_and_market_odds",
        "wide_columns": columns("wide_pick"),
        "narrow_columns": columns("narrow_pick"),
        "matches": matches,
    }
    for path in OUTPUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"API-Football tamamlandi: {len(matches)} mac, {sum(bool(m['score_predictions']) for m in matches)} skor modeli.")


if __name__ == "__main__":
    main()    for match in matches:
        fixture_id = match.get("api_fixture_id")
        match["model_1x2"] = {}
        match["model_score_predictions"] = []
        match["market_odds"] = {}
        match["market_score_predictions"] = []
        match["model_internal_alignment"] = {"status": "unavailable"}
        if fixture_id:
            try:
                markets, correct = collect_odds(api_get("/odds", key, fixture=fixture_id))
                market_scores, market_source = score_predictions(markets, correct)
                model_1x2, model_scores = statistical_model(
                    api_get("/predictions", key, fixture=fixture_id), markets
                )
                match["market_odds"] = markets
                match["market_score_predictions"] = market_scores
                match["market_score_model"] = market_source if market_scores else "unavailable"
                match["model_1x2"] = model_1x2
                match["model_score_predictions"] = model_scores
                match["score_predictions"] = model_scores
                match["score_model"] = "api_football_statistical"
                match["model_internal_alignment"] = alignment(
                    model_1x2, model_scores, match["narrow_pick"]
                )
            except (RuntimeError, requests.RequestException) as error:
                match["api_error"] = str(error)
                match["score_predictions"] = []
                match["score_model"] = "unavailable"
        else:
            match["score_predictions"] = []
            match["score_model"] = "unavailable"
    def columns(field: str) -> int:
        result = 1
        for match in matches:
            result *= sum(symbol in match[field] for symbol in ("1", "X", "2"))
        return result
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "Europe/Istanbul",
        "count": len(matches),
        "source": "api_football_odds",
        "wide_columns": columns("wide_pick"),
        "narrow_columns": columns("narrow_pick"),
        "matches": matches,
    }
    for path in OUTPUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"API-Football tamamlandi: {len(matches)} mac, {sum(bool(m['score_predictions']) for m in matches)} skor modeli.")


if __name__ == "__main__":
    main()
