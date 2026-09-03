"""Aggregate source-level prediction-site inputs into the per-match consensus file."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "data/external_predictions.csv"
CONSENSUS = ROOT / "data/consensus.csv"
OUTCOMES = ("1", "X", "2")
ALLOWED_PICKS = {"1", "X", "2", "1X", "X2", "12"}
EXTERNAL_FIELDS = [
    "week_id", "match_no", "source_name", "source_type", "pick",
    "prob_1_pct", "prob_x_pct", "prob_2_pct", "confidence_pct",
    "comment_summary", "source_url", "source_published_at", "collected_at",
]
SUMMARY_FIELDS = [
    "external_sites_1_pct", "external_sites_x_pct", "external_sites_2_pct",
    "external_source_count", "external_numeric_source_count",
    "external_pick_1_pct", "external_pick_x_pct", "external_pick_2_pct",
    "external_top_signal", "external_agreement_pct", "external_source_names",
    "external_comment_summary", "external_updated_at",
]


def normalize_pick(value: str, match_no: str, source_name: str) -> str:
    raw = (value or "").strip().upper().replace("0", "X")
    raw = raw.replace("-", "").replace("/", "").replace(" ", "")
    if not raw:
        return ""
    pick = "".join(symbol for symbol in OUTCOMES if symbol in raw)
    if pick not in ALLOWED_PICKS:
        raise SystemExit(
            f"{match_no}. maç / {source_name}: pick={value!r} geçersiz; 1X2 yasak."
        )
    return pick


def parse_number(value: str) -> float | None:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def distribution(row: dict) -> dict[str, float]:
    values = {
        "1": parse_number(row.get("prob_1_pct", "")),
        "X": parse_number(row.get("prob_x_pct", "")),
        "2": parse_number(row.get("prob_2_pct", "")),
    }
    if any(value is None or value < 0 for value in values.values()):
        return {}
    total = sum(values.values())
    if total <= 0:
        return {}
    return {symbol: value * 100 / total for symbol, value in values.items()}


def row_timestamp(row: dict) -> str:
    return (row.get("collected_at") or row.get("source_published_at") or "").strip()


def latest_source_rows(rows: list[dict]) -> list[dict]:
    latest: dict[str, tuple[str, int, dict]] = {}
    for index, row in enumerate(rows):
        source = (row.get("source_name") or "").strip()
        if not source:
            continue
        candidate = (row_timestamp(row), index, row)
        if source not in latest or candidate[:2] >= latest[source][:2]:
            latest[source] = candidate
    return [item[2] for item in latest.values()]


def summarize(rows: list[dict]) -> dict[str, str]:
    rows = latest_source_rows(rows)
    numeric = [item for item in (distribution(row) for row in rows) if item]
    picks = []
    for row in rows:
        pick = normalize_pick(
            row.get("pick", ""), row.get("match_no", ""), row.get("source_name", "")
        )
        if pick:
            picks.append(pick)

    summary = {field: "" for field in SUMMARY_FIELDS}
    summary["external_source_count"] = str(len(rows)) if rows else ""
    summary["external_numeric_source_count"] = str(len(numeric)) if numeric else ""

    if numeric:
        for symbol, key in (("1", "1"), ("X", "x"), ("2", "2")):
            average = sum(item[symbol] for item in numeric) / len(numeric)
            summary[f"external_sites_{key}_pct"] = f"{average:.1f}"

    if picks:
        votes = {symbol: 0.0 for symbol in OUTCOMES}
        for pick in picks:
            share = 1 / len(pick)
            for symbol in OUTCOMES:
                if symbol in pick:
                    votes[symbol] += share
        vote_pct = {symbol: votes[symbol] * 100 / len(picks) for symbol in OUTCOMES}
        for symbol, key in (("1", "1"), ("X", "x"), ("2", "2")):
            summary[f"external_pick_{key}_pct"] = f"{vote_pct[symbol]:.1f}"
        ranked = sorted(vote_pct.items(), key=lambda item: item[1], reverse=True)
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            summary["external_top_signal"] = ranked[0][0]
        summary["external_agreement_pct"] = f"{ranked[0][1]:.1f}"

    summary["external_source_names"] = "; ".join(
        sorted({(row.get("source_name") or "").strip() for row in rows if row.get("source_name")})
    )
    notes = []
    for row in rows:
        note = " ".join((row.get("comment_summary") or "").split())
        if note:
            notes.append(f"{row.get('source_name', '').strip()}: {note}")
    summary["external_comment_summary"] = " | ".join(notes)
    dates = [row_timestamp(row) for row in rows if row_timestamp(row)]
    summary["external_updated_at"] = max(dates) if dates else ""
    return summary


def ensure_external_file() -> None:
    if EXTERNAL.exists():
        return
    EXTERNAL.parent.mkdir(parents=True, exist_ok=True)
    with EXTERNAL.open("w", newline="", encoding="utf-8") as file:
        csv.DictWriter(file, fieldnames=EXTERNAL_FIELDS, lineterminator="\n").writeheader()


def main() -> None:
    ensure_external_file()
    with EXTERNAL.open(newline="", encoding="utf-8-sig") as file:
        external_rows = list(csv.DictReader(file))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in external_rows:
        match_no = (row.get("match_no") or "").strip()
        if match_no:
            grouped[match_no].append(row)

    existing_rows: dict[str, dict] = {}
    fieldnames = ["match_no"]
    if CONSENSUS.exists():
        with CONSENSUS.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            fieldnames = list(reader.fieldnames or fieldnames)
            existing_rows = {
                (row.get("match_no") or "").strip(): row
                for row in reader
                if (row.get("match_no") or "").strip()
            }
    for field in SUMMARY_FIELDS:
        if field not in fieldnames:
            fieldnames.append(field)

    CONSENSUS.parent.mkdir(parents=True, exist_ok=True)
    with CONSENSUS.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for number in range(1, 16):
            match_no = str(number)
            row = dict(existing_rows.get(match_no, {"match_no": match_no}))
            row.update(summarize(grouped.get(match_no, [])))
            writer.writerow(row)
    print(
        f"{len(external_rows)} kaynak satırı işlendi; data/consensus.csv özeti güncellendi."
    )


if __name__ == "__main__":
    main()
