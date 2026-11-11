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
    found = []  # (kind, key, price, row)

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
        need = cfg.get("targets", {}).get(str(iid))
        med = statistics.median(w7) if w7 else cur
        hit = manual is not None and cur <= manual
        if not hit and len(w7) >= cfg["min_samples"]:
            rank = sum(1 for v in w7 if v < cur) / len(w7)
            hit = rank <= cfg["mat_max_rank"] and cur <= med * cfg["mat_drop_vs_median"]
        if hit:
            disc = round(100 - 100 * cur / med) if med else 0
            row = [name[:22], money(cur), money(med), f"-%{disc}", str(s[-1][3]), str(need) if need else "-"]
            found.append(("mat", f"mat{iid}", cur, row, disc))

    # 2) Favor crate
    if W is not None:
        book = {int(k): [(p, q) for p, q in v["l"]] for k, v in snap["items"].items()}
        try:
            rows, _ = W.evaluate(book)
            tgt = cfg.get("favor_target", 60)
            for r in [r for r in rows if r["per_favor"] <= cfg["favor_per_favor_max"]][:4]:
                n = -(-tgt // r["favor"])
                row = [r["crate"][:22], money(r["per_favor"]), str(r["favor"]), r["bundle"][:24], money(r["crate_price"]), f"{n}x ~{money(r['per_favor'] * n * r['favor'])}"]
                found.append(("favor", f"favor{r['crate']}", r["per_favor"], row, -r["per_favor"]))
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
    for gain, iid, p0, q0, nxt, n in sorted(snipes, reverse=True)[:6]:
        nm = names.get(iid) or f"item {iid}"
        row = [nm[:26], money(p0), f"x{q0}", money(nxt), "~" + money(gain), str(n)]
        found.append(("snipe", f"snipe{iid}", p0, row, gain))

    # tekrar bildirimi bastir
    fresh = []
    for kind, key, price, row, score in found:
        prev = state.get(key)
        if prev:
            age = (now - datetime.datetime.strptime(prev["ts"], "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 3600
            if age < cfg["realert_hours"] and price >= prev["price"] * 0.9:
                continue
        state[key] = {"ts": ts, "price": price}
        fresh.append((kind, row, score))
    cutoff = (now - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = {k: v for k, v in state.items() if v["ts"] >= cutoff}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    if fresh:
        send_embeds(fresh, now + datetime.timedelta(hours=3))
    return fresh


def cm(x):
    return str(x).replace(" ", "")


def short(n):
    return n.replace("Journeyman", "Jrny").replace("Apprentice", "Appr").replace("Expert", "Exp")


def fmt_row(kind, r):
    if kind == "favor":   # [crate, per_favor, F, bundle, crate_price, "3x ~44s 30c"]
        return f"{short(r[0])[:14]:<15}{cm(r[1]) + '/F':>9} {cm(r[5])}"
    if kind == "mat":     # [name, simdi, medyan, "-%20", stok, ihtiyac]
        return f"{r[0][:17]:<17}{cm(r[1]):>8}{r[3].replace('%', ''):>6}{r[5]:>5}"
    return f"{r[0][:16]:<17}{cm(r[1]) + '>' + cm(r[3]):>13} {cm(r[4])}"   # snipe


SECTIONS = {
    "favor": ("Favor - ucuz crate", 0x2ECC71, f"{'Crate':<15}{'Net/Fav':>9} 60F icin",
              "Doldur, Marcy Baker'a teslim et."),
    "mat": ("Malzeme dustu - toplu al", 0x3498DB, f"{'Item':<17}{'Simdi':>8}{'Fark':>6}{'Lazim':>5}",
            "7 gunun en ucuz dilimi. 'Lazim' = rota ihtiyaci."),
    "snipe": ("Snipe - al ve yeniden sat", 0xE67E22, f"{'Item':<17}{'Ilan>Sonraki':>13} Kar",
              "Oyunda fiyati dogrula."),
}


def send_embeds(fresh, local_now, demo=False):
    embeds = []
    for kind in ("favor", "mat", "snipe"):
        items = sorted([f for f in fresh if f[0] == kind], key=lambda f: -f[2])[:10]
        if not items:
            continue
        title, color, header, hint = SECTIONS[kind]
        body = "\n".join([header] + [fmt_row(kind, f[1]) for f in items])
        embeds.append({"title": f"{title} ({len(items)})", "color": color,
                       "description": hint + "\n```\n" + body + "\n```"})
    summary = " | ".join(f"{SECTIONS[k][0].split(' - ')[0]} {sum(1 for f in fresh if f[0] == k)}" for k in ("favor", "mat", "snipe") if any(f[0] == k for f in fresh))
    embeds[-1]["footer"] = {"text": f"Veri: {local_now:%H:%M} (TR)" + (" | ORNEK VERI" if demo else "")}
    post({"content": ("**ORNEK** " if demo else "") + "AH firsatlari: " + summary, "embeds": embeds})


def post(payload):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    print(json.dumps(payload, ensure_ascii=False, indent=1)[:3000])
    if not url:
        print("(DISCORD_WEBHOOK_URL yok, gonderilmedi)")
        return
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "wow-ah-bot/1.0"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:  # noqa: BLE001
        print("Discord gonderilemedi:", e)


def demo():
    fresh = [
        ("favor", ["Journeyman Parts", "1s 18c", "20", "4x Bronze Framework", "7s 10c", "3x ~70s 80c"], -118),
        ("mat", ["Silk Cloth", "1s 52c", "1s 90c", "-%20", "3525", "640"], 20),
        ("mat", ["Bronze Bar", "1s 70c", "2s 10c", "-%19", "1869", "110"], 19),
        ("snipe", ["Plans: Mithril Spurs", "5g 99s", "x2", "9g 99s", "~8g", "5"], 80000),
    ]
    send_embeds(fresh, datetime.datetime.utcnow() + datetime.timedelta(hours=3), demo=True)


def send(text):
    post({"content": text[:1900]})


def _old_send(text):
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
