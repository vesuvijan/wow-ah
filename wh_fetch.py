#!/usr/bin/env python3
"""Wowhead sayfalarini (ABD'deki GitHub runner'dan) headless tarayicida acip metnini kaydeder.
Ortam: URLS (bosluk/satir ile ayrilmis). Sadece *.wowhead.com. Cikti: data/page_N.txt, data/index.json"""
import json
import os
import re
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

urls = [u for u in re.split(r"\s+", os.environ.get("URLS", "").strip()) if u]
os.makedirs("data", exist_ok=True)
index = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36", viewport={"width": 1400, "height": 2000})
    for i, u in enumerate(urls[:12], 1):
        host = (urlparse(u).hostname or "").lower()
        if not (host == "wowhead.com" or host.endswith(".wowhead.com")) or urlparse(u).scheme != "https":
            index.append({"url": u, "error": "sadece https wowhead.com"}); continue
        pg = ctx.new_page()
        try:
            r = pg.goto(u, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
            txt = pg.inner_text("body")
            open(f"data/page_{i}.txt", "w", encoding="utf-8").write(txt[:300000])
            index.append({"url": u, "status": r.status if r else None, "title": pg.title(), "chars": len(txt)})
        except Exception as e:  # noqa: BLE001
            index.append({"url": u, "error": str(e)[:200]})
        pg.close()
    b.close()
json.dump(index, open("data/index.json", "w"), indent=1, ensure_ascii=False)
for x in index:
    print(x)
