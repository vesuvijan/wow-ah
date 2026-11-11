#!/usr/bin/env python3
"""AH'deki her gear/recipe ilanini Docker Tuckalot'un ekipmanina gore puanlar; yeni (ilk kez gorulen) itemlari yakalar.
alerts.run() icinden cagrilir:  rows = ah_gear.scan(snap, cfg)  -> [(kind, key, price, row, score)]
Onbellek: data/tipcache.json (Wowhead Forever tooltip; varyantlar ?bonus= ile), data/known_items.json (ilk gorulme)."""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("DPS", "1")
import gear_score as G   # noqa: E402  (ofa/* dosyalarini yukler)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
CACHE = "data/tipcache.json"
KNOWN = "data/known_items.json"
RECIPE_RE = re.compile(r"^(Pattern|Plans|Schematic|Formula|Recipe|Design|Manual|Technique|Book):", re.I)
PLAN = json.load(open("plans/gear_plan_dps.json"))
PLAN_L = json.load(open("plans/gear_plan.json"))
LEVEL = PLAN["meta"]["level"]
W = G.weights(min(LEVEL, 59))
EQ = PLAN["eqval"]
TOTAL = PLAN["total"] or 1
SLOT_EQ = {"HEAD": ["HEAD"], "NECK": ["NECK"], "SHOULDER": ["SHOULDER"], "BACK": ["BACK"], "CHEST": ["CHEST"], "WRIST": ["WRIST"], "HANDS": ["HANDS"],
           "WAIST": ["WAIST"], "LEGS": ["LEGS"], "FEET": ["FEET"], "FINGER": ["FINGER_1", "FINGER_2"], "TRINKET": ["TRINKET_1", "TRINKET_2"], "RANGED": ["RANGED"]}
SLOT_NAME = {"HEAD": "Head", "NECK": "Neck", "SHOULDER": "Shoulders", "BACK": "Back", "CHEST": "Chest", "WRIST": "Wrists", "HANDS": "Hands", "WAIST": "Waist",
             "LEGS": "Legs", "FEET": "Feet", "FINGER": "Ring", "TRINKET": "Trinket", "RANGED": "Ranged weapon", "1H": "One-hand weapon", "MH": "Main-hand weapon",
             "OH": "Off-hand weapon", "2H": "Two-hand weapon"}
# plan'daki hedef itemlarin isimleri -> tarif (recipe) esleme icin
WANT = {}
for p_ in (PLAN, PLAN_L):
    for sl, v in p_.items():
        if isinstance(v, dict) and "options" in v:
            for o in v["options"]:
                if o["gain_pct"] >= 2.0:
                    WANT[o["name"].lower()] = (o["name"], o["gain_pct"])
lock, last = threading.Lock(), [0.0]


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def pace(rate):
    with lock:
        now = time.time()
        wait = last[0] + 1.0 / rate - now
        last[0] = max(now, last[0] + 1.0 / rate)
    if wait > 0:
        time.sleep(wait)


def fetch_tip(key, rate=6.0):
    iid, _, v = key.partition(":")
    url = f"https://nether.wowhead.com/forever/tooltip/item/{iid}"
    if v.startswith("b"):
        url += "?bonus=" + v[1:].replace("-", ":")
    for t in range(2):
        pace(rate)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25) as r:
                return key, json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return key, {"none": 1}
            time.sleep(2)
        except Exception:  # noqa: BLE001
            time.sleep(2)
    return key, None


def money(c):
    c = int(round(c)); g, rem = divmod(c, 10000); s, cu = divmod(rem, 100)
    return "".join([f"{g}g" if g else "", f"{s}s" if s else "", f"{cu}c" if cu or not (g or s) else ""])


