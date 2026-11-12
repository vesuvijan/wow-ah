#!/usr/bin/env python3
"""Son N saatin toplu ozeti.  Kullanim: python digest.py [saat=8]
Veriyi snapshot dalindaki data/alert_log.jsonl'dan okur (alerts.py her uyariyi oraya yazar)."""
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta

hours = float(sys.argv[1]) if len(sys.argv) > 1 else 8
subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", "snapshot"], check=False)
raw = subprocess.run(["git", "show", "FETCH_HEAD:data/alert_log.jsonl"], capture_output=True, text=True).stdout
rows = [json.loads(l) for l in raw.splitlines() if l.strip()]
if not rows:
    sys.exit("Kayit yok (alert_log.jsonl henuz olusmadi).")
now = datetime.strptime(max(r["ts"] for r in rows), "%Y-%m-%dT%H:%M:%SZ")
since = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
rows = [r for r in rows if r["ts"] >= since]
tr = lambda ts: (datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)).strftime("%d.%m %H:%M")
by = defaultdict(list)
for r in rows:
    by[r["kind"]].append(r)
print(f"Son {hours:g} saat ({tr(since)} - {tr(max(r['ts'] for r in rows))} TR): {sum(len(v) for k, v in by.items() if k != 'status')} uyari")
for kind in ("gear", "recipe", "writ", "snipe", "flip", "favor", "sell", "mat", "new"):
    v = by.get(kind)
    if not v:
        continue
    best = {}
    for r in v:                      # ayni item icin en iyi (en yuksek skor) kayit
        k = r["row"][0]
        if k not in best or r["score"] > best[k]["score"]:
            best[k] = r
    print(f"\n[{kind.upper()}] {len(v)} uyari, {len(best)} farkli")
    for r in sorted(best.values(), key=lambda x: -x["score"])[:8]:
        print(f"  {tr(r['ts'])}  " + " | ".join(str(x) for x in r["row"][:6] if x not in ("", None)))
st = by.get("status")
if st:
    print(f"\n[SON DURUM {tr(st[-1]['ts'])}]")
    print("\n".join("  " + l for l in st[-1]["row"]))
