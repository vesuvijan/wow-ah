#!/usr/bin/env python3
"""Item veritabani tarayici (resumable parcalar). Ortam: BLIZZARD_CLIENT_ID/SECRET, REGION, NS, START, END, RATE (istek/sn, vars. 9).
Her item icin ad, sinif, slot, kalite, seviye, bind, vendor fiyatlari, statlar, silah dps/hiz, zirh, efekt metni saklar. Cikti: data/items_<START>_<END>.json"""
import json
import os
import sys
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import fetch_ah as F

REGION = os.environ.get("REGION", "eu")
NS = os.environ.get("NS", f"static-forever-{REGION}")
START, END = int(os.environ.get("START", "1")), int(os.environ.get("END", "25000"))
IDS_FILE = os.environ.get("IDS_FILE", "")
TAG = os.environ.get("TAG", "")
RATE = float(os.environ.get("RATE", "9"))
DEADLINE = time.time() + float(os.environ.get("MAX_MIN", "330")) * 60
lock = threading.Lock()
last = [0.0]


def nm(x):
    if isinstance(x, dict):
        return x.get("en_US") or next(iter(x.values()), "")
    return x or ""


def pace():
    with lock:
        now = time.time()
        wait = last[0] + 1.0 / RATE - now
        last[0] = max(now, last[0] + 1.0 / RATE)
    if wait > 0:
        time.sleep(wait)


def parse(d):
    pv = d.get("preview_item") or {}
    stats = []
    for s in pv.get("stats", []) or []:
        t = (s.get("type") or {}).get("type") or nm((s.get("type") or {}).get("name"))
        stats.append([t, s.get("value")])
    w = pv.get("weapon") or {}
    eff = [nm((sp.get("spell") or {}).get("name")) + ": " + nm(sp.get("description")) for sp in pv.get("spells", []) or []]
    return {
        "n": nm(d.get("name")), "c": nm((d.get("item_class") or {}).get("name")), "s": nm((d.get("item_subclass") or {}).get("name")),
        "inv": (d.get("inventory_type") or {}).get("type"), "q": (d.get("quality") or {}).get("type"),
        "il": d.get("level"), "rl": d.get("required_level"), "b": (pv.get("binding") or {}).get("type"),
        "sp": d.get("sell_price"), "pp": d.get("purchase_price"), "st": stats,
        "dps": (w.get("dps") or {}).get("value"), "spd": (w.get("attack_speed") or {}).get("value"),
        "dmg": [(w.get("damage") or {}).get("min_value"), (w.get("damage") or {}).get("max_value")] if w else None,
        "ar": (pv.get("armor") or {}).get("value"), "eff": eff or None,
        "req": [r for r in [(pv.get("requirements") or {}).get("level", {}).get("display_string")] if r] or None,
    }


def fetch(args):
    i, token = args
    if time.time() > DEADLINE:
        return i, "skip"
    pace()
    url = f"https://{REGION}.api.blizzard.com/data/wow/item/{i}?namespace={NS}&locale=en_US"
    try:
        return i, parse(F.get_json(url, token, tries=3))
    except urllib.error.HTTPError as e:
        return i, ("404" if e.code == 404 else f"http{e.code}")
    except Exception as e:  # noqa: BLE001
        return i, "err"


def main():
    cid, sec = os.environ.get("BLIZZARD_CLIENT_ID"), os.environ.get("BLIZZARD_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("BLIZZARD_CLIENT_ID/SECRET gerekli")
    token = F.get_token(cid, sec)
    os.makedirs("data", exist_ok=True)
    items, stat = {}, {"ok": 0, "404": 0, "other": 0, "skip": 0}
    with ThreadPoolExecutor(max_workers=8) as ex:
        id_list = json.load(open(IDS_FILE)) if IDS_FILE else range(START, END + 1)
        for k, (i, r) in enumerate(ex.map(fetch, ((i, token) for i in id_list))):
            if isinstance(r, dict):
                items[str(i)] = r
                stat["ok"] += 1
            elif r == "404":
                stat["404"] += 1
            elif r == "skip":
                stat["skip"] += 1
            else:
                stat["other"] += 1
            if k % 2000 == 0:
                print(k, stat, flush=True)
            if k and k % 3000 == 0:  # token yenile (24 saat gecerli ama guvenli olsun)
                pass
    out = {"ns": NS, "start": START, "end": END, "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stat": stat, "items": items}
    with open(f"data/items_{TAG or str(START) + '_' + str(END)}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print("bitti", stat)


if __name__ == "__main__":
    main()
