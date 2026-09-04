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
BALANCE_EXPECTED_GAP_MAX = 0.75
BALANCE_COVERAGE_GAP_MIN = 4
BIG_TR = {"galatasaray", "fenerbahce", "besiktas", "trabzonspor"}
CONS_FIELDS = [
    "match_no",
    "sportoto_1_pct", "sportoto_x_pct", "sportoto_2_pct",
    "nesine_1_pct", "nesine_x_pct", "nesine_2_pct",
    "bilyoner_1_pct", "bilyoner_x_pct", "bilyoner_2_pct",
    "misli_1_pct", "misli_x_pct", "misli_2_pct",
    "hedef15_1_pct", "hedef15_x_pct", "hedef15_2_pct",
    "model_a_name", "model_a_1_pct", "model_a_x_pct", "model_a_2_pct",
    "model_b_name", "model_b_1_pct", "model_b_x_pct", "model_b_2_pct",
    "model_c_name", "model_c_1_pct", "model_c_x_pct", "model_c_2_pct",
    "source_updated_at",
    "site_pick", "site_note",
    "external_sites_1_pct", "external_sites_x_pct", "external_sites_2_pct",
    "external_source_count", "external_numeric_source_count",
    "external_pick_1_pct", "external_pick_x_pct", "external_pick_2_pct",
    "external_top_signal", "external_agreement_pct", "external_source_names",
    "external_comment_summary", "external_updated_at",
]
PUBLIC_SOURCES = ("sportoto", "nesine", "bilyoner", "misli")
MODEL_SOURCES = ("hedef15", "model_a", "model_b", "model_c")


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
    if raw == "1X2":
        raise SystemExit(f"{match_no}. maçta {field}={value!r} geçersiz: 1X2 yasak.")
    if raw not in ALLOWED:
        raise SystemExit(f"{match_no}. maçta {field}={value!r} geçersiz tercih.")
    return raw


def parse_manual_pick(value, field: str, match_no: str) -> tuple[str, str, dict | None]:
    """Parse one manual request without stopping the other match analyses."""
    requested = (value or "").strip().upper().replace("0", "X")
    requested = requested.replace("-", "").replace("/", "").replace(" ", "")
    try:
        return norm_pick(value, field, match_no), requested, None
    except SystemExit as error:
        return "", requested, {
            "status": "rejected_invalid_pick",
            "requested": requested,
            "error": str(error),
        }


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


def recommended_pick(decision: dict, pick_width: int) -> str:
    if decision.get("status") != "ready" or pick_width not in {1, 2}:
        return ""
    symbols = [item["symbol"] for item in decision.get("ranked_outcomes", [])[:pick_width]]
    return pair(symbols)


def covered_probability(decision: dict, pick: str) -> float | None:
    if decision.get("status") != "ready" or not pick:
        return None
    probabilities = {
        item["symbol"]: float(item["percentage"])
        for item in decision.get("ranked_outcomes", [])
    }
    return round(sum(probabilities.get(symbol, 0) for symbol in OUTCOMES if symbol in pick), 1)


def validate_manual_pick(pick: str, reason: str, decision: dict) -> tuple[str, dict]:
    if not pick:
        return "", {"status": "not_requested"}
    pick_width = width(pick)
    recommended = recommended_pick(decision, pick_width)
    requested_probability = covered_probability(decision, pick)
    recommended_probability = covered_probability(decision, recommended)
    probability_loss = (
        round(recommended_probability - requested_probability, 1)
        if requested_probability is not None and recommended_probability is not None
        else None
    )
    audit = {
        "requested": pick,
        "recommended_same_width": recommended,
        "requested_probability_pct": requested_probability,
        "recommended_probability_pct": recommended_probability,
        "probability_loss_pct": probability_loss,
        "reason": reason,
    }
    if not recommended:
        return pick, audit | {"status": "accepted_without_model"}
    if pick == recommended:
        return pick, audit | {"status": "accepted_model_aligned"}
    if reason.strip():
        return pick, audit | {"status": "accepted_documented_override"}
    return "", audit | {"status": "rejected_missing_reason", "effective": recommended}


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


