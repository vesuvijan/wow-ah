#!/usr/bin/env python3
"""Dungeon/raid loot kaynaklarini Blizzard journal API'sinden ceker: instance -> encounter -> items. Cikti: data/sources.json (item_id -> [instance, boss]) ve data/sources_report.json"""
import json, os, sys, urllib.error
import fetch_ah as F
REGION = os.environ.get("REGION", "eu")
rep = {}
def g(path, ns, token):
    url = f"https://{REGION}.api.blizzard.com{path}{'&' if '?' in path else '?'}namespace={ns}&locale=en_US"
    try:
        return F.get_json(url, token, tries=2)
    except urllib.error.HTTPError as e:
        rep[path + "@" + ns] = e.code
    except Exception as e:  # noqa: BLE001
        rep[path + "@" + ns] = str(e)[:60]
def nm(x): return x.get("en_US") if isinstance(x, dict) else x
def main():
    token = F.get_token(os.environ["BLIZZARD_CLIENT_ID"], os.environ["BLIZZARD_CLIENT_SECRET"])
    os.makedirs("data", exist_ok=True)
    src, used = {}, None
    for ns in (f"static-forever-{REGION}", f"static-classic1x-{REGION}", f"static-classic-{REGION}"):
        idx = g("/data/wow/journal-instance/index", ns, token)
        if idx and idx.get("instances"):
            used = ns; break
    rep["namespace"] = used
    if used:
        for ins in idx["instances"]:
            d = g(f"/data/wow/journal-instance/{ins['id']}", used, token)
            if not d: continue
            for enc in d.get("encounters", []):
                e = g(f"/data/wow/journal-encounter/{enc['id']}", used, token)
                if not e: continue
                for it in e.get("items", []):
                    iid = (it.get("item") or {}).get("id")
                    if iid: src.setdefault(str(iid), []).append([nm(ins.get("name")), nm(enc.get("name"))])
        rep["instances"] = len(idx["instances"])
    json.dump(src, open("data/sources.json", "w"), separators=(",", ":"))
    json.dump(rep, open("data/sources_report.json", "w"), indent=1)
    print(json.dumps(rep, indent=1)[:2000], "items:", len(src))
if __name__ == "__main__": main()
