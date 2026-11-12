#!/usr/bin/env python3
"""Wowhead sayfalarini (ABD'deki GitHub runner'dan) headless tarayicida acip metnini kaydeder.
Ortam: URLS (bosluk/satir ile ayrilmis). Sadece ALLOWED hostlar; XHR/JSON yanitlari data/net_N.json. Cikti: data/page_N.txt, data/index.json"""
import json
import os
import re
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ALLOWED = ("wowhead.com", "wow.gg", "timesaver.gg", "ahledger.com", "wowbackend-production.up.railway.app")
RAW = ("/api/", ".json", ".csv")
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
        if any(k in u for k in RAW):   # API/veri: wow.gg sayfasindan fetch (origin kontrolu icin)
            try:
                if "railway.app" in u:
                    if not getattr(ctx, "_wg", None):
                        ctx._wg = ctx.new_page()
                        ctx._wg.goto("https://wow.gg/auction-house/forever", wait_until="domcontentloaded", timeout=60000)
                        ctx._wg.wait_for_timeout(4000)
                    res = ctx._wg.evaluate("async (u) => { const r = await fetch(u); return [r.status, await r.text()]; }", u)
                    class _R: pass
                    r = _R(); r.status = res[0]; body = res[1]
                else:
                    r = ctx.request.get(u, timeout=60000)
                    body = r.text()
                open(f"data/page_{i}.txt", "w", encoding="utf-8").write(body)
                index.append({"url": u, "status": r.status, "raw": True, "chars": len(body)})
            except Exception as e:  # noqa: BLE001
                index.append({"url": u, "error": str(e)[:200]})
            continue
        pg = ctx.new_page()
        net = []
        def on_resp(resp, net=net):
            try:
                ct = resp.headers.get("content-type", "")
                if resp.request.resource_type in ("xhr", "fetch") or "json" in ct or "csv" in ct:
                    body = resp.text()
                    full = "railway.app" in resp.url
                    net.append({"url": resp.url, "status": resp.status, "ct": ct, "len": len(body), "head": body if full else body[:3000],
                                "req_headers": resp.request.all_headers() if full else None})
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
