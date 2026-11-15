"""Builds the AH Desk addon inbox (Inbox.lua) from the dashboard data: recent alerts as messages, plus a price table for tooltips.
Extra hand-written messages come from addon_messages.json ([{"id","t","text"}])."""
import json, os, sys, time, zlib
from datetime import datetime, timezone

SITE = "site/data"
IMPORTANT = ("sell", "gear", "snipe", "dip", "favor")


def lua_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ").replace("|", "||") + '"'


def lot_price(it):
    lv = it.get("lv") or []
    lot = max(20, min(200, round((it.get("qty") or 0) * 0.05)))
    got = tot = 0
    for p, q in lv:
        t = min(q, lot - got)
        got += t
        tot += p * t
        if got >= lot:
            return tot / got
    return None


def build(out_path):
    now = json.load(open(f"{SITE}/now.json"))["items"]
    feed = json.load(open(f"{SITE}/feed.json"))["items"]
    meta = json.load(open(f"{SITE}/meta.json"))
    invest = {str(i) for i in meta.get("invest", [])}
    cutoff = time.time() - 12 * 3600
    msgs, seen = [], set()
    for a in feed:
        ts = datetime.fromisoformat(a["ts"].replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()
        if a["k"] not in IMPORTANT or ts < cutoff:
            continue
        key = a["k"] + "|" + (a.get("item") or "")
        if key in seen:
            continue
        seen.add(key)
        msgs.append({"id": f"a{int(ts)}{zlib.crc32(key.encode()) % 100000}", "t": int(ts), "k": "alert", "text": a["t"]})
    msgs = msgs[:25]
    if os.path.exists("addon_messages.json"):
        for m in json.load(open("addon_messages.json")):
            msgs.append({"id": m["id"], "t": int(m["t"]), "k": "chat", "text": m["text"]})
    msgs.sort(key=lambda m: m["t"])
    lines = ["-- generated; do not edit", "AHDeskInbox = {", f"  built = {int(time.time())},", f'  scan = {lua_str(meta.get("fetched", ""))},', "  messages = {"]
    for m in msgs:
        lines.append(f'    {{ id = {lua_str(m["id"])}, t = {m["t"]}, k = {lua_str(m["k"])}, text = {lua_str(m["text"])} }},')
    lines.append("  },")
    lines.append("  prices = {")
    for iid, it in now.items():
        if it.get("min") is None:
            continue
        m7 = it.get("m7") or 0
        sig = ""
        if iid in invest and m7:
            lp = lot_price(it)
            lo, hi = it.get("lo30"), it.get("hi30")
            pos = (it["min"] - lo) / (hi - lo) if lo is not None and hi and hi > lo else 0.5
            if lp and lp <= m7 * 0.8 and pos <= 0.25:
                sig = "B"
            elif lp and lp >= m7 * 1.15 and pos >= 0.6:
                sig = "S"
        lines.append(f'    [{int(iid)}] = {{ {int(it["min"])}, {int(m7)}, "{sig}" }},')
    lines += ["  },", "}", ""]
    open(out_path, "w", encoding="utf-8").write("\n".join(lines))
    return len(msgs)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "site/data/Inbox.lua"
    print("inbox messages:", build(out))
