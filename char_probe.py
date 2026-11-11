#!/usr/bin/env python3
"""Karakter (Armory) verisini Blizzard Profile API'den ceker. Ortam: BLIZZARD_CLIENT_ID/SECRET, REGION, REALM (slug veya ad), CHAR.
Birden fazla namespace dener, calisan her biri icin ekipman/statistik/uzmanlik/pvp dosyalarini yazar. Cikti: data/char_*.json, data/char_report.json"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse

import fetch_ah as F

REGION = os.environ.get("REGION", "eu")
REALM = os.environ.get("REALM", "").strip()
CHAR = os.environ.get("CHAR", "").strip().lower()
NS = [f"profile-forever-{REGION}", f"profile-1.60.1_70399-forever-{REGION}", f"profile-classic1x-{REGION}", f"profile-classic-{REGION}"]
report = []


def slug(s):
    s = s.lower().replace("'", "").replace(" ", "-")
    return re.sub(r"[^a-z0-9\-_]", "", s)


def call(path, ns, token):
    url = f"https://{REGION}.api.blizzard.com{path}{'&' if '?' in path else '?'}namespace={ns}&locale=en_US"
    try:
        return F.get_json(url, token, tries=2)
    except urllib.error.HTTPError as e:
        report.append({"ns": ns, "path": path, "status": e.code})
    except Exception as e:  # noqa: BLE001
        report.append({"ns": ns, "path": path, "status": "ERR " + str(e)[:80]})
    return None


def main():
    cid, sec = os.environ.get("BLIZZARD_CLIENT_ID"), os.environ.get("BLIZZARD_CLIENT_SECRET")
    if not cid or not sec or not REALM or not CHAR:
        sys.exit("BLIZZARD_CLIENT_ID/SECRET, REALM, CHAR gerekli")
    token = F.get_token(cid, sec)
    os.makedirs("data", exist_ok=True)
    # realm listesi (slug bulmak icin)
    for ns in (f"dynamic-forever-{REGION}", f"dynamic-{REGION}", f"dynamic-classic1x-{REGION}"):
        d = call("/data/wow/realm/index", ns, token)
        if d:
            realms = [(r.get("slug"), (r.get("name") if isinstance(r.get("name"), str) else (r.get("name") or {}).get("en_US"))) for r in d.get("realms", [])]
            with open("data/realms.json", "w", encoding="utf-8") as f:
                json.dump({"ns": ns, "realms": realms}, f, indent=0)
            report.append({"ns": ns, "realms_found": len(realms)})
            break
    realms = [slug(REALM), slug(REALM).replace("_", "-"), "pvp_rp", "pvp-rp", "rp-pvp"] if REALM else []
    names = [CHAR, CHAR.replace(" ", "-"), CHAR.replace("-", " "), CHAR.replace(" ", "")]
    ok = False
    for ns in NS:
        for realm in dict.fromkeys(realms):
            for nm_ in dict.fromkeys(names):
                base = f"/profile/wow/character/{realm}/{urllib.parse.quote(nm_)}"
                prof = call(base, ns, token)
                if not prof:
                    continue
                ok = True
                out = {"namespace": ns, "profile": prof}
                for part in ("equipment", "statistics", "specializations", "appearance", "pvp-summary", "professions", "reputations"):
                    d = call(f"{base}/{part}", ns, token)
                    if d is not None:
                        out[part] = d
                with open(f"data/char_{slug(nm_)}_{ns}.json", "w", encoding="utf-8") as f:
                    json.dump(out, f, indent=1)
                report.append({"ns": ns, "realm": realm, "name": nm_, "character_ok": True, "parts": [k for k in out if k not in ("namespace", "profile")]})
                break
            if ok:
                break
        if ok:
            break
    with open("data/char_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(report, indent=1)[:3000])
    if not ok:
        print("Karakter bulunamadi: realm slug ve karakter adini dogrula (data/realms.json'a bak).")


if __name__ == "__main__":
    main()
