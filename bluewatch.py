#!/usr/bin/env python3
"""WoW Forever blue post / hotfix izleyici: yeni bir Forever duyurusu cikinca telefona (ntfy) ve Discord'a anlik gonderir.
Kaynaklar: (1) news.blizzard.com WoW haber sayfasi (resmi, en hizli), (2) Warcraft Tavern blue tracker RSS (forum blue postlari + hotfix).
Durum: data/blue_seen.json (snapshot dalinda). Ilk calismada mevcut her seyi sessizce 'gorulmus' sayar.
Ortam: NTFY_TOPIC, DISCORD_WEBHOOK_URL (ikisi de opsiyonel), BLUE_FORCE=1 (son N postu tekrar yolla, test)."""
import html
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

STATE = "data/blue_seen.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
KEY = re.compile(r"forever|hotfix", re.I)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def from_news():
    """news.blizzard.com: /en-us/article/<id>/<slug> baglantilari; slug'da forever veya hotfix gecenler."""
    out, seen = [], set()
    try:
        page = get("https://news.blizzard.com/en-us/world-of-warcraft")
    except Exception as e:  # noqa: BLE001
        print("news.blizzard.com okunamadi:", e)
        return out
    for m in re.finditer(r'href="(/en-us/article/(\d+)/([^"#?]+))"', page):
        path, aid, slug = m.groups()
        if aid in seen or not KEY.search(slug):
            continue
        seen.add(aid)
        out.append({"id": "blog-" + aid, "title": slug.replace("-", " ").title(),
                    "link": "https://news.blizzard.com" + path, "desc": "", "ts": None, "src": "Blizzard News"})
    return out


def from_tavern():
    out = []
    try:
        xml = get("https://blue-tracker.warcrafttavern.com/rss/all")
    except Exception as e:  # noqa: BLE001
        print("blue tracker okunamadi:", e)
        return out
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        g = lambda k: (re.search(rf"<{k}[^>]*>(.*?)</{k}>", it, re.S) or [0, ""])[1]
        title, link, guid, cat = clean(g("title")), clean(g("link")), clean(g("guid")), clean(g("category"))
        if "/blue-tracker/forever/" not in link and not KEY.search(title):
            continue
        try:
            ts = parsedate_to_datetime(g("pubDate")).astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            ts = None
        out.append({"id": guid, "title": title, "link": link, "desc": clean(g("description")), "ts": ts,
                    "src": "Blue post (" + (cat or "?").upper() + ")", "region": cat})
    return out


def tkey(t):
    return "".join(sorted(re.sub(r"[^a-z0-9]", "", t.lower())))


def dedupe(items):
    """Ayni duyuru birden cok kaynakta/bolgede gelir: ayni blog id'si, ya da US kopyasi icin EU zaten varsa atla."""
    best, eu = {}, [i for i in items if i.get("region") == "eu"]
    for i in items:
        if i.get("region") == "us" and any(
            e["ts"] and i["ts"] and abs((e["ts"] - i["ts"]).total_seconds()) < 7200
            and e["title"].lower().split()[:3] == i["title"].lower().split()[:3] for e in eu):
            continue
        best.setdefault(i["id"], i)
    # blog-<id> ile forum kopyasi ayni yazi: basliga gore tekille (tarih bicimi farkina dayanikli)
    seen_titles, out = set(), []
    for i in best.values():
        k = tkey(i["title"])
        if k in seen_titles:
            continue
        seen_titles.add(k)
        out.append(i)
    return out


def describe(i):
    if i["desc"] or not i["link"].startswith("https://news.blizzard.com"):
        return
    try:
        m = re.search(r'<meta[^>]+(?:property="og:description"|name="description")[^>]+content="([^"]*)"', get(i["link"]))
        i["desc"] = clean(m.group(1)) if m else ""
    except Exception as e:  # noqa: BLE001
        print("aciklama okunamadi:", e)


def send(i):
    describe(i)
    title = ("WoW Forever: " + i["title"])[:110]
    body = (i["desc"][:350] + (" ..." if len(i["desc"]) > 350 else "")) if i["desc"] else "Yeni resmi Blizzard duyurusu."
    body += f"\n{i['link']}"
    topic, hook = os.environ.get("NTFY_TOPIC"), os.environ.get("DISCORD_WEBHOOK_URL")
    print("YENI:", title, i["link"])
    if topic:
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                headers={"Title": title.encode("ascii", "ignore").decode(), "Tags": "mega", "Priority": "high",
                         "Click": i["link"], "User-Agent": "wow-ah-bot/1.0"}), timeout=30).read()
        except Exception as e:  # noqa: BLE001
            print("ntfy hata:", e)
    if hook:
        try:
            urllib.request.urlopen(urllib.request.Request(
                hook, data=json.dumps({"content": f"**{title}**\n{body}"[:1900]}).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "wow-ah-bot/1.0"}), timeout=30).read()
        except Exception as e:  # noqa: BLE001
            print("Discord hata:", e)


def main():
    items = dedupe(from_news() + from_tavern())
    try:
        state = json.load(open(STATE))
    except Exception:  # noqa: BLE001
        state = None
    done = set(state["seen"]) if state else set()
    keys = set(state.get("keys", [])) if state else set()
    fresh = [i for i in items if i["id"] not in done and tkey(i["title"]) not in keys]
    if state is None:
        print(f"ilk calisma: {len(items)} mevcut post sessizce kaydedildi")
        fresh = []
    if os.environ.get("BLUE_FORCE"):
        fresh = items[:2]
    for i in sorted(fresh, key=lambda x: x["ts"] or datetime.now(timezone.utc)):
        send(i)
    seen = sorted(done | {i["id"] for i in items})[-400:]
    os.makedirs("data", exist_ok=True)
    allkeys = sorted(keys | {tkey(i["title"]) for i in items})[-400:]
    json.dump({"seen": seen, "keys": allkeys, "at": datetime.now(timezone.utc).isoformat()}, open(STATE, "w"))
    print(f"kontrol: {len(items)} forever/hotfix post, {len(fresh)} yeni")


if __name__ == "__main__":
    main()
