#!/usr/bin/env python3
"""WoW Forever - Waylaid Crate en ucuz Merchant's Favor hesaplayici (v2, tam otomatik)

Kullanim (PowerShell, sadece Python gerekir, ek paket yok):
  $env:BLIZZARD_CLIENT_ID="..."
  $env:BLIZZARD_CLIENT_SECRET="..."
  py waylaid_calc_v2.py

Sonuc ekrana yazilir VE waylaid_sonuc.txt dosyasina kaydedilir (dosyayi sohbete ekleyebilirsin).

Formul: (bos crate fiyati + material fiyati - teslim odulu gumus) / Favor = Favor basina maliyet
Crate fiyati AH'den otomatik cekilir (crate item ID'leri Wowhead Forever'dan).

Secenekler:
  --houses 110,111   sadece bu house'lari tara (varsayilan: ruleset'teki tum Alliance house'lar)
  --faction Horde    Alliance / Horde / Blackwater / all
  --ruleset 15       1=PvP 2=Normal 3=RP 15=RPPvP
  --check-ids        script'teki item ID'lerinin isimlerini Blizzard'dan dogrulamayi dener
"""
import argparse
import base64
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------- material item ID'leri
ITEMS = {
    # Ore / Bar
    "Copper Ore": 2770, "Tin Ore": 2771, "Iron Ore": 2772, "Silver Ore": 2775,
    "Gold Ore": 2776, "Mithril Ore": 3858,
    "Copper Bar": 2840, "Bronze Bar": 2841, "Silver Bar": 2842, "Gold Bar": 3577,
    "Iron Bar": 3575, "Tin Bar": 3576, "Steel Bar": 3859, "Mithril Bar": 3860,
    # Herbs
    "Peacebloom": 2447, "Silverleaf": 765, "Earthroot": 2449, "Mageroyal": 785,
    "Briarthorn": 2450, "Stranglekelp": 3820, "Bruiseweed": 2453,
    "Wild Steelbloom": 3355, "Grave Moss": 3369, "Kingsblood": 3356,
    "Liferoot": 3357, "Fadeleaf": 3818, "Goldthorn": 3821, "Khadgar's Whisker": 3358,
    "Wintersbite": 3819, "Firebloom": 4625, "Purple Lotus": 8831, "Arthas' Tears": 8836,
    # Cloth / Leather / Hide
    "Linen Cloth": 2589, "Wool Cloth": 2592, "Silk Cloth": 4306, "Mageweave Cloth": 4338,
    "Light Leather": 2318, "Medium Leather": 2319, "Heavy Leather": 4234,
    "Bolt of Linen Cloth": 2996, "Bolt of Woolen Cloth": 2997, "Bolt of Silk Cloth": 4305,
    "Bolt of Mageweave": 4339,
    "Cured Light Hide": 4231, "Cured Medium Hide": 4233, "Cured Heavy Hide": 4236,
    # Engineering parts
    "Handful of Copper Bolts": 4359, "Copper Tube": 4361, "Copper Modulator": 4363,
    "Bronze Tube": 4371, "Whirring Bronze Gizmo": 4375, "Bronze Framework": 4382,
    # Enchanting
    "Strange Dust": 10940, "Soul Dust": 11083, "Vision Dust": 11137,
    "Greater Magic Essence": 10939, "Greater Astral Essence": 11082, "Greater Mystic Essence": 11135,
    "Small Glimmering Shard": 10978, "Large Glimmering Shard": 11084,
    "Small Glowing Shard": 11138, "Large Glowing Shard": 11139,
    "Small Radiant Shard": 11177, "Large Radiant Shard": 11178,
}
# Bu material ID'leri hafizadan; dogrulanmadi (diger ID'ler Wowhead ile dogrulandi / cok bilinenler)
SUPHELI_ITEMS = {"Bronze Framework", "Large Glimmering Shard", "Small Glowing Shard", "Large Glowing Shard",
                 "Small Radiant Shard", "Large Radiant Shard"}

