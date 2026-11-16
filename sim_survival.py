#!/usr/bin/env python3
"""Survival Hunter DPS modeli (Forever, level ~56). Beklenen-deger zaman cizelgesi (rastgelelik yok -> karsilastirmalar gurultusuz).
Girdi: data/char_live.json (AH Desk) + silah tooltip'leri. Calistir: python3 sim_survival.py
UYARI: Forever'a ozel formuller yayinlanmadi; sabitler ASSUMP sozlugunde, duyarlilik testiyle gosterilir."""
import json, copy

# ---------------- varsayimlar (Classic 1.12 rank degerleri + Forever tasarim notlari) ----------------
ASSUMP = dict(
    fight=180.0,
    armor_red=0.30,        # hedef zirh azaltma (lvl 58-60 elite)
    miss_base=0.09,        # +3 level hedefe miss (beyaz/ozel) ; hit ile azalir
    dw_extra_miss=0.19,    # dual wield beyaz vurus cezasi (ozel yetenekler etkilenmez)
    dodge=0.065,           # hedef dodge (Mongoose Bite tetikler)
    crit_mult=2.0,
    pred_edge_melee_crit=0.10,   # Predator's Edge 5/5 (melee crit hasar bonusu) - tahmin
    pred_edge_oh=0.20,           # dual wield OH hasar artisi (Predator's Edge) - tahmin
    savage=1.04,           # Savage Strikes 2/2 : tum melee +%4 (Blizzard)
    melee_uptime=0.30,     # savasin kacinda melee menzilindeyiz (beyaz melee vuruslari)
    arcane_base=200, arcane_ap=0.15, arcane_cd=6.0,       # Arcane Shot R7 (52)
    multi_base=120, multi_cd=10.0,                         # Multi-Shot R4 (52): silah dmg + 120
    serp_total=210, serp_dur=15.0,                          # Serpent Sting (DoT, AP'siz)
    raptor_flat=140, raptor_cd=6.0,                         # Raptor Strike (R7) : silah + flat
    mb_flat=115, mb_ap=0.0,                                 # Mongoose Bite R4
    strider_cd=10.0, strider_wpn=1.0,                       # Strider Kick: 1x silah hasari
    aimed_use=False,
    ranged_range_bonus=1.0,
)

def agi_to_crit(level=56): return 1/50.0  # %/agi (Hunter ~ 53 @60)

def base_character():
    c = json.load(open("data/char_live.json"))["stats"]
    return dict(ap=c["ap"], rap=c["rap"], agi=c["agi"], str=c["str"], crit=c["crit"], hit=c["hit"],
                rmin=c["rmin"], rmax=c["rmax"], rspeed=c["rspeed"])

# silah: avg taban hasar (AP'siz), hiz, stat bonuslari
W = {
 "Thrash Blade":   dict(min=66,max=124,spd=2.70,ap=0,agi=0,str=0,crit=0,hit=0,proc_extra=True,hand="1h"),
 "Dustwallow Dirk":dict(min=43,max=81, spd=1.70,ap=0,agi=6,str=0,crit=0,hit=0,hand="oh"),
 "Frenzied Striker":dict(min=108,max=162,spd=2.80,ap=0,agi=0,str=0,crit=0,hit=2,hand="2h"),
 "Hunting Spear":  dict(min=111,max=168,spd=3.10,ap=0,agi=0,str=0,crit=1,hit=0,hand="2h"),
 "Lord Alexander's Battle Axe":dict(min=123,max=185,spd=3.20,ap=0,agi=17,str=16,crit=0,hit=0,hand="2h"),
 "Peacemaker":     dict(min=137,max=206,spd=3.40,ap=56,agi=0,str=0,crit=1,hit=0,hand="2h"),
 "Dreadforge Retaliator":dict(min=149,max=225,spd=3.70,ap=42,agi=0,str=0,crit=1,hit=0,hand="2h"),
 "Barbarous Blade":dict(min=0,max=0,spd=3.20,ap=50,agi=0,str=0,crit=1,hit=0,hand="2h"),
}

def derive(weapons, stats_delta=None, A=ASSUMP):
    """weapons: ('2h',name) veya ('dw',mh,oh). Mevcut dengeden (Thrash+Dirk takili) silah katkisini cikarip yenisini ekler."""
    B = base_character()
    cur = [W["Thrash Blade"], W["Dustwallow Dirk"]]
    ap = B["ap"] - sum(w["ap"] for w in cur); agi = B["agi"] - sum(w["agi"] for w in cur)
    st = B["str"] - sum(w["str"] for w in cur)
    crit = B["crit"] - sum(w["crit"] for w in cur) - 0
    hit = B["hit"] - sum(w["hit"] for w in cur)
    new = [W[n] for n in weapons[1:]]
    ap += sum(w["ap"] for w in new); agi += sum(w["agi"] for w in new); st += sum(w["str"] for w in new)
    crit += sum(w["crit"] for w in new); hit += sum(w["hit"] for w in new)
    # Agility -> crit/AP geri hesaba gerek yok: B zaten agi icerir. Agi delta'sini crit/AP'ye cevir
    dagi = agi - (B["agi"] - sum(w["agi"] for w in cur)) - 0
    crit_pct = crit + (agi - B["agi"]) * agi_to_crit()
    ap_tot = ap + (agi - B["agi"])      # 1 agi = 1 AP (melee)
    rap_tot = B["rap"] - (B["ap"] - ap_tot) * 0 + (ap_tot - B["ap"])  # rap ayni farki alir
    if stats_delta:
        ap_tot += stats_delta.get("ap", 0); rap_tot += stats_delta.get("ap", 0)
        crit_pct += stats_delta.get("crit", 0) + stats_delta.get("agi", 0) * agi_to_crit()
        ap_tot += stats_delta.get("agi", 0); rap_tot += stats_delta.get("agi", 0)
        hit += stats_delta.get("hit", 0)
    return dict(ap=ap_tot, rap=rap_tot, crit=crit_pct, hit=hit, weapons=new, kind=weapons[0], B=B)

