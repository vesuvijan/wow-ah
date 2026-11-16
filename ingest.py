"""Ingest in-game data (AH Desk + Syndicator SavedVariables) into the repo.
Usage: python3 ingest.py <SavedVariables dir>
Updates: plans/gear_plan_dps.json (equipped gear + level), holdings.json (stock), data/char_live.json (stats, professions, talents, money)."""
import json, re, sys, warnings, os
warnings.filterwarnings("ignore")
from slpp import slpp as lua

D = sys.argv[1]
MAIN = "Docker"


def load(name, var):
    s = open(os.path.join(D, name), encoding="utf8").read()
    i = s.index(var + " = ") + len(var) + 3
    j = s.find("\n" + var.split("_")[0] + "_", i)
    return lua.decode(s[i:j if j > 0 else None])


ahd = load("AHDesk.lua", "AHDeskDB")
main = None
for k, v in ahd["chars"].items():
    if k.startswith(MAIN) and v.get("gear"):
        main = v
if not main:
    sys.exit("main character not found in AHDesk.lua")

# 1) equipped gear -> plan
plan = json.load(open("plans/gear_plan_dps.json"))
old = {e["slot"]: e for e in plan["equipped"]}
eq = []
for slot, g in main["gear"].items():
    if slot == "TABARD":
        continue
    prev = old.get(slot, {})
    eq.append({"slot": slot, "name": g["n"], "id": g["id"], "ilvl": prev.get("ilvl") if prev.get("id") == g["id"] else None,
               "q": prev.get("q") if prev.get("id") == g["id"] else None, "enchant": None})
if "AMMO" in old:
    eq.append(old["AMMO"])
changed = sorted(s for s in {e["slot"] for e in eq} if old.get(s, {}).get("id") != next(e["id"] for e in eq if e["slot"] == s))
plan["equipped"] = eq
plan["meta"]["level"] = main.get("level", plan["meta"].get("level"))
json.dump(plan, open("plans/gear_plan_dps.json", "w"), ensure_ascii=False, indent=1)
print("gear slots changed:", changed)

# 2) holdings from Syndicator (RP-PvP realm characters only)
syn = load("Syndicator.lua", "SYNDICATOR_DATA")["Characters"]
names, tot = {}, {}


def walk(x):
    if isinstance(x, dict):
        if "itemID" in x:
            m = re.search(r"\[(.*?)\]", x.get("itemLink", ""))
            names[x["itemID"]] = m.group(1) if m else str(x["itemID"])
            tot[x["itemID"]] = tot.get(x["itemID"], 0) + x.get("itemCount", 1)
        else:
            for v in x.values():
                walk(v)
    elif isinstance(x, list):
        for v in x:
            walk(v)


for c, v in syn.items():
    if not c.endswith("-RPPvP"):
        continue
    for part in ("bags", "bank", "bankTabs", "mail", "auctions"):
        walk(v.get(part))
src = open("alerts.py").read()
inv = {int(x) for x in re.findall(r"\d+", re.search(r"INVEST\s*=\s*\{(.*?)\}", src, re.S).group(1))}
keep = inv | {7912, 12365, 2838, 4306}
hold = {names[i]: n for i, n in tot.items() if i in keep}
json.dump(hold, open("holdings.json", "w"), indent=1, ensure_ascii=False)
print("holdings:", len(hold))

# 3) live character snapshot for the dashboard
live = {"at": ahd.get("lastAt"), "name": "Docker Tuckalot", "level": main.get("level"), "class": main.get("class"), "money": main.get("money"),
        "stats": main.get("stats"), "professions": main.get("professions"), "talents": (main.get("specs") or {}).get("talents"),
        "reps": main.get("reps"), "gear": {k: g["n"] for k, g in main["gear"].items()}}
os.makedirs("data", exist_ok=True)
json.dump(live, open("data/char_live.json", "w"), ensure_ascii=False, indent=1)