# ---------------------------------------------------------------- crate tablosu
# isim: (crate_item_id, id_kesin, favor, odul_bakir, odul_kesin, [(material, adet), ...])
# Her crate icin bundle'lardan SADECE BIRINI doldurman yeter (en ucuzu secilir).
# id_kesin=False -> ID komsu ID'lerden tahmin edildi (Wowhead'de dogrudan gorulmedi).
# odul_kesin=False -> Favor/gumus kaynaklarda net degil, kalibi izleyerek tahmin edildi.
# Odul bakir cinsinden: 2.5 gumus = 250. Beyaz crate (ham madde) = 1x, yesil crate (islenmis) = 2x.
CRATES = {
    # ---- Apprentice
    "Apprentice Herbs": (248682, True, 5, 250, True, [("Peacebloom", 20), ("Silverleaf", 20), ("Earthroot", 10), ("Mageroyal", 10), ("Briarthorn", 10)]),
    "Apprentice Ore": (248683, True, 5, 250, True, [("Copper Ore", 20), ("Tin Ore", 20)]),
    "Apprentice Textiles": (248684, True, 5, 250, True, [("Linen Cloth", 40), ("Light Leather", 20)]),
    "Apprentice Curiosities": (248685, False, 5, 250, True, [("Strange Dust", 20), ("Greater Magic Essence", 4), ("Small Glimmering Shard", 6), ("Large Glimmering Shard", 2)]),
    "Apprentice Fabrics": (248702, True, 10, 500, True, [("Cured Light Hide", 2), ("Bolt of Linen Cloth", 20)]),
    "Apprentice Ingots": (248703, True, 10, 500, True, [("Copper Bar", 20), ("Tin Bar", 20), ("Bronze Bar", 10)]),
    "Apprentice Parts": (248704, True, 10, 500, True, [("Handful of Copper Bolts", 16), ("Copper Tube", 16), ("Copper Modulator", 4)]),
    # ---- Journeyman
    "Journeyman Herbs": (248686, True, 10, 500, True, [("Stranglekelp", 10), ("Bruiseweed", 10), ("Wild Steelbloom", 10), ("Grave Moss", 10), ("Kingsblood", 10)]),
    "Journeyman Ore": (248687, True, 10, 500, True, [("Silver Ore", 10), ("Iron Ore", 20)]),
    "Journeyman Textiles": (248688, False, 10, 500, True, [("Wool Cloth", 20), ("Silk Cloth", 40), ("Medium Leather", 20)]),
    "Journeyman Curiosities": (248689, True, 10, 500, True, [("Soul Dust", 20), ("Greater Astral Essence", 4), ("Small Glowing Shard", 6), ("Large Glowing Shard", 2)]),
    "Journeyman Fabrics": (248705, False, 20, 1000, True, [("Bolt of Woolen Cloth", 6), ("Bolt of Silk Cloth", 10), ("Cured Medium Hide", 2)]),
    "Journeyman Ingots": (248706, True, 20, 1000, True, [("Silver Bar", 10), ("Iron Bar", 20)]),
    "Journeyman Parts": (248707, True, 20, 1000, True, [("Bronze Tube", 8), ("Whirring Bronze Gizmo", 7), ("Bronze Framework", 4)]),
    # ---- Expert (level 20+). Expert Parts atlandi (material ID'leri belirsiz).
    "Expert Herbs (Earthly)": (248690, False, 15, 750, False, [("Liferoot", 20), ("Fadeleaf", 10), ("Goldthorn", 10), ("Khadgar's Whisker", 10)]),
    "Expert Herbs (Flowering)": (248691, False, 15, 750, False, [("Wintersbite", 10), ("Firebloom", 10), ("Purple Lotus", 20), ("Arthas' Tears", 10)]),
    "Expert Ore": (248692, False, 15, 750, True, [("Gold Ore", 10), ("Mithril Ore", 20)]),
    "Expert Textiles": (248693, True, 15, 750, False, [("Mageweave Cloth", 40), ("Heavy Leather", 20)]),
    "Expert Curiosities": (248694, False, 15, 750, True, [("Vision Dust", 20), ("Greater Mystic Essence", 4), ("Small Radiant Shard", 6), ("Large Radiant Shard", 2)]),
    "Expert Fabrics": (248708, True, 30, 1500, True, [("Bolt of Mageweave", 8), ("Cured Heavy Hide", 2)]),
    "Expert Ingots": (248709, False, 30, 1500, False, [("Mithril Bar", 20), ("Steel Bar", 15), ("Gold Bar", 10)]),
}
CRATE_NAME_BY_ID = {v[0]: k for k, v in CRATES.items()}
REF_ITEMS = ["Linen Cloth", "Silverleaf", "Peacebloom", "Copper Ore"]  # hangi house senin marketin: oyundaki AH ile kiyasla