def run(weapons, stats_delta=None, A=None):
    A = A or ASSUMP
    c = derive(weapons, stats_delta, A)
    T = A["fight"]; dmg = {}
    def add(k, v): dmg[k] = dmg.get(k, 0) + v
    arm = 1 - A["armor_red"]
    miss_r = max(0.0, A["miss_base"] - c["hit"]/100)            # ranged miss
    miss_m = max(0.0, A["miss_base"] - c["hit"]/100)            # melee ozel
    miss_w = max(0.0, A["miss_base"] + (A["dw_extra_miss"] if c["kind"]=="dw" else 0) - c["hit"]/100)
    cr = c["crit"]/100.0
    cm = A["crit_mult"]
    cm_melee = cm + A["pred_edge_melee_crit"]
    ex = lambda base, crit, mult, miss: base*(1-miss)*(1+crit*(mult-1))
    # ----- ranged: paper doll ortalama + degisen RAP
    B = c["B"]
    rav = (B["rmin"]+B["rmax"])/2 - (B["rap"]*B["rspeed"]/14.0) + c["rap"]*B["rspeed"]/14.0
    auto_n = T / B["rspeed"]
    add("Auto Shot", auto_n * ex(rav*arm, cr, cm, miss_r))
    # ----- Arcane Shot (arcane = zirhsiz)
    arc = A["arcane_base"] + A["arcane_ap"]*c["rap"]
    add("Arcane Shot", (T/A["arcane_cd"]) * ex(arc, cr, cm, miss_r*0.5))
    # ----- Multi-Shot
    ms = rav*0 + (rav - c["rap"]*B["rspeed"]/14.0*0) + A["multi_base"]   # silah+ammo+RAP(norm) + flat
    add("Multi-Shot", (T/A["multi_cd"]) * ex(ms*arm, cr, cm, miss_r))
    # ----- Serpent Sting (zirhsiz, kritlemez)
    add("Serpent Sting", T/A["serp_dur"] * A["serp_total"])
    # ----- melee ozel yetenekler (yalnizca melee_uptime boyunca)
    up = A["melee_uptime"]; Tm = T*up
    ws = c["weapons"]
    mh = ws[0]; oh = ws[1] if c["kind"]=="dw" else None
    def wdmg(w): return (w["min"]+w["max"])/2 + c["ap"]*w["spd"]/14.0
    sav = A["savage"]
    # Raptor Strike: swing yerine gecer
    rs_n = Tm / max(A["raptor_cd"], mh["spd"])
    rs = (wdmg(mh) + A["raptor_flat"]) * sav
    add("Raptor Strike", rs_n * ex(rs*arm, cr, cm_melee, miss_m))
    # Strider Kick: silah hasari
    sk_n = Tm / A["strider_cd"]
    add("Strider Kick", sk_n * ex(wdmg(mh)*A["strider_wpn"]*sav*arm, cr, cm_melee, miss_m))
    # Mongoose Bite: hedef dodge + Expose Prey; ~kullanilir ve 5s penceresi, rs ile paylasmaz
    mb_n = Tm * A["dodge"] / mh["spd"] * 1.0 + Tm/20.0*0.5
    add("Mongoose Bite", mb_n * ex((A["mb_flat"]+A["mb_ap"]*c["ap"])*sav*arm, cr, cm_melee, 0.0)*1.0)
    # beyaz melee: MH (RS ile degisen swing cikarilir) + OH
    mh_sw = Tm/mh["spd"] - rs_n - sk_n*0.0
    proc = 0.0
    if mh.get("proc_extra"): proc = 0.045 * mh["spd"] / 2.7 * 3.5 * 0.0 + 0.04   # ~%4 ekstra swing
    add("Melee MH", max(mh_sw,0)*(1+proc) * ex(wdmg(mh)*sav*arm, cr, cm_melee, miss_w))
    if oh:
        oh_dmg = (wdmg(oh)*0.5)*(1+A["pred_edge_oh"])
        add("Melee OH", (Tm/oh["spd"]) * ex(oh_dmg*sav*arm, cr, cm_melee, miss_w))
    tot = sum(dmg.values())
    return tot/T, dmg

def report(title, weapons):
    d, parts = run(weapons)
    print(f"{title:42s} {d:8.1f} dps   " + "  ".join(f"{k}:{v/ASSUMP['fight']:.0f}" for k,v in parts.items()))
    return d

if __name__ == "__main__":
    base = report("Thrash Blade + Dustwallow Dirk (su an)", ("dw","Thrash Blade","Dustwallow Dirk"))
    for n in ("Frenzied Striker","Hunting Spear","Lord Alexander's Battle Axe","Peacemaker","Dreadforge Retaliator"):
        d = report(n+" (2H)", ("2h",n))
        print(f"      fark: {d-base:+.1f} dps ({(d/base-1)*100:+.2f}%)")
