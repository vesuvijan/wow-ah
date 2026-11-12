#!/usr/bin/env python3
"""Wowhead sayfalarini (ABD'deki GitHub runner'dan) headless tarayicida acip metnini kaydeder.
Ortam: URLS (bosluk/satir ile ayrilmis). Sadece ALLOWED hostlar; XHR/JSON yanitlari data/net_N.json. Cikti: data/page_N.txt, data/index.json"""
import json
import os
import re
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ALLOWED = ("wowhead.com", "wow.gg", "timesaver.gg")
urls = [u for u in re.split(r"\s+", os.environ.get("URLS", "").strip()) if u]
os.makedirs("data", exist_ok=True)
index = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36", viewport={"width": 1400, "height": 2000})
    for i, u in enumerate(urls[:12], 1):
        host = (urlparse(u).hostname or "").lower()
        if not any(host == d or host.endswith("." + d) for d in ALLOWED) or urlparse(u).scheme != "https":
            index.append({"url": u, "error": "host izinli degil"}); continue
        pg = ctx.new_page()
        net = []
        def on_resp(resp, net=net):
            try:
                ct = resp.headers.get("content-type", "")
                if resp.request.resource_type in ("xhr", "fetch") or "json" in ct or "csv" in ct:
                    body = resp.text()
                    net.append({"url": resp.url, "status": resp.status, "ct": ct, "len": len(body), "head": body[:3000]})
            except Exception:  # noqa: BLE001
                pass
        pg.on("response", on_resp)
        try:
            r = pg.goto(u, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
            txt = pg.inner_text("body")
            open(f"data/page_{i}.txt", "w", encoding="utf-8").write(txt[:300000])
            json.dump(net, open(f"data/net_{i}.json", "w"), indent=1, ensure_ascii=False)
            index.append({"url": u, "status": r.status if r else None, "title": pg.title(), "chars": len(txt)})
        except Exception as e:  # noqa: BLE001
            index.append({"url": u, "error": str(e)[:200]})
        pg.close()
    b.close()
json.dump(index, open("data/index.json", "w"), indent=1, ensure_ascii=False)
for x in index:
    print(x)