# ---------------------------------------------------------------- yardimcilar
def money(c):
    if c is None:
        return "-"
    sign = "-" if c < 0 else ""
    c = int(round(abs(c)))
    g, rem = divmod(c, 10000)
    s, cu = divmod(rem, 100)
    parts = []
    if g:
        parts.append(f"{g}g")
    if s or g:
        parts.append(f"{s}s")
    parts.append(f"{cu}c")
    return sign + " ".join(parts)


def get_token(cid, secret):
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    req = urllib.request.Request(
        "https://oauth.battle.net/token",
        data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {basic}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["access_token"]


def get_json(url, token, tries=3):
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
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 * (i + 1))
                last = e
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def list_houses(base, ns, rs, token):
    d = get_json(f"{base}/data/wow/ruleset/{rs}/auctions/index?namespace={ns}", token)
    for v in d.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "id" in v[0]:
            return [(h["id"], (h.get("name") or {}).get("en_US", "")) for h in v]
    raise RuntimeError("Index cevabinda house listesi bulunamadi: " + json.dumps(d)[:300])


def load_house(base, ns, rs, house, token):
    """item_id -> [(birim_fiyat_bakir, adet)] ; hem normal hem commodity ilanlari."""
    book = {}
    for suffix in ("", "/commodities"):
        url = f"{base}/data/wow/ruleset/{rs}/auctions/{house}{suffix}?namespace={ns}"
        try:
            d = get_json(url, token)
        except urllib.error.HTTPError as e:
            print(f"  uyari: {house}{suffix} -> HTTP {e.code}", file=sys.stderr)
            continue
        for a in d.get("auctions", []):
            q = a.get("quantity", 1) or 1
            if "unit_price" in a:
                p = a["unit_price"]
            elif a.get("buyout"):
                p = a["buyout"] / q
            else:
                continue
            book.setdefault(a["item"]["id"], []).append((p, q))
    return book


def cost_to_buy(book, item_id, qty):
    """Ilanlari ucuzdan pahaliya yiyerek qty adet icin toplam maliyet; yetmezse None."""
    need, total = qty, 0.0
    for p, q in sorted(book.get(item_id, [])):
        take = min(q, need)
        total += p * take
        need -= take
        if need <= 0:
            return total
    return None


def lowest(book, item_id):
    L = book.get(item_id)
    return min(p for p, _ in L) if L else None


def evaluate(book):
    rows, missing = [], []
    for name, (crate_id, id_ok, favor, reward, reward_ok, bundles) in CRATES.items():
        crate_price = lowest(book, crate_id)
        if crate_price is None:
            missing.append(name)
            continue
        best = None
        for mat, qty in bundles:
            mc = cost_to_buy(book, ITEMS[mat], qty)
            if mc is None:
                continue
            if best is None or mc < best[1]:
                best = (f"{qty}x {mat}", mc, mat)
        if best is None:
            missing.append(name + " (material yok)")
            continue
        total = best[1] + crate_price - reward
        notes = []
        if not id_ok:
            notes.append("crate ID tahmini")
        if not reward_ok:
            notes.append("odul tahmini")
        if best[2] in SUPHELI_ITEMS:
            notes.append("material ID suphe")
        rows.append({"crate": name, "bundle": best[0], "mats": best[1], "crate_price": crate_price,
                     "favor": favor, "total": total, "per_favor": total / favor, "notes": notes})
    rows.sort(key=lambda r: r["per_favor"])
    return rows, missing


def crate_scan(book, lo=248540, hi=248720):
    out = []
    for i, L in book.items():
        if lo <= i <= hi:
            out.append((i, min(p for p, _ in L), sum(q for _, q in L)))
    return sorted(out)


