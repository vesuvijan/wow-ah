#!/usr/bin/env python3
"""Forever API kesfi + recipe dokumu + AH item isimleri (GitHub Actions'ta elle calistirilir).

Cikti (data/ klasorunde):
  probe_report.json            hangi endpoint/namespace calisti (HTTP kodlari)
  recipes_<namespace>.json     calisan her namespace icin tum profession/recipe/reagent verisi
  names.json                   house AH'indeki her item ID icin isim/sinif/bind tipi (bulunabildigi kadar)
Gereken ortam degiskenleri: BLIZZARD_CLIENT_ID, BLIZZARD_CLIENT_SECRET (REGION, RULESET, HOUSE istege bagli).
fetch_ah.py ile ayni klasorde olmali.
"""
import json
import os
import sys
import time
import urllib.error

import fetch_ah as F

REGION = os.environ.get("REGION", "eu")
RULESET = os.environ.get("RULESET", "15")
HOUSE = int(os.environ.get("HOUSE", "123"))
DEADLINE = time.time() + 100 * 60  # 40 dk sonra kalan isleri birak
NAMESPACES = [f"static-forever-{REGION}", f"static-1.60.1_70399-forever-{REGION}",
              f"static-classic1x-{REGION}", f"static-classic-{REGION}"]
report = []


def call(path, ns, token, quiet=False):
    sep = "&" if "?" in path else "?"
    url = f"https://{REGION}.api.blizzard.com{path}{sep}namespace={ns}&locale=en_US"
    try:
        d = F.get_json(url, token, tries=2)
        if not quiet:
            report.append({"ns": ns, "path": path, "status": 200,
                           "keys": list(d.keys())[:12] if isinstance(d, dict) else type(d).__name__})
        return d
    except urllib.error.HTTPError as e:
        if not quiet:
            report.append({"ns": ns, "path": path, "status": e.code})
    except Exception as e:  # noqa: BLE001
        if not quiet:
            report.append({"ns": ns, "path": path, "status": "ERR " + str(e)[:80]})
    return None


def nm(x):
    if isinstance(x, dict):
        return x.get("en_US") or next(iter(x.values()), "")
    return x or ""


def dump_recipes(ns, token):
    idx = call("/data/wow/profession/index", ns, token)
    if not idx:
        return None, None
    out = {"namespace": ns, "professions": {}}
    n_rec = 0
    for p in idx.get("professions", []):
        pd = call(f"/data/wow/profession/{p['id']}", ns, token)
        if not pd:
            continue
        entry = {"name": nm(p.get("name")), "recipes": {}}
        for st in pd.get("skill_tiers", []) or []:
            sd = call(f"/data/wow/profession/{p['id']}/skill-tier/{st['id']}", ns, token)
            if not sd:
                continue
            for cat in sd.get("categories", []) or []:
                for r in cat.get("recipes", []) or []:
                    if time.time() > DEADLINE:
                        break
                    rd = call(f"/data/wow/recipe/{r['id']}", ns, token, quiet=True)
                    if not rd:
                        entry["recipes"][str(r["id"])] = {"name": nm(r.get("name")), "missing": True}
                        continue
                    ci = rd.get("crafted_item") or rd.get("horde_crafted_item") or rd.get("alliance_crafted_item") or {}
                    entry["recipes"][str(r["id"])] = {
                        "name": nm(rd.get("name")),
                        "skill_tier": nm(st.get("name")),
                        "crafted": [ci.get("id"), nm(ci.get("name"))] if ci else None,
                        "qty": rd.get("crafted_quantity", {}).get("value") if isinstance(rd.get("crafted_quantity"), dict) else rd.get("crafted_quantity"),
                        "reagents": [[(rg.get("reagent") or {}).get("id"), nm((rg.get("reagent") or {}).get("name")), rg.get("quantity")]
                                     for rg in rd.get("reagents", []) or []],
                    }
                    n_rec += 1
        out["professions"][str(p["id"])] = entry
    return out, n_rec


def dump_names(ids, token):
    names = {}
    for ns in NAMESPACES:
        todo = [i for i in ids if i not in names]
        if not todo:
            break
        hits = 0
        for i in todo:
            if time.time() > DEADLINE:
                break
            d = call(f"/data/wow/item/{i}", ns, token, quiet=True)
            if not d:
                continue
            hits += 1
            pv = d.get("preview_item") or {}
            bind = ((pv.get("binding") or {}).get("type")) if isinstance(pv, dict) else None
            names[i] = {"n": nm(d.get("name")), "c": nm((d.get("item_class") or {}).get("name")),
                        "s": nm((d.get("item_subclass") or {}).get("name")), "b": bind, "ns": ns,
                        "sp": d.get("sell_price"), "pp": d.get("purchase_price")}
        report.append({"names_namespace": ns, "tried": len(todo), "found": hits})
    return names


def main():
    cid, sec = os.environ.get("BLIZZARD_CLIENT_ID"), os.environ.get("BLIZZARD_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET tanimli degil")
    token = F.get_token(cid, sec)
    os.makedirs("data", exist_ok=True)

    # 1) recipe dokumu: calisan her (farkli) namespace icin
    seen_idx = []
    extra_ids = set()
    for ns in NAMESPACES:
        if time.time() > DEADLINE:
            break
        probe = call("/data/wow/profession/index", ns, token, quiet=True)
        if not probe:
            report.append({"ns": ns, "path": "/data/wow/profession/index", "status": "yok"})
            continue
        sig = json.dumps(probe, sort_keys=True)
        if sig in seen_idx:
            report.append({"ns": ns, "path": "/data/wow/profession/index", "status": "oncekiyle ayni, atlandi"})
            continue
        seen_idx.append(sig)
        out, n = dump_recipes(ns, token)
        if out:
            for pr in out["professions"].values():
                for rc in pr["recipes"].values():
                    if rc.get("crafted") and rc["crafted"][0]:
                        extra_ids.add(int(rc["crafted"][0]))
                    for rg in rc.get("reagents", []) or []:
                        if rg[0]:
                            extra_ids.add(int(rg[0]))
            with open(f"data/recipes_{ns}.json", "w", encoding="utf-8") as f:
                json.dump(out, f, separators=(",", ":"))
            report.append({"ns": ns, "recipes_dumped": n})

    # 2) AH'deki item ID'leri icin isimler
    base, dyn = f"https://{REGION}.api.blizzard.com", f"dynamic-forever-{REGION}"
    ah = F.snapshot_house(base, dyn, RULESET, HOUSE, token)
    ids = sorted({int(i) for i in ah} | extra_ids)
    names = dump_names(ids, token)
    with open("data/names.json", "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in names.items()}, f, separators=(",", ":"))
    report.append({"ah_items": len(ids), "names_found": len(names)})

    with open("data/probe_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(report[-6:], indent=1))


if __name__ == "__main__":
    main()
