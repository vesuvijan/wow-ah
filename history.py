#!/usr/bin/env python3
"""Saatlik snapshot'tan izlenen item'larin fiyatini data/history.csv'ye ekler ve data/report.txt uretir.
Girdi : data/house_<HOUSE>.json (fetch_ah.py ciktisi)
Cikti : data/history.csv  (ts,item_id,min_bakir,ort200_bakir,adet)   -> en fazla 60 gun tutulur
        data/report.txt   (okunakli ozet: simdiki fiyat, 7 gunluk medyan/min, AL/BEKLE, rota maliyetleri)
"""
import csv
import datetime
import json
import os
import hashlib
import statistics
import sys

HOUSE = os.environ.get("HOUSES", "123").split(",")[0].strip()
KEEP_DAYS = 60
MIN_SAMPLES = 12          # bu kadar olcum olmadan AL/BEKLE denmez
BUY_PERCENTILE = 0.20     # gecmisin en ucuz %20'lik dilimindeyse AL

# id: (isim, grup)
WATCH = {
    # Tailoring rotasi
    2589: ("Linen Cloth", "T"), 2592: ("Wool Cloth", "T"), 4306: ("Silk Cloth", "T"), 4338: ("Mageweave Cloth", "T"),
    2996: ("Bolt of Linen", "T"), 2997: ("Bolt of Woolen", "T"), 4305: ("Bolt of Silk", "T"), 4339: ("Bolt of Mageweave", "T"),
    2320: ("Coarse Thread", "T"), 2321: ("Fine Thread", "T"), 4291: ("Silken Thread", "T"), 8343: ("Heavy Silken Thread", "T"),
    2604: ("Red Dye", "T"), 3383: ("Elixir of Wisdom", "T"), 4318: ("Gloves of Meditation (satis)", "T"),
    249430: ("Magenta Dye", "T"), 249409: ("Cerulean Dye", "T"), 254035: ("Mageweave Reagent Bag (satis)", "T"),
    # Engineering rotasi
    2835: ("Rough Stone", "E"), 2836: ("Coarse Stone", "E"), 2838: ("Heavy Stone", "E"), 7912: ("Solid Stone", "E"),
    2840: ("Copper Bar", "E"), 2841: ("Bronze Bar", "E"), 2842: ("Silver Bar", "E"), 3859: ("Steel Bar", "E"),
    3860: ("Mithril Bar", "E"), 2319: ("Medium Leather", "E"), 2880: ("Weak Flux", "E"), 1206: ("Moss Agate", "E"),
    2770: ("Copper Ore", "E"), 3858: ("Mithril Ore", "E"),
    # Favor crate'leri ve bundle malzemeleri
    248686: ("Crate Journeyman Herbs", "F"), 248707: ("Crate Journeyman Parts", "F"), 248688: ("Crate Journeyman Textiles", "F"),
    248705: ("Crate Journeyman Fabrics", "F"), 248682: ("Crate Apprentice Herbs", "F"),
    4382: ("Bronze Framework", "F"), 2453: ("Bruiseweed", "F"), 765: ("Silverleaf", "F"), 3820: ("Stranglekelp", "F"),
}

# Rota toplam malzemeleri (id: adet). Kaynak: wow-professions.com Forever rotalari; tahmini.
ROUTES = {
    "Tailoring 1->190 (kumas)": {2589: 60, 2592: 459, 4306: 640, 4338: 115},
    "Engineering 1->225 (hammadde)": {2835: 60, 2840: 66, 2589: 50, 2836: 60, 2842: 5, 2841: 110, 2880: 25,
                                      1206: 10, 2838: 30, 2592: 60, 2319: 15, 7912: 120, 3859: 4, 3860: 100, 4338: 20},
}


def money(c):
    if c is None:
        return "-"
    c = int(round(c))
    g, rem = divmod(c, 10000)
    s, cu = divmod(rem, 100)
    return (f"{g}g " if g else "") + (f"{s}s " if (s or g) else "") + f"{cu}c"


