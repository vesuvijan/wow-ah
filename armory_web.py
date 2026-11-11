#!/usr/bin/env python3
"""armorywowforever.com karakter sayfasini headless tarayicida acar; sayfanin yaptigi JSON isteklerini ve render edilmis metni kaydeder.
Ortam: URL. Cikti: data/web_*.json / web_page.txt / web_page.html / web_requests.json"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("URL", "https://armorywowforever.com/c/forever/eu/pvp_rp/Docker-Tuckalot")
os.makedirs("data", exist_ok=True)
reqs, bodies = [], {}


def on_response(r):
    try:
        u = r.url
        ct = r.headers.get("content-type", "")
        reqs.append({"url": u, "status": r.status, "type": ct})
        if "json" in ct or "/api" in u:
            bodies[u] = r.text()[:400000]
    except Exception as e:  # noqa: BLE001
        reqs.append({"url": r.url, "err": str(e)[:80]})


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 2000})
    pg.on("response", on_response)
    pg.goto(URL, wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(8000)
    open("data/web_page.txt", "w", encoding="utf-8").write(pg.inner_text("body"))
    open("data/web_page.html", "w", encoding="utf-8").write(pg.content())
    pg.screenshot(path="data/web_page.png", full_page=True)
    b.close()
json.dump(reqs, open("data/web_requests.json", "w"), indent=1)
for i, (u, t) in enumerate(bodies.items()):
    open(f"data/web_json_{i}.json", "w", encoding="utf-8").write(json.dumps({"url": u, "body": t}))
print(len(reqs), "istek,", len(bodies), "json")
for r in reqs:
    print(r.get("status"), r["url"][:150])
