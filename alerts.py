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


def run(snap, series, watch, hold=(), need_map=None, cfg_path="alerts.json"):
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
        if iid not in (need_map or {}):
            continue
        s = series.get(iid)
        if not s:
            continue
        cur = s[-1][1]
        w7 = [x[1] for x in s if x[0] >= week]
        manual = cfg["max_price"].get(str(iid))
        need = (need_map or {}).get(iid)
        med = statistics.median(w7) if w7 else cur
        hit = manual is not None and cur <= manual
        if not hit and len(w7) >= cfg["min_samples"]:
            rank = sum(1 for v in w7 if v < cur) / len(w7)
            hit = rank <= cfg["mat_max_rank"] and cur <= med * cfg["mat_drop_vs_median"]
        if hit:
            disc = round(100 - 100 * cur / med) if med else 0
            row = [name[:22], money(cur), money(med), f"-%{disc}", str(s[-1][3]), str(need) if need else "-"]
            found.append(("mat", f"mat{iid}", cur, row, disc))

    # 1b) fiyat firlamasi: elde tutulan item'lar -> SAT
    for iid in hold:
        s = series.get(iid)
        if not s:
            continue
        cur = s[-1][1]
        if cur < cfg.get("sell_min_price", 100):
            continue
        w7 = [x[1] for x in s if x[0] >= week]
        spike = None
        if len(w7) >= cfg["min_samples"]:
            med = statistics.median(w7)
            rank = sum(1 for v in w7 if v <= cur) / len(w7)
            if cur >= med * cfg.get("sell_up_vs_median", 1.15) and rank >= 0.9:
                spike = med
        if spike is None and len(s) >= 8:
            med8 = statistics.median([x[1] for x in s[-8:-1]])
            if cur >= med8 * cfg.get("sell_jump", 1.3):
                spike = med8
        if spike:
            up = round(100 * cur / spike - 100)
            nm = watch[iid][0]
            found.append(("sell", f"sell{iid}", cur, [nm, money(cur), money(spike), f"+{up}%", str(s[-1][3]), ""], up))

    # 1c) vendor flip: craft -> NPC'ye sat
    try:
        for r in vendor_flips(snap, cfg):
            found.append(("flip", f"flip{r['rid']}", r["profit"], [r["recipe"], money(r["cost"]), money(r["vendor"]), money(r["profit"]), r["prof"], ""], r["profit"]))
    except Exception as e:  # noqa: BLE001
        print("flip hatasi:", e)

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
            if kind == "sell":
                if age < cfg["realert_hours"] and price <= prev["price"] * 1.1:
                    continue
            elif age < cfg["realert_hours"] and price >= prev["price"] * 0.9:
                continue
        state[key] = {"ts": ts, "price": price}
        fresh.append((kind, row, score))
    cutoff = (now - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = {k: v for k, v in state.items() if v["ts"] >= cutoff}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    return fresh


_PROF = {"Alchemy": "Alc", "Enchanting": "Ench", "Engineering": "Eng", "Tailoring": "Tail", "Leatherworking": "LW",
         "Blacksmithing": "BS", "Cooking": "Cook", "Mining": "Min", "First Aid": "FA"}


def vendor_flips(snap, cfg):
    """Craft maliyeti (AH reagent fiyati; AH'de yoksa vendor alis fiyati) < NPC satis fiyati ise listele."""
    try:
        recipes = json.load(open("data/recipes.json", encoding="utf-8"))["professions"]
        names = json.load(open("data/names.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if not any(v.get("sp") for v in names.values()):
        return []
    book = {int(k): [(p, q) for p, q in v["l"]] for k, v in snap["items"].items()}
    out = []
    allow = cfg.get("flip_professions")
    for pr in recipes.values():
        if allow and pr["name"] not in allow:
            continue
        for rid, rc in pr["recipes"].items():
            ci = rc.get("crafted")
            if not ci or not ci[0] or not rc.get("reagents"):
                continue
            sp = (names.get(str(ci[0])) or {}).get("sp")
            if not sp:
                continue
            qty = int(rc.get("qty") or 1)
            cost, ok = 0.0, True
            for rid_, _nm, q in rc["reagents"]:
                c = W.cost_to_buy(book, int(rid_), q) if W else None
                if c is None:
                    pp = (names.get(str(rid_)) or {}).get("pp")
                    if not pp:
                        ok = False
                        break
                    c = pp * q
                cost += c
            if not ok:
                continue
            profit = sp * qty - cost
            if profit >= cfg.get("flip_min_profit", 3000) and profit >= cost * cfg.get("flip_min_roi", 0.2):
                out.append({"rid": rid, "recipe": rc["name"][:13], "prof": _PROF.get(pr["name"], pr["name"][:4]),
                            "cost": cost, "vendor": sp * qty, "profit": profit})
    return sorted(out, key=lambda r: -r["profit"])[:15]


def cm(x):
    return str(x).replace(" ", "")


def short(n):
    return n.replace("Journeyman", "Jrny").replace("Apprentice", "Appr").replace("Expert", "Exp")


def grid(headers, rows, widths):
    """Box-drawn table (monospace, for a Discord code block)."""
    def line(l, m, r):
        return l + m.join("\u2500" * (w + 1) for w in widths) + r
    def cell_row(cells):
        return "\u2502" + "\u2502".join(" " + str(c)[:w].ljust(w) for c, w in zip(cells, widths)) + "\u2502"
    out = [line("\u250c", "\u252c", "\u2510"), cell_row(headers), line("\u251c", "\u253c", "\u2524")]
    out += [cell_row(r) for r in rows]
    out.append(line("\u2514", "\u2534", "\u2518"))
    return "```\n" + "\n".join(out) + "\n```"


SECTIONS = {
    "favor": ("Merchant's Favor - cheap crates", 0x2ECC71, ["Crate", "Net/Fav", "For 60F"], (13, 7, 9),
              "Fill the crate, hand it in to Marcy Baker. Net = after turn-in reward."),
    "mat": ("Raw mats - bulk buy", 0x3498DB, ["Item", "Now", "Off", "Need"], (13, 7, 5, 5),
            "Price is in the cheapest 7-day band. Need = route requirement."),
    "sell": ("Price spike - sell what you hold", 0xE74C3C, ["Item", "Now", "Typical", "Up"], (13, 7, 7, 5),
             "Price is well above its usual level. Good time to sell stock."),
    "flip": ("Vendor flip - craft, sell to NPC", 0x9B59B6, ["Recipe", "Cost", "NPC", "Profit", "Prof"], (13, 7, 7, 7, 4),
             "Craft from AH mats and sell to a vendor. Profit after cost."),
    "snipe": ("Snipe - buy and relist", 0xE67E22, ["Item", "Ask", "Next", "Gain"], (13, 6, 6, 5),
              "Cheapest listing is <60% of the next one. Verify in game."),
}


def cells(kind, r):
    if kind == "favor":   # [crate, per_favor, F, bundle, crate_price, "3x ~44s 30c"]
        return [short(r[0]), cm(r[1]), cm(r[5])]
    if kind == "mat":     # [name, now, median, "-%20", stock, need]
        return [r[0], cm(r[1]), r[3].replace("-%", "-") + "%", r[5]]
    if kind == "flip":    # [recipe, cost, vendor, profit, prof, ""]
        return [r[0], cm(r[1]), cm(r[2]), cm(r[3]), r[4]]
    if kind == "sell":    # [name, now, typical, "+25%", stock, ""]
        return [r[0], cm(r[1]), cm(r[2]), r[3]]
    return [r[0], cm(r[1]), cm(r[3]), cm(r[4])]   # snipe


def todo_lines(fresh):
    """Cok kisa 'simdi ne yap' listesi."""
    lines = []
    for kind in ("sell", "snipe", "flip", "favor", "mat"):
        items = sorted([f for f in fresh if f[0] == kind], key=lambda f: -f[2])[:1 if kind == "favor" else 2]
        for _, r, _s in items:
            if kind == "sell":
                lines.append(f"SELL {r[0]} now ({cm(r[1])}, {r[3]} above normal)")
            elif kind == "snipe":
                lines.append(f"SNIPE {r[0]} at {cm(r[1])} (resell {cm(r[3])})")
            elif kind == "flip":
                lines.append(f"CRAFT {r[0]} -> sell to NPC (+{cm(r[3])} each)")
            elif kind == "favor":
                n = r[5].split("x")[0]
                lines.append(f"FAVOR buy {n}x {short(r[0])} crate + {r[3]} per crate")
            else:
                lines.append(f"BUY {r[0]} at {cm(r[1])} (need {r[5]})")
    return lines[:6]


def send_embeds(fresh, local_now, demo=False, status=None):
    embeds = []
    for kind in ("sell", "flip", "favor", "mat", "snipe"):
        items = sorted([f for f in fresh if f[0] == kind], key=lambda f: -f[2])[:10]
        if not items:
            continue
        title, color, headers, widths, hint = SECTIONS[kind]
        embeds.append({"title": f"{title} ({len(items)})", "color": color,
                       "description": hint + "\n" + grid(headers, [cells(kind, f[1]) for f in items], widths)})
    names_ = {"flip": "Flips", "sell": "SELL", "favor": "Favor", "mat": "Mats", "snipe": "Snipes"}
    summary = " | ".join(f"{names_[k]} {sum(1 for f in fresh if f[0] == k)}" for k in ("sell", "flip", "favor", "mat", "snipe") if any(f[0] == k for f in fresh))
    if status:
        embeds.append({"title": "Status", "color": 0x95A5A6, "description": "```\n" + "\n".join(status) + "\n```"})
    embeds[-1]["footer"] = {"text": f"Data: {local_now:%H:%M} (TR time)" + (" | SAMPLE DATA" if demo else "")}
    todo = todo_lines(fresh)
    body = "\n".join("\u2022 " + t for t in todo) if todo else "\u2022 Nothing to do right now - wait for a better price"
    content = ("**SAMPLE** " if demo else "") + "**DO NOW**\n" + body
    post({"content": content, "embeds": embeds})


def status(snap, series, watch, hold, need_map, route_lines, cfg_path="alerts.json"):
    """Her veri guncellemesinde kisa durum degerlendirmesi (satirlar)."""
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    now = datetime.datetime.strptime(snap["fetched_at"], "%Y-%m-%dT%H:%M:%SZ")
    week = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []
    if W is not None:
        book = {int(k): [(p, q) for p, q in v["l"]] for k, v in snap["items"].items()}
        try:
            rows, _ = W.evaluate(book)
            r = rows[0]
            lines.append(f"Favor best: {short(r['crate'])} {cm(money(r['per_favor']))}/F (buy <= {cm(money(cfg['favor_per_favor_max']))})")
        except Exception:  # noqa: BLE001
            pass
    lines += route_lines
    # alim bandina en yakin rota malzemeleri
    ranked = []
    nsamp = 0
    for iid in (need_map or {}):
        s = series.get(iid)
        if not s:
            continue
        w7 = [x[1] for x in s if x[0] >= week]
        nsamp = max(nsamp, len(w7))
        if len(w7) >= cfg["min_samples"]:
            rank = sum(1 for v in w7 if v < s[-1][1]) / len(w7)
            ranked.append((rank, watch[iid][0], s[-1][1]))
    if ranked:
        ranked.sort()
        lines.append("Cheapest vs 7d: " + ", ".join(f"{n} {cm(money(p))} (p{round(r * 100)})" for r, n, p in ranked[:3]))
    else:
        lines.append(f"Price history: {nsamp}/{cfg['min_samples']} samples, buy signals start after that")
    movers = []
    for iid in hold:
        s = series.get(iid)
        if not s or s[-1][1] < cfg.get("sell_min_price", 100):
            continue
        w7 = [x[1] for x in s if x[0] >= week]
        if len(w7) >= cfg["min_samples"]:
            med = statistics.median(w7)
            movers.append((s[-1][1] / med - 1, watch[iid][0]))
    if movers:
        movers.sort()
        up, dn = movers[-1], movers[0]
        lines.append(f"Holdings: top {up[1]} {up[0] * 100:+.0f}%, low {dn[1]} {dn[0] * 100:+.0f}%")
    return lines


def notify(fresh, status_lines, snap):
    local = datetime.datetime.strptime(snap["fetched_at"], "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(hours=3)
    send_embeds(fresh, local, status=status_lines)


def digest(snap, route_lines, force=False):
    """Gunde bir kez (TR ~09:00 sonrasi) kisa ozet. state['_digest'] ile tekrarlanmaz."""
    ts = snap["fetched_at"]
    now = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    state_path = "data/alert_state.json"
    try:
        state = json.load(open(state_path, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    today = now.strftime("%Y-%m-%d")
    if not force and (now.hour < 6 or state.get("_digest", {}).get("day") == today):
        return
    best = ""
    if W is not None:
        book = {int(k): [(p, q) for p, q in v["l"]] for k, v in snap["items"].items()}
        try:
            rows, _ = W.evaluate(book)
            r = rows[0]
            best = f"Favor: best is {short(r['crate'])} at {cm(money(r['per_favor']))}/Favor"
        except Exception:  # noqa: BLE001
            pass
    lines = [best] + [l for l in route_lines if l]
    local = now + datetime.timedelta(hours=3)
    body = "\n".join(lines)
    post({"content": f"**Daily summary** ({local:%d %b %H:%M} TR)",
          "embeds": [{"title": "Where prices stand", "color": 0x95A5A6, "description": "```\n" + body + "\n```"}]})
    state["_digest"] = {"day": today, "ts": ts, "price": 0}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)


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
        ("favor", ["Journeyman Parts", "1s 18c/F", "20", "4x Bronze Framework", "7s 10c", "3x ~70s 80c"], -118),
        ("favor", ["Journeyman Herbs", "1s 38c/F", "10", "10x Bruiseweed", "8s 28c", "6x ~82s 80c"], -138),
        ("mat", ["Silk Cloth", "1s 52c", "1s 90c", "-%20", "3525", "640"], 20),
        ("mat", ["Bronze Bar", "1s 70c", "2s 10c", "-%19", "1869", "110"], 19),
        ("flip", ["Iron Grenade", "4s 10c", "5s 0c", "90c", "Eng", ""], 9000),
        ("sell", ["Mithril Ore", "1g 85s", "1g 30s", "+42%", "530", ""], 42),
        ("snipe", ["Plans: Mithril Spurs", "5g 99s", "x2", "9g 99s", "~8g", "5"], 80000),
    ]
    send_embeds(fresh, datetime.datetime.utcnow() + datetime.timedelta(hours=3), demo=True,
                status=["Favor best: Jrny Parts 1s27c/F (buy <= 1s20c)", "Tailoring route: 22g now (7d low 20g)", "Cheapest vs 7d: Silk 1s89c (p35)", "Holdings: top Iron Ore +8%, low Heavy Leather -3%"])