def source_distribution(row: dict | None, source: str) -> dict[str, float]:
    values = {}
    for symbol, key in (("1", "1"), ("X", "x"), ("2", "2")):
        raw = (row or {}).get(f"{source}_{key}_pct", "")
        try:
            if raw != "":
                values[symbol] = float(str(raw).replace(",", "."))
        except ValueError:
            pass
    if len(values) != 3 or sum(values.values()) <= 0:
        return {}
    total = sum(values.values())
    return {symbol: value * 100 / total for symbol, value in values.items()}


def consensus_avg(row: dict | None, sources=PUBLIC_SOURCES + MODEL_SOURCES) -> dict[str, float]:
    values = {symbol: [] for symbol in OUTCOMES}
    for source in sources:
        distribution = source_distribution(row, source)
        for symbol, key in (("1", "1"), ("X", "x"), ("2", "2")):
            if distribution:
                values[symbol].append(distribution[symbol])
    return {symbol: round(sum(items) / len(items), 1) for symbol, items in values.items() if items}


def source_count(row: dict | None, sources) -> int:
    return sum(bool(source_distribution(row, source)) for source in sources)


def independent_model_consensus(row: dict | None) -> tuple[dict[str, float], int]:
    distributions = [
        value for source in MODEL_SOURCES
        if (value := source_distribution(row, source))
    ]
    external = source_distribution(row, "external_sites")
    try:
        external_count = int(float((row or {}).get("external_numeric_source_count", 0) or 0))
    except ValueError:
        external_count = 0
    weighted = [(value, 1) for value in distributions]
    if external and external_count > 0:
        weighted.append((external, external_count))
    total_count = sum(count for _, count in weighted)
    if not total_count:
        return {}, 0
    average = {
        symbol: round(
            sum(value[symbol] * count for value, count in weighted) / total_count, 1
        )
        for symbol in OUTCOMES
    }
    return average, total_count


def blend_distributions(internal: dict, external: dict, external_weight: float) -> dict:
    return {
        symbol: round(float(internal.get(symbol, 0)) * (1 - external_weight) + float(external.get(symbol, 0)) * external_weight, 1)
        for symbol in OUTCOMES
    }


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
    row = match.get("external_consensus") or {}
    external_models, model_coverage = independent_model_consensus(row)
    if model:
        if external_models:
            weight = 0.25 if model_coverage >= 2 else 0.15
            return blend_distributions(model, external_models, weight), f"internal_plus_external_models_{model_coverage}"
        return model, "internal_model"
    consensus = external_models or consensus_avg(row, PUBLIC_SOURCES)
    if consensus:
        return consensus, "external_models" if external_models else "public_consensus_only"
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

    row = match.get("external_consensus") or {}
    consensus = consensus_avg(row, PUBLIC_SOURCES)
    external_models, model_coverage = independent_model_consensus(row)
    public_coverage = source_count(row, PUBLIC_SOURCES)
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
    site_signal = (row.get("external_top_signal") or "").strip().upper()
    try:
        site_agreement = float((row.get("external_agreement_pct") or "0").replace(",", "."))
    except ValueError:
        site_agreement = 0.0
    if not trap and site_signal in OUTCOMES:
        if site_signal == top and site_agreement >= 65 and top_pct < 60:
            trap = True
            trap_reason = "Tahmin siteleri favoride birleşmiş ama model aynı gücü üretmiyor."
        elif site_signal != top and site_agreement >= 45:
            trap = True
            trap_reason = "Tahmin sitesi yönü modelden ayrışıyor; ters taraf kontrol edilmeli."

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
        "policy": "narrow_first_no_triples_v6",
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
        "external_model_1x2": external_models,
        "consensus_coverage": {
            "public_sources": public_coverage,
            "independent_model_sources": model_coverage,
            "prediction_site_rows": int(float(row.get("external_source_count", 0) or 0)),
        },
        "prediction_site_signal": {
            "top": row.get("external_top_signal", ""),
            "agreement_pct": row.get("external_agreement_pct", ""),
            "pick_distribution": {
                "1": row.get("external_pick_1_pct", ""),
                "X": row.get("external_pick_x_pct", ""),
                "2": row.get("external_pick_2_pct", ""),
            },
            "sources": row.get("external_source_names", ""),
            "comment_summary": row.get("external_comment_summary", ""),
            "updated_at": row.get("external_updated_at", ""),
        },
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


