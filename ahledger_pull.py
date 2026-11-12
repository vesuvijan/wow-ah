#!/usr/bin/env python3
"""wow.gg Forever AH (kaynak: AHledger) verisini kendi pazarimiz icin indirir: RP PvP Alliance EU.
Sitenin kendi sayfasini acar, sayfanin kendi istegindeki anahtari kullanir, yavas (1.5 sn arayla) sayfalar.
Cikti: data/ahl_<market>.json  {itemId: {name, median7d, median30d, low30d, high30d, scans, hist:[[ts,median,min,qty],..]}}
Ortam: MARKET (vars. forever.rppvp.alliance.eu), PROBE (item detay endpoint denemeleri icin itemId)"""
import json, os, time
from playwright.sync_api import sync_playwright

MARKET = os.environ.get("MARKET", "forever.rppvp.alliance.eu")
API = "https://wowbackend-production.up.railway.app/api/forever/ah"
os.makedirs("data", exist_ok=True)
hdr = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36")
    pg = ctx.new_page()
    def grab(req):
        if "railway.app" in req.url and not hdr:
            h = req.headers
            if h.get("x-api-key"):
                hdr.update({"x-api-key": h["x-api-key"], "accept": "application/json"})
    pg.on("request", grab)
    pg.goto("https://wow.gg/auction-house/forever", wait_until="domcontentloaded", timeout=60000)
    for _ in range(30):
        if hdr: break
        pg.wait_for_timeout(1000)
    js = "async ([u,h]) => { const r = await fetch(u, {headers: h}); return [r.status, await r.text()]; }"
    def get(u):
        return pg.evaluate(js, [u, hdr])
    out, page, pages = {}, 1, 1
    per = 100
    while page <= pages:
        st, body = get(f"{API}?market={MARKET}&sort=name&dir=asc&page={page}&per={per}&locale=en")
        if st != 200:
            print("hata", page, st, body[:200]); break
        j = json.loads(body)
        pages = j.get("pages", 1); per = j.get("per", per)
        for r in j["rows"]:
            out[str(r["itemId"])] = {k: r.get(k) for k in ("name", "quality", "itemClass", "itemSubclass", "minBuyout", "median", "quantity",
                                                        "median7d", "median30d", "low30d", "high30d", "scans", "vendorSell")}
            out[str(r["itemId"])]["hist"] = [[h["capturedAt"], h.get("median"), h.get("minBuyout"), h.get("quantity")] for h in r.get("historyPoints", [])]
        print("sayfa", page, "/", pages, "per", per, "toplam", len(out))
        page += 1
        time.sleep(1.5)
    # onceki arsiv (ahledger dalindan geri yuklendi) + tam gecmis: 30 noktadan fazlasi olanlar icin detay
    old = {}
    try:
        old = json.load(open(f"data/prev_{MARKET}.json"))
    except Exception:  # noqa: BLE001
        pass
    for iid, v in out.items():
        pts = {h[0]: h for h in old.get(iid, {}).get("hist", [])}
        pts.update({h[0]: h for h in v["hist"]})
        v["hist"] = [pts[k] for k in sorted(pts)]
    if os.environ.get("DETAIL"):
        need = [i for i, v in out.items() if (v.get("scans") or 0) > len(v["hist"])]
        print("detay gerekli", len(need))
        t0 = time.time()
        for n, iid in enumerate(need, 1):
            if time.time() - t0 > 50 * 60:
                print("sure doldu, kalan", len(need) - n + 1); break
            st, body = get(f"{API}/item/{iid}?market={MARKET}&locale=en")
            if st == 200:
                j = json.loads(body)
                for m in j.get("markets", []):
                    if m.get("market") == MARKET:
                        pts = {h[0]: h for h in out[iid]["hist"]}
                        pts.update({h["capturedAt"]: [h["capturedAt"], h.get("median"), h.get("minBuyout"), h.get("quantity")] for h in m.get("historyPoints", [])})
                        out[iid]["hist"] = [pts[k] for k in sorted(pts)]
                        out[iid]["firstSeen"] = j.get("firstSeen")
            elif st == 429:
                time.sleep(30)
            if n % 100 == 0:
                print("detay", n, "/", len(need))
            time.sleep(1.0)
    probe = os.environ.get("PROBE", "")
    tests = {}
    if probe:
        for u in (f"{API}/item/{probe}?market={MARKET}&locale=en", f"{API}/items/{probe}?market={MARKET}&locale=en",
                  f"{API}/{probe}?market={MARKET}&locale=en", f"{API}/history?market={MARKET}&itemId={probe}&locale=en",
                  f"{API}/item/{probe}/history?market={MARKET}&locale=en"):
            st, body = get(u); tests[u] = [st, body[:4000]]; time.sleep(1.5)
    b.close()
json.dump(out, open(f"data/ahl_{MARKET}.json", "w"), ensure_ascii=False, separators=(",", ":"))
json.dump({"market": MARKET, "items": len(out), "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "probe": tests,
           "source": "Prices: AHledger (https://ahledger.com) via wow.gg"}, open("data/ahl_meta.json", "w"), indent=1, ensure_ascii=False)
print("bitti", len(out))