def avg_cheapest(levels, want=200):
    got, tot = 0, 0.0
    for p, q in levels:
        take = min(q, want - got)
        tot += p * take
        got += take
        if got >= want:
            break
    return (tot / got) if got else None


def main():
    snap_path = f"data/house_{HOUSE}.json"
    hist_path = "data/history.csv"
    snap = json.load(open(snap_path, encoding="utf-8"))
    ts = snap["fetched_at"]
    # veri degismediyse (API saatlik yenileniyorsa) tekrar kaydetme/uyarma
    h = hashlib.sha1(json.dumps(snap["items"], sort_keys=True).encode()).hexdigest()
    try:
        if open("data/last_hash.txt").read().strip() == h and os.path.exists(hist_path):
            print("veri degismedi, atlandi")
            return
    except OSError:
        pass
    with open("data/last_hash.txt", "w") as f:
        f.write(h)
    now = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    cutoff = (now - datetime.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = []
    if os.path.exists(hist_path):
        with open(hist_path, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if len(r) == 5 and r[0] >= cutoff and r[0] != ts:
                    rows.append(r)
    for iid in WATCH:
        it = snap["items"].get(str(iid))
        if not it:
            continue
        lv = it["l"]
        rows.append([ts, str(iid), f"{lv[0][0]:.0f}", f"{avg_cheapest(lv):.0f}", str(it["n"])])
    with open(hist_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    # ---- rapor
    series = {}
    for r in rows:
        series.setdefault(int(r[1]), []).append((r[0], float(r[2]), float(r[3]), int(r[4])))
    stamps = sorted({r[0] for r in rows})
    out = [f"Rapor: {ts} | house {HOUSE} | {len(stamps)} olcum, {stamps[0]} -> {stamps[-1]}", ""]
    week = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sig = {}
    for grp, title in (("T", "TAILORING"), ("E", "ENGINEERING"), ("F", "FAVOR")):
        out.append(f"== {title} ==")
        out.append(f"{'item':<34}{'simdi':>10}{'24s ort':>10}{'7g medyan':>11}{'7g min':>10}{'stok':>7}  sinyal")
        for iid, (name, g) in WATCH.items():
            if g != grp or iid not in series:
                continue
            s = series[iid]
            cur = s[-1][1]
            w7 = [x[1] for x in s if x[0] >= week]
            d1 = [x[1] for x in s if x[0] >= day]
            med, mn = statistics.median(w7), min(w7)
            if len(w7) < MIN_SAMPLES:
                signal = f"veri az ({len(w7)}/{MIN_SAMPLES})"
            else:
                rank = sum(1 for v in w7 if v < cur) / len(w7)
                signal = "AL" if rank <= BUY_PERCENTILE else ("BEKLE" if rank >= 0.6 else "normal")
            sig[iid] = signal
            out.append(f"{name:<34}{money(cur):>10}{money(statistics.mean(d1)):>10}{money(med):>11}{money(mn):>10}{s[-1][3]:>7}  {signal}")
        out.append("")
    out.append("== ROTA MALIYETI (ort. en ucuz 200 birim fiyatiyla) ==")
    for name, mats in ROUTES.items():
        def cost(pick):
            t = 0.0
            for iid, q in mats.items():
                s = series.get(iid)
                if not s:
                    return None
                t += q * pick(s)
            return t
        cur = cost(lambda s: s[-1][2])
        w = cost(lambda s: min(x[2] for x in s if x[0] >= week) if any(x[0] >= week for x in s) else s[-1][2])
        m = cost(lambda s: statistics.median([x[2] for x in s if x[0] >= week] or [s[-1][2]]))
        out.append(f"{name}: simdi {money(cur)} | 7g medyan {money(m)} | 7g en ucuz {money(w)}")
    out.append("")
    out.append("Not: AL = fiyat son 7 gunun en ucuz %20'lik dilimi; en az 12 olcum (12 saat) sonra anlamli.")
    try:
        import alerts
        alerts.run(snap, {k: v for k, v in series.items()}, WATCH)
    except Exception as e:  # noqa: BLE001
        print("alerts hatasi:", e)
    with open("data/report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out[:3]))


if __name__ == "__main__":
    sys.exit(main())