def wide_upgrade_reason(match: dict, added_symbol: str) -> str:
    decision = match.get("decision", {})
    reasons = []
    if decision.get("trap_favorite_alarm"):
        reasons.append("tuzak favori/kitle-model ayrışması")
    external = decision.get("external_model_1x2") or {}
    if external and max(external, key=external.get) == added_symbol:
        reasons.append("bağımsız model konsensüsü")
    sample = match.get("model_sample") or {}
    if (sample.get("h2h") or {}).get("matches", 0):
        reasons.append("H2H kontrolü")
    if (sample.get("recent_form") or {}).get("home"):
        reasons.append("son 5 form kontrolü")
    if not reasons:
        reasons.append("dar kupon risk sıralaması")
    return "; ".join(reasons)


def portfolio_audit(matches: list[dict], field: str) -> dict:
    expected = {symbol: 0.0 for symbol in OUTCOMES}
    coverage = {symbol: 0 for symbol in OUTCOMES}
    ready_count = complete_pick_count = 0
    inefficient = []

    for match in matches:
        pick = match.get(field, "")
        if pick:
            complete_pick_count += 1
            for symbol in OUTCOMES:
                if symbol in pick:
                    coverage[symbol] += 1
        decision = match.get("decision", {})
        if decision.get("status") != "ready":
            continue
        ready_count += 1
        for item in decision.get("ranked_outcomes", []):
            expected[item["symbol"]] += float(item["percentage"]) / 100
        if pick:
            best = recommended_pick(decision, width(pick))
            actual_probability = covered_probability(decision, pick)
            best_probability = covered_probability(decision, best)
            loss = round((best_probability or 0) - (actual_probability or 0), 1)
            match[f"{field}_probability_audit"] = {
                "pick": pick,
                "best_same_width": best,
                "covered_probability_pct": actual_probability,
                "best_probability_pct": best_probability,
                "probability_loss_pct": loss,
                "efficient": loss <= 0.1,
            }
            if loss > 0.1:
                inefficient.append({
                    "match_no": match.get("match_no"),
                    "pick": pick,
                    "best_same_width": best,
                    "probability_loss_pct": loss,
                })

    expected = {symbol: round(value, 2) for symbol, value in expected.items()}
    warnings = []
    audit_complete = ready_count == len(matches) and complete_pick_count == len(matches)
    expected_x2_gap = round(abs(expected["X"] - expected["2"]), 2)
    coverage_x2_gap = abs(coverage["X"] - coverage["2"])
    if audit_complete and expected_x2_gap <= BALANCE_EXPECTED_GAP_MAX and coverage_x2_gap >= BALANCE_COVERAGE_GAP_MIN:
        warnings.append(
            "X ve 2 beklenen sonuç sayıları yakın olmasına rağmen kupon kapsaması aşırı ayrışıyor."
        )
    if inefficient:
        warnings.append(f"{len(inefficient)} seçim aynı genişlikteki en yüksek olasılıklı tercihten sapıyor.")
    if not audit_complete:
        warnings.append("Portföy denge denetimi kısmi: 15 maçın tamamında model ve tercih bulunmuyor.")
    return {
        "field": field,
        "ready_model_count": ready_count,
        "complete_pick_count": complete_pick_count,
        "audit_complete": audit_complete,
        "expected_result_counts": expected,
        "coverage_counts": coverage,
        "expected_x_vs_2_gap": expected_x2_gap,
        "coverage_x_vs_2_gap": coverage_x2_gap,
        "imbalance_alarm": bool(warnings and audit_complete and expected_x2_gap <= BALANCE_EXPECTED_GAP_MAX and coverage_x2_gap >= BALANCE_COVERAGE_GAP_MIN),
        "inefficient_selections": inefficient,
        "warnings": warnings,
    }


