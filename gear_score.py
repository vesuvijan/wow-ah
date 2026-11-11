#!/usr/bin/env python3
"""Hunter gear planner: tooltip + kaynak (OneForAll) + AH fiyati + Sharpie leveling agirliklari -> slot basina upgrade listesi.
Girdi : data/tooltips_*.json (tooltip_crawl.py), ofa/ofa_sources.json, data/house_123.json (AH), data/char.json (armory), ofa/hunter_weights.json
Cikti : data/gear_plan.json, data/gear_plan.txt
Kullanim: python gear_score.py [--level 46] [--dw]"""
import glob
import html
import json
import os
import re
import sys

LEVEL = int(next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--level"), 46))
PLAN_MAX = int(next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--max"), 60))
W = json.load(open("ofa/hunter_weights.json"))
SRC = json.load(open("ofa/ofa_sources.json"))["items"]
REQ = json.load(open("ofa/req_levels.json"))

SLOT = {"Head": "HEAD", "Neck": "NECK", "Shoulder": "SHOULDER", "Back": "BACK", "Chest": "CHEST", "Wrist": "WRIST", "Hands": "HANDS",
        "Waist": "WAIST", "Legs": "LEGS", "Feet": "FEET", "Finger": "FINGER", "Trinket": "TRINKET", "One-Hand": "1H", "Main Hand": "MH",
        "Off Hand": "OH", "Held In Off-hand": "OH_HELD", "Two-Hand": "2H", "Ranged": "RANGED", "Thrown": "RANGED"}
ARMOR = {"1": "Cloth", "2": "Leather", "3": "Mail", "4": "Plate", "6": "Shield"}
STATMAP = {"Agility": "agi", "Strength": "str", "Stamina": "sta", "Intellect": "int", "Spirit": "spi"}


DPSMODE = os.environ.get("DPS") == "1"
SUFFIX = "_dps" if DPSMODE else ""


def weights(level):
    w = _weights(level)
    if DPSMODE:   # sadece hasar: caster/mana statlarini sifirla
        for k in ("spi", "int", "mp5", "sta", "hp", "hp5", "sp", "nature", "armor"):
            w[k] = 0
    return w


def _weights(level):
    k = W["curve"]
    lo = max([x for x in k if x[0] <= level], key=lambda x: x[0], default=k[0])
    hi = min([x for x in k if x[0] >= level], key=lambda x: x[0], default=k[-1])
    keys = set(lo[1]) | set(hi[1])
    if hi[0] == lo[0]:
        return {a: lo[1].get(a, 0) for a in keys}
    t = (level - lo[0]) / (hi[0] - lo[0])
    return {a: lo[1].get(a, 0) * (1 - t) + hi[1].get(a, 0) * t for a in keys}


def parse(iid, t):
    tip = t["tooltip"]
    plain = html.unescape(re.sub(r"<[^>]+>", "\n", tip.replace("<br>", "\n")))
    lines = [x.strip() for x in plain.split("\n") if x.strip()]
    r = {"id": int(iid), "name": t["name"], "q": t.get("quality"), "stats": {}, "eff": {}}
    m = re.search(r"<!--ilvl-->(\d+)", tip); r["ilvl"] = int(m.group(1)) if m else None
    m = re.search(r"<!--rlvl-->(\d+)", tip); r["req"] = int(m.group(1)) if m else 0
    r["bind"] = "BoP" if "Binds when picked up" in tip else ("BoE" if "Binds when equipped" in tip else ("BoU" if "Binds when used" in tip else ""))
    r["random"] = "Random enchantment" in tip
    for w in SLOT:
        if re.search(rf"(?:<td>|<br>){re.escape(w)}(?:</td>|<br>|<)", tip):
            r["slot"] = SLOT[w]; break
    m = re.search(r"<!--scstart(\d+):(\d+)-->", tip)
    if m:
        r["cls"], r["sub"] = int(m.group(1)), int(m.group(2))
        if r["cls"] == 4:
            r["armor_type"] = ARMOR.get(str(r["sub"]), "")
    for sid, v, n in re.findall(r"<!--stat(\d+)-->\+(\d+) ([A-Za-z ]+)", tip):
        r["stats"][n.strip()] = r["stats"].get(n.strip(), 0) + int(v)
    m = re.search(r"<!--amr-->(\d+)", tip); r["armor"] = int(m.group(1)) if m else 0
    m = re.search(r"<!--dps-->\(([\d.]+) damage per second\)", tip); r["dps"] = float(m.group(1)) if m else 0
    m = re.search(r"<!--spd-->([\d.]+)", tip); r["spd"] = float(m.group(1)) if m else 0
    m = re.search(r"<!--dmg-->(\d+) - (\d+)", tip); r["dmg"] = (int(m.group(1)), int(m.group(2))) if m else None
    sell = re.findall(r'moneygold">(\d+)<|moneysilver">(\d+)<|moneycopper">(\d+)<', tip)
    g = s = c = 0
    for a, b, d in sell:
        g += int(a or 0); s += int(b or 0); c += int(d or 0)
    r["sell"] = g * 10000 + s * 100 + c
    eff = []
    for ln in lines:
        if re.match(r"(Equip|Use|Chance on hit):", ln):
            eff.append(ln)
            e = ln
            m = re.search(r"critical strike with .*? by ([\d.]+)%|critical strike by ([\d.]+)%", e)
            if m: r["eff"]["crit"] = r["eff"].get("crit", 0) + float(m.group(1) or m.group(2))
            m = re.search(r"chance to hit by ([\d.]+)%", e)
            if m: r["eff"]["hit"] = r["eff"].get("hit", 0) + float(m.group(1))
            m = re.search(r"Increases ranged attack power by (\d+)|\+(\d+) ranged Attack Power", e, re.I)
            if m: r["eff"]["rap"] = r["eff"].get("rap", 0) + int(m.group(1) or m.group(2))
            else:
                m = re.search(r"\+(\d+) Attack Power|Increases attack power by (\d+)", e, re.I)
                if m and "Use:" not in e: r["eff"]["ap"] = r["eff"].get("ap", 0) + int(m.group(1) or m.group(2))
            m = re.search(r"Restores (\d+) mana per 5 sec", e)
            if m: r["eff"]["mp5"] = r["eff"].get("mp5", 0) + int(m.group(1))
    r["effects"] = eff
    r["unscored_effects"] = [e for e in eff if not re.search(r"critical strike|chance to hit|Attack Power|attack power|mana per 5 sec", e)]
    return r


def fix_req(r):
    """Tooltip'te level sarti yoksa: wago/Blizzard tablosu -> kaynak (quest/dungeon quest) -> ilvl tahmini."""
    if r["req"]:
        return r["req"]
    v = REQ.get(str(r["id"]))
    if v:
        return v
    lv = [s.get("need") or s.get("qlvl") for s in SRC.get(str(r["id"]), {}).get("src", []) if s["type"] == "dquest"]
    lv = [x for x in lv if x]
    if lv:
        return min(lv)
    il = r.get("ilvl") or 0
    return 60 if il >= 60 else max(0, il - 5)


def valid_source(s):
    """Alliance Hunter icin gecerli mi (karsi taraf / baska sinif quest'lerini ele)."""
    if s.get("side") in ("H",) or s.get("faction") in ("Horde",):
        return False
    c = s.get("cls")
    if c not in (None, "", "0"):
        try:
            if not int(c) & 4:
                return False
        except ValueError:
            pass
    return True


DUNG = json.load(open("ofa/ofa_sources.json")).get("dungeons", {})


def dmin(dn):
    m = re.match(r"(\d+)", str((DUNG.get(dn) or {}).get("level") or ""))
    return int(m.group(1)) if m else 0


def reachable(r, level):
    """Kaynaklardan en az biri su level'da erisilebilir mi (kaynak bilinmiyorsa True)."""
    srcs = [x for x in SRC.get(str(r["id"]), {}).get("src", []) if valid_source(x)]
    if not srcs:
        return True
    for x in srcs:
        t = x["type"]
        if t == "boss" and dmin(x["dungeon"]) <= level + 2:
            return True
        if t == "dquest" and (x.get("need") or 0) <= level and dmin(x["dungeon"]) <= level + 2:
            return True
        if t == "quest" and (x.get("req") or 0) <= level:
            return True
        if t in ("rep", "craft", "set"):
            return True
    return False


def obtainable(r):
    srcs = SRC.get(str(r["id"]), {}).get("src", [])
    return (not srcs) or any(valid_source(s) for s in srcs)


def usable(r):
    if r.get("slot") is None:
        return False
    if r.get("cls") == 4 and r.get("armor_type") in ("Plate", "Shield", "Cloth") and r["slot"] not in ("BACK", "NECK", "FINGER", "TRINKET"):
        return False
    if r.get("cls") == 2 and r.get("sub") not in (0, 1, 4, 5, 6, 7, 8, 10, 13, 15, 2, 3, 18):
        return False       # wand/thrown/misc
    return True


def value(r, w, hand="MH"):
    v = 0.0
    for n, x in r["stats"].items():
        v += w.get(STATMAP.get(n, ""), 0) * x
    for k, x in r["eff"].items():
        v += w.get(k, 0) * x
    v += w.get("armor", 0) * r.get("armor", 0)
    if r.get("dps"):
        if r["slot"] == "RANGED":
            v += w.get("dps", 0) * r["dps"]
        elif hand == "OH":
            v += w.get("dpsoh", w.get("dpsmelee", 0) * 0.5) * r["dps"]
        else:
            v += w.get("dpsmelee", 0) * r["dps"]
    return v


def stat_str(c):
    parts = [f"+{v} {k[:3] if k != 'Stamina' else 'Sta'}" for k, v in c["stats"].items()]
    parts = [f"+{v} {k}" for k, v in c["stats"].items()]
    for k, v in c["eff"].items():
        parts.append({"crit": f"+{v:g}% crit", "hit": f"+{v:g}% hit", "ap": f"+{v} AP", "rap": f"+{v} ranged AP", "mp5": f"+{v} mp5"}.get(k, k))
    if c.get("armor"):
        parts.append(f"{c['armor']} armor")
    if c.get("dps"):
        parts.append(f"{c['dps']:.1f} dps / {c['spd']:.1f}s")
    return ", ".join(parts)


def money(c):
    c = int(round(c)); g, rem = divmod(c, 10000); s, cu = divmod(rem, 100)
    return "".join([f"{g}g" if g else "", f"{s}s" if s else "", f"{cu}c" if cu or not (g or s) else ""])


def src_text(iid, ah):
    out = []
    for s in SRC.get(str(iid), {}).get("src", []):
        t = s["type"]
        if t == "boss":
            ch = f" {s['chance']:g}%" if s.get("chance") is not None else ""
            out.append(f"Drop: {s['boss']} ({s['dungeon']}){ch}")
        elif t == "dquest":
            out.append(f"Dungeon quest: {s['quest']} ({s['dungeon']}, lvl {s.get('qlvl')})")
        elif t == "quest":
            out.append(f"Quest: {s.get('quest')} (lvl {s.get('req')})" + (f" @ {s['giver']}" if s.get("giver") else ""))
        elif t == "rep":
            out.append(f"Rep: {s['faction']} {s['rank']}")
        elif t == "craft":
            out.append(f"Craft: {s['prof']} {s['skill']}")
        elif t == "set":
            out.append(f"Set: {s['set']}")
    seen, res = set(), []
    for o in out:
        if o not in seen:
            seen.add(o); res.append(o)
    if iid in ah:
        res.append(f"AH {money(ah[iid])}")
    return res[:3] or ["unknown source"]


def main():
    tips = {}
    for f in glob.glob("data/tooltips_*.json"):
        tips.update(json.load(open(f)))
    items = {}
    for iid, t in tips.items():
        try:
            items[int(iid)] = parse(iid, t)
            items[int(iid)]["req"] = fix_req(items[int(iid)])
        except Exception as e:  # noqa: BLE001
            print("parse hatasi", iid, e, file=sys.stderr)
    ah = {}
    if os.path.exists("data/house_123.json"):
        snap = json.load(open("data/house_123.json"))
        for k, v in snap["items"].items():
            if v["l"]:
                ah[int(k)] = v["l"][0][0]
    char = json.load(open("data/char.json"))
    w_now = weights(min(LEVEL, 59))
    w_late = weights(min(PLAN_MAX, 59))
    equipped = {}
    for it in char["items"]:
        equipped[it["slot"]] = it
    cands = [r for r in items.values() if usable(r) and (r["q"] or 0) >= 2 and r["req"] <= PLAN_MAX and (r["ilvl"] or 0) <= 70 and obtainable(r) and r["id"] not in (11285, 8)]
    skipped_random = [r for r in cands if r["random"]]
    cands = [r for r in cands if not r["random"]]
    # ekipman degerleri (random suffix'ler tahmini)
    def slotkey(r):
        return {"1H": "WEAPON", "MH": "WEAPON", "OH": "WEAPON", "2H": "2H", "RANGED": "RANGED"}.get(r["slot"], r["slot"])
    eq_val, eq_note = {}, {}
    for sl, it in equipped.items():
        r = items.get(it["id"])
        base_slot = {"FINGER_1": "FINGER", "FINGER_2": "FINGER", "TRINKET_1": "TRINKET", "TRINKET_2": "TRINKET", "MAIN_HAND": None, "OFF_HAND": None}.get(sl, sl)
        if not r or base_slot is None and sl not in ("MAIN_HAND", "RANGED"):
            continue
        if sl in ("MAIN_HAND", "OFF_HAND"):
            continue
        if r["random"] or sl == "BACK" and not r["stats"]:
            near = sorted(value(c, w_now) for c in cands if c["slot"] == (base_slot or sl) and abs((c["ilvl"] or 0) - (r["ilvl"] or 0)) <= 5)
            eq_val[sl] = near[len(near) // 2] if near else 0
            eq_note[sl] = "random-suffix, estimated"
        else:
            eq_val[sl] = value(r, w_now)
            eq_note[sl] = ""
        eq_val[sl] += 0
    eq_ids = {it["id"] for it in equipped.values()}
    total = sum(eq_val.values()) or 1
    lines = [f"Hunter gear plan | level {LEVEL} -> {PLAN_MAX} | weights: Sharpie Gear Judge leveling curve | tooltips {len(items)} | candidates {len(cands)}", ""]
    plan = {}
    SLOTS = [("HEAD", "HEAD"), ("NECK", "NECK"), ("SHOULDER", "SHOULDER"), ("BACK", "BACK"), ("CHEST", "CHEST"), ("WRIST", "WRIST"),
             ("HANDS", "HANDS"), ("WAIST", "WAIST"), ("LEGS", "LEGS"), ("FEET", "FEET"), ("FINGER_1", "FINGER"), ("TRINKET_1", "TRINKET")]
    for esl, cs in SLOTS:
        cur = eq_val.get(esl, 0)
        it = equipped.get(esl, {})
        pool = [c for c in cands if c["slot"] == cs and c["id"] not in eq_ids]
        now = sorted([c for c in pool if c["req"] <= LEVEL and reachable(c, LEVEL)], key=lambda c: -value(c, w_now))[:8]
        later = sorted([c for c in pool if LEVEL < c["req"] <= PLAN_MAX], key=lambda c: -value(c, w_late))[:8]
        lines.append(f"== {cs}: now {it.get('name','-')} (ilvl {it.get('ilvl','-')}) value {cur:.0f}{' ['+eq_note.get(esl,'')+']' if eq_note.get(esl) else ''}")
        rows = []
        for tag, grp, w in (("NOW", now, w_now), ("LVL" , later, w_late)):
            for c in grp:
                v = value(c, w)
                gain = 100 * (v - cur) / total
                rows.append({"tag": tag, "id": c["id"], "name": c["name"], "req": c["req"], "ilvl": c["ilvl"], "bind": c["bind"], "gain_pct": round(gain, 1),
                             "value": round(v, 1), "src": src_text(c["id"], ah), "extra": c["unscored_effects"][:2], "q": c["q"], "stats": stat_str(c), "atype": c.get("armor_type", "")})
                lines.append(f"  {tag} {c['name'][:30]:<30} req{c['req']:>3} ilvl{c['ilvl']:>3} {c['bind']:<3} {gain:+5.1f}%  {' | '.join(rows[-1]['src'])}" + (f"  [+effect not scored: {'; '.join(c['unscored_effects'][:1])[:70]}]" if c["unscored_effects"] else ""))
        plan[cs] = {"equipped": it.get("name"), "value": round(cur, 1), "options": rows}
        lines.append("")
    # silahlar
    lines.append("== WEAPONS (dual wield)")
    mh_pool = [c for c in cands if c["slot"] in ("1H", "MH") and c.get("cls") == 2 and c["req"] <= PLAN_MAX]
    oh_pool = [c for c in cands if c["slot"] in ("1H", "OH") and c.get("cls") == 2 and c["req"] <= PLAN_MAX]
    def best_pairs(lvl):
        mh = sorted([c for c in mh_pool if c["req"] <= lvl and (lvl > LEVEL or reachable(c, LEVEL))], key=lambda c: -value(c, w_now, "MH"))[:25]
        oh = sorted([c for c in oh_pool if c["req"] <= lvl and (lvl > LEVEL or reachable(c, LEVEL))], key=lambda c: -value(c, w_now, "OH"))[:25]
        pairs = []
        for a in mh:
            for b in oh:
                if a["id"] == b["id"]:
                    continue
                pairs.append((value(a, w_now, "MH") + value(b, w_now, "OH"), a, b))
        return sorted(pairs, key=lambda x: -x[0])[:6]
    def wi(c):
        return {"id": c["id"], "name": c["name"], "q": c["q"], "req": c["req"], "dps": c["dps"], "spd": c["spd"], "bind": c["bind"], "src": src_text(c["id"], ah), "stats": stat_str(c)}
    wq = {}
    for tag, lvl in (("NOW", LEVEL), ("LVL", PLAN_MAX)):
        for v, a, b in best_pairs(lvl)[:5]:
            lines.append(f"  {tag} MH {a['name'][:24]} ({a['dps']:.1f} dps, {a['spd']:.1f}s, req{a['req']}: {src_text(a['id'], ah)[0]})")
            lines.append(f"      OH {b['name'][:24]} ({b['dps']:.1f} dps, {b['spd']:.1f}s, req{b['req']}: {src_text(b['id'], ah)[0]})  value {v:.0f}")
            wq.setdefault(tag, []).append({"value": round(v, 1), "mh": wi(a), "oh": wi(b)})
    two = sorted([c for c in cands if c["slot"] == "2H"], key=lambda c: -value(c, w_now, "MH"))[:3]
    lines.append("  2H reference (you chose dual wield): " + "; ".join(f"{c['name']} ({c['dps']:.1f} dps, req{c['req']})" for c in two))
    rg = sorted([c for c in cands if c["slot"] == "RANGED" and c["req"] <= PLAN_MAX], key=lambda c: -value(c, w_now))[:6]
    cur_r = equipped.get("RANGED", {})
    lines.append(f"== RANGED now: {cur_r.get('name','-')}")
    for c in rg:
        lines.append(f"  {c['name'][:28]:<28} req{c['req']:>3} {c['dps']:.1f} dps {c['bind']} | {' | '.join(src_text(c['id'], ah))}")
    plan["weapons"] = wq
    plan["ranged"] = [{"id": c["id"], "name": c["name"], "q": c["q"], "req": c["req"], "dps": c["dps"], "spd": c["spd"], "bind": c["bind"], "src": src_text(c["id"], ah), "stats": stat_str(c)} for c in rg]
    plan["equipped"] = [{"slot": k, "name": v["name"], "ilvl": v["ilvl"], "q": v["quality"], "id": v["id"], "enchant": v.get("enchant")} for k, v in equipped.items()]
    plan["meta"] = {"level": LEVEL, "plan_max": PLAN_MAX, "tooltips": len(items), "candidates": len(cands), "skipped_random": len(skipped_random)}
    lines.append("")
    lines.append(f"Skipped (random suffix, stats unknown until you see the item): {len(skipped_random)} items")
    open(f"data/gear_plan{SUFFIX}.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump(plan, open(f"data/gear_plan{SUFFIX}.json", "w"), indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
