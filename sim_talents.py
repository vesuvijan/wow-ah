#!/usr/bin/env python3
"""Talent'li Survival/Marksmanship hibrit DPS modeli (Forever). sim_survival.py'nin uzerine kurulu.
Talent degerleri: guildorder / timesaver.gg Forever hesaplayicilari (pre-launch tam rank degerleri) + Blizzard Forever Hunter makalesi.
Mevcut talentler char_live.json'daki gercek build; plan = OneForAll ekran goruntusundeki preset (MM 22 / SV 29).
Calistir: python3 sim_talents.py"""
import copy, json
import sim_survival as S

W = S.W
W["Frenzied Striker"].update(hit=2)
W["Distracting Dagger"] = dict(min=37, max=69, spd=1.30, ap=0, agi=3, str=0, crit=0, hit=0, hand="oh")
W["Bloodseeker"] = dict(min=85, max=128, spd=3.30, ap=0, rap=0, agi=7, str=8, crit=0, hit=0)

# mevcut (char_live.json) talent rank'lari: statlarda zaten ISLENMIS
CUR = dict(lethal_attacks=5, careful_aim=2, surefooted=3, lightning_reflexes=5, savage_strikes=2,
           predator_edge=5, mortal_shots=0, lone_wolf=0, barrage=0, rws=0, improved_stings=0,
           improved_arcane=0, expose_prey=2, lacerating=1, deadly_aspects=5)

# OneForAll ekran goruntusundeki PLAN (okunan rank'lar)
PLAN = dict(lethal_attacks=5, careful_aim=5, surefooted=1, lightning_reflexes=4, savage_strikes=2,
            predator_edge=0, mortal_shots=3, lone_wolf=1, barrage=0, rws=0, improved_stings=3,
            improved_arcane=0, expose_prey=2, lacerating=0, deadly_aspects=0)

INT = 91.0
LR_PER = 0.02        # Lightning Reflexes: rank basina %Agility (guildorder: 2%)
AGI_NOW = 283.0
# talent etkileri sabitleri
LA_PER = 1.0         # %crit / rank (tum saldirilar)
CA_PER = 0.20        # AP = %20*Int / rank
SF_PER = 1.0         # %hit / rank
SS_PER = 0.02        # Savage Strikes: tum melee hasar +%2/rank (Blizzard)
PE_PER = 0.06        # Predator's Edge: melee ozel crit hasar bonusu +%6/rank
MS_PER = 0.06        # Mortal Shots: ranged crit hasar bonusu +%6/rank
BA_PER = 0.03        # Barrage: Multi-Shot +%3/rank
RWS_PER = 0.01       # Ranged Weapon Spec: ranged silah hasari +%1/rank
IS_PER = 0.02        # Improved Stings: Serpent +%6 / 3 rank
IA_PER = 0.3         # Improved Arcane: cd -0.3s/rank
DA_PER = 0.02        # Deadly Aspects: auto basina %2/rank sans, +%30 ranged hiz 12s
LW = 0.20            # Lone Wolf: petsiz tum saldirilar +%20