def check_ids(region, token, out):
    ns = f"static-1.60.1_70399-forever-{region}"
    ids = {v: k for k, v in ITEMS.items()}
    ids.update({v[0]: "CRATE " + k for k, v in CRATES.items()})
    out("\n--- ID dogrulama (Blizzard item verisi eksik olabilir, 404 = dogrulanamadi, yanlis demek degil) ---")
    for iid in sorted(ids):
        try:
            d = get_json(f"https://{region}.api.blizzard.com/data/wow/item/{iid}?namespace={ns}", token, tries=2)
            nm = (d.get("name") or {}).get("en_US", "?")
            ok = "OK " if ids[iid].replace("CRATE ", "Waylaid Crate: ").lower() in nm.lower() or nm.lower() in ids[iid].lower() else "??"
            out(f"{ok} {iid}: script='{ids[iid]}' blizzard='{nm}'")
        except urllib.error.HTTPError as e:
            out(f"-- {iid}: script='{ids[iid]}' HTTP {e.code} (dogrulanamadi)")
        except Exception as e:  # noqa: BLE001
            out(f"-- {iid}: script='{ids[iid]}' hata {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="eu")
    ap.add_argument("--ruleset", type=int, default=15, help="1=PvP 2=Normal 3=RP 15=RPPvP")
    ap.add_argument("--faction", default="Alliance", help="Alliance / Horde / Blackwater / all")
    ap.add_argument("--houses", help="Elle house ID listesi, orn: 110,111")
    ap.add_argument("--check-ids", action="store_true")
    ap.add_argument("--out", default="waylaid_sonuc.txt")
    a = ap.parse_args()

    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    cid, sec = os.environ.get("BLIZZARD_CLIENT_ID"), os.environ.get("BLIZZARD_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit('BLIZZARD_CLIENT_ID ve BLIZZARD_CLIENT_SECRET ortam degiskenlerini ayarla (README: $env:BLIZZARD_CLIENT_ID="...").')
    token = get_token(cid, sec)
    base, ns = f"https://{a.region}.api.blizzard.com", f"dynamic-forever-{a.region}"

    if a.houses:
        houses = [(int(h), "") for h in a.houses.split(",")]
    else:
        allh = list_houses(base, ns, a.ruleset, token)
        houses = [(i, n) for i, n in allh if a.faction == "all" or a.faction.lower() in n.lower()]
    out(f"Tarih: {time.strftime('%Y-%m-%d %H:%M')} | {a.region.upper()} ruleset {a.ruleset} | house'lar: {[h for h, _ in houses]}")

    for hid, hname in houses:
        book = load_house(base, ns, a.ruleset, hid, token)
        out(f"\n=== House {hid} {hname} | {len(book)} farkli item ===")
        if not book:
            out("  (bos house)")
            continue
        ref = ", ".join(f"{n} {money(lowest(book, ITEMS[n]))}" for n in REF_ITEMS)
        out(f"Kontrol (oyundaki AH'deki en ucuz fiyatlarla karsilastir, tutan house senin marketin): {ref}")
        rows, missing = evaluate(book)
        out(f"{'Favor basina':>13} | {'Crate':<26} {'Favor':>5} | {'Toplam/crate':>12} | en ucuz bundle (material + crate)")
        for r in rows:
            note = f"  [{', '.join(r['notes'])}]" if r["notes"] else ""
            out(f"{money(r['per_favor']):>13} | {r['crate']:<26} {r['favor']:>5} | {money(r['total']):>12} | "
                f"{r['bundle']} ({money(r['mats'])}) + crate {money(r['crate_price'])}{note}")
        if missing:
            out("AH'de crate ya da material bulunamadi: " + "; ".join(missing))
        scan = crate_scan(book)
        if scan:
            out("AH'de bulunan crate-araligi item ID'leri (ID dogrulamasi icin): " + "; ".join(
                f"{i}={CRATE_NAME_BY_ID.get(i, '?')} en ucuz {money(p)} x{q}" for i, p, q in scan))

    if a.check_ids:
        check_ids(a.region, token, out)

    try:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nSonuc dosyaya da kaydedildi: {os.path.abspath(a.out)}")
    except OSError as e:
        print("Dosyaya yazilamadi:", e)


if __name__ == "__main__":
    main()
