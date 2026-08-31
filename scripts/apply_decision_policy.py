"""Apply narrow-first, no-1X2 Spor Toto decision policy to matches.json."""
from __future__ import annotations

import csv
import json
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_FILES = [ROOT / "data/matches.json", ROOT / "docs/data/matches.json"]
PRED = ROOT / "data/predictions.csv"
CONS = ROOT / "data/consensus.csv"
OUTCOMES = ("1", "X", "2")
ALLOWED = {"1", "X", "2", "1X", "X2", "12"}
NARROW_TARGET_DOUBLES = 7
NARROW_MAX_DOUBLES = 8
WIDE_TARGET_DOUBLES = 11
BIG_TR = {"galatasaray", "fenerbahce", "besiktas", "trabzonspor"}
CONS_FIELDS = [
    "match_no",
    "sportoto_1_pct", "sportoto_x_pct", "sportoto_2_pct",
    "nesine_1_pct", "nesine_x_pct", "nesine_2_pct",
    "bilyoner_1_pct", "bilyoner_x_pct", "bilyoner_2_pct",
    "misli_1_pct", "misli_x_pct", "misli_2_pct",
    "hedef15_1_pct", "hedef15_x_pct", "hedef15_2_pct",
    "site_pick", "site_note",
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    for word in ("fk", "sk", "spor", "sportif", "faaliyetler", "tumosan", "corendon", "arca"):
        s = s.replace(word, " ")
    return " ".join(s.split())


def norm_pick(value, field: str, match_no: str) -> str:
    raw = (value or "").strip().upper().replace("0", "X")
    raw = raw.replace("-", "").replace("/", "").replace(" ", "")
    if not raw:
        return ""
    pick = "".join(symbol for symbol in OUTCOMES if symbol in raw)
    if len(pick) == 3 or pick == "1X2":
        raise SystemExit(f"{match_no}. maçta {field}={value!r} geçersiz: 1X2 yasak.")
    if pick not in ALLOWED:
        raise SystemExit(f"{match_no}. maçta {field}={value!r} geçersiz tercih.")
    return pick


def width(pick: str) -> int:
    return sum(symbol in (pick or "") for symbol in OUTCOMES)


def columns(matches: list[dict], field: str) -> int:
    total = 1
    for match in matches:
        pick_width = width(match.get(field, ""))
        if not pick_width:
            return 0
        total *= pick_width
    return total


def ordered(dist: dict | None) -> list[tuple[str, float]]:
    return sorted(
        ((symbol, float((dist or {}).get(symbol, 0) or 0)) for symbol in OUTCOMES),
        key=lambda item: item[1],
        reverse=True,
    )


def pair(symbols) -> str:
    return "".join(symbol for symbol in OUTCOMES if symbol in symbols)


def union_pick(left: str, right: str) -> str:
    return "".join(symbol for symbol in OUTCOMES if symbol in (left or "") or symbol in (right or ""))


def ensure_consensus(row_count: int = 15) -> None:
    if CONS.exists():
        return
    CONS.parent.mkdir(parents=True, exist_ok=True)
    with CONS.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CONS_FIELDS, lineterminator="\n")
        writer.writeheader()
        for index in range(1, row_count + 1):
            writer.writerow({"match_no": str(index)})