def dps(tal, melee_w=("2h", "Frenzied Striker"), ranged="Bloodseeker", uptime=0.5, A=None, detail=False):
    A = dict(S.ASSUMP if A is None else A); A["melee_uptime"] = uptime
    c = S.derive(melee_w, None, A)
    B = c["B"]
    # talent farki (mevcut -> plan)
    d = lambda k: tal[k] - CUR[k]
    dagi = (AGI_NOW / (1 + LR_PER * CUR["lightning_reflexes"])) * LR_PER * d("lightning_reflexes")
    dap = CA_PER * INT * d("careful_aim") + dagi
    ap = c["ap"] + dap
    rap = c["rap"] + dap
    crit = c["crit"] + LA_PER * d("lethal_attacks") + dagi / 50.0
    hit = c["hit"] + SF_PER * d("surefooted")
    # ranged silah degisimi (Megashot Rifle -> secilen)
    rw = (48 + 89) / 2; rsp = B["rspeed"]; ammo = 14.7
    if ranged == "Bloodseeker":
        rwn = (85 + 128) / 2; rspn = 3.30; rap += -19 + 7; crit += 7 / 50.0
        ap += 7; ap += 0
    else:
        rwn = rw; rspn = rsp
    arm = 1 - A["armor_red"]
    miss = max(0.0, A["miss_base"] - hit / 100)
    cr = crit / 100.0
    lw = 1 + LW * tal["lone_wolf"]
    cm_r = A["crit_mult"] + MS_PER * tal["mortal_shots"]
    cm_m = A["crit_mult"] + PE_PER * tal["predator_edge"]
    T = A["fight"]
    ex = lambda b, cc, m, ms: b * (1 - ms) * (1 + cc * (m - 1))
    out = {}
    # auto shot
    base_hit = (rwn * (1 + RWS_PER * tal["rws"])) + ammo * rspn
    auto_dmg = base_hit + rap * rspn / 14.0
    haste = 1.0
    if tal["deadly_aspects"]:
        p = DA_PER * tal["deadly_aspects"]
        import math
        up = 1 - math.exp(-12.0 * p / rspn)
        haste = 1 + 0.30 * up
    out["Auto Shot"] = (T / rspn * haste) * ex(auto_dmg * arm, cr, cm_r, miss) * lw
    # arcane (arcane = zirhsiz)
    arc = A["arcane_base"] + A["arcane_ap"] * rap
    arc_cd = A["arcane_cd"] - IA_PER * tal["improved_arcane"]
    out["Arcane Shot"] = (T / arc_cd) * ex(arc, cr, cm_r, miss * 0.5) * lw
    # multi shot
    ms_d = (base_hit + rap * rspn / 14.0 + A["multi_base"]) * (1 + BA_PER * tal["barrage"])
    out["Multi-Shot"] = (T / A["multi_cd"]) * ex(ms_d * arm, cr, cm_r, miss) * lw
    out["Serpent Sting"] = T / A["serp_dur"] * A["serp_total"] * (1 + IS_PER * tal["improved_stings"]) * lw
    # melee
    Tm = T * uptime
    mh = c["weapons"][0]
    sav = 1 + SS_PER * tal["savage_strikes"]
    wd = lambda w: (w["min"] + w["max"]) / 2 + ap * w["spd"] / 14.0
    rs_n = Tm / max(A["raptor_cd"], mh["spd"])
    out["Raptor Strike"] = rs_n * ex((wd(mh) + A["raptor_flat"]) * sav * arm, cr, cm_m, miss) * lw
    sk_n = Tm / A["strider_cd"]
    out["Strider Kick"] = sk_n * ex(wd(mh) * sav * arm, cr, cm_m, miss) * lw
    ep = 0.05 * tal["expose_prey"]
    mb_n = Tm * A["dodge"] / mh["spd"] + Tm / mh["spd"] * ep * 0.3 + Tm / 20.0 * 0.5
    mb_d = (A["mb_flat"] + A["mb_ap"] * ap) * sav * arm
    out["Mongoose Bite"] = mb_n * ex(mb_d, cr, cm_m, 0.0) * (1 + 0.4 * tal["lacerating"]) * lw
    mh_sw = max(Tm / mh["spd"] - rs_n, 0)
    dwx = A["dw_extra_miss"] if melee_w[0] == "dw" else 0.0
    miss_w = max(0.0, A["miss_base"] + dwx - hit / 100)
    out["Melee swings"] = mh_sw * ex(wd(mh) * sav * arm, cr, A["crit_mult"], miss_w) * lw
    if melee_w[0] == "dw":
        oh = c["weapons"][1]
        oh_d = wd(oh) * 0.5 * (1 + 0.10 * tal["predator_edge"]) * sav * arm
        out["Off hand swings"] = (Tm / oh["spd"]) * ex(oh_d, cr, A["crit_mult"], miss_w) * lw
    tot = sum(out.values()) / T
    return (tot, {k: v / T for k, v in out.items()}) if detail else tot

def pct(a, b): return (a / b - 1) * 100

if __name__ == "__main__":
    for up in (0.3, 0.6, 1.0):
        cur = dps(CUR, uptime=up)
        pl = dps(PLAN, uptime=up)
        print(f"melee {up:.1f}: mevcut talent (petli, Lone Wolf yok) {cur:6.1f}  plan {pl:6.1f}  ({pct(pl,cur):+.1f}%)")
    print()
    base = dps(PLAN, uptime=0.5)
    print("PLAN @melee %50 =", round(base, 1), "dps; her talent'tan 1 rank EKLEMENIN degeri:")
    for k in ("surefooted", "predator_edge", "mortal_shots", "careful_aim", "lethal_attacks", "barrage", "rws",
              "improved_stings", "lightning_reflexes", "savage_strikes", "improved_arcane", "lacerating", "expose_prey", "deadly_aspects"):
        t = dict(PLAN); t[k] += 1
        print(f"  +1 {k:20s} {pct(dps(t, uptime=0.5), base):+.2f}%")
