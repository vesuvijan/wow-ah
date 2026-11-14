#!/usr/bin/env python3
"""Forever: tum bolgelerdeki ruleset ve AH (house) listesini bulur -> data/houses.json"""
import json, os, urllib.error
import fetch_ah as F

cid, sec = os.environ["BLIZZARD_CLIENT_ID"], os.environ["BLIZZARD_CLIENT_SECRET"]
out = {"tries": []}
for region in ("eu", "us"):
    token = F.get_token(cid, sec)
    base, ns = f"https://{region}.api.blizzard.com", f"dynamic-forever-{region}"
    def g(path, ns=ns):
        try:
            d = F.get_json(f"{base}{path}?namespace={ns}", token, tries=1)
            out["tries"].append({"region": region, "path": path, "ok": True, "body": json.dumps(d)[:3000]})
            return d
        except Exception as e:  # noqa: BLE001
            out["tries"].append({"region": region, "path": path, "ok": False, "err": str(e)[:120]})
            return None
    for p in ("/data/wow/ruleset/index", "/data/wow/rulesets/index", "/data/wow/connected-realm/index", "/data/wow/realm/index",
              "/data/wow/ruleset/15", "/data/wow/ruleset/15/auctions/index", "/data/wow/auctions/index"):
        g(p)
    found = []
    for rs in range(1, 41):
        d = g(f"/data/wow/ruleset/{rs}/auctions/index")
        if d:
            found.append({"ruleset": rs, "index": d})
    out[region] = found
json.dump(out, open("data/houses.json", "w"), indent=1)
print({r: [(f["ruleset"], str(f["index"])[:200]) for f in out.get(r, [])] for r in ("eu", "us")})
