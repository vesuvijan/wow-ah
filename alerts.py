#!/usr/bin/env python3
"""Discord uyarilari: favor crate, mat dususu, snipe. history.py tarafindan cagrilir.
Ortam: DISCORD_WEBHOOK_URL (yoksa sadece ekrana yazar). Ayarlar: alerts.json. Durum: data/alert_state.json"""
import datetime
import json
import os
import statistics
import urllib.request

try:
    import waylaid_calc_v2 as W
except ImportError:  # noqa: BLE001
    W = None


def money(c):
    c = int(round(c))
    g, rem = divmod(c, 10000)
    s, cu = divmod(rem, 100)
    return (f"{g}g " if g else "") + (f"{s}s " if (s or g) else "") + f"{cu}c"


def load_names():
    try:
        return {int(k): v.get("n", "") for k, v in json.load(open("data/names.json", encoding="utf-8")).items()}
    except Exception:  # noqa: BLE001
        return {}


def run(snap, series, watch, cfg_path="alerts.json"):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    names = load_names()
    ts = snap["fetched_at"]
    now = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    week = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state_path = "data/alert_state.json"
    try:
        state = json.load(open(state_path, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    found = []  # (key, price, text)

    # 1) mat dususu (izlenen item'lar)
    for iid, (name, grp) in watch.items():
        if "satis" in name or grp == "F":
            continue
        s = series.get(iid)
        if not s:
            continue
        cur = s[-1][1]
        w7 = [x[1] for x in s if x[0] >= week]
        manual = cfg["max_price"].get(str(iid))
        if manual is not None and cur <= manual:
            found.append((f"mat{iid}", cur, f"MAT {name}: {money(cur)} (esik {money(manual)}), stok {s[-1][3]}"))
            continue
        if len(w7) >= cfg["min_samples"]:
            med = statistics.median(w7)
            rank = sum(1 for v in w7 if v < cur) / len(w7)
            if rank <= cfg["mat_max_rank"] and cur <= med * cfg["mat_drop_vs_median"]:
                found.append((f"mat{iid}", cur, f"MAT {name}: {money(cur)} (7g medyan {money(med)}, %{round(100 - 100 * cur / med)} ucuz), stok {s[-1][3]}"))

    # 2) Favor crate
    if W is not None:
        book = {int(k): [(p, q) for p, q in v["l"]] for k, v in snap["items"].items()}
        try:
            rows, _ = W.evaluate(book)
            good = [r for r in rows if r["per_favor"] <= cfg["favor_per_favor_max"]]
            for r in good[:3]:
                found.append((f"favor{r['crate']}", r["per_favor"],
                              f"FAVOR {r['crate']}: {money(r['per_favor'])}/Favor ({r['favor']}F) | {r['bundle']} {money(r['mats'])} + crate {money(r['crate_price'])}"))
        except Exception as e:  # noqa: BLE001
            print("favor hesabi hatasi:", e)

    # 3) snipe: en ucuz ilan bir sonraki fiyatin <%60'i
    snipes = []
    for k, v in snap["items"].items():
        L = v["l"]
        if len(L) < 2:
            continue
        p0, q0 = L[0]
        nxt = next((p for p, q in L if p > p0), None)
        if nxt and p0 < 0.6 * nxt and q0 <= cfg["snipe_max_listing_qty"] and (nxt - p0) * q0 >= cfg["snipe_min_gain"]:
            snipes.append(((nxt - p0) * q0, int(k), p0, q0, nxt, v["n"]))
    for gain, iid, p0, q0, nxt, n in sorted(snipes, reverse=True)[:5]:
        nm = names.get(iid) or f"item {iid}"
        found.append((f"snipe{iid}", p0, f"SNIPE {nm}: {money(p0)} x{q0}, sonraki {money(nxt)} (kazanc ~{money(gain)}), toplam stok {n}"))

    # tekrar bildirimi bastir
    out = []
    for key, price, text in found:
        prev = state.get(key)
        if prev:
            age = (now - datetime.datetime.strptime(prev["ts"], "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 3600
            if age < cfg["realert_hours"] and price >= prev["price"] * 0.9:
                continue
        state[key] = {"ts": ts, "price": price}
        out.append(text)
    cutoff = (now - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = {k: v for k, v in state.items() if v["ts"] >= cutoff}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    if out:
        send("**AH uyarisi** (" + ts + ")\n" + "\n".join(out[:12]))
    return out


def send(text):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    print(text)
    if not url:
        print("(DISCORD_WEBHOOK_URL yok, gonderilmedi)")
        return
    req = urllib.request.Request(url, data=json.dumps({"content": text[:1900]}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "wow-ah-bot/1.0"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:  # noqa: BLE001
        print("Discord gonderilemedi:", e)
