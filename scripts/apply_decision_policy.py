"""Apply no-1X2 Spor Toto decision policy to data/matches.json."""
from __future__ import annotations

import csv, json, unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_FILES = [ROOT / "data/matches.json", ROOT / "docs/data/matches.json"]
PRED = ROOT / "data/predictions.csv"
CONS = ROOT / "data/consensus.csv"
OUTCOMES = ("1", "X", "2")
ALLOWED = {"1", "X", "2", "1X", "X2", "12"}
WIDE_DOUBLES, NARROW_DOUBLES, NARROW_MAX = 11, 7, 8
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
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    for w in ("fk", "sk", "spor", "sportif", "faaliyetler", "tumosan", "corendon", "arca"):
        s = s.replace(w, " ")
    return " ".join(s.split())


def norm_pick(v, field, no):
    raw = (v or "").strip().upper().replace("0", "X").replace("-", "").replace("/", "").replace(" ", "")
    if not raw:
        return ""
    pick = "".join(x for x in OUTCOMES if x in raw)
    if len(pick) == 3 or pick == "1X2":
        raise SystemExit(f"{no}. maçta {field}={v!r} geçersiz: 1X2 yasak.")
    if pick not in ALLOWED:
        raise SystemExit(f"{no}. maçta {field}={v!r} geçersiz tercih.")
    return pick


def width(pick: str) -> int:
    return sum(x in pick for x in OUTCOMES)


def columns(matches, field):
    total = 1
    for m in matches:
        w = width(m.get(field, ""))
        if not w:
            return 0
        total *= w
    return total


def ordered(dist):
    return sorted(((x, float((dist or {}).get(x, 0) or 0)) for x in OUTCOMES), key=lambda t: t[1], reverse=True)


def pair(symbols):
    return "".join(x for x in OUTCOMES if x in symbols)


def ensure_consensus(n=15):
    if CONS.exists():
        return
    CONS.parent.mkdir(parents=True, exist_ok=True)
    with CONS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CONS_FIELDS, lineterminator="\n")
        w.writeheader()
        for i in range(1, n + 1):
            w.writerow({"match_no": str(i)})


def load_csv(path):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        return {(r.get("match_no") or "").strip(): r for r in csv.DictReader(f) if (r.get("match_no") or "").strip()}


def consensus_avg(row):
    vals = {x: [] for x in OUTCOMES}
    for src in ("sportoto", "nesine", "bilyoner", "misli", "hedef15"):
        for sym, key in (("1", "1"), ("X", "x"), ("2", "2")):
            raw = (row or {}).get(f"{src}_{key}_pct", "")
            try:
                if raw != "": vals[sym].append(float(str(raw).replace(",", ".")))
            except ValueError:
                pass
    return {k: round(sum(v) / len(v), 1) for k, v in vals.items() if v}


def early_tr(m):
    try: month = datetime.fromisoformat(m["date"]).month
    except Exception: month = 0
    return m.get("country") == "Türkiye" and month in {8, 9}


def big_team(m):
    return norm(m.get("home", "")) in BIG_TR or norm(m.get("away", "")) in BIG_TR


def decide(m):
    dist = m.get("model_1x2") or {}
    if not dist:
        return {"status": "unavailable", "reason": "Model yok; manuel tek/çift tercih girilmeli."}
    r = ordered(dist); top, p1 = r[0]; second, p2 = r[1]; _, p3 = r[2]
    margin = p1 - p2
    reasons = []
    if p1 < 58: reasons.append("Favori %58 altında; tek için ayrışma yok.")
    if margin < 15: reasons.append("İlk iki ihtimal farkı 15 puanın altında.")
    if early_tr(m) and not big_team(m) and 50 <= p1 <= 58:
        reasons.append("Türkiye erken sezon + büyük takım dışı %50-58 favori; tek yasak.")
    cons = consensus_avg(m.get("external_consensus") or {})
    trap, trap_reason = False, ""
    if cons:
        ctop, cp = ordered(cons)[0]
        if ctop == top and cp >= 65 and p1 < 60:
            trap, trap_reason = True, "Kitle favoriye yığılmış ama model aynı gücü üretmiyor."
        elif ctop != top and cp >= 45:
            trap, trap_reason = True, "Kitle/model yönü ayrışıyor; ters taraf yaşatılmalı."
    surprise = 10 - max(0, (p1 - 33.3) / 5) - max(0, margin / 8) + (1 if reasons else 0) + (1 if trap else 0)
    surprise = round(max(0, min(10, surprise)), 1)
    conf = "A" if not reasons and p1 >= 65 and margin >= 25 and surprise <= 3.5 else "B" if not reasons and p1 >= 58 and margin >= 15 else "D" if surprise >= 8 else "C"
    return {
        "status": "ready", "policy": "no_triples_v2", "model_single": top,
        "model_double": pair([top, second]), "ranked_outcomes": [{"symbol": s, "percentage": p} for s, p in r],
        "top_margin_pct": round(margin, 1), "third_probability_pct": round(p3, 1),
        "single_forbidden": bool(reasons), "single_forbidden_reasons": reasons,
        "favorite_risk_reason": reasons[0] if reasons else trap_reason or "Favori ayrışmış; tek kararı kolon dağılımına göre verilecek.",
        "trap_favorite_alarm": trap, "trap_favorite_reason": trap_reason, "consensus_1x2": cons,
        "surprise_score": surprise, "confidence_class": conf,
    }