def build_narrow_primary(matches: list[dict]) -> dict:
    manual_double_count = sum(1 for match in matches if width(match.get("narrow_pick", "")) == 2)
    blanks = [
        match for match in matches
        if not match.get("narrow_pick")
        and match.get("decision", {}).get("status") == "ready"
        and match.get("manual_narrow_audit", {}).get("status") != "rejected_invalid_pick"
    ]
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
    rejected_manual = [
        match.get("match_no") for match in matches
        if match.get("manual_narrow_audit", {}).get("status") == "rejected_missing_reason"
    ]
    if rejected_manual:
        warnings.append(
            f"Gerekçesiz manuel dar sapma reddedildi: {', '.join(rejected_manual)}. maçlar."
        )
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
        "policy": "narrow_first_no_triples_v6",
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
    rejected_manual = [
        match.get("match_no") for match in matches
        if match.get("manual_wide_audit", {}).get("status") == "rejected_missing_reason"
    ]
    if rejected_manual:
        warnings.append(
            f"Gerekçesiz manuel geniş sapma reddedildi: {', '.join(rejected_manual)}. maçlar."
        )
    for match in matches:
        manual_wide = match.get("manual_wide_pick", "")
        narrow = match.get("narrow_pick", "")
        if match.get("manual_wide_audit", {}).get("status") == "rejected_invalid_pick":
            match["wide_pick"] = ""
            match["wide_pick_origin"] = "manual_wide_rejected_invalid"
        elif manual_wide:
            # Manuel tercih aynen korunur. Darı kapsamıyorsa bütünlük denetimi
            # kuponu geçersiz işaretler; seçim sessizce değiştirilmez.
            match["wide_pick"] = manual_wide
            match["wide_pick_origin"] = "manual_wide"
            if manual_wide != narrow:
                match["wide_extra_reason"] = "manuel geniş kupon değerlendirmesi"
        else:
            match["wide_pick"] = narrow
            match["wide_pick_origin"] = "from_narrow_primary"

    current_doubles = sum(1 for match in matches if width(match.get("wide_pick", "")) == 2)
    upgrade_slots = max(0, WIDE_TARGET_DOUBLES - current_doubles)
    candidates = sorted(
        [
            match for match in matches
            if width(match.get("wide_pick", "")) == 1
            and match.get("decision", {}).get("status") == "ready"
            and not match.get("manual_wide_pick")
        ],
        key=risk_score,
        reverse=True,
    )

    for match in candidates[:upgrade_slots]:
        upgraded = double_including(match["wide_pick"], match["decision"])
        if width(upgraded) == 2:
            match["wide_pick"] = upgraded
            match["wide_pick_origin"] = "narrow_plus_sanal_extra"
            added = next(symbol for symbol in OUTCOMES if symbol in upgraded and symbol not in match["narrow_pick"])
            match["wide_extra_outcome"] = added
            match["wide_extra_reason"] = wide_upgrade_reason(match, added)

    if any(not match.get("wide_pick") for match in matches):
        warnings.append("Model/konsensüs olmayan maçlarda manuel geniş tercih gerekiyor.")
    col = columns(matches, "wide_pick")
    if col > 2500:
        warnings.append(f"Geniş sanal kupon 2500 üstü: {col}")

    return {
        "field": "wide_pick",
        "role": "secondary_virtual_control_coupon",
        "policy": "narrow_first_no_triples_v6",
        "target_doubles": WIDE_TARGET_DOUBLES,
        "single_count": sum(1 for match in matches if width(match.get("wide_pick", "")) == 1),
        "double_count": sum(1 for match in matches if width(match.get("wide_pick", "")) == 2),
        "manual_count": sum(1 for match in matches if match.get("manual_wide_pick", "")),
        "columns": col,
        "warnings": warnings,
    }