def load_csv(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as file:
        return {
            (row.get("match_no") or "").strip(): row
            for row in csv.DictReader(file)
            if (row.get("match_no") or "").strip()
        }


def consensus_avg(row: dict | None) -> dict[str, float]:
    values = {symbol: [] for symbol in OUTCOMES}
    for source in ("sportoto", "nesine", "bilyoner", "misli", "hedef15"):
        for symbol, key in (("1", "1"), ("X", "x"), ("2", "2")):
            raw = (row or {}).get(f"{source}_{key}_pct", "")
            try:
                if raw != "":
                    values[symbol].append(float(str(raw).replace(",", ".")))
            except ValueError:
                pass
    return {symbol: round(sum(items) / len(items), 1) for symbol, items in values.items() if items}


def early_tr(match: dict) -> bool:
    try:
        month = datetime.fromisoformat(match["date"]).month
    except Exception:
        month = 0
    return match.get("country") == "Türkiye" and month in {8, 9}


def has_big_team(match: dict) -> bool:
    return norm(match.get("home", "")) in BIG_TR or norm(match.get("away", "")) in BIG_TR


def base_distribution(match: dict) -> tuple[dict, str]:
    model = match.get("model_1x2") or {}
    if model:
        return model, "model"
    consensus = consensus_avg(match.get("external_consensus") or {})
    if consensus:
        return consensus, "consensus"
    return {}, "unavailable"


def decide(match: dict) -> dict:
    dist, source = base_distribution(match)
    if not dist:
        return {"status": "unavailable", "reason": "Model/konsensüs yok; manuel tek/çift tercih girilmeli."}

    ranked = ordered(dist)
    top, top_pct = ranked[0]
    second, second_pct = ranked[1]
    _, third_pct = ranked[2]
    margin = top_pct - second_pct
    reasons: list[str] = []

    if top_pct < 58:
        reasons.append("Favori %58 altında; tek için ayrışma yok.")
    if margin < 15:
        reasons.append("İlk iki ihtimal farkı 15 puanın altında.")
    if early_tr(match) and not has_big_team(match) and 50 <= top_pct <= 58:
        reasons.append("Türkiye erken sezon + büyük takım dışı %50-58 favori; tek yasak.")

    consensus = consensus_avg(match.get("external_consensus") or {})
    trap = False
    trap_reason = ""
    if consensus:
        consensus_top, consensus_pct = ordered(consensus)[0]
        if consensus_top == top and consensus_pct >= 65 and top_pct < 60:
            trap = True
            trap_reason = "Kitle favoriye yığılmış ama model aynı gücü üretmiyor."
        elif consensus_top != top and consensus_pct >= 45:
            trap = True
            trap_reason = "Kitle/model yönü ayrışıyor; ters taraf yaşatılmalı."

    surprise = 10 - max(0, (top_pct - 33.3) / 5) - max(0, margin / 8)
    surprise += 1 if reasons else 0
    surprise += 1 if trap else 0
    surprise = round(max(0, min(10, surprise)), 1)

    confidence = (
        "A" if not reasons and top_pct >= 65 and margin >= 25 and surprise <= 3.5
        else "B" if not reasons and top_pct >= 58 and margin >= 15
        else "D" if surprise >= 8
        else "C"
    )

    return {
        "status": "ready",
        "policy": "narrow_first_no_triples_v3",
        "distribution_source": source,
        "model_single": top,
        "model_double": pair([top, second]),
        "ranked_outcomes": [{"symbol": symbol, "percentage": pct} for symbol, pct in ranked],
        "top_margin_pct": round(margin, 1),
        "third_probability_pct": round(third_pct, 1),
        "single_forbidden": bool(reasons),
        "single_forbidden_reasons": reasons,
        "favorite_risk_reason": reasons[0] if reasons else trap_reason or "Favori ayrışmış; tek kararı dar kupon bütçesine göre verilecek.",
        "trap_favorite_alarm": trap,
        "trap_favorite_reason": trap_reason,
        "consensus_1x2": consensus,
        "surprise_score": surprise,
        "confidence_class": confidence,
    }


def risk_score(match: dict) -> float:
    decision = match.get("decision", {})
    if decision.get("status") != "ready":
        return 999.0
    top_pct = decision["ranked_outcomes"][0]["percentage"]
    value = 100 - top_pct + decision.get("surprise_score", 0) * 2 - decision.get("top_margin_pct", 0) * 0.4
    if decision.get("single_forbidden"):
        value += 30
    if decision.get("trap_favorite_alarm"):
        value += 12
    return value


def double_including(base_pick: str, decision: dict) -> str:
    if width(base_pick) == 2:
        return base_pick
    if width(base_pick) != 1 or decision.get("status") != "ready":
        return decision.get("model_double", "")
    base_symbol = next(symbol for symbol in OUTCOMES if symbol in base_pick)
    for item in decision.get("ranked_outcomes", []):
        candidate = item["symbol"]
        if candidate != base_symbol:
            return pair([base_symbol, candidate])
    return base_pick


def build_narrow_primary(matches: list[dict]) -> dict:
    manual_double_count = sum(1 for match in matches if width(match.get("narrow_pick", "")) == 2)
    blanks = [match for match in matches if not match.get("narrow_pick") and match.get("decision", {}).get("status") == "ready"]
    forced = sorted(
        [match for match in blanks if match["decision"].get("single_forbidden")],
        key=risk_score,
        reverse=True,
    )

    desired_doubles = max(NARROW_TARGET_DOUBLES, min(NARROW_MAX_DOUBLES, manual_double_count + len(forced)))
    desired_doubles = min(NARROW_MAX_DOUBLES, desired_doubles)
    slots = max(0, desired_doubles - manual_double_count)

    double_ids = {id(match) for match in forced[:slots]}
    rest = sorted([match for match in blanks if id(match) not in double_ids], key=risk_score, reverse=True)
    double_ids.update(id(match) for match in rest[: max(0, slots - len(double_ids))])

    for match in blanks:
        decision = match["decision"]
        if id(match) in double_ids:
            match["narrow_pick"] = decision["model_double"]
            match["narrow_pick_origin"] = "auto_primary_double"
        else:
            match["narrow_pick"] = decision["model_single"]
            match["narrow_pick_origin"] = "auto_primary_single"

    warnings = []
    if len(forced) > slots:
        warnings.append(f"Zorunlu çift sinyali {len(forced)}, dar kapasite {slots}; en riskliler çiftlendi.")
    if any(not match.get("narrow_pick") for match in matches):
        warnings.append("Model/konsensüs olmayan maçlarda manuel dar tercih gerekiyor.")
    col = columns(matches, "narrow_pick")
    if col and not (128 <= col <= 256):
        warnings.append(f"Dar kupon hedef bandı 128-256 dışında: {col}")

    return {
        "field": "narrow_pick",
        "role": "primary_real_money_coupon",
        "policy": "narrow_first_no_triples_v3",
        "target_doubles": NARROW_TARGET_DOUBLES,
        "max_doubles": NARROW_MAX_DOUBLES,
        "single_count": sum(1 for match in matches if width(match.get("narrow_pick", "")) == 1),
        "double_count": sum(1 for match in matches if width(match.get("narrow_pick", "")) == 2),
        "manual_count": sum(1 for match in matches if match.get("manual_narrow_pick", "")),
        "columns": col,
        "warnings": warnings,
    }


def build_wide_from_narrow(matches: list[dict]) -> dict:
    warnings = []
    for match in matches:
        manual_wide = match.get("manual_wide_pick", "")
        narrow = match.get("narrow_pick", "")
        if manual_wide:
            merged = union_pick(manual_wide, narrow)
            if width(merged) <= 2:
                match["wide_pick"] = merged
                match["wide_pick_origin"] = "manual_wide_plus_narrow" if merged != manual_wide else "manual_wide"
            else:
                match["wide_pick"] = narrow
                match["wide_pick_origin"] = "narrow_kept_manual_wide_conflict"
                warnings.append(f"{match.get('match_no')}. maçta manuel geniş darı üçlüye çevireceği için dar tercih korundu.")
        else:
            match["wide_pick"] = narrow
            match["wide_pick_origin"] = "from_narrow_primary"

    current_doubles = sum(1 for match in matches if width(match.get("wide_pick", "")) == 2)
    upgrade_slots = max(0, WIDE_TARGET_DOUBLES - current_doubles)
    candidates = sorted(
        [match for match in matches if width(match.get("wide_pick", "")) == 1 and match.get("decision", {}).get("status") == "ready"],
        key=risk_score,
        reverse=True,
    )

    for match in candidates[:upgrade_slots]:
        upgraded = double_including(match["wide_pick"], match["decision"])
        if width(upgraded) == 2:
            match["wide_pick"] = upgraded
            match["wide_pick_origin"] = "narrow_plus_sanal_extra"

    if any(not match.get("wide_pick") for match in matches):
        warnings.append("Model/konsensüs olmayan maçlarda manuel geniş tercih gerekiyor.")
    col = columns(matches, "wide_pick")
    if col > 2500:
        warnings.append(f"Geniş sanal kupon 2500 üstü: {col}")

    return {
        "field": "wide_pick",
        "role": "secondary_virtual_control_coupon",
        "policy": "narrow_first_no_triples_v3",
        "target_doubles": WIDE_TARGET_DOUBLES,
        "single_count": sum(1 for match in matches if width(match.get("wide_pick", "")) == 1),
        "double_count": sum(1 for match in matches if width(match.get("wide_pick", "")) == 2),
        "manual_count": sum(1 for match in matches if match.get("manual_wide_pick", "")),
        "columns": col,
        "warnings": warnings,
    }


def enrich(document: dict) -> dict:
    matches = document.get("matches") or []
    if len(matches) != 15:
        raise SystemExit(f"JSON 15 yerine {len(matches)} maç içeriyor.")

    ensure_consensus(len(matches))
    predictions = load_csv(PRED)
    consensus_rows = load_csv(CONS)

    for match in matches:
        match_no = str(match.get("match_no") or match.get("fixture_id") or "")
        row = predictions.get(match_no, {})
        match["match_no"] = match_no
        match["manual_narrow_pick"] = norm_pick(row.get("narrow_pick"), "narrow_pick", match_no)
        match["manual_wide_pick"] = norm_pick(row.get("wide_pick"), "wide_pick", match_no)
        match["narrow_pick"] = match["manual_narrow_pick"]
        match["wide_pick"] = ""
        match["external_consensus"] = consensus_rows.get(match_no, {})
        match["decision"] = decide(match)

    document["narrow_strategy"] = build_narrow_primary(matches)
    document["wide_strategy"] = build_wide_from_narrow(matches)

    for match in matches:
        if width(match.get("wide_pick", "")) >= 3 or width(match.get("narrow_pick", "")) >= 3:
            raise SystemExit(f"{match['match_no']}. maçta üçlü tercih üretildi; politika ihlali.")

    document["narrow_columns"] = columns(matches, "narrow_pick")
    document["wide_columns"] = columns(matches, "wide_pick")
    document["primary_coupon"] = "narrow"
    document["secondary_coupon"] = "wide_virtual"
    document["decision_policy"] = {
        "name": "narrow_first_no_triples_v3",
        "primary_coupon": "narrow_real_money",
        "secondary_coupon": "wide_virtual_plus_probability",
        "allowed_picks": sorted(ALLOWED),
        "forbidden_picks": ["1X2"],
        "narrow_target": "7-8 doubles = 128-256 columns; real-money primary coupon",
        "wide_target": "narrow coupon + extra probabilities; target 11 doubles + 4 singles = 2048 columns",
        "principles": [
            "Önce gerçek oynanacak dar kupon üretilir.",
            "Geniş kupon dar kuponun üzerine sanal +ihtimal kontrolüdür.",
            "1X2 kullanılmaz.",
            "Tahmin siteleri kopya için değil konsensüs/tuzak favori için kullanılır.",
            "Türkiye erken sezonunda büyük takım dışı %50-58 favoriler tek geçilmez.",
        ],
    }
    document["source"] = str(document.get("source", "unknown")) + "+narrow_first_no_triples_policy"
    document["matches"] = matches
    return document


def main() -> None:
    source = next((path for path in JSON_FILES if path.exists()), None)
    if not source:
        raise SystemExit("matches.json bulunamadı.")
    document = enrich(json.loads(source.read_text(encoding="utf-8")))
    for path in JSON_FILES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Dar öncelikli karar politikası uygulandı: dar {document['narrow_columns']} kolon, "
        f"geniş sanal {document['wide_columns']} kolon, üçlü yok."
    )


if __name__ == "__main__":
    main()
