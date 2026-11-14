#!/usr/bin/env python3
"""Dashboard verisi: data/ altindaki snapshot, isimler, AHledger arsivi, uyari kaydi, tum pazarlar -> site/data/*.json
Calistirma (workflow'da history.py'den sonra): python site_build.py
"""
import csv
import datetime
import glob
import json
import os
import shutil
import re
import statistics

import alerts

OUT = "site/data"
os.makedirs(OUT, exist_ok=True)
MY = "eu-123"


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def dump(name, obj):
    with open(f"{OUT}/{name}", "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)


def hours(ts):  # ISO -> epoch saat (float, 2 hane)
    t = datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    return round(t.timestamp() / 3600, 2)


snap = load("data/house_123.json", {"items": {}, "variants": {}, "fetched_at": ""})
names = load("data/names.json", {}) or {}
ahl = load("data/ahl.json", {}) or {}
holdings = load("holdings.json", {}) or {}
fetched = snap.get("fetched_at", "")


def nm(i):
    i = str(i)
    if i in names:
        return names[i]["n"]
    if i in ahl:
        return ahl[i]["name"]
    return f"Item #{i}"


# ---- gecmis: AHledger arsivi (acilistan beri) + kendi saatlik olcumlerimiz (izlenen itemler)
hist = {}
for i, v in ahl.items():
    pts = [[hours(t), mn] for t, _med, mn, _q in v.get("hist", []) if mn]
    if pts:
        hist[i] = pts
try:
    for r in csv.reader(open("data/history.csv", encoding="utf-8")):
        if len(r) >= 5 and r[1].isdigit():
            hist.setdefault(r[1], []).append([hours(r[0]), round(float(r[2]))])
except OSError:
    pass
for i, v in snap["items"].items():
    if fetched:
        hist.setdefault(i, []).append([hours(fetched), round(v["l"][0][0])])
for i in hist:
    seen, out = set(), []
    for h, p in sorted(hist[i]):
        k = round(h)
        if k in seen:
            continue
        seen.add(k)
        out.append([h, p])
    hist[i] = out
dump("hist.json", hist)


def med_days(i, days):
    pts = hist.get(str(i), [])
    if not pts:
        return None
    cut = pts[-1][0] - 24 * days
    vals = [p for h, p in pts if h >= cut]
    return round(statistics.median(vals)) if vals else None


# ---- bizim pazar: simdiki fiyatlar
now = {}
for i, v in snap["items"].items():
    meta = names.get(i, {})
    a = ahl.get(i, {})
    now[i] = {
        "n": nm(i), "c": meta.get("c") or a.get("itemClass"), "q": a.get("quality"),
        "min": round(v["l"][0][0]), "qty": v["n"], "lv": [[round(p), q] for p, q in v["l"][:8]],
        "m7": med_days(i, 7), "lo30": a.get("low30d"), "hi30": a.get("high30d"),
        "sp": meta.get("sp") if meta.get("sp") is not None else a.get("vendorSell"),
    }
dump("now.json", {"fetched": fetched, "items": now})

# ---- tum pazarlar (ayni item tum sunucularda)
idx = load("data/markets/index.json", {"markets": []})
mk = [m for m in idx.get("markets", [])]
x = {}
for mi, m in enumerate(mk):
    d = load(f"data/markets/{m['key']}.json", {"items": {}})
    for i, (p, q) in d["items"].items():
        x.setdefault(i, {})[mi] = [round(p), q]
names_all = {i: nm(i) for i in set(x) | set(now)}
dump("x.json", {"fetched": idx.get("fetched_at"), "markets": mk, "mine": next((k for k, m in enumerate(mk) if m["key"] == MY), None), "items": x})
dump("names.json", names_all)

# ---- firsat akisi (son 7 gun), ayni anahtar tekrar etmez
feed, status, writmkt = [], [], []
SKIP = {"status", "writmkt", "new", "recipe"}
try:
    for line in open("data/alert_log.jsonl", encoding="utf-8"):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j["kind"] == "status":
            status = j["row"]
            continue
        if j["kind"] == "writmkt":
            writmkt = j["row"]
            continue
        if j["kind"] in SKIP:
            continue
        try:
            txt = alerts.todo_lines([(j["kind"], j["row"], j.get("score", 0))])
        except Exception:  # noqa: BLE001
            txt = []
        feed.append({"ts": j["ts"], "k": j["kind"], "t": txt[0] if txt else " | ".join(str(c) for c in j["row"][:4]), "s": j.get("score", 0),
                     "item": j["row"][0] if j["row"] else ""})
except OSError:
    pass
feed.sort(key=lambda f: f["ts"], reverse=True)
dump("feed.json", {"items": feed[:400], "status": status, "writmkt": writmkt})

# ---- banka
bank = []
for name, cnt in holdings.items():
    iid = next((i for i, v in now.items() if v["n"].lower() == name.lower()), None)
    if not iid:
        iid = next((i for i, n in names_all.items() if n.lower() == name.lower()), None)
    cur = now.get(iid, {}) if iid else {}
    pts = hist.get(iid, []) if iid else []
    d1 = None
    if len(pts) > 2:
        last = pts[-1][0]
        old = [p for h, p in pts if h <= last - 24]
        if old:
            d1 = round(100 * pts[-1][1] / old[-1] - 100)
    bank.append({"id": iid, "n": name, "cnt": cnt, "min": cur.get("min"), "qty": cur.get("qty"), "m7": cur.get("m7"),
                 "lo30": cur.get("lo30"), "hi30": cur.get("hi30"), "d24": d1, "sp": cur.get("sp")})
dump("bank.json", bank)

# ---- meslek planlari: guncel fiyat + stok derinligiyle maliyet
VENDOR = {"Empty Vial": 20, "Simple Wood": 38, "Leaded Vial": 40}
PLANS = [
    {"title": "Alchemy 68 -> 150", "who": "alt", "steps": [
        ["68-90", "Elixir of Minor Fortitude", 23, {"Earthroot": 2, "Peacebloom": 1, "Empty Vial": 1}, "Elixir of Minor Fortitude", 1],
        ["90-120", "Elixir of Wisdom", 30, {"Mageroyal": 1, "Briarthorn": 2, "Empty Vial": 1}, "Elixir of Wisdom", 1],
        ["120-130", "Lesser Mana Potion", 10, {"Mageroyal": 1, "Stranglekelp": 1, "Empty Vial": 1}, "Lesser Mana Potion", 1],
        ["130-150", "Fire Oil", 20, {"Firefin Snapper": 2, "Empty Vial": 1}, "Fire Oil", 2]]},
    {"title": "Enchanting 41 -> 150 (Strange Dust)", "who": "alt", "steps": [
        ["41-70", "Enchant Chest - Inferior Stamina", 30, {"Strange Dust": 1}, None, 0],
        ["70-100", "Enchant Bracer - Minor Stamina", 30, {"Strange Dust": 2}, None, 0],
        ["100-109", "Enchant Cloak - Minor Protection", 9, {"Strange Dust": 2}, None, 0],
        ["109-110", "Runed Silver Rod", 1, {"Silver Rod": 1, "Strange Dust": 3, "Lesser Magic Essence": 4, "Shadowgem": 1}, None, 0],
        ["110-130", "Enchant Cloak - Minor Protection", 32, {"Strange Dust": 2}, None, 0],
        ["130-150", "Enchant Boots - Minor Stamina", 20, {"Strange Dust": 4}, None, 0]]},
    {"title": "Enchanting 41 -> 150 (Magic Wands)", "who": "alt", "steps": [
        ["41-70", "Lesser Magic Wand", 30, {"Simple Wood": 1, "Lesser Magic Essence": 1}, "Lesser Magic Wand", 1],
        ["70-150", "Greater Magic Wand", 140, {"Simple Wood": 1, "Lesser Magic Essence": 2}, "Greater Magic Wand", 1]]},
]
byname = {v["n"]: i for i, v in now.items()}
for i, n in names_all.items():
    byname.setdefault(n, i)


def depth_cost(name, qty):
    if name in VENDOR:
        return VENDOR[name] * qty, qty, "vendor"
    i = byname.get(name)
    if not i or i not in snap["items"]:
        return None, 0, "missing"
    t = g = 0
    for p, q in sorted(snap["items"][i]["l"]):
        k = min(q, qty - g)
        t += p * k
        g += k
        if g >= qty:
            break
    return round(t), g, "ah"


plans = []
for P in PLANS:
    need = {}
    back = 0
    steps = []
    for rng, rec, n, mats, out, per in P["steps"]:
        for m, q in mats.items():
            need[m] = need.get(m, 0) + n * q
        sp = 0
        if out:
            oi = byname.get(out)
            sp = (names.get(oi, {}).get("sp") or 0) if oi else 0
            back += sp * per * n
        steps.append({"range": rng, "recipe": rec, "n": n, "mats": mats, "vendor_back": sp * per * n})
    shop, total, missing = [], 0, []
    for m, q in need.items():
        c, got, src = depth_cost(m, q)
        if c is None or got < q:
            missing.append(m)
        total += c or 0
        shop.append({"n": m, "qty": q, "cost": c, "got": got, "src": src, "unit": round(c / got) if c and got else None,
                     "m7": now.get(byname.get(m, ""), {}).get("m7")})
    plans.append({"title": P["title"], "steps": steps, "shop": shop, "total": total, "back": back, "net": total - back, "missing": missing})
dump("plans.json", plans)


# ---- karakter + item veritabani (tooltip + kaynak + deger)
char = load("data/char.json", None)
tips = load("data/tooltips_ofa.json", {}) or {}
if tips:
    import gear_score as G
    lvl = (char or {}).get("level") or 50
    w = G.weights(lvl)
    # Survival hibrit (melee + ranged, PvP): AP birimi; 1 melee DPS ~ 14 AP, off-hand %75 (Predator's Edge)
    w.update({"str": 1.0, "ap": 1.15, "rap": 0.6, "agi": 2.4, "sta": 2.0, "spi": 0.4, "int": 0.6, "mp5": 2.0,
              "dpsmelee": 16.0, "dpsoh": 12.0, "dps": 8.0, "hit": 20.5, "crit": 19.8, "hp5": 2.0})
    WSUB = {0: "Axe", 1: "2H Axe", 2: "Bow", 3: "Gun", 4: "Mace", 5: "2H Mace", 6: "Polearm", 7: "Sword", 8: "2H Sword", 10: "Staff",
            13: "Fist Weapon", 15: "Dagger", 18: "Crossbow"}
    db = {}
    for iid, t in tips.items():
        try:
            r = G.parse(iid, t)
            r["req"] = G.fix_req(r)
        except Exception:  # noqa: BLE001
            continue
        if not r.get("slot") or not G.usable(r) or not G.obtainable(r):
            continue
        if r.get("cls") == 2 and r.get("sub") in (4, 5):      # Hunter mace kullanamaz
            continue
        if re.match(r"(Plans|Pattern|Schematic|Formula|Recipe|Design|Manual):", r["name"]):
            continue
        typ = r.get("armor_type") or (WSUB.get(r.get("sub")) if r.get("cls") == 2 else "")
        e = {"n": r["name"], "q": r.get("q"), "sl": r["slot"], "rq": r["req"], "il": r.get("ilvl"), "b": r["bind"], "ty": typ or "",
             "st": G.stat_str(r), "v": round(G.value(r, w, "MH"), 1), "src": [x.replace(" (lvl 0)", "") for x in G.src_text(int(iid), {}) if x != "unknown source"],
             "x": r.get("unscored_effects", [])[:2]}
        if r["slot"] in ("1H", "OH"):
            e["vo"] = round(G.value(r, w, "OH"), 1)
        if r.get("random"):
            e["rnd"] = 1
        if iid in now:
            e["ah"] = now[iid]["min"]
        db[iid] = e
    dump("itemdb.json", {"level": lvl, "w": {k: round(v, 3) for k, v in w.items()}, "items": db})
    print("item db:", len(db))
if char:
    dump("char.json", char)

dump("meta.json", {"fetched": fetched, "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "items": len(now), "markets": len(mk), "ntfy": os.environ.get("NTFY_TOPIC", "")})

for f in glob.glob("web/*"):
    if os.path.isfile(f):
        shutil.copy(f, "site/")
print("site hazir:", {f: os.path.getsize(f"{OUT}/{f}") for f in os.listdir(OUT)})