def risk(m):
    d = m.get("decision", {})
    if d.get("status") != "ready": return 999
    top = d["ranked_outcomes"][0]["percentage"]
    val = 100 - top + d.get("surprise_score", 0) * 2 - d.get("top_margin_pct", 0) * .4
    if d.get("single_forbidden"): val += 30
    if d.get("trap_favorite_alarm"): val += 12
    return val


def apply(matches, field, target, max_double):
    manual_double = sum(1 for m in matches if m.get(field) and width(m[field]) == 2)
    slots = max(0, max_double - manual_double)
    need = max(0, target - manual_double)
    blank = [m for m in matches if not m.get(field) and m.get("decision", {}).get("status") == "ready"]
    forced = sorted([m for m in blank if m["decision"].get("single_forbidden")], key=risk, reverse=True)
    doubles = {id(m) for m in forced[:slots]}
    rest = sorted([m for m in blank if id(m) not in doubles], key=risk, reverse=True)
    doubles.update(id(m) for m in rest[:max(0, need - len(doubles))])
    for m in blank:
        m[field] = m["decision"]["model_double"] if id(m) in doubles else m["decision"]["model_single"]
    warn = []
    if len(forced) > slots: warn.append(f"Zorunlu çift sinyali {len(forced)}, kapasite {slots}; en riskliler seçildi.")
    col = columns(matches, field)
    if field == "wide_pick" and col > 2500: warn.append(f"Geniş kupon 2500 üstü: {col}")
    if field == "narrow_pick" and not (128 <= col <= 256): warn.append(f"Dar kupon 128-256 dışında: {col}")
    return {"field": field, "policy": "no_triples_v2", "target_doubles": target, "max_doubles": max_double,
            "single_count": sum(1 for m in matches if width(m.get(field, "")) == 1),
            "double_count": sum(1 for m in matches if width(m.get(field, "")) == 2),
            "manual_count": sum(1 for m in matches if m.get("manual_" + field, "")), "columns": col, "warnings": warn}


def enrich(doc):
    matches = doc.get("matches") or []
    if len(matches) != 15: raise SystemExit(f"JSON 15 yerine {len(matches)} maç içeriyor.")
    ensure_consensus(len(matches)); pred, cons = load_csv(PRED), load_csv(CONS)
    for m in matches:
        no = str(m.get("match_no") or m.get("fixture_id") or "")
        p = pred.get(no, {})
        m["match_no"] = no
        m["manual_wide_pick"] = norm_pick(p.get("wide_pick"), "wide_pick", no)
        m["manual_narrow_pick"] = norm_pick(p.get("narrow_pick"), "narrow_pick", no)
        m["wide_pick"], m["narrow_pick"] = m["manual_wide_pick"], m["manual_narrow_pick"]
        m["external_consensus"] = cons.get(no, {})
        m["decision"] = decide(m)
    doc["wide_strategy"] = apply(matches, "wide_pick", WIDE_DOUBLES, WIDE_DOUBLES)
    doc["narrow_strategy"] = apply(matches, "narrow_pick", NARROW_DOUBLES, NARROW_MAX)
    for m in matches:
        if width(m.get("wide_pick", "")) >= 3 or width(m.get("narrow_pick", "")) >= 3:
            raise SystemExit(f"{m['match_no']}. maçta üçlü tercih üretildi; politika ihlali.")
    doc["wide_columns"], doc["narrow_columns"] = columns(matches, "wide_pick"), columns(matches, "narrow_pick")
    doc["decision_policy"] = {"name": "no_triples_v2", "allowed_picks": sorted(ALLOWED), "forbidden_picks": ["1X2"],
        "wide_target": "11 doubles + 4 singles = 2048 columns", "narrow_target": "7-8 doubles = 128-256 columns",
        "principles": ["1X2 kullanılmaz.", "Tahmin siteleri kopya için değil konsensüs/tuzak favori için kullanılır.", "Türkiye erken sezonunda büyük takım dışı %50-58 favoriler tek geçilmez."]}
    doc["source"] = str(doc.get("source", "unknown")) + "+no_triples_policy"
    doc["matches"] = matches
    return doc


def main():
    src = next((p for p in JSON_FILES if p.exists()), None)
    if not src: raise SystemExit("matches.json bulunamadı.")
    doc = enrich(json.loads(src.read_text(encoding="utf-8")))
    for p in JSON_FILES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Karar politikası uygulandı: geniş {doc['wide_columns']} kolon, dar {doc['narrow_columns']} kolon, üçlü yok.")

if __name__ == "__main__":
    main()