def coupon_integrity(matches: list[dict], field: str) -> dict:
    """Validate a coupon without changing its effective picks."""
    is_narrow = field == "narrow_pick"
    label = "Dar" if is_narrow else "Geniş"
    audit_field = "manual_narrow_audit" if is_narrow else "manual_wide_audit"
    errors = []
    incomplete_match_nos = []
    expected_match_nos = {str(number) for number in range(1, 16)}
    actual_match_nos = [str(match.get("match_no") or "?") for match in matches]
    actual_match_no_set = set(actual_match_nos)

    # Eksik satır diğer maçları bastırmaz; kuponu yalnızca eksik bırakır.
    incomplete_match_nos.extend(sorted(expected_match_nos - actual_match_no_set, key=int))
    duplicate_match_nos = sorted(
        {match_no for match_no in actual_match_nos if actual_match_nos.count(match_no) > 1}
    )
    unexpected_match_nos = sorted(actual_match_no_set - expected_match_nos)
    if duplicate_match_nos:
        errors.append({
            "code": "duplicate_match_rows",
            "match_nos": duplicate_match_nos,
            "message": f"Tekrarlanan maç satırları: {', '.join(duplicate_match_nos)}.",
        })
    if unexpected_match_nos:
        errors.append({
            "code": "unexpected_match_rows",
            "match_nos": unexpected_match_nos,
            "message": f"Beklenmeyen maç satırları: {', '.join(unexpected_match_nos)}.",
        })

    for match in matches:
        match_no = str(match.get("match_no") or "?")
        audit = match.get(audit_field, {})
        if audit.get("status") == "rejected_invalid_pick":
            errors.append({
                "code": "invalid_manual_pick",
                "match_no": match_no,
                "requested": audit.get("requested", ""),
                "message": audit.get("error", "Geçersiz manuel tercih."),
            })
        pick = match.get(field, "")
        if not pick:
            if match_no not in incomplete_match_nos:
                incomplete_match_nos.append(match_no)
        elif pick not in ALLOWED or width(pick) not in {1, 2}:
            errors.append({
                "code": "invalid_effective_pick",
                "match_no": match_no,
                "pick": pick,
                "message": f"{match_no}. maçta {field}={pick!r} geçersiz.",
            })

    double_count = sum(1 for match in matches if width(match.get(field, "")) == 2)
    col = columns(matches, field)
    if not incomplete_match_nos:
        if is_narrow and double_count not in {NARROW_TARGET_DOUBLES, NARROW_MAX_DOUBLES}:
            errors.append({
                "code": "narrow_double_count",
                "message": f"Dar kupon 7-8 yerine {double_count} çift içeriyor.",
            })
        if is_narrow and not (128 <= col <= 256):
            errors.append({
                "code": "narrow_column_limit",
                "message": f"Dar kupon 128-256 yerine {col} kolon içeriyor.",
            })
        if not is_narrow and double_count != WIDE_TARGET_DOUBLES:
            errors.append({
                "code": "wide_double_count",
                "message": f"Geniş kupon 11 yerine {double_count} çift içeriyor.",
            })
        if not is_narrow and col > 2500:
            errors.append({
                "code": "wide_column_limit",
                "message": f"Geniş kupon 2500 sınırını aşıyor: {col} kolon.",
            })

    if not is_narrow:
        for match in matches:
            match_no = str(match.get("match_no") or "?")
            narrow = match.get("narrow_pick", "")
            wide = match.get("wide_pick", "")
            if not narrow:
                if match_no not in incomplete_match_nos:
                    incomplete_match_nos.append(match_no)
                continue
            if narrow and wide and any(symbol in narrow and symbol not in wide for symbol in OUTCOMES):
                errors.append({
                    "code": "wide_missing_narrow_pick",
                    "match_no": match_no,
                    "narrow_pick": narrow,
                    "wide_pick": wide,
                    "message": f"{match_no}. maçta geniş tercih ({wide}) dar tercihi ({narrow}) kapsamıyor.",
                })

    status = "invalid" if errors else "incomplete" if incomplete_match_nos else "valid"
    return {
        "field": field,
        "label": label,
        "status": status,
        "final": status == "valid",
        "playable": status == "valid" and is_narrow,
        "complete_pick_count": sum(1 for match in matches if match.get(field, "")),
        "incomplete_match_nos": incomplete_match_nos,
        "double_count": double_count,
        "columns": col,
        "errors": errors,
    }


