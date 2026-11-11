#!/usr/bin/env python3
"""gear_plan.json + gear_plan_dps.json -> tek dosyali HTML (artifact). Kullanim: python build_page.py <plan.json> <plan_dps.json> <out.html>"""
import json
import sys

a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
data = json.dumps({"lvl": a, "dps": b}, separators=(",", ":")).replace("</", "<\\/")
HTML = r'''<title>Docker Tuckalot Gear Planner</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap">
<style>
/* Layout: sticky slot rail + ranked upgrade list; green = wearable now, amber = needs a higher level. */
:root{
  --bg:#f3f5f2; --panel:#ffffff; --panel2:#eaeee9; --line:#d5dbd3; --fg:#18201a; --mute:#5c685f;
  --now:#157a3c; --now-bg:#dff3e5; --later:#a35f00; --later-bg:#fbeacc; --acc:#2b5d8a;
  --q2:#1a8a2e; --q3:#1f64c4; --q4:#8e3fc2; --q1:#4b5563; --bad:#b3261e;
  --head:'Space Grotesk','Inter',system-ui,sans-serif; --body:'Inter',system-ui,sans-serif;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#12170f; --panel:#1b2218; --panel2:#232c20; --line:#334030; --fg:#e8eee6; --mute:#9aa898;
  --now:#5fd184; --now-bg:#173a24; --later:#f0b24a; --later-bg:#3b2a0c; --acc:#7db4e6;
  --q2:#4ade5e; --q3:#5aa2ff; --q4:#c68bff; --q1:#9ca3af; --bad:#ff8a80; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#12170f; --panel:#1b2218; --panel2:#232c20; --line:#334030; --fg:#e8eee6; --mute:#9aa898;
  --now:#5fd184; --now-bg:#173a24; --later:#f0b24a; --later-bg:#3b2a0c; --acc:#7db4e6;
  --q2:#4ade5e; --q3:#5aa2ff; --q4:#c68bff; --q1:#9ca3af; --bad:#ff8a80; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--body);font-size:14px;line-height:1.45;
  padding-block:20px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.wrap{max-width:1100px;margin:0 auto;display:flex;flex-direction:column;gap:16px}
h1,h2,h3{font-family:var(--head);margin:0;text-wrap:balance}
h1{font-size:26px;letter-spacing:-.01em}
.sub{color:var(--mute);margin:4px 0 0}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.eq{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}
.eq div{display:flex;flex-direction:column;min-width:0;padding:6px 8px;background:var(--panel2);border-radius:6px}
.eq small{color:var(--mute);font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.eq b{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.q1{color:var(--q1)}.q2{color:var(--q2)}.q3{color:var(--q3)}.q4{color:var(--q4)}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{background:var(--panel);color:var(--fg);border:0;padding:7px 12px;font:inherit;cursor:pointer}
.seg button+button{border-left:1px solid var(--line)}
.seg button[aria-pressed="true"]{background:var(--acc);color:var(--bg);font-weight:600}
button:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--mute);font-size:13px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}
.main{display:grid;grid-template-columns:150px minmax(0,1fr);gap:16px;align-items:start}
.rail{position:sticky;top:8px;display:flex;flex-direction:column;gap:4px}
.rail button{text-align:left;background:var(--panel);border:1px solid var(--line);color:var(--fg);padding:8px 10px;border-radius:8px;font:inherit;cursor:pointer;display:flex;justify-content:space-between;gap:6px}
.rail button[aria-pressed="true"]{background:var(--acc);color:var(--bg);border-color:var(--acc);font-weight:600}
.rail em{font-style:normal;font-size:12px;opacity:.85}
.list{display:flex;flex-direction:column;gap:8px}
.row{display:grid;grid-template-columns:64px minmax(0,1fr) auto;gap:12px;align-items:center;background:var(--panel);border:1px solid var(--line);border-left-width:5px;border-radius:8px;padding:10px 12px}
.row.now{border-left-color:var(--now)}.row.lvl{border-left-color:var(--later)}
.gain{font-family:var(--head);font-weight:700;font-size:18px;text-align:center;font-variant-numeric:tabular-nums}
.gain.pos{color:var(--now)}.gain.neg{color:var(--bad)}
.nm{font-weight:600;font-size:15px}
.st{color:var(--mute);font-size:12.5px;margin-top:2px;overflow-wrap:anywhere}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.chip{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--panel2);border:1px solid var(--line);overflow-wrap:anywhere}
.chip.drop{border-color:var(--q3)}.chip.quest{border-color:var(--now)}.chip.craft{border-color:var(--later)}.chip.rep{border-color:var(--q4)}.chip.ah{border-color:var(--acc);font-weight:600}
.meta{display:flex;flex-direction:column;align-items:flex-end;gap:4px;font-size:12px;color:var(--mute);white-space:nowrap}
.pill{font-weight:600;padding:2px 8px;border-radius:999px;font-size:12px}
.pill.now{background:var(--now-bg);color:var(--now)}.pill.lvl{background:var(--later-bg);color:var(--later)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.pair>div{min-width:0}
.pairhead{display:flex;justify-content:space-between;font-family:var(--head);font-weight:700;margin-bottom:6px}
h2{font-size:18px;margin-bottom:8px}
.note{color:var(--mute);font-size:13px;max-width:75ch}
.cur{font-size:13px;color:var(--mute);margin:0 0 8px}
@media(max-width:720px){
  .main{grid-template-columns:1fr}
  .rail{position:static;flex-direction:row;flex-wrap:wrap}
  .row{grid-template-columns:52px minmax(0,1fr)}
  .meta{grid-column:1/-1;flex-direction:row;align-items:center;flex-wrap:wrap}
  .pair{grid-template-columns:1fr}
}
</style>
<div class="wrap">
  <header>
    <h1>Docker Tuckalot</h1>
    <p class="sub" id="sub"></p>
  </header>
  <section class="panel"><h2>Wearing now</h2><div class="eq" id="eq"></div></section>
  <section class="panel">
    <div class="controls">
      <div class="seg" id="mode" role="group" aria-label="Scoring"><button data-v="dps" aria-pressed="true">Damage focus</button><button data-v="lvl" aria-pressed="false">Leveling mix</button></div>
      <div class="seg" id="when" role="group" aria-label="Level"><button data-v="all" aria-pressed="true">All</button><button data-v="NOW" aria-pressed="false">Wearable now</button><button data-v="LVL" aria-pressed="false">Level 60 plan</button></div>
    </div>
    <p class="note" id="modeNote"></p>
    <div class="legend"><span><i class="dot" style="background:var(--now)"></i>Wearable now (your level or below)</span><span><i class="dot" style="background:var(--later)"></i>Needs a higher level</span><span>Gain = change in total gear value if this replaces what you wear</span></div>
  </section>
  <div class="main">
    <nav class="rail" id="rail" aria-label="Slots"></nav>
    <div class="list" id="list"></div>
  </div>
</div>
<script>
const DATA = __DATA__;
const SLOTS = [["ALL","Overview"],["WEAPONS","Weapons"],["HEAD","Head"],["NECK","Neck"],["SHOULDER","Shoulders"],["BACK","Back"],["CHEST","Chest"],["WRIST","Wrists"],["HANDS","Hands"],["WAIST","Waist"],["LEGS","Legs"],["FEET","Feet"],["FINGER","Rings"],["TRINKET","Trinkets"]];
const QN = {1:"q1",2:"q2",3:"q3",4:"q4"};
const state = {mode:"dps", when:"all", slot:"ALL"};
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const LEVEL = DATA.lvl.meta.level;
try { const s = JSON.parse(localStorage.getItem("gp") || "{}"); Object.assign(state, s); } catch(e) {}
function save(){ try{ localStorage.setItem("gp", JSON.stringify(state)); }catch(e){} }
const plan = () => DATA[state.mode];
function chip(t){
  const k = t.startsWith("Drop")?"drop":t.startsWith("AH")?"ah":t.startsWith("Craft")?"craft":t.startsWith("Rep")?"rep":t.startsWith("Set")?"":"quest";
  return `<span class="chip ${k}">${esc(t.replace(" (lvl 0)",""))}</span>`;
}
function row(o){
  const g = o.gain_pct, cls = o.tag==="NOW"?"now":"lvl";
  const pill = o.req<=LEVEL ? `<span class="pill now">Wearable now</span>` : `<span class="pill lvl">Needs Lv ${o.req}</span>`;
  return `<article class="row ${cls}">
    <div class="gain ${g>=0?"pos":"neg"}">${g>=0?"+":""}${g.toFixed(1)}%</div>
    <div><div class="nm ${QN[o.q]||""}">${esc(o.name)}</div>
      <div class="st">${esc(o.stats||"")}${o.atype?` · ${esc(o.atype)}`:""}</div>
      <div class="chips">${o.src.map(chip).join("")}</div>
      ${o.extra&&o.extra.length&&o.extra[0].length>14?`<div class="st">Not scored: ${esc(o.extra[0].slice(0,110))}</div>`:""}</div>
    <div class="meta">${pill}<span>ilvl ${o.ilvl} · ${esc(o.bind||"—")}</span></div></article>`;
}
function wrow(w, label){
  const pill = w.req<=LEVEL ? `<span class="pill now">Wearable now</span>` : `<span class="pill lvl">Needs Lv ${w.req}</span>`;
  return `<div><div class="nm ${QN[w.q]||""}">${esc(label)} ${esc(w.name)}</div>
    <div class="st">${w.dps.toFixed(1)} dps · ${w.spd.toFixed(1)}s · ${esc(w.stats.replace(/, [\d.]+ dps.*$/,"")||"")}</div>
    <div class="chips">${w.src.map(chip).join("")}</div><div class="meta" style="align-items:flex-start;margin-top:6px">${pill}<span>${esc(w.bind||"")}</span></div></div>`;
}
function weapons(){
  const p = plan().weapons; let out = "";
  for (const tag of ["NOW","LVL"]) {
    if (state.when!=="all" && state.when!==tag) continue;
    out += `<h2>${tag==="NOW"?"Dual wield you can use now":"Dual wield at level 60"}</h2>`;
    out += (p[tag]||[]).map(x=>`<article class="row ${tag==="NOW"?"now":"lvl"}" style="grid-template-columns:64px minmax(0,1fr)"><div class="gain pos">${Math.round(x.value)}</div><div class="pair">${wrow(x.mh,"Main hand")}${wrow(x.oh,"Off hand")}</div></article>`).join("");
  }
  out += `<h2>Ranged</h2>` + plan().ranged.filter(r=>state.when==="all"||(state.when==="NOW"?r.req<=LEVEL:r.req>LEVEL)).map(r=>`<article class="row ${r.req<=LEVEL?"now":"lvl"}" style="grid-template-columns:64px minmax(0,1fr)"><div class="gain pos">${r.dps.toFixed(0)}</div><div>${wrow(r,"")}</div></article>`).join("");
  return out;
}
function slotRows(slot){
  const cur = plan()[slot];
  const opts = cur.options.filter(o=>state.when==="all"||o.tag===state.when);
  return `<p class="cur">Wearing: <b>${esc(cur.equipped||"-")}</b> (value ${cur.value})</p>` + (opts.map(row).join("") || `<p class="note">No options for this filter.</p>`);
}
function overview(){
  const rows = [];
  for (const [k] of SLOTS.slice(2)) {
    const best = plan()[k].options.filter(o=>o.tag==="NOW")[0];
    if (best) rows.push(best);
  }
  rows.sort((x,y)=>y.gain_pct-x.gain_pct);
  return `<h2>Biggest upgrades you can take now</h2>` + rows.slice(0,12).map(r=>row(r)).join("");
}
function render(){
  $("#sub").textContent = `Level ${LEVEL} Human Hunter · Survival, dual wield · plan for level ${DATA.lvl.meta.plan_max} · ${DATA.lvl.meta.tooltips.toLocaleString()} items read (dungeon drops, quests, reputation, crafting, sets)`;
  $("#eq").innerHTML = DATA.lvl.equipped.map(e=>`<div><small>${esc(e.slot.replace("_"," "))}</small><b class="${QN[({UNCOMMON:2,RARE:3,EPIC:4,COMMON:1}[e.q])||1]}">${esc(e.name)}</b><small>ilvl ${e.ilvl}${e.enchant?" · "+esc(e.enchant):""}</small></div>`).join("");
  for (const [g,id] of [["mode","mode"],["when","when"]]) document.querySelectorAll(`#${id} button`).forEach(b=>b.setAttribute("aria-pressed", String(state[g]===b.dataset.v)));
  $("#modeNote").textContent = state.mode==="dps" ? "Damage focus counts Agility, Attack Power, crit, hit and weapon DPS only. Best for killing speed." : "Leveling mix also counts Stamina, Intellect, Spirit and mana regen the way the Sharpie leveling curve does. Spirit is valued highly here, so caster-style pieces rank higher.";
  $("#rail").innerHTML = SLOTS.map(([k,n])=>`<button data-s="${k}" aria-pressed="${state.slot===k}"><span>${n}</span></button>`).join("");
  $("#list").innerHTML = state.slot==="ALL" ? overview() : state.slot==="WEAPONS" ? weapons() : slotRows(state.slot);
}
document.addEventListener("click", e=>{
  const b = e.target.closest("button"); if(!b) return;
  if (b.closest("#mode")) state.mode=b.dataset.v; else if (b.closest("#when")) state.when=b.dataset.v; else if (b.dataset.s) state.slot=b.dataset.s; else return;
  save(); render();
});
render();
</script>
'''.replace("__DATA__", data)
open(sys.argv[3], "w", encoding="utf-8").write(HTML)
print(len(HTML))
