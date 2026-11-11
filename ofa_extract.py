#!/usr/bin/env python3
"""OneForAll (github.com/smoergi/OneForAll_Forever, GPL-3) Lua veri dosyalarindan item kaynaklarini cikarir.
Kullanim: python ofa_extract.py <OneForAll/Data dizini> -> ofa/ofa_sources.json
Cikti: {"items": {item_id: {"name":..,"slot":..,"q":.., "src":[{...}]}}, "dungeons": {...}}
src turleri: boss (dungeon, boss, chance), dquest (dungeon, quest, lvl, choice), quest (quest ids, req lvl), set (set, group),
rep (faction, rank, vendors), craft (profession, skill, recipe)"""
import glob
import json
import os
import re
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "OneForAll/Data"
items = {}
dungeons = {}


def add(iid, name=None, slot=None, q=None, **src):
    e = items.setdefault(str(iid), {"src": []})
    if name and not e.get("name"):
        e["name"] = name
    if slot and not e.get("slot"):
        e["slot"] = slot
    if q is not None and e.get("q") is None:
        e["q"] = q
    if src:
        e["src"].append(src)


# ---- 1) dungeon dosyalari (boss loot + dungeon quest odulleri)
chance = {}
txt = open(f"{D}/DungeonDropChance.lua", encoding="utf-8").read()
cur_d = cur_b = None
for line in txt.splitlines():
    m = re.match(r'^  \["([^"]+)"\] = \{\s*$', line)
    if m:
        cur_d = m.group(1)
        continue
    m = re.match(r'^    \["([^"]+)"\] = \{(.*)\},?\s*$', line)
    if m and cur_d:
        for iid, ch in re.findall(r"\[(\d+)\]=([\d.]+)", m.group(2)):
            chance[(cur_d, m.group(1), int(iid))] = float(ch)

for f in sorted(glob.glob(f"{D}/Dungeons/*.lua")):
    t = open(f, encoding="utf-8").read()
    m = re.search(r'DUNGEON_REGISTRY\["([^"]+)"\]\s*=\s*\{', t)
    if not m:
        continue
    dn = m.group(1)
    lv = re.search(r'\blevel\s*=\s*"([^"]+)"', t)
    dungeons[dn] = {"level": lv.group(1) if lv else None}
    mode, boss, quest = None, None, None
    for line in t.splitlines():
        if re.match(r"^    quests = \{", line):
            mode = "q"
        elif re.match(r"^    bosses = \{", line):
            mode = "b"
        elif re.match(r"^    \w+ = ", line) and not re.match(r"^    (quests|bosses) = ", line):
            mode = None
        if mode == "q":
            m = re.match(r'^            name = "([^"]+)"', line)
            if m:
                quest = {"name": m.group(1)}
            for k in ("level", "requires"):
                m = re.match(rf"^            {k} = (\d+)", line)
                if m and quest is not None:
                    quest[k] = int(m.group(1))
            m = re.match(r'^            faction = "(\w+)"', line)
            if m and quest is not None:
                quest["faction"] = m.group(1)
            if "rewardItems = {" in line and quest is not None:
                choice = None
                for iid, nm, q in re.findall(r'\{(\d+),\s*"([^"]+)",\s*(\d)\}', line):
                    add(iid, nm, None, int(q), type="dquest", dungeon=dn, quest=quest["name"], qlvl=quest.get("level"),
                        need=quest.get("requires"), faction=quest.get("faction"))
        elif mode == "b":
            m = re.match(r'^            name = "([^"]+)"', line)
            if m:
                boss = m.group(1)
            for iid, nm, slot, q in re.findall(r'\{(\d+),\s*"([^"]+)",\s*"([^"]*)",\s*(\d)\}', line):
                add(iid, nm, slot, int(q), type="boss", dungeon=dn, boss=boss, chance=chance.get((dn, boss, int(iid))))