def decision_coverage(matches: list[dict]) -> dict:
    """Summarize independent match decisions without blocking available matches."""
    automatic_ready = []
    manual_only = []
    partial = []
    pending = []
    narrow_ready = []
    wide_ready = []

    for match in matches:
        match_no = str(match.get("match_no") or "?")
        decision_ready = match.get("decision", {}).get("status") == "ready"
        narrow_ok = width(match.get("narrow_pick", "")) in {1, 2}
        wide_ok = width(match.get("wide_pick", "")) in {1, 2}
        if decision_ready:
            match["decision_status"] = "ready"
            automatic_ready.append(match_no)
        elif narrow_ok and wide_ok:
            match["decision_status"] = "manual_ready"
            manual_only.append(match_no)
        elif narrow_ok or wide_ok:
            match["decision_status"] = "partial"
            partial.append(match_no)
        else:
            match["decision_status"] = "unavailable"
            pending.append(match_no)
        if narrow_ok:
            narrow_ready.append(match_no)
        if wide_ok:
            wide_ready.append(match_no)

    expected_match_nos = {str(number) for number in range(1, 16)}
    actual_match_nos = {str(match.get("match_no") or "?") for match in matches}
    missing_match_nos = sorted(expected_match_nos - actual_match_nos, key=int)
    pending.extend(match_no for match_no in missing_match_nos if match_no not in pending)
    completed = (
        not missing_match_nos
        and len(narrow_ready) == 15
        and len(wide_ready) == 15
    )
    incomplete = [
        str(match.get("match_no") or "?")
        for match in matches
        if match.get("decision_status") not in {"ready", "manual_ready"}
    ]
    incomplete.extend(match_no for match_no in missing_match_nos if match_no not in incomplete)
    return {
        "status": "complete" if completed else "unavailable" if len(pending) == 15 else "partial",
        "total_matches": 15,
        "ready_count": len(automatic_ready) + len(manual_only),
        "automatic_ready_count": len(automatic_ready),
        "manual_only_count": len(manual_only),
        "partial_count": len(partial),
        "pending_count": len(pending),
        "automatic_ready_match_nos": automatic_ready,
        "manual_only_match_nos": manual_only,
        "partial_match_nos": partial,
        "pending_match_nos": pending,
        "incomplete_match_nos": incomplete,
        "narrow_ready_count": len(narrow_ready),
        "wide_ready_count": len(wide_ready),
    }


