#!/usr/bin/env python3
"""python flow_report.py <item_id|isim parcasi> [gun=7]  -> satis akisi ozeti (data/flow.csv + data/history.csv)"""
import csv, json, sys, datetime, statistics
def money(c):
    c = int(c); g, r = divmod(c, 10000); s, k = divmod(r, 100)
    return (f"{g}g " if g else "") + (f"{s}s " if s or g else "") + (f"{k}c" if k or not (g or s) else "") if g or s or k else "0c"
q = sys.argv[1]; days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
names = {}
try: names = {int(k): v["n"] for k, v in json.load(open("data/names.json")).items()}
except Exception: pass
iid = int(q) if q.isdigit() else next((k for k, v in names.items() if q.lower() in v.lower()), None)
if iid is None: sys.exit("item bulunamadi")
cut = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
rows = [r for r in csv.reader(open("data/flow.csv")) if int(r[1]) == iid and r[0] >= cut]
hist = [r for r in csv.reader(open("data/history.csv")) if int(r[1]) == iid and r[0] >= cut]
print(f"== {names.get(iid, iid)} ({iid}) son {days} gun, {len(rows)} saatlik degisim kaydi ==")
if hist:
    mins = [float(r[2]) for r in hist]
    print(f"Fiyat (min listing): simdi {money(mins[-1])} | en dusuk {money(min(mins))} | en yuksek {money(max(mins))} | medyan {money(statistics.median(mins))}")
    print(f"Listedeki adet: simdi {hist[-1][4]} | en az {min(int(r[4]) for r in hist)} | en cok {max(int(r[4]) for r in hist)}")
if rows:
    sold = sum(int(r[2]) for r in rows); other = sum(int(r[5]) for r in rows); add = sum(int(r[6]) for r in rows)
    sp = [(int(r[3]), int(r[4]), int(r[2])) for r in rows if int(r[2])]
    print(f"Tahmini satilan: {sold} adet (gunluk ~{sold/days:.1f})")
    if sp: print(f"  satis fiyat araligi: {money(min(a for a,_,_ in sp))} - {money(max(b for _,b,_ in sp))}, agirlikli ort {money(sum((a+b)/2*n for a,b,n in sp)/sold)}")
    print(f"Yeni listelenen: {add} adet | iptal/sure dolan/pahali kaybolan: {other} adet")
    print(f"Satilmayan oran (listelenen - satilan - iptal): {max(add - sold - other, 0)} adet net birikti")
else:
    print("Akis kaydi yok (flow.csv yeni basladi, saatlik veri birikiyor).")
