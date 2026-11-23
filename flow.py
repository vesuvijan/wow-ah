#!/usr/bin/env python3
"""Iki saatlik snapshot arasindaki farktan akis (flow) cikarir -> data/flow.csv
Girdi : data/house_prev.json (onceki snapshot), data/house_123.json (simdiki)
Cikti : data/flow.csv  ts,item,sold_est,sold_min,sold_max,gone_other,added,added_min,added_max,qty,minp
  sold_est   : listeden kaybolan adet, onceki snapshot'ta en ucuz fiyat seviyelerindeydi (alicilar once en ucuzu alir) -> tahmini SATIS
  gone_other : kaybolan ama pahali seviyedeydi (iptal / sure doldu / undercut sonrasi iptal) -> satis sayilmaz
  added      : yeni listelenen adet (fiyat araligi added_min..added_max)
Not: Blizzard API satis kaydi vermez; bu tahmindir. Fiyatlar bakir."""
import csv, datetime, json, os, sys

def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return None

# her zaman izlenecekler: Devilsaur Leggings/Gauntlets + hammaddeler (Cured Rugged Hide, Devilsaur Leather, Rugged Leather)
EXTRA = {15062, 15063, 15407, 15417, 8170}


def tracked():
    ids = set(EXTRA)
    try:
        import re
        m = re.search(r"SEL = \{([^}]*)\}", open("markets_sel.py").read())
        ids |= {int(x) for x in m.group(1).split(",")}
    except Exception:
        pass
    try:
        rows = list(csv.reader(open("data/history.csv")))[-4000:]
        ids |= {int(r[1]) for r in rows if len(r) > 1}
    except Exception:
        pass
    return ids

def main():
    cur, prev = load("data/house_123.json"), load("data/house_prev.json")
    if not cur or not prev or cur.get("fetched_at") == prev.get("fetched_at"):
        print("flow: onceki snapshot yok / ayni"); return
    ts = cur["fetched_at"]
    out = []
    for iid in sorted(tracked()):
        a = {p: q for p, q in prev["items"].get(str(iid), {}).get("l", [])}
        b = {p: q for p, q in cur["items"].get(str(iid), {}).get("l", [])}
        if not a and not b: continue
        # seviye bazli fark
        gone, add = [], []
        for p in set(a) | set(b):
            d = b.get(p, 0) - a.get(p, 0)
            if d < 0: gone.append((p, -d))
            elif d > 0: add.append((p, d))
        if not gone and not add: continue
        # onceki en ucuz seviyeler: alicilarin ilk aldigi katman. kaybolan fiyat <= (onceki min * 1.15) -> satis
        pmin = min(a) if a else None
        sold = [(p, q) for p, q in gone if pmin is not None and p <= pmin * 1.15]
        other = [(p, q) for p, q in gone if (p, q) not in sold]
        out.append([ts, iid,
                    sum(q for _, q in sold), int(min((p for p, _ in sold), default=0)), int(max((p for p, _ in sold), default=0)),
                    sum(q for _, q in other),
                    sum(q for _, q in add), int(min((p for p, _ in add), default=0)), int(max((p for p, _ in add), default=0)),
                    sum(b.values()), int(min(b)) if b else 0])
    path = "data/flow.csv"
    old = []
    if os.path.exists(path):
        old = list(csv.reader(open(path)))
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = [r for r in old if r and r[0] >= cutoff]
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(old + out)
    print("flow:", len(out), "satir eklendi,", len(old) + len(out), "toplam")

if __name__ == "__main__":
    main()
