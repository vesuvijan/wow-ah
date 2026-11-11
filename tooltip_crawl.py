#!/usr/bin/env python3
"""Wowhead Forever tooltip API'sinden (nether.wowhead.com/forever/tooltip/item/<id>) ham item tooltip'lerini ceker.
Ortam: IDS_FILE (JSON liste), TAG, RATE (vars. 6/sn). Cikti: data/tooltips_<TAG>.json {id: {name,quality,icon,tooltip,spells}|null}"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

IDS = json.load(open(os.environ["IDS_FILE"]))
TAG = os.environ.get("TAG", "x")
RATE = float(os.environ.get("RATE", "6"))
DEADLINE = time.time() + float(os.environ.get("MAX_MIN", "40")) * 60
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
lock, last = threading.Lock(), [0.0]


def pace():
    with lock:
        now = time.time()
        wait = last[0] + 1.0 / RATE - now
        last[0] = max(now, last[0] + 1.0 / RATE)
    if wait > 0:
        time.sleep(wait)


def fetch(i):
    if time.time() > DEADLINE:
        return i, "skip"
    for t in range(3):
        pace()
        try:
            req = urllib.request.Request(f"https://nether.wowhead.com/forever/tooltip/item/{i}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return i, json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return i, None
            time.sleep(2 + t * 3)
        except Exception:  # noqa: BLE001
            time.sleep(2 + t * 3)
    return i, "err"


out, st = {}, {"ok": 0, "none": 0, "err": 0, "skip": 0}
with ThreadPoolExecutor(max_workers=6) as ex:
    for k, (i, r) in enumerate(ex.map(fetch, IDS)):
        if isinstance(r, dict):
            out[str(i)] = r
            st["ok"] += 1
        elif r is None:
            st["none"] += 1
        else:
            st[r] += 1
        if k % 500 == 0:
            print(k, st, flush=True)
os.makedirs("data", exist_ok=True)
json.dump(out, open(f"data/tooltips_{TAG}.json", "w"), separators=(",", ":"))
print("bitti", st)
