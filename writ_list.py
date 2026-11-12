#!/usr/bin/env python3
"""Crafting'siz writ alim listesi.  Kullanim: python writ_list.py [adet=50]
Her sipariş turu icin: writ fiyati + istedigi item'in AH fiyati, rep basina toplam; en ucuzdan N farkli siparis (gunde ayni siparis 1 kez)."""
import json, re, subprocess, sys, statistics as st
N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
def show(path):
    return subprocess.run(["git", "show", path], capture_output=True, text=True).stdout
subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", "snapshot"])
h = json.loads(show("FETCH_HEAD:data/house_123.json")); tc = json.loads(show("FETCH_HEAD:data/tipcache.json"))
subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", "probe"])
n = json.loads(show("FETCH_HEAD:data/names.json"))
it = h["items"]; REP = {"Journeyman": 75, "Expert": 125, "Artisan": 200}
rev = {}
for k, v in n.items():
    rev.setdefault(v.get("n", "").lower(), []).append(k)
def g(c):
    c = int(round(c)); s, cu = divmod(c, 100); gg, s = divmod(s, 100)
    return (f"{gg}g" if gg else "") + (f"{s}s" if s else "") + (f"{cu}c" if cu or not (gg or s) else "")
rows, noah = [], []
for i, v in it.items():
    nm = n.get(str(i), {}).get("n", "")
    if not nm.startswith("Craftsman's Writ:") or not v["l"]:
        continue
    item = nm.split(": ", 1)[1]
    t = re.search(r"\b(Journeyman|Expert|Artisan)\b", re.sub(r"<[^>]+>", " ", (tc.get(str(i)) or {}).get("tooltip", "")))
    if not t:
        continue
    tier = t.group(1); rep = REP[tier]; w = v["l"][0][0]
    opts = [sorted(it[x]["l"])[0][0] for x in rev.get(item.lower(), []) if x in it and it[x]["l"]]
    if not opts:
        noah.append((tier, item)); continue
    ic = min(opts); rows.append(((w + ic) / rep, tier, item, w, ic, rep, v["l"][0][1]))
rows.sort()
print(f"Snapshot {h['fetched_at']} | AH'den tam alinabilen {len(rows)} siparis, item'i AH'de olmayan {len(noah)} (crafting gerekir)")
tot_c = tot_r = 0
print(f"\n{'#':>3} {'c/rep':>6} {'tur':<10} {'siparis':<28} {'writ':>7} {'item':>7}  toplam / kumulatif rep")
for k, x in enumerate(rows[:N], 1):
    tot_c += x[3] + x[4]; tot_r += x[5]
    print(f"{k:>3} {x[0]:6.0f} {x[1]:<10} {x[2]:<28} {g(x[3]):>7} {g(x[4]):>7}  {g(x[3] + x[4]):>7} / {tot_r} rep (toplam {g(tot_c)})")
for t in REP:
    a = [x for x in rows if x[1] == t]; b = [y for y in noah if y[0] == t]
    if a or b:
        print(f"{t}: {len(a)} alinabilir, {len(b)} AH'de item yok -> Sealed'dan rastgele cikarsa {len(b)/(len(a)+len(b)):.0%} ihtimalle craft'siz teslim edilemez")
