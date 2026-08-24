"""Update the weekly 15-match Spor Toto coupon from the public bulletin."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
COUPON = ROOT / "data/coupon.csv"
PREDICTIONS = ROOT / "data/predictions.csv"
OFFICIAL_SOURCE_URL = "https://www.sportoto.gov.tr/spor-toto-listeler"
FALLBACK_SOURCE_URL = "https://sportotoformul15.com/"
DATE_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})$")
MATCH_RE = re.compile(r"^(.+?)\s+vs\s+(.+?)$", re.IGNORECASE)

TEAM_NAMES = {
    "paris st germain": "Paris Saint-Germain",
    "atletico madrid": "Atletico Madrid",
}

class OfficialTableParser(HTMLParser):
    """Collect table cells from the official Spor Toto bulletin."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self.current_row = []
        elif tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.current_cell is not None:
            assert self.current_row is not None
            self.current_row.append(" ".join(" ".join(self.current_cell).split()))
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = None


class VisibleTextParser(HTMLParser):
    """Collect visible text without executing page scripts."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth and data.strip():
            self.parts.append(data)


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
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())


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



def validate_matches(matches: list[dict], now: datetime | None = None) -> list[dict]:
    if len(matches) != 15:
        raise ValueError(f"Kaynakta 15 yerine {len(matches)} gecerli mac bulundu.")
    if [match["match_no"] for match in matches] != [str(number) for number in range(1, 16)]:
        raise ValueError("Bultendeki mac numaralari 1-15 sirali degil.")
    pairs = {(match["home"], match["away"]) for match in matches}
    if len(pairs) != 15:
        raise ValueError("Bultende yinelenen mac bulundu.")

    reference = now or datetime.now()
    dates = [datetime.fromisoformat(match["date"]) for match in matches]
    reference_aware = (
        reference.astimezone(dates[0].tzinfo)
        if reference.tzinfo
        else reference.replace(tzinfo=dates[0].tzinfo)
    )
    if min(dates) < reference_aware - timedelta(days=1) or max(dates) > reference_aware + timedelta(days=10):
        raise ValueError("Bulten tarihleri beklenen yeni hafta araliginda degil.")
    return matches


def extract_official_matches(html: str, now: datetime | None = None) -> list[dict]:
    parser = OfficialTableParser()
    parser.feed(html)
    matches = []
    for row in parser.rows:
        if len(row) < 4 or not row[0].isdigit():
            continue
        match_no = int(row[0])
        if not 1 <= match_no <= 15:
            continue
        if " - " not in row[1]:
            continue
        home_raw, away_raw = row[1].split(" - ", 1)
        date_match = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", row[2])
        time_match = re.fullmatch(r"\d{2}:\d{2}", row[3])
        if not date_match or not time_match:
            continue
        home = canonical_team(home_raw)
        away = canonical_team(away_raw)
        league, country = competition_for(match_no, home, away)
        local_date = datetime.strptime(
            f"{date_match.group(1)} {row[3]}", "%d.%m.%Y %H:%M"
        )
        matches.append({
            "match_no": str(match_no),
            "date": local_date.isoformat() + "+03:00",
            "league": league,
            "country": country,
            "home": home,
            "away": away,
        })
    return validate_matches(matches, now)


def extract_matches(html: str, now: datetime | None = None) -> list[dict]:
    parser = VisibleTextParser()
    parser.feed(html)
    text = "\n".join(parser.parts)
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
            "date": local_date.isoformat() + "+03:00",
            "league": league,
            "country": country,
            "home": home,
            "away": away,
        })

    return validate_matches(matches, now)


def csv_text(rows: list[dict], fields: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main() -> None:
    headers = {"User-Agent": "sportoto-ai/1.0 (+GitHub Actions weekly bulletin update)"}
    try:
        response = requests.get(OFFICIAL_SOURCE_URL, headers=headers, timeout=45)
        response.raise_for_status()
        matches = extract_official_matches(response.text)
        source = OFFICIAL_SOURCE_URL
    except (requests.RequestException, ValueError) as official_error:
        print(f"Resmi Spor Toto kaynagi kullanilamadi: {official_error}")
        response = requests.get(FALLBACK_SOURCE_URL, headers=headers, timeout=45)
        response.raise_for_status()
        matches = extract_matches(response.text)
        source = FALLBACK_SOURCE_URL
    print(f"Liste kaynagi: {source}")

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