def scan(snap, cfg, budget_s=150):
    cache = load(CACHE, {})
    known = load(KNOWN, None)
    keys = {}
    for k, v in snap["items"].items():
        if v["l"]:
            keys[k] = v
    variants = snap.get("variants", {})
    has_var = {k.split(":")[0] for k in variants}
    for k in has_var:
        keys.pop(k, None)
    for k, v in variants.items():
        if v["l"]:
            keys[k] = v
    # 1) eksik tooltip'leri cek (sure sinirli, kalan sonraki calismada)
    missing = [k for k in keys if k not in cache]
    deadline = time.time() + budget_s
    got = 0
    if missing:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for k, t in ex.map(lambda kk: fetch_tip(kk) if time.time() < deadline else (kk, "skip"), missing):
                if t == "skip" or t is None:
                    continue
                cache[k] = t
                got += 1
    json.dump(cache, open(CACHE, "w"), separators=(",", ":"))
    # 2) puanla
    out, new_rows = [], []
    first_run = known is None
    known = known or {}
    pending = set(known.pop("_pending", []))
    now_ts = snap["fetched_at"]
    for k in keys:
        iid_ = k.split(":")[0]
        if iid_ not in known:
            known[iid_] = now_ts
            if not first_run:
                pending.add(iid_)
    want_min = cfg.get("gear_min_gain", 3.0)
    max_price = cfg.get("gear_max_price", 1000000)
    rec_max = cfg.get("recipe_max_price", 2000000)
    best_oh = PLAN["weapons"]["NOW"][0]["oh"].get("val_oh", 0) if PLAN.get("weapons", {}).get("NOW") else 0
    for k, v in keys.items():
        t = cache.get(k)
        iid = k.split(":")[0]
        p0, q0 = v["l"][0]
        if not t or t.get("none"):
            continue
        is_new = iid in pending
        pending.discard(iid)
        try:
            r = G.parse(iid, t)
        except Exception:  # noqa: BLE001
            continue
        r["req"] = G.fix_req(r)
        label = r["name"] + (" (random-stat variant)" if ":" in k else "")
        # tarif / pattern
        if RECIPE_RE.match(r["name"]):
            plain = re.sub(r"<[^>]+>", " ", t["tooltip"])
            m = re.search(r"Teaches you how to (?:make|create|craft)\s+(.+?)[.\n]", plain) or re.search(r"Teaches you .*?:\s*(.+?)[.\n]", plain)
            target = (m.group(1).strip() if m else re.sub(r"^[A-Za-z]+:\s*", "", r["name"]))
            hit = WANT.get(target.lower()) or WANT.get(re.sub(r"^[A-Za-z]+:\s*", "", r["name"]).lower())
            if hit and p0 <= rec_max:
                out.append(("recipe", f"recipe{k}", p0, [r["name"], money(p0), f"x{q0}", f"Makes {hit[0]} (+{hit[1]:.1f}% upgrade)", "", ""], hit[1] * 1000 - p0 / 1000))
            continue
        if not G.usable(r) or (r["q"] or 0) < 2 or r["req"] > LEVEL + 2:
            continue
        sl = r["slot"]
        if sl in SLOT_EQ:
            eqs = [EQ.get(s, 0) for s in SLOT_EQ[sl]]
            cur = min(eqs) if eqs else 0
            val = G.value(r, W)
            gain = 100 * (val - cur) / TOTAL
            if gain >= want_min and p0 <= max_price:
                out.append(("gear", f"gear{k}", p0, [label, money(p0), f"+{gain:.1f}%", SLOT_NAME.get(sl, sl), r["bind"] or "-", G_stats(r), f"req {r['req']}"], gain))
                if is_new and not first_run:
                    new_rows.append(("new", f"new{k}", p0, [label, money(p0), "upgrade", SLOT_NAME.get(sl, sl), "", G_stats(r), ""], gain + 100))
        elif sl in ("1H", "MH", "OH") and r.get("cls") == 2 and r["dps"]:
            ov = G.value(r, W, "OH")
            if best_oh and ov >= 0.9 * best_oh and p0 <= max_price:
                out.append(("gear", f"gear{k}", p0, [label, money(p0), f"{r['dps']:.1f} dps", SLOT_NAME.get(sl, sl), r["bind"] or "-", G_stats(r), f"req {r['req']}"], ov / 10))
        if is_new and not first_run and (r["q"] or 0) >= cfg.get("new_item_min_quality", 3):
            new_rows.append(("new", f"new{k}", p0, [label, money(p0), "new on AH", SLOT_NAME.get(sl, sl or "item"), "", G_stats(r), ""], 50 + (r["q"] or 0)))
    known["_pending"] = sorted(pending)
    json.dump(known, open(KNOWN, "w"), separators=(",", ":"))
    print(f"ah_gear: {len(keys)} listings, tooltips cached {len(cache)} (+{got}, missing {len(missing) - got}), gear/recipe hits {len(out)}, new {len(new_rows)}{' (first run: seeded silently)' if first_run else ''}")
    out.sort(key=lambda x: -x[4])
    return out[:12] + new_rows[:6]


def G_stats(r):
    return G.stat_str(r)