def enrich(document: dict) -> dict:
    matches = document.get("matches") or []
    ensure_consensus(len(matches))
    predictions = load_csv(PRED)
    consensus_rows = load_csv(CONS)

    for match in matches:
        match_no = str(match.get("match_no") or match.get("fixture_id") or "")
        row = predictions.get(match_no, {})
        match["match_no"] = match_no
        match["external_consensus"] = consensus_rows.get(match_no, {})
        match["decision"] = decide(match)
        narrow_pick, requested_narrow, narrow_input_error = parse_manual_pick(
            row.get("narrow_pick"), "narrow_pick", match_no
        )
        wide_pick, requested_wide, wide_input_error = parse_manual_pick(
            row.get("wide_pick"), "wide_pick", match_no
        )
        narrow_reason = (row.get("narrow_reason") or "").strip()
        wide_reason = (row.get("wide_reason") or "").strip()
        match["requested_manual_narrow_pick"] = requested_narrow
        match["requested_manual_wide_pick"] = requested_wide
        match["manual_narrow_reason"] = narrow_reason
        match["manual_wide_reason"] = wide_reason
        if narrow_input_error:
            match["manual_narrow_pick"] = ""
            match["manual_narrow_audit"] = narrow_input_error
        else:
            match["manual_narrow_pick"], match["manual_narrow_audit"] = validate_manual_pick(
                narrow_pick, narrow_reason, match["decision"]
            )
        if wide_input_error:
            match["manual_wide_pick"] = ""
            match["manual_wide_audit"] = wide_input_error
        else:
            match["manual_wide_pick"], match["manual_wide_audit"] = validate_manual_pick(
                wide_pick, wide_reason, match["decision"]
            )
        match["narrow_pick"] = match["manual_narrow_pick"]
        match["wide_pick"] = ""

    document["narrow_strategy"] = build_narrow_primary(matches)
    document["wide_strategy"] = build_wide_from_narrow(matches)
    narrow_validation = coupon_integrity(matches, "narrow_pick")
    wide_validation = coupon_integrity(matches, "wide_pick")
    document["narrow_strategy"]["validation"] = narrow_validation
    document["wide_strategy"]["validation"] = wide_validation
    document["narrow_strategy"]["portfolio_audit"] = portfolio_audit(matches, "narrow_pick")
    document["wide_strategy"]["portfolio_audit"] = portfolio_audit(matches, "wide_pick")

    for match in matches:
        if width(match.get("wide_pick", "")) >= 3 or width(match.get("narrow_pick", "")) >= 3:
            raise SystemExit(f"{match['match_no']}. maçta üçlü tercih üretildi; politika ihlali.")

    document["narrow_columns"] = columns(matches, "narrow_pick")
    document["wide_columns"] = columns(matches, "wide_pick")
    document["decision_coverage"] = decision_coverage(matches)
    validation_statuses = {narrow_validation["status"], wide_validation["status"]}
    overall_validation_status = (
        "invalid" if "invalid" in validation_statuses
        else "incomplete" if "incomplete" in validation_statuses
        else "valid"
    )
    document["coupon_validation"] = {
        "status": overall_validation_status,
        "narrow_playable": narrow_validation["playable"],
        "wide_virtual_final": wide_validation["final"],
        "narrow": narrow_validation,
        "wide": wide_validation,
    }
    document["publication_status"] = "match_based"
    document["primary_coupon"] = "narrow"
    document["secondary_coupon"] = "wide_virtual"
    document["decision_policy"] = {
        "name": "narrow_first_no_triples_v6",
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
            "Kaynak tahminleri ayrı satırlarda tutulur; yüzdesiz tercihler olasılığa çevrilmez.",
            "Yorumların yalnızca kısa özeti ve kaynak bağlantısı saklanır; tam metin kopyalanmaz.",
            "Aynı oynanma yüzdesini taşıyan bayi kaynakları tek kitle sinyali sayılır; mükerrer ağırlık verilmez.",
            "Bağımsız tahmin modelleri, kaynak sayısına göre ana olasılığa en fazla %25 ağırlıkla katılır.",
            "Geniş kupon yalnızca dar kuponun üzerine kurulur ve dar tercihi mutlaka kapsar.",
            "Kolon, çift sayısı veya kapsama kuralını ihlal eden kupon yalnız uyarılmaz; invalid ve oynanamaz işaretlenir.",
            "H2H ve son form her hafta yeniden hesaplanır; ilk 5-6 haftada H2H ağırlığı düşürülür.",
            "Tek ve çiftlerde varsayılan tercih, aynı genişlikte en yüksek toplam olasılığı kapsar; X'e güvenlik önceliği verilmez.",
            "Model sıralamasından manuel sapma yalnızca yazılı kadro, piyasa, H2H veya takım karakteri gerekçesiyle kabul edilir.",
            "Beklenen X ve 2 sayıları yakınken kapsama farkı 4 veya daha fazlaysa portföy dengesizliği alarmı üretilir.",
            "Sabit 5-5-5 sonuç kotası uygulanmaz; dağılım maçların olasılıklarına göre denetlenir.",
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