# ---- 2) genel quest odulleri
t = open(f"{D}/QuestRewards.lua", encoding="utf-8").read()
mi = re.search(r"items = \[\[(.*?)\]\]", t, re.S)
mq = re.search(r"quests = \{(.*?)\n  \}", t, re.S)
qinfo = {}
if mq:
    for qid, body in re.findall(r'\[(\d+)\]\s*=\s*"([^"]*)"', mq.group(1)):
        p = body.split("|")
        if len(p) >= 9:
            qinfo[int(qid)] = {"name": p[0], "lvl": p[1], "req": p[2], "side": p[3], "cls": p[4], "giver": p[7], "map": p[8]}
for line in (mi.group(1).strip().splitlines() if mi else []):
    p = line.split(",", 3)
    if len(p) == 4 and p[0].isdigit():
        qids = [int(x) for x in p[2].split("/") if x.isdigit()]
        qi = qinfo.get(qids[0], {}) if qids else {}
        add(p[0], p[3], None, None, type="quest", quest=qi.get("name"), qid=qids[:3], req=int(p[1] or 0), side=qi.get("side"),
            cls=qi.get("cls"), giver=qi.get("giver"))

# ---- 3) Armory: setler + reputation
a = open(f"{D}/Armory.lua", encoding="utf-8").read()
for body in re.findall(r"^  \{id=\d+, n=\"[^\"]*\".*$", a, re.M):
    pass
sets_part = a.split("FLT.ARMORY_REPUTATION")[0]
for line in sets_part.splitlines():
    m = re.match(r'^\s*\{id=(\d+), n="([^"]*)"(?:, g="(\w+)")?(?:, sub="([^"]*)")?', line)
    if not m:
        continue
    for iid, nm, slot, q in re.findall(r'\{(\d+),"([^"]+)","([^"]*)",(\d)', line):
        add(iid, nm, slot, int(q), type="set", set=m.group(2), group=m.group(3))
rep_part = a.split("FLT.ARMORY_REPUTATION")[1] if "FLT.ARMORY_REPUTATION" in a else ""
RANK = {"4": "Friendly", "5": "Honored", "6": "Revered", "7": "Exalted"}
for line in rep_part.splitlines():
    m = re.match(r'^\s*\{id=(\d+), n="([^"]*)"', line)
    if not m:
        continue
    side = re.search(r'side="(\w)"', line)
    for iid, nm, slot, q, rank, kind in re.findall(r'\{(\d+),"([^"]+)",(?:"([^"]*)"|nil),(\d),(?:"[^"]*"|\d+),(\d),"(\w+)"', line):
        if kind == "gear":
            add(iid, nm, slot, int(q), type="rep", faction=m.group(2), rank=RANK.get(rank, rank), side=side.group(1) if side else None)

# ---- 4) Meslekler (craft)
for f in glob.glob(f"{D}/Professions/*.lua"):
    prof = os.path.basename(f)[:-4]
    if prof in ("BossDrops",):
        continue
    for line in open(f, encoding="utf-8"):
        m = re.match(r'^\s*\{s=\d+, i=(\d+), n="([^"]*)", q=\d+(?:, lv=(\d+))?.*?req=(\d+|nil)', line)
        if m and m.group(4) != "nil":
            reag = [(int(a_), int(b_)) for a_, b_ in re.findall(r"\{(\d+),(\d+),\"", line)]
            add(m.group(1), m.group(2), None, None, type="craft", prof=prof, skill=int(m.group(4)), lv=int(m.group(3)) if m.group(3) else None, reagents=reag)

os.makedirs("ofa", exist_ok=True)
json.dump({"items": items, "dungeons": dungeons}, open("ofa/ofa_sources.json", "w"), separators=(",", ":"))
from collections import Counter
c = Counter(s["type"] for e in items.values() for s in e["src"])
print(len(items), "items;", dict(c), "dungeons", len(dungeons))
