#!/usr/bin/env python3
"""Discord uyarilari: favor crate, mat dususu, snipe. history.py tarafindan cagrilir.
Ortam: DISCORD_WEBHOOK_URL (yoksa sadece ekrana yazar). Ayarlar: alerts.json. Durum: data/alert_state.json"""
import datetime
import json
import re
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


QUIET = {"new", "recipe"}          # ilk kez gorulen itemlar: anlik mesaj yok, sadece ozet icin kaydedilir
LOG = "data/alert_log.jsonl"


def log_alert(ts, kind, row, score=0, **extra):
    """Her uyariyi/durumu kaydet; digest.py 'son N saatin ozeti' icin okur. 7 gun tutulur."""
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "kind": kind, "row": row, "score": score, **extra}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


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
            lst = sorted(snap["items"].get(str(iid), {}).get("l", []))
            cap = cur * 1.1
            avail = sum(q for p, q in lst if p <= cap)
            row = [name, money(cur), money(med), f"-%{disc}", str(s[-1][3]), str(need) if need else "-", avail, money(cap)]
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
            found.append(("flip", f"flip{r['rid']}", r["profit"], [r["recipe"], money(r["cost"]), money(r["vendor"]), money(r["profit"]), r["prof"], r["mats"]], r["profit"]))
    except Exception as e:  # noqa: BLE001
        print("flip hatasi:", e)

    # 2) Favor crate: gercek stok derinligine gore (crate ve mat adedi), marjinal Favor basina fiyat limitin altinda kaldigi surece
    if W is not None:
        book = {int(k): sorted((p, q) for p, q in v["l"]) for k, v in snap["items"].items()}
        try:
            tgt = cfg.get("favor_target", 60)
            lim = cfg["favor_per_favor_max"]
            plans = []
            for cname, (crate_id, _ok, favor, reward, _rok, bundles) in W.CRATES.items():
                nmax = -(-tgt // favor)
                best = None
                for mat, qty in bundles:
                    prev, last = 0.0, None
                    for n_ in range(1, nmax + 1):
                        cc = W.cost_to_buy(book, crate_id, n_)
                        mc = W.cost_to_buy(book, W.ITEMS[mat], n_ * qty)
                        if cc is None or mc is None:
                            break
                        tot = cc + mc - reward * n_
                        if (tot - prev) / favor > lim:
                            break
                        prev, last = tot, (n_, cc, mc, tot)
                    if last and (best is None or last[3] / (last[0] * favor) < best[3] / (best[0] * favor)):
                        best = last + (mat, qty)
                if best:
                    n_, cc, mc, tot, mat, qty = best
                    plans.append(dict(crate=cname, bundle=f"{qty}x {mat}", mats=mc / n_, crate_price=cc / n_, favor=favor, total=tot / n_,
                                      per_favor=tot / (n_ * favor), mat=mat, qty=qty, reward=reward, n=n_, want=nmax))
            plans.sort(key=lambda r: r["per_favor"])
            for r in plans[:4]:
                n = r["n"]
                row = [r["crate"][:22], money(r["per_favor"]), str(r["favor"]), r["bundle"][:24], money(r["crate_price"]), f"{n}x ~{money(r['per_favor'] * n * r['favor'])}", r]
                found.append(("favor", f"favor{r['crate']}", r["per_favor"], row, -r["per_favor"]))
        except Exception as e:  # noqa: BLE001
            print("favor hesabi hatasi:", e)

    # 3a) gunluk en dusuk fiyat gecmisi (tum item/varyant) -> snipe icin "kendi tarihine gore ucuz mu" kontrolu
    day_key = ts[:10]
    try:
        mh = json.load(open("data/minhist.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        mh = {}
    allk = dict(snap["items"]); allk.update(snap.get("variants", {}))
    for k, v in allk.items():
        if not v["l"]:
            continue
        e = mh.setdefault(k, {})
        e[day_key] = min(e.get(day_key, 1e18), v["l"][0][0])
    for k in list(mh):
        days = sorted(mh[k])[-14:]
        mh[k] = {d: mh[k][d] for d in days}
        if k not in allk and len(days) and days[-1] < (now - datetime.timedelta(days=14)).strftime("%Y-%m-%d"):
            del mh[k]
    json.dump(mh, open("data/minhist.json", "w"), separators=(",", ":"))

    # 3) snipe: AYNI varyantin en ucuz ilani, ayni varyantin sonraki >=2 birim ilaninin medyaninin <%60'i
    snipes = []
    variants = snap.get("variants", {})
    has_var = {k.split(":")[0] for k in variants}
    pool = [(k, v) for k, v in snap["items"].items() if k not in has_var] + list(variants.items())
    for k, v in pool:
        L = v["l"]
        if len(L) < 2:
            continue
        p0, q0 = L[0]
        above = []
        for p, q in L[1:]:
            above += [p] * int(q)
            if len(above) >= 3:
                break
        if len(above) < 2:
            continue
        ref = statistics.median(above[:3])
        past = [x for d, x in sorted(mh.get(k, {}).items()) if d < day_key]
        if len(past) < 3:
            continue            # kendi fiyat gecmisini bilmeden snipe deme
        if p0 > 0.6 * statistics.median(past):
            continue            # gecmiste de bu kadar ucuzdu -> firsat degil
        if p0 < 0.6 * ref and q0 <= cfg["snipe_max_listing_qty"] and (ref - p0) * q0 >= cfg["snipe_min_gain"]:
            snipes.append(((ref - p0) * q0, k, p0, q0, ref, v["n"]))
    for gain, k, p0, q0, nxt, n in sorted(snipes, reverse=True)[:6]:
        iid = int(k.split(":")[0])
        nm = names.get(iid) or f"item {iid}"
        if ":" in k:
            nm += " #" + k.split(":")[1]
        row = [nm, money(p0), f"x{q0}", money(nxt), "~" + money(gain), str(n)]
        found.append(("snipe", f"snipe{k}", p0, row, gain))

    # 3b) Sealed Writ: reputation (Azeroth Commerce Authority) icin ucuz alim. Rep/writ: Journeyman 75, Expert 125, Artisan 200
    WRITS = {"262888": ("Sealed Journeyman's Writ", 75), "262889": ("Sealed Expert's Writ", 125), "262890": ("Sealed Artisan's Writ", 200)}
    lim = cfg.get("writ_max_copper_per_rep", 20)
    for wid, (wname, rep) in WRITS.items():
        v = snap["items"].get(wid)
        if not v or not v["l"]:
            continue
        cheap = [(p, q) for p, q in v["l"] if p / rep <= lim]
        if not cheap:
            continue
        qty = sum(q for _, q in cheap)
        top = max(p for p, _ in cheap)
        row = [wname, cm(money(cheap[0][0])), f"{rep} rep", f"{cm(money(cheap[0][0] / rep))} per rep", f"x{qty} up to {cm(money(top))}", ""]
        found.append(("writ", f"writ{wid}", cheap[0][0], row, -cheap[0][0] / rep))

    # 3c) Writ kumari: Sealed Writ ac -> rastgele siparis cikar -> acilmis writ'i sat. Acilmis writ ilanlarinin tier'e gore medyan ask'i
    try:
        tc = json.load(open("data/tipcache.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        tc = {}
    opened = {"Journeyman": [], "Expert": [], "Artisan": []}
    prev = {}
    try:
        prev = json.load(open("data/writ_prev.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    cur = {}
    for k, v in snap["items"].items():
        nm = names.get(int(k)) if str(k).isdigit() else None
        if not nm or not nm.startswith("Craftsman's Writ:") or not v["l"]:
            continue
        m = re.search(r"\b(Journeyman|Expert|Artisan)\b", re.sub(r"<[^>]+>", " ", (tc.get(str(k)) or {}).get("tooltip", "")))
        if not m:
            continue
        opened[m.group(1)].append(v["l"][0][0])
        cur[k] = [m.group(1), sum(q for _, q in v["l"])]
    gone = {t: 0 for t in opened}
    for k, (t, q) in prev.items():
        gone[t] += max(0, q - cur.get(k, [t, 0])[1])      # kaybolan ilan adedi (satis veya sure bitimi)
    json.dump(cur, open("data/writ_prev.json", "w"))
    mk = {}
    for t, lows in opened.items():
        if lows:
            mk[t] = (statistics.median(lows), len(lows), sum(q for _, q in [x for x in cur.values() if x[0] == t]))
    log_alert(ts, "writmkt", [f"{t}: median ask {cm(money(m_[0]))}, {m_[1]} order types, {m_[2]} listed, {gone[t]} listings gone since last snapshot" for t, m_ in mk.items()])
    gmin = cfg.get("writ_gamble_ratio", 3.0)
    for wid, (wname, rep) in WRITS.items():
        t = wname.split("'")[0].replace("Sealed ", "")
        v = snap["items"].get(wid)
        if t not in mk or not v or not v["l"]:
            continue
        sell = mk[t][0] * 0.95
        n_ok = sum(q for p, q in v["l"] if sell / p >= gmin)
        if n_ok:
            p0 = v["l"][0][0]
            row = [wname, cm(money(p0)), f"~{cm(money(sell))} each", f"x{min(n_ok, 5)} test", f"{mk[t][1]} order types, median ask {cm(money(mk[t][0]))}", ""]
            found.append(("gamble", f"gamble{wid}", p0, row, sell / p0))

    # 3d) Opened writ, crafting YOK: writ + istedigi item'i AH'den satin al. Tum meslekler. Rep basina toplam maliyet.
    try:
        rev = {}
        for id_, nm0 in names.items():
            rev.setdefault(str(nm0).lower(), []).append(int(id_))
        bk = {int(k_): sorted((p_, q_) for p_, q_ in v_["l"]) for k_, v_ in snap["items"].items()}
        REPT = {"Journeyman": 75, "Expert": 125, "Artisan": 200}
        lim_e = cfg.get("writ_ah_max_copper_per_rep", 150)
        for k_, v_ in snap["items"].items():
            nm_ = names.get(int(k_)) if str(k_).isdigit() else None
            if not nm_ or not nm_.startswith("Craftsman's Writ:") or not v_["l"]:
                continue
            item_ = nm_.split(": ", 1)[1]
            opts = [bk[i_][0][0] for i_ in rev.get(item_.lower(), []) if bk.get(i_)]
            mt = re.search(r"\b(Journeyman|Expert|Artisan)\b", re.sub(r"<[^>]+>", " ", (tc.get(str(k_)) or {}).get("tooltip", "")))
            if not opts or not mt:
                continue
            rep_, w_, ic_ = REPT[mt.group(1)], v_["l"][0][0], min(opts)
            per = (w_ + ic_) / rep_
            if per <= lim_e:
                row = [f"Craftsman's Writ: {item_} ({mt.group(1)})", cm(money(w_)), f"{rep_} rep", f"{cm(money(per))} per rep", f"{item_} ~{cm(money(ic_))}", ""]
                found.append(("writ", f"writbuy{k_}", w_, row, -per))
    except Exception as e:  # noqa: BLE001
        print("writ_ah hatasi:", e)

    # 4) AH'de Docker Tuckalot icin gear upgrade / tarif / yeni item
    try:
        import ah_gear
        found += ah_gear.scan(snap, cfg)
    except Exception as e:  # noqa: BLE001
        print("ah_gear hatasi:", e)

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
        log_alert(ts, kind, row, score)
        if kind in QUIET:
            continue            # sadece ozet kaydina yazilir, Discord'a anlik gitmez
        fresh.append((kind, row, score))
    cutoff = (now - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = {k: v for k, v in state.items() if v["ts"] >= cutoff}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    try:   # kaydi 7 gunle sinirla
        keep = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = [l for l in open(LOG, encoding="utf-8") if json.loads(l)["ts"] >= keep]
        open(LOG, "w", encoding="utf-8").writelines(rows)
    except Exception:  # noqa: BLE001
        pass
    return fresh


_PROF = {"Alchemy": "Alc", "Enchanting": "Ench", "Engineering": "Eng", "Tailoring": "Tail", "Leatherworking": "LW",
         "Blacksmithing": "BS", "Cooking": "Cook", "Mining": "Min", "First Aid": "FA"}


VENDOR_REAGENTS = {2320, 2321, 4291, 8343, 14341, 3371, 3372, 2325, 2604, 2605, 4340, 4341, 4342, 6260, 6261, 2880, 3466, 4289}  # iplik, boya, sise, flux, tuz


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
                    # AH'de yok / yeterli adet yok. Sadece bilinen vendor reagent'lari (iplik, boya, sise, flux...) static fiyatla hesaplanir.
                    if int(rid_) not in VENDOR_REAGENTS:
                        ok = False
                        break
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
                out.append({"rid": rid, "recipe": rc["name"], "prof": pr["name"], "mats": ", ".join(f"{q}x {nm_}" for _i, nm_, q in rc["reagents"]),
                            "cost": cost, "vendor": sp * qty, "profit": profit})
    return sorted(out, key=lambda r: -r["profit"])[:15]


def cm(x):
    """'4g 0s 5c' -> '4g5c'; sifir birimleri atar: '89g 0s 0c' -> '89g'."""
    parts = re.findall(r"(\d+)([gsc])", str(x))
    if not parts:
        return str(x).replace(" ", "")
    keep = [f"{n}{u}" for n, u in parts if int(n) != 0]
    return ("-" if str(x).strip().startswith("-") else "") + ("".join(keep) if keep else "0c")


def short(n):
    return n   # no abbreviations: always the full name


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
    "gear": ("Gear upgrade on the AH for Docker Tuckalot", 0x1ABC9C, ["#", "Price", "Gain", "Slot"], (2, 9, 7, 14),
             "Better than what you wear now, wearable at your level. Check the stats in game before buying."),
    "recipe": ("Recipe for one of your upgrades", 0xF1C40F, ["#", "Price", "Qty"], (2, 9, 4),
               "The pattern/plan teaches a craft that is an upgrade for you."),
    "new": ("New on the AH (first time seen)", 0xE91E63, ["#", "Price", "Type", "Slot"], (2, 9, 10, 14),
            "Never listed before. Good items first."),
    "favor": ("Merchant's Favor - cheap crates", 0x2ECC71, ["Crate", "Net/Fav", "For 60F"], (13, 7, 9),
              "Fill the crate, hand it in to Marcy Baker. Net = after turn-in reward."),
    "mat": ("Raw mats - bulk buy", 0x3498DB, ["Item", "Now", "Off", "Need"], (13, 7, 5, 5),
            "Price is in the cheapest 7-day band. Need = route requirement."),
    "sell": ("Price spike - sell what you hold", 0xE74C3C, ["Item", "Now", "Typical", "Up"], (13, 7, 7, 5),
             "Price is well above its usual level. Good time to sell stock."),
    "flip": ("Vendor flip - craft, sell to NPC", 0x9B59B6, ["Recipe", "Cost", "NPC", "Profit", "Prof"], (13, 7, 7, 7, 4),
             "Craft from AH mats and sell to a vendor. Profit after cost."),
    "writ": ("Cheap reputation - Writs", 0x00BCD4, ["#", "Price", "Reputation", "Cost"], (2, 9, 10, 12),
             "Buy the writ and the item it asks for on the AH (no crafting), accept the order and hand the item in = reputation + a coin pouch of silver. Each order once per day. Cost = all-in silver per reputation point."),
    "gamble": ("Writ gamble - open and resell (TEST SIZE)", 0xFF5722, ["#", "Cost", "Resale", "Try"], (2, 9, 12, 8),
               "Unproven: we see asking prices, not sales. Buy only the test amount, open them, list the orders, see if they sell."),
    "snipe": ("Snipe - buy and relist", 0xE67E22, ["Item", "Ask", "Resell", "Gain"], (14, 7, 7, 7),
              "Same variant, <60% of its own 3-day+ price history and of the next 3 listings. Verify in game."),
}


def crate_full(name):
    m = re.match(r"(\w+) (\w+) \((\w+)\)", name)
    return "Waylaid Crate: " + (f"{m.group(3)} {m.group(1)} {m.group(2)}" if m else name)


def favor_card(r):
    d = r[6]
    n, q = d["n"], d["qty"]
    unit = d["mats"] / q
    lines = [f"{crate_full(d['crate'])} (+{d['favor']} Favor)",
             f"1 Buy crate  {cm(money(d['crate_price']))} each, x{n}",
             f"2 Buy mats   {d['mat']} x{q}/crate",
             f"             ~{cm(money(unit))} each = {cm(money(d['mats']))}/crate",
             f"3 Fill it, hand in to Marcy Baker",
             f"             reward {cm(money(d['reward']))} + {d['favor']} Favor",
             f"Net/crate {cm(money(d['total']))} = {cm(money(d['per_favor']))}/Favor",
             f"{n} crate{'s' if n > 1 else ''} = +{n * d['favor']} Favor: buy {n * q}x {d['mat']}" + (f" (only {n} of the {d['want']} crates for 60 Favor can be filled at this price)" if n < d.get('want', n) else ""),
             f"           total net ~{cm(money(d['total'] * n))}"]
    return "\n".join(lines)


def cells(kind, r):
    if kind in ("gear", "new"):      # [label, price, gain/type, slot, bind, stats, req]
        return [r[0], cm(r[1]), r[2], r[3]]
    if kind == "gamble":             # [sealed name, cost, ~resale, "xN test", info, ""]
        return [r[0], r[1], r[2], r[3]]
    if kind == "writ":               # [name, price, rep, cost/rep, "xN up to P", ""]
        return [r[0], r[1], r[2], r[3]]
    if kind == "recipe":             # [name, price, qty, makes, "", ""]
        return [r[0], cm(r[1]), r[2]]
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
    for kind in ("sell", "gear", "recipe", "snipe", "flip", "favor", "writ", "gamble", "mat"):
        items = sorted([f for f in fresh if f[0] == kind], key=lambda f: -f[2])[:1 if kind == "favor" else 2]
        for _, r, _s in items:
            if kind == "sell":
                lines.append(f"SELL {r[0]} now ({cm(r[1])}, {r[3]} above normal)")
            elif kind == "gear":
                gain = f"{r[2]} better than what you wear" if str(r[2]).startswith("+") else str(r[2])
                lines.append(f"BUY GEAR {r[0]} at {cm(r[1])} ({r[3]}): {gain}. Stats: {r[5]}")
            elif kind == "recipe":
                lines.append(f"BUY RECIPE {r[0]} at {cm(r[1])}. {r[3]}")
            elif kind == "new":
                lines.append(f"NEW ITEM {r[0]} at {cm(r[1])} ({r[3]}): {r[5]}")
            elif kind == "writ" and r[0].startswith("Craftsman"):
                lines.append(f"BUY REP {r[0]} at {cm(r[1])} AND buy the item it asks for on the AH ({r[4]}): {r[2]} for {r[3]} all-in, no crafting. Accept the order, hand the item in. Once per order per day")
            elif kind == "writ":
                lines.append(f"BUY REP {r[0]}: {r[4]} listed at {cm(r[1])} each (that is {r[3]}, {r[2]} each). Open it, buy/craft the item it asks for, hand in for reputation and a coin pouch. Once per order per day")
            elif kind == "gamble":
                lines.append(f"TEST {r[0]}: buy {r[3].split()[0][1:]} at {cm(r[1])} each, open them (right-click), list the resulting Craftsman's Writ orders on the AH at about {r[2].split()[0][1:]} each ({r[4]}). Small test only: we see asking prices, not real sales yet")
            elif kind == "snipe":
                lines.append(f"SNIPE {r[0]} at {cm(r[1])} (resell {cm(r[3])})")
            elif kind == "flip":
                lines.append(f"CRAFT {r[0]} ({r[4]}): buy {r[5]} on the AH (about {cm(r[1])} total), craft it, sell it to any vendor for {cm(r[2])} = {cm(r[3])} profit per craft")
            elif kind == "favor":
                if len(r) > 6:
                    d = r[6]
                    lines.append(f"FAVOR buy {d['n']}x {crate_full(d['crate'])} (~{cm(money(d['crate_price']))} ea) + {d['n'] * d['qty']}x {d['mat']} (~{cm(money(d['mats'] / d['qty']))} ea) = +{d['n'] * d['favor']} Favor{' (all the stock available at this price)' if d['n'] < d.get('want', d['n']) else ''}, net ~{cm(money(d['total'] * d['n']))} = {cm(money(d['per_favor']))} per Favor")
                else:
                    n = r[5].split("x")[0]
                    lines.append(f"FAVOR buy {n}x {short(r[0])} crate + {r[3]} per crate")
            else:
                lines.append(f"BUY {r[0]} at {cm(r[1])}: {r[6]} units listed up to {cm(r[7])}, route needs {r[5]}" if len(r) > 7 else f"BUY {r[0]} at {cm(r[1])} (need {r[5]})")
    return lines[:6]


def send_embeds(fresh, local_now, demo=False, status=None):
    embeds = []
    for kind in ("sell", "gear", "recipe", "new", "flip", "favor", "writ", "gamble", "mat", "snipe"):
        items = sorted([f for f in fresh if f[0] == kind], key=lambda f: -f[2])[:10]
        if not items:
            continue
        title, color, headers, widths, hint = SECTIONS[kind]
        if kind == "favor" and all(len(f[1]) > 6 for f in items):
            body_ = "```\n" + "\n\n".join(favor_card(f[1]) for f in items[:3]) + "\n```"
            embeds.append({"title": f"{title} ({len(items)})", "color": color, "description": hint + "\n" + body_})
            continue
        rows_ = [[str(i + 1)] + cells(kind, f[1])[1:] for i, f in enumerate(items)]
        if kind == "flip":
            headers, widths, rows_ = ["#", "Cost", "NPC", "Profit"], (2, 8, 8, 8), [r_[:4] for r_ in rows_]
        def _det(kind_, r_):
            if kind_ == "flip":
                return f" ({r_[4]})\n    Mats: {r_[5]}"
            if kind_ in ("gear", "new"):
                return f" ({r_[4]}, {r_[6]}): {r_[5]}" if r_[5] else ""
            if kind_ == "recipe":
                return f"\n    {r_[3]}"
            return ""
        listing = "\n".join(f"{i + 1}. **{f[1][0]}**" + _det(kind, f[1]) for i, f in enumerate(items))
        embeds.append({"title": f"{title} ({len(items)})", "color": color,
                       "description": hint + "\n" + listing + "\n" + grid(["#"] + list(headers[1:]), rows_, (2,) + tuple(widths[1:]))})
    names_ = {"flip": "Flips", "sell": "SELL", "favor": "Favor", "mat": "Mats", "snipe": "Snipes", "gear": "Gear", "recipe": "Recipes", "new": "New", "writ": "Rep", "gamble": "Writ gamble"}
    summary = " | ".join(f"{names_[k]} {sum(1 for f in fresh if f[0] == k)}" for k in names_ if any(f[0] == k for f in fresh))
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
            lines.append(f"Favor best: {crate_full(r['crate'])} = {cm(money(r['per_favor']))} per Favor (your buy limit {cm(money(cfg['favor_per_favor_max']))}). "
                         f"How: buy the crate ({cm(money(r['crate_price']))}), buy {r['qty']}x {r['mat']} to fill it (~{cm(money(r['mats']))}), hand it in to Marcy Baker = +{r['favor']} Favor")
        except Exception:  # noqa: BLE001
            pass
    lines += route_lines
    try:   # etkinlik takvimi (kaynak: mein-mmo, gfinity; tarihler degisebilir)
        today = (datetime.datetime.strptime(snap["fetched_at"], "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(hours=3)).date()
        D = datetime.date
        dmf = [(D(2026, 11, 9), D(2026, 11, 16)), (D(2026, 12, 7), D(2026, 12, 14)), (D(2027, 1, 4), D(2027, 1, 11))]
        cur_ = next(((s_, e_) for s_, e_ in dmf if s_ <= today <= e_), None)
        nxt = next((s_ for s_, e_ in dmf if s_ > today), None)
        ev = (f"Darkmoon Faire is on, ends in {(cur_[1] - today).days} days" if cur_ else "Darkmoon Faire is not on") + (f"; next starts in {(nxt - today).days} days" if nxt else "")
        raid = (D(2026, 12, 9) - today).days
        lines.append(f"Events: {ev}. Raids (Barrow Deeps, Hyjal Summit, Onyxia) unlock in {raid} days" if raid > 0 else f"Events: {ev}")
    except Exception:  # noqa: BLE001
        pass
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
    log_alert(snap["fetched_at"], "status", list(status_lines or []))
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
