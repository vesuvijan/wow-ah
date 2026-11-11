#!/usr/bin/env python3
"""Saatlik AH snapshot: WoW Forever AH verisini Blizzard API'den cekip kucuk bir JSON dosyasina yazar.
GitHub Actions icinde calisir (README yok, ayarlar ortam degiskenlerinden):
  BLIZZARD_CLIENT_ID, BLIZZARD_CLIENT_SECRET   (GitHub Secrets'tan gelir)
  REGION (eu), RULESET (15), HOUSES (123 ya da 119,123)
Cikti: data/house_<id>.json  ->  {"fetched_at":..., "items": {"<item_id>": {"n": toplam_adet, "l": [[birim_fiyat_bakir, adet], ...en ucuz 30 fiyat seviyesi]}}}
"""
import base64
import datetime
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

KEEP = 30  # item basina en ucuz KEEP fiyat seviyesi


def get_token(cid, secret):
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    req = urllib.request.Request("https://oauth.battle.net/token", data=b"grant_type=client_credentials",
                                 headers={"Authorization": f"Basic {basic}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["access_token"]


def get_json(url, token, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
            return json.loads(data)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(3 * (i + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(3 * (i + 1))
    raise last


def snapshot_house(base, ns, ruleset, house, token):
    levels = {}  # item_id -> {fiyat: adet}
    for suffix in ("", "/commodities"):
        url = f"{base}/data/wow/ruleset/{ruleset}/auctions/{house}{suffix}?namespace={ns}"
        try:
            d = get_json(url, token)
        except urllib.error.HTTPError as e:
            print(f"uyari: house {house}{suffix} -> HTTP {e.code}", file=sys.stderr)
            continue
        for a in d.get("auctions", []):
            q = a.get("quantity", 1) or 1
            if "unit_price" in a:
                p = a["unit_price"]
            elif a.get("buyout"):
                p = a["buyout"] / q
            else:
                continue
            p = round(p, 2)
            lv = levels.setdefault(a["item"]["id"], {})
            lv[p] = lv.get(p, 0) + q
    items = {}
    for iid, lv in levels.items():
        L = sorted(lv.items())
        items[str(iid)] = {"n": sum(q for _, q in L), "l": [[p, q] for p, q in L[:KEEP]]}
    return items


def main():
    cid, sec = os.environ.get("BLIZZARD_CLIENT_ID"), os.environ.get("BLIZZARD_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET tanimli degil")
    region = os.environ.get("REGION", "eu")
    ruleset = os.environ.get("RULESET", "15")
    houses = [int(x) for x in os.environ.get("HOUSES", "123").split(",") if x.strip()]
    token = get_token(cid, sec)
    base, ns = f"https://{region}.api.blizzard.com", f"dynamic-forever-{region}"
    os.makedirs("data", exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for h in houses:
        items = snapshot_house(base, ns, ruleset, h, token)
        if not items:
            print(f"house {h}: veri yok, dosya yazilmadi", file=sys.stderr)
            continue
        out = {"fetched_at": now, "region": region, "ruleset": int(ruleset), "house": h, "items": items}
        with open(f"data/house_{h}.json", "w", encoding="utf-8") as f:
            json.dump(out, f, separators=(",", ":"))
        print(f"house {h}: {len(items)} item yazildi ({now})")


if __name__ == "__main__":
    main()
