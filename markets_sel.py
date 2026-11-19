#!/usr/bin/env python3
"""data/markets/*.json -> kucuk data/markets_sel.json (secili item'lar) ; snapshot branch'ine gider, server karsilastirmasi icin."""
import glob, json, os
SEL = {12363,12360,12359,13468,12811,11382,12655,12799,12800,12361,12364,7910,11754,10620,3858,3860,4306,7082,7080,7078,7076,7068,12803,12808,12809,12810,14343,14344,13926,8153,7971,7972,16202,16204}
out = {"markets": {}}
idx = {}
try:
    idx = {m["key"]: m for m in json.load(open("data/markets/index.json")).get("markets", [])}
    out["fetched_at"] = json.load(open("data/markets/index.json")).get("fetched_at")
except Exception:
    pass
for f in sorted(glob.glob("data/markets/*-*.json")):
    key = os.path.basename(f)[:-5]
    d = json.load(open(f))
    out["markets"][key] = {"meta": idx.get(key), "items": {k: v for k, v in d.get("items", {}).items() if int(k) in SEL}}
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/markets_sel.json", "w"), separators=(",", ":"))
print("markets_sel:", len(out["markets"]), "markets")
