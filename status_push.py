#!/usr/bin/env python3
"""Gunde iki kez (09:00 ve 21:00 Istanbul) telefona kisa durum ozeti (ntfy). site_build.py'den sonra calisir.
Durum: data/status_sent.json (ayni slot iki kez gonderilmez). FORCE_STATUS=1 ile hemen gonderir."""
import datetime
import json
import os
import urllib.request

SLOTS = (9, 21)
topic, site = os.environ.get("NTFY_TOPIC"), os.environ.get("SITE_URL", "")
if not topic:
    raise SystemExit(0)
now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
slot = max((h for h in SLOTS if now.hour >= h), default=None)
key = f"{now:%Y-%m-%d}-{slot}"
try:
    sent = json.load(open("data/status_sent.json"))
except Exception:  # noqa: BLE001
    sent = {}
if not os.environ.get("FORCE_STATUS") and (slot is None or sent.get("last") == key):
    raise SystemExit(0)

L = lambda p: json.load(open(f"site/data/{p}", encoding="utf-8"))  # noqa: E731
now_d, bank, feed, hist = L("now.json")["items"], L("bank.json"), L("feed.json"), L("hist.json")


def money(c):
    if c is None:
        return "-"
    c = int(round(c))
    g, s, k = c // 10000, c // 100 % 100, c % 100
    return f"{g}g{s:02d}s" if g else (f"{s}s{k:02d}c" if s else f"{k}c")


def price_ago(iid, hours):
    pts = hist.get(str(iid), [])
    if not pts:
        return None
    target = pts[-1][0] - hours
    old = [p for h, p in pts if h <= target]
    return old[-1] if old else None


tot = tot24 = 0
for b in bank:
    if b.get("min"):
        tot += b["min"] * b["cnt"]
        tot24 += (price_ago(b["id"], 24) or b["min"]) * b["cnt"]
lines = [f"Bank: {money(tot)} ({'+' if tot >= tot24 else '-'}{money(abs(tot - tot24))} in 24h)"]


def live(kind, sign, limit=3):
    seen, out = set(), []
    for a in feed["items"]:
        if a["k"] != kind or not a.get("id") or a["id"] in seen:
            continue
        seen.add(a["id"])
        it = now_d.get(a["id"])
        if not it or not it.get("m7"):
            continue
        p = round(100 * it["min"] / it["m7"] - 100)
        if (sign > 0 and p >= 10) or (sign < 0 and p <= -10):
            held = next((b["cnt"] for b in bank if b["id"] == a["id"]), 0)
            out.append((abs(p), f"{it['n']} {money(it['min'])} ({p:+d}%{', you hold ' + str(held) if held else ''})"))
    return [t for _, t in sorted(out, reverse=True)[:limit]]


s = live("sell", 1)
if s:
    lines.append("SELL: " + "; ".join(s))
b = live("dip", -1)
if b:
    lines.append("CHEAP: " + "; ".join(b))
for l in feed.get("status", []):
    if l.startswith("Favor best:"):
        lines.append(l.split(". How:")[0].replace("Waylaid Crate: ", ""))
    if l.startswith("Events:"):
        lines.append(l)
title = f"AH status {now:%H:%M} - bank {money(tot)}"
hdr = {"Title": title, "Tags": "bar_chart", "Priority": "low", "User-Agent": "wow-ah-bot/1.0"}
if site:
    hdr["Click"] = site
urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", data="\n".join(lines).encode(), headers=hdr), timeout=30).read()
sent["last"] = key
json.dump(sent, open("data/status_sent.json", "w"))
print("durum gonderildi:", title)
print("\n".join(lines))
