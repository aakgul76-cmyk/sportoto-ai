"""Update the weekly 15-match Spor Toto coupon from the public bulletin."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
COUPON = ROOT / "data/coupon.csv"
PREDICTIONS = ROOT / "data/predictions.csv"
SOURCE_URL = "https://sportotoformul15.com/"
DATE_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})$")
MATCH_RE = re.compile(r"^(.+?)\s+vs\s+(.+?)$", re.IGNORECASE)

TEAM_NAMES = {
    "paris st germain": "Paris Saint-Germain",
    "atletico madrid": "Atletico Madrid",
}

COMPETITIONS = {
    ("bundesliga", "Almanya"): {
        "borussia dortmund", "hamburger sv", "bayern munih", "bayern munich",
        "bayer leverkusen", "rb leipzig", "eintracht frankfurt", "wolfsburg",
        "werder bremen", "stuttgart", "freiburg", "mainz", "hoffenheim",
    },
    ("Ligue 1", "Fransa"): {
        "lille", "paris saint germain", "paris st germain", "monaco",
        "marsilya", "marseille", "strasbourg", "lens", "lyon", "nice", "rennes",
    },
    ("Premier League", "İngiltere"): {
        "tottenham hotspur", "newcastle united", "arsenal", "manchester city",
        "manchester united", "liverpool", "chelsea", "aston villa", "everton",
        "west ham united", "brighton", "crystal palace", "fulham",
    },
    ("La Liga", "İspanya"): {
        "sevilla", "atletico madrid", "real madrid", "barcelona", "villarreal",
        "real sociedad", "real betis", "athletic bilbao", "valencia", "getafe",
        "celta vigo", "osasuna", "espanyol", "levante", "rayo vallecano",
    },
    ("Serie A", "İtalya"): {
        "cagliari", "inter", "milan", "torino", "juventus", "napoli", "roma",
        "lazio", "atalanta", "fiorentina", "bologna", "udinese", "genoa",
    },
}


def normalized(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .split()
    )


def canonical_team(value: str) -> str:
    value = " ".join(value.split())
    return TEAM_NAMES.get(normalized(value), value)


def competition_for(match_no: int, home: str, away: str) -> tuple[str, str]:
    if match_no <= 9:
        return "Süper Lig", "Türkiye"
    teams = {normalized(home), normalized(away)}
    for competition, known_teams in COMPETITIONS.items():
        if teams <= known_teams:
            return competition
    raise ValueError(
        f"{match_no}. macin ligi belirlenemedi: {home} - {away}. "
        "Takimlari COMPETITIONS listesine ekleyin."
    )


def extract_matches(html: str, now: datetime | None = None) -> list[dict]:
    text = BeautifulSoup(html, "html.parser").get_text("\n")
    if "GÜNCEL BÜLTEN" not in text or "KUPON" not in text:
        raise ValueError("Guncel bulten bolumu kaynak sayfada bulunamadi.")
    section = text.split("GÜNCEL BÜLTEN", 1)[1].split("KUPON", 1)[0]
    tokens = [" ".join(token.split()) for token in section.splitlines() if token.strip()]

    matches = []
    for index, token in enumerate(tokens):
        date_match = DATE_RE.match(token)
        if not date_match:
            continue
        matchup = None
        for candidate in tokens[index + 1:index + 6]:
            found = MATCH_RE.match(candidate)
            if found:
                matchup = found
                break
        if matchup is None:
            continue
        match_no = len(matches) + 1
        home = canonical_team(matchup.group(1))
        away = canonical_team(matchup.group(2))
        league, country = competition_for(match_no, home, away)
        local_date = datetime.strptime(
            f"{date_match.group(1)} {date_match.group(2)}", "%d.%m.%Y %H:%M"
        )
        matches.append({
            "match_no": str(match_no),
            "date": local_date.isoformat() + ":00+03:00",
            "league": league,
            "country": country,
            "home": home,
            "away": away,
        })

    if len(matches) != 15:
        raise ValueError(f"Kaynakta 15 yerine {len(matches)} gecerli mac bulundu.")
    pairs = {(match["home"], match["away"]) for match in matches}
    if len(pairs) != 15:
        raise ValueError("Bultende yinelenen mac bulundu.")

    reference = now or datetime.now()
    dates = [datetime.fromisoformat(match["date"]) for match in matches]
    reference_aware = reference.astimezone(dates[0].tzinfo) if reference.tzinfo else reference.replace(tzinfo=dates[0].tzinfo)
    if min(dates) < reference_aware - timedelta(days=1) or max(dates) > reference_aware + timedelta(days=10):
        raise ValueError("Bulten tarihleri beklenen yeni hafta araliginda degil.")
    return matches


def csv_text(rows: list[dict], fields: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main() -> None:
    response = requests.get(
        SOURCE_URL,
        headers={"User-Agent": "sportoto-ai/1.0 (+GitHub Actions weekly bulletin update)"},
        timeout=45,
    )
    response.raise_for_status()
    matches = extract_matches(response.text)

    coupon_text = csv_text(
        matches, ["match_no", "date", "league", "country", "home", "away"]
    )
    current = COUPON.read_text(encoding="utf-8-sig") if COUPON.exists() else ""
    if current.replace("\r\n", "\n") == coupon_text:
        print("Spor Toto listesi zaten guncel.")
        return

    COUPON.write_text(coupon_text, encoding="utf-8")
    empty_predictions = [
        {
            "match_no": str(number),
            "wide_pick": "",
            "narrow_pick": "",
            "score_1": "",
            "score_1_pct": "",
            "score_2": "",
            "score_2_pct": "",
            "score_3": "",
            "score_3_pct": "",
        }
        for number in range(1, 16)
    ]
    PREDICTIONS.write_text(
        csv_text(
            empty_predictions,
            [
                "match_no", "wide_pick", "narrow_pick", "score_1", "score_1_pct",
                "score_2", "score_2_pct", "score_3", "score_3_pct",
            ],
        ),
        encoding="utf-8",
    )
    print(f"Yeni Spor Toto listesi kaydedildi: {matches[0]['date']} - {matches[-1]['date']}")


if __name__ == "__main__":
    main()
