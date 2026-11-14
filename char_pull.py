#!/usr/bin/env python3
"""armorywowforever.com'dan karakter verisini (ekipman, statlar, talentler) ceker -> data/char.json
Ortam: URL (karakter sayfasi). Blizzard profil verisi oyundan cikis yapinca guncellenir; site onbellek tutabilir."""
import json
import os

from playwright.sync_api import sync_playwright

URL = os.environ.get("URL", "https://armorywowforever.com/c/forever/eu/pvp_rp/Docker-Tuckalot")
os.makedirs("data", exist_ok=True)
got = {}


def on_response(r):
    if "/api/character/" in r.url:
        try:
            got["c"] = r.json()
        except Exception:  # noqa: BLE001
            pass


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.on("response", on_response)
    pg.goto(URL, wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(5000)
    if got.get("c", {}).get("refreshing"):   # site arkada yeniliyor: biraz bekleyip tekrar yukle
        pg.wait_for_timeout(25000)
        got.clear()
        pg.reload(wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(5000)
    b.close()
c = got.get("c")
if not c:
    raise SystemExit("karakter verisi alinamadi")
keep = {k: c.get(k) for k in ("name", "level", "race", "className", "guild", "lastLogin", "fetchedAt", "fromCache", "averageIlvl", "stats")}
keep["items"] = [{k: i.get(k) for k in ("slot", "id", "name", "quality", "ilvl", "icon", "enchant")} for i in c.get("items", [])]
keep["talents"] = [{"name": t["name"], "points": t["points"], "talents": [[x["name"], x["rank"]] for x in t.get("talents", [])]}
                   for g in c.get("talents", []) if g.get("active") for t in g.get("trees", [])]
json.dump(keep, open("data/char.json", "w"), ensure_ascii=False, indent=1)
print(keep["name"], keep["level"], len(keep["items"]), "item; lastLogin", keep["lastLogin"], "fromCache", keep["fromCache"])
