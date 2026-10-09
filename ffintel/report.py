"""Renders the single-file dashboard (data embedded, no external requests)."""
import json

TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Fantasy Intel</title>
<style>
:root{
  color-scheme:light;
  --bg:#f4f5f7; --card:#ffffff; --card-2:#fafbfc; --ink:#14161a; --ink-2:#3d434d; --mute:#69707c;
  --line:#e4e7ec; --line-2:#eef0f4; --chip:#eef1f6;
  --acc:#2a78d6; --acc-soft:#e8f0fb;
  --good:#10714d; --good-bg:#e3f5ec; --bad:#b52d2a; --bad-bg:#fbe9e8; --warn:#8a6206; --warn-bg:#fdf0d9;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.04);
  --radius:14px;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  color-scheme:dark;
  --bg:#0e1014; --card:#171a20; --card-2:#1c2028; --ink:#e9ecf1; --ink-2:#c2c8d2; --mute:#8d96a3;
  --line:#242932; --line-2:#1f242c; --chip:#212733;
  --acc:#5fa0ee; --acc-soft:#16283f;
  --good:#3fc490; --good-bg:#10291f; --bad:#f08b88; --bad-bg:#2c1615; --warn:#e8b563; --warn-bg:#2e2410;
  --shadow:none;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;-webkit-font-smoothing:antialiased}
b,strong{font-weight:650}
header{max-width:1180px;margin:auto;padding:22px 20px 10px}
h1{margin:0;font-size:21px;font-weight:700;letter-spacing:-.02em;display:flex;align-items:center;gap:10px}
h1::before{content:"";width:6px;height:22px;border-radius:3px;background:linear-gradient(180deg,var(--acc),#1baf7a)}
header p{margin:6px 0 0;color:var(--mute);font-size:12.5px;letter-spacing:.01em}
nav{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
nav div{display:flex;gap:2px;overflow-x:auto;max-width:1180px;margin:auto;padding:9px 20px;scrollbar-width:none}
nav div::-webkit-scrollbar{display:none}
nav button{flex:none;border:0;background:none;color:var(--mute);padding:7px 13px;border-radius:9px;font:inherit;font-size:13.5px;font-weight:600;cursor:pointer;white-space:nowrap;transition:background .12s,color .12s}
nav button:hover{color:var(--ink);background:var(--line-2)}
nav button.on{background:var(--acc-soft);color:var(--acc)}
main{max-width:1180px;margin:auto;padding:16px 20px 72px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;margin-bottom:16px;box-shadow:var(--shadow)}
.card h2{margin:0 0 3px;font-size:15.5px;font-weight:650;letter-spacing:-.01em}
.sub{color:var(--mute);font-size:13px;margin:0 0 12px;max-width:80ch}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -18px;padding:0 18px}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:8px 10px;border-bottom:1px solid var(--line-2);text-align:right;white-space:nowrap}
th{color:var(--mute);font-weight:600;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;cursor:pointer;user-select:none;position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);z-index:2}
th:hover{color:var(--ink)}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--card);z-index:1}
td.l,th.l{text-align:left}
tbody tr:last-child td{border-bottom:0}
tr.p{cursor:pointer}tr.p:hover td{background:var(--card-2)}
.pos{display:inline-block;min-width:28px;text-align:center;font-size:10px;font-weight:700;letter-spacing:.04em;border-radius:5px;padding:2px 5px;background:var(--chip);color:var(--ink-2);margin-right:7px}
.tag{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.02em;border-radius:999px;padding:2px 8px;vertical-align:middle}
.U{background:var(--good-bg);color:var(--good)}.O{background:var(--bad-bg);color:var(--bad)}
.I{background:var(--warn-bg);color:var(--warn)}.S{background:var(--acc-soft);color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:10px}
.stat{background:var(--card-2);border:1px solid var(--line-2);border-radius:11px;padding:11px 12px;position:relative;overflow:hidden}
.stat::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--acc);opacity:.55}
.stat b{display:block;font-size:21px;font-weight:680;letter-spacing:-.02em;line-height:1.25}
.stat span{color:var(--mute);font-size:11.5px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
input,select{font:inherit;font-size:13.5px;padding:8px 11px;border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
input:focus,select:focus{outline:2px solid var(--acc-soft);border-color:var(--acc)}
.chips button{border:1px solid var(--line);background:var(--card);color:var(--ink-2);border-radius:999px;padding:6px 13px;font:inherit;font-size:13px;font-weight:600;cursor:pointer}
.chips button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.trade{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line-2)}
.trade:last-child{border:0}.trade .arrow{color:var(--mute);font-size:17px}.trade small{color:var(--mute)}
.why{color:var(--mute);font-size:12px;white-space:normal;text-align:left;min-width:220px;line-height:1.4}
.good{color:var(--good)}.bad{color:var(--bad)}.mute{color:var(--mute)}
.bars{display:flex;gap:4px;align-items:flex-end;height:64px;margin-top:6px}
.bars div{flex:1;background:var(--acc);border-radius:4px 4px 2px 2px;min-width:10px;position:relative;opacity:.9}
.bars div span{position:absolute;top:-16px;left:0;right:0;text-align:center;font-size:10px;color:var(--mute)}
dialog{border:1px solid var(--line);border-radius:16px;background:var(--card);color:var(--ink);max-width:580px;width:calc(100% - 28px);padding:20px;box-shadow:0 12px 40px rgba(16,24,40,.18)}
dialog::backdrop{background:rgba(9,11,15,.55)}
.x{float:right;border:0;background:none;color:var(--mute);font-size:22px;line-height:1;cursor:pointer;padding:0 2px}
.kv{display:grid;grid-template-columns:1fr 1fr;gap:2px 18px;font-size:13px;font-variant-numeric:tabular-nums}
.kv div{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--line-2);padding:5px 0}
.kv span{color:var(--mute)}
.banner{background:var(--warn-bg);color:var(--warn);border-radius:11px;padding:11px 13px;margin-bottom:14px;font-size:13px;line-height:1.5}
.taList{max-height:340px;overflow:auto;margin-top:8px;border:1px solid var(--line);border-radius:11px;padding:5px;background:var(--card-2)}
.taRow{display:flex;gap:8px;align-items:center;padding:7px;border-radius:8px;font-size:13px;cursor:pointer;flex-wrap:wrap}
.taRow:hover{background:var(--chip)}.taRow.on{background:var(--acc-soft)}
.taRow span:last-child{margin-left:auto;font-size:11.5px;color:var(--mute);font-variant-numeric:tabular-nums}
.split{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
.split>div{min-width:0}.split .tw{margin:0;padding:0}
@media(max-width:900px){.split{grid-template-columns:minmax(0,1fr)}}
@media(max-width:700px){main{padding:14px 16px 60px}header{padding:18px 16px 8px}nav div{padding:8px 16px}.card{padding:14px}.tw{margin:0 -14px;padding:0 14px}}
.lineup td{padding:9px 10px}
.lu-slot{width:52px;font-size:11px;font-weight:700;letter-spacing:.04em;color:var(--mute)}
table.lineup td.lu-slot{position:static}
.lu-total td{background:var(--card-2);border-bottom:1px solid var(--line)}
.lu-div td{background:var(--card);color:var(--mute);font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:14px 10px 6px;border-bottom:1px solid var(--line)}
.lu-new td{background:var(--acc-soft)!important}
.mv{padding:6px 0;border-bottom:1px solid var(--line-2)}.mv:last-child{border:0}
.st-good::before{background:var(--good)!important;opacity:.9!important}.st-bad::before{background:var(--bad)!important;opacity:.9!important}
@media(max-width:700px){.lineup .c-opp,.lineup .c-ros,.lineup .c-note,.lineup .c-ver{display:none}.lineup td{padding:9px 6px}}
.teamhead{padding:12px 16px}
.idea{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:10px;background:var(--card-2)}
.idea-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.idea .trade{border:0;padding:8px 0}
.idea-nums{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px}
.btn{display:inline-block;font-size:13px;font-weight:600;color:var(--acc);cursor:pointer}.teamhead select{min-width:240px;font-weight:600}
.method p{margin:7px 0;max-width:78ch;color:var(--ink-2)}.method h3{margin:16px 0 4px;font-size:13.5px;letter-spacing:-.01em}
</style></head><body>
<header><h1>Fantasy Intel</h1><p id="meta"></p></header>
<nav><div id="tabs"></div></nav>
<main id="main"></main>
<dialog id="dlg"></dialog>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const P=D.players, L=D.league, byId={};P.forEach(p=>byId[p.player_id]=p);
const $=s=>document.querySelector(s);
const f1=v=>v==null?'–':(+v).toFixed(1), f0=v=>v==null?'–':Math.round(v), pct=v=>v==null?'–':Math.round(v*100)+'%';
const sgn=v=>v==null?'–':(v>0?'+':'')+(+v).toFixed(1);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pos=p=>`<span class="pos">${p}</span>`;
const verdict=v=>v==='Undervalued'?'<span class="tag U">Undervalued</span>':v==='Overvalued'?'<span class="tag O">Overvalued</span>':'';
const INJ_LABEL={QUESTIONABLE:'Q',DOUBTFUL:'D',LIMITED:'Limited',DNP:'DNP','LEFT GAME':'Left game','SNAPS DOWN':'Snaps ↓',RETURNED:'Returned',CLEARED:'Cleared',SEASON:'Out for season',UNAVAILABLE:'Unavail.',SUSPENSION:'Susp.',INACTIVE:'Inactive'};
const INJ_CLASS={CLEARED:'U',RETURNED:'S','SNAPS DOWN':'S',LIMITED:'S',SEASON:'O',IR:'O',OUT:'O','LEFT GAME':'O'};
const inj=p=>p.inj_status?`<span class="tag ${INJ_CLASS[p.inj_status]||'I'}" title="${esc(p.inj_detail)}">${INJ_LABEL[p.inj_status]||p.inj_status}</span>`:'';
const ago=t=>{if(!t)return '';const d=new Date(t);if(isNaN(d))return '';const h=(Date.now()-d)/36e5;return h<1?'just now':h<24?Math.round(h)+'h ago':Math.round(h/24)+'d ago'};
const sigList=p=>(p.inj_signals||[]).map(s=>`<div style="padding:6px 0;border-bottom:1px dashed var(--line)"><b>${esc(INJ_LABEL[s.status]||s.status)}</b> <span class="mute">· ${esc(s.source)}${s.when?' · '+ago(s.when):''}</span><br><span style="font-size:13px">${esc(s.detail)}</span></div>`).join('');
const star=p=>p.star?'<span class="tag S" title="Proven star">★</span>':'';
const bye=p=>p.on_bye?'<span class="tag" style="background:var(--chip);color:var(--mute)">BYE</span>':'';
const nm=p=>`${pos(p.position)}<b>${esc(p.name)}</b> <span class="mute">${esc(p.team||'')}</span> ${star(p)} ${bye(p)} ${inj(p)}`;
const playOdds=p=>p.on_bye?'bye':pct(p.play_prob);
const wk=p=>p.on_bye?'<span class="mute">bye</span>':f1(p.week_proj);
const LN=D.lines||{};
const spreadTxt=v=>v==null?'':(v<0?'favored by '+Math.abs(v):v>0?'underdog by '+v:'pick\'em');
const gameTxt=p=>{if(p.on_bye)return 'BYE';const l=LN[p.team];if(!p.opponent)return '—';
  return `vs ${esc(p.opponent)}${l?` · team total <b>${f1(l.implied)}</b> <span class="mute">(usually ${f1(l.team_avg)}; ${spreadTxt(l.spread)})</span>`:''}`};
const gameFx=p=>p.vegas!=null?`Vegas ×${(+p.vegas).toFixed(2)}`:(p.matchup&&Math.abs(p.matchup-1)>=0.005?`matchup ×${(+p.matchup).toFixed(2)}`:'');
const advRows=p=>{const R=[];const a=(l,v)=>{if(v!=null&&v!=='–')R.push(`<div><span>${l}</span><b>${v}</b></div>`)};
  const pc=v=>v==null?null:Math.round(v)+'%';
  a('Route participation',pc(p.route_pct));a('Routes per game',p.routes_pg!=null?f1(p.routes_pg):null);
  a('Targets per route',pc(p.tprr));a('Yards per route',p.yprr!=null?(+p.yprr).toFixed(2):null);
  a('First-read target share',pc(p.fr_share));a('Target separation (yds)',p.separation!=null?(+p.separation).toFixed(2):null);
  a('Slot rate',pc(p.slot_rate));a('Opportunity share',pc(p.opp_share));a('Weighted opps / game',p.wopp_pg!=null?f1(p.wopp_pg):null);
  return R.join('')};
const routeBars=p=>{const w=p.route_weeks||[];if(w.length<2)return '';return `<div class="bars" style="height:56px">${w.map(([k,v])=>`<div style="height:${Math.max(3,v)}%"><span>${Math.round(v)}</span></div>`).join('')}</div><p class="sub">Route participation by week (${w.map(x=>'wk '+x[0]).join(', ')})</p>`};
const gen=new Date(D.generated);
$('#meta').textContent=`${D.season} season · week ${D.week}${D.plan_week!==D.week?` (planning for week ${D.plan_week})`:''} · stats through week ${D.data_through_week} · updated ${gen.toLocaleString()}`;

function table(rows,cols,opts={}){
  const id='t'+Math.random().toString(36).slice(2);
  let st={k:opts.sort||null,d:-1};
  const draw=()=>{
    let r=rows.slice();
    if(st.k){const c=cols.find(c=>c.k===st.k);const g=c.v||(x=>x[c.k]);r.sort((a,b)=>{const x=g(a),y=g(b);if(x==null)return 1;if(y==null)return -1;return (x>y?1:x<y?-1:0)*st.d})}
    const h=cols.map(c=>`<th class="${c.l?'l':''}" data-k="${c.k}" title="${esc(c.t||'')}">${c.h}${st.k===c.k?(st.d<0?' ↓':' ↑'):''}</th>`).join('');
    const b=r.map(x=>`<tr class="${x.player_id?'p':''}" data-id="${x.player_id||''}">${cols.map(c=>`<td class="${c.l?'l':''}">${c.f?c.f(x):esc(x[c.k])}</td>`).join('')}</tr>`).join('');
    document.getElementById(id).innerHTML=`<table><thead><tr>${h}</tr></thead><tbody>${b||`<tr><td colspan="${cols.length}" class="mute">Nothing here right now.</td></tr>`}</tbody></table>`;
    document.querySelectorAll(`#${id} th`).forEach(th=>th.onclick=()=>{const k=th.dataset.k;st.d=st.k===k?-st.d:-1;st.k=k;draw()});
    document.querySelectorAll(`#${id} tr.p`).forEach(tr=>tr.onclick=()=>detail(tr.dataset.id));
  };
  setTimeout(draw);return `<div class="tw" id="${id}"></div>`;
}

function detail(id){
  const p=byId[id];if(!p)return;const w=p.weekly_pts||[];const mx=Math.max(1,...w);
  $('#dlg').innerHTML=`<button class="x" onclick="dlg.close()">×</button>
  <h2 style="margin:0 0 2px">${esc(p.name)} ${star(p)} ${verdict(p.verdict)}</h2>
  <p class="sub">${p.position} · ${esc(p.team||'')} · age ${f0(p.age)}${p.owner_name?' · on '+esc(p.owner_name):' · free agent'}</p>
  ${p.inj_status?`<div class="banner"><b>${esc(INJ_LABEL[p.inj_status]||p.inj_status)}</b> · ${p.on_bye?'on bye next week':pct(p.play_prob)+' to play next week'} · ${f1(p.exp_missed)} games expected missed<br>${esc(p.inj_detail)}</div>
   ${(p.inj_signals||[]).length>1?`<details style="margin:-6px 0 12px"><summary class="sub" style="cursor:pointer">All ${p.inj_signals.length} injury signals</summary>${sigList(p)}</details>`:''}`:''}
  ${p.fill_in_for?`<div class="banner" style="background:var(--good-bg);color:var(--good)">Took over for injured ${esc(p.fill_in_for)} last game</div>`:''}
  ${p.next_up_for?`<div class="banner" style="background:var(--good-bg);color:var(--good)">Next man up: ${esc(p.next_up_for)} is likely out this week${p.position==='RB'&&p.hc_contingent?`, so his week ${D.plan_week} projection includes the fill-in role (~${f1(p.hc_contingent)} pts if ${esc(p.next_up_for)} sits)`:''}.</div>`:''}
  ${p.depth_move?`<div class="banner" style="${p.depth_dir==='up'?'background:var(--good-bg);color:var(--good)':''}">Depth chart: ${p.depth_dir==='up'?'moved up':'moved down'}, ${esc(p.depth_move)}</div>`:''}
  ${p.note?`<p class="sub">${esc(p.note)}</p>`:''}
  <div class="grid" style="margin-bottom:12px">
   <div class="stat"><b>${f1(p.proj_ppg)}</b><span>Our proj. PPG</span></div>
   <div class="stat"><b>${f0(p.ros_points)}</b><span>Rest-of-season pts</span></div>
   <div class="stat"><b>${p.position}${f0(p.own_pos_rank)} / ${p.consensus_pos_rank?p.position+f0(p.consensus_pos_rank):'–'}</b><span>Our rank / consensus</span></div>
  </div>
  ${p.role_factor!=null&&p.role_factor<0.95&&p.proj_ppg_raw>p.proj_ppg?`<p class="sub">Role ceiling: with his current workload he keeps ${pct(p.role_factor)} of the value above replacement, trimming ${f1(p.proj_ppg_raw)} to ${f1(p.proj_ppg)} per game.</p>`:''}
  <p class="sub" style="margin-bottom:18px">How we got ${f1(p.proj_ppg_raw??p.proj_ppg)}:${p.preseason_ppg?` draft day said <b>${f1(p.preseason_ppg)}</b> (worth ${f1(p.preseason_weight_games)} games and fading),`:''} history says <b>${f1(p.prior_ppg)}</b> (${esc(p.prior_source)}, worth ${f1(p.prior_weight_games)} games), this season says <b>${f1(p.cur_ppg)}</b> actual / <b>${f1((p.xfp_total||0)/Math.max(p.all_games||1,1))}</b> expected from usage. This season gets ${pct(p.current_weight)} of the weight.</p>
  ${w.length?`<div class="bars">${w.map(v=>`<div style="height:${Math.max(3,v/mx*100)}%"><span>${v}</span></div>`).join('')}</div><p class="sub">Points by week</p>`:''}
  <div class="kv">
   <div><span>Snap % (season / role now)</span><b>${pct(p.snap_pct)} / ${pct(p.role_share)}</b></div><div><span>Target share</span><b>${pct(p.target_share)}</b></div>
   <div><span>Air yards share</span><b>${pct(p.air_yards_share)}</b></div><div><span>WOPR</span><b>${f1(p.wopr)}</b></div>
   <div><span>Touches</span><b>${f0(p.touches)}</b></div><div><span>Targets / rec</span><b>${f0(p.targets)} / ${f0(p.receptions)}</b></div>
   <div><span>Rush yds</span><b>${f0(p.rush_yds)}</b></div><div><span>Rec yds</span><b>${f0(p.rec_yds)}</b></div>
   <div><span>RZ targets</span><b>${f0(p.rz_targets)}</b></div><div><span>RZ target share</span><b>${pct(p.rz_tgt_share)}</b></div>
   <div><span>RZ carries / inside 10</span><b>${f0(p.rz_carries)} / ${f0(p.i10_carries)}</b></div><div><span>End-zone targets</span><b>${f0(p.ez_targets)}</b></div>
   <div><span>TDs</span><b>${f0(p.tds)}</b></div><div><span>Expected pts (total)</span><b>${f1(p.xfp_total)}</b></div>
   ${p.position==='QB'?`<div><span>Pass yds / TD / INT</span><b>${f0(p.pass_yds)} / ${f0(p.pass_tds)} / ${f0(p.ints)}</b></div>`:''}
   <div><span>Quarterback</span><b>${esc(p.qb||'—')} ${p.qb_factor&&Math.abs(p.qb_factor-1)>=0.01?`<span class="${p.qb_factor<1?'bad':'good'}">${sgn((p.qb_factor-1)*100)}%</span>`:''}</b></div>
   <div><span>Next game</span><b>${gameTxt(p)} ${gameFx(p)?`<span class="mute">${gameFx(p)}</span>`:''}</b></div>
   <div><span>Depth chart</span><b>${p.depth_label?esc(p.depth_label)+` <span class="mute">(${esc(p.depth_source)})</span>`:'–'}</b></div>
   <div><span>FantasyPros ROS rank</span><b>${p.fp_ros?f1(p.fp_ros):'–'} <span class="mute">(${p.fp_ros_best??'–'}–${p.fp_ros_worst??'–'})</span></b></div>
   <div><span>ESPN ROS proj.</span><b>${f0(p.espn_proj)}</b></div>
  </div>
  ${advRows(p)?`<h3 style="margin:16px 0 6px;font-size:14px">Advanced <span class="mute" style="font-weight:400">· ${p.pp_url?`<a href="${esc(p.pp_url)}" target="_blank" rel="noopener" style="color:var(--acc)">PlayerProfiler</a>`:'PlayerProfiler'}${p.pp_updated?', '+ago(p.pp_updated):''}</span></h3>
  ${routeBars(p)}<div class="kv">${advRows(p)}</div>`:''}`;
  $('#dlg').showModal();
}

const RK=[{k:'name',h:'Player',l:1,f:nm},{k:'proj_ppg',h:'Proj',f:x=>f1(x.proj_ppg),t:'Our projected points per game'},
 {k:'week_proj',h:'Next wk',f:x=>wk(x)},{k:'ros_points',h:'ROS',f:x=>f0(x.ros_points),t:'Rest-of-season points (injuries & byes included)'}];

const views={
 team(){
  if(!L)return noLeague();
  if(TV.id==null)TV.id=L.team.team_id;
  setTimeout(tvRender);
  const list=[...L.team.strength].sort((a,b)=>(b.team_id===L.team.team_id)-(a.team_id===L.team.team_id)||a.power_rank-b.power_rank);
  return `${L.mock?'<div class="banner">Demo mode: the league below is made up. Real players and stats, fake rosters.</div>':''}
  ${L.note?`<div class="banner">${esc(L.note)}</div>`:''}
  <div class="card teamhead"><div class="row" style="margin:0">
    <select id="tvSel" aria-label="Team">${list.map(t=>`<option value="${t.team_id}">${esc(t.name)}${t.team_id===L.team.team_id?'  (you)':'  · #'+t.power_rank}</option>`).join('')}</select>
    <span class="mute" style="font-size:13px">Pick any team in the league.</span></div></div>
  <div id="tvBody"></div>
  <div class="card"><h2>League power rankings</h2><p class="sub">By projected rest-of-season starting lineup. Tap a team to open it.</p>${table(L.team.strength,[{k:'name',h:'Team',l:1,f:x=>`<a style="cursor:pointer;color:var(--ink)" onclick="TV.id=${x.team_id};tvRender();window.scrollTo({top:0,behavior:'smooth'})">${x.team_id===L.team.team_id?'<b>'+esc(x.name)+'</b>':esc(x.name)}</a>`},{k:'record',h:'Rec'},{k:'lineup_ppw',h:'Lineup/wk',f:x=>f1(x.lineup_ppw)},{k:'QB_ppw',h:'QB',f:x=>f1(x.QB_ppw)},{k:'RB_ppw',h:'RB',f:x=>f1(x.RB_ppw)},{k:'WR_ppw',h:'WR',f:x=>f1(x.WR_ppw)},{k:'TE_ppw',h:'TE',f:x=>f1(x.TE_ppw)}],{sort:'lineup_ppw'})}</div>`;
 },
 waivers(){
  if(!L)return noLeague();
  return `<div class="card"><h2>Waiver targets</h2><p class="sub">Ranked by how much each player improves your lineup for the rest of the season, plus bench value. "Drop" is your least valuable bench player.</p>
  ${table(L.waivers,[{k:'name',h:'Player',l:1,f:nm},{k:'score',h:'Score',f:x=>f1(x.score)},{k:'gain_week',h:'+Lineup/wk',f:x=>sgn(x.gain_week)},{k:'proj_ppg',h:'Proj',f:x=>f1(x.proj_ppg)},{k:'pct_owned',h:'Own%',f:x=>x.pct_owned==null?'–':f0(x.pct_owned)+(x.pct_change?` <span class="${x.pct_change>0?'good':'bad'}">${sgn(x.pct_change)}</span>`:'')},{k:'role_share',h:'Role',f:x=>pct(x.role_share),t:'Snap share in his last two games'},{k:'drop',h:'Drop',l:1},{k:'why',h:'Why',l:1,f:x=>`<div class="why">${esc(x.why)}</div>`}],{})}</div>
  ${L.stashes&&L.stashes.length?`<div class="card"><h2>Injured stashes</h2><p class="sub">Free agents worth a bench spot for later, not help this week.</p>${table(L.stashes,[{k:'name',h:'Player',l:1,f:nm},{k:'exp_missed',h:'Games out',f:x=>f1(x.exp_missed)},{k:'proj_ppg',h:'Proj when back',f:x=>f1(x.proj_ppg)},{k:'ros_value',h:'ROS value',f:x=>f0(x.ros_value)},{k:'inj_detail',h:'Status',l:1,f:x=>`<div class="why">${esc(x.inj_detail||'')}</div>`}],{})}</div>`:''}
  <div class="card"><h2>Best available by position</h2><p class="sub">Healthy and playing this week. Injured free agents are in the stash list above.</p>${['QB','RB','WR','TE'].map(ps=>{const r=P.filter(p=>p.position===ps&&!p.owner_name&&p.ros_games>0&&(p.exp_missed||0)<1&&(p.play_prob==null||p.play_prob>=0.5||p.on_bye)).slice(0,5);return `<p style="margin:8px 0 2px"><b>${ps}</b></p>`+r.map(p=>`<div class="p" style="cursor:pointer" onclick="detail('${p.player_id}')">${nm(p)} <span class="mute">${f1(p.proj_ppg)} proj · ${ps}${f0(p.own_pos_rank)}</span></div>`).join('')}).join('')}</div>`;
 },
 trades(){
  if(!L)return noLeague();
  const Pn=L.partners||{mine:{needs:[],ranks:{},surplus:[]},teams:[]}, me=Pn.mine, n=L.team.strength.length;
  const chip=(ps,rank)=>`<span class="tag ${rank>n*2/3?'O':rank<=n/3?'U':'S'}" style="margin:2px">${ps} ${ord(rank)}</span>`;
  const list=a=>a&&a.length?a.join(', '):'<span class="mute">none</span>';
  const partners=Pn.teams.map(t=>`<tr><td class="l"><b>${esc(t.team)}</b></td><td class="l">${['QB','RB','WR','TE'].map(ps=>chip(ps,t.ranks[ps])).join('')}</td>
     <td class="l">${t.fills_your_need.length?`<span class="good">${t.fills_your_need.join(', ')}</span>`:'<span class="mute">—</span>'}</td>
     <td class="l">${t.you_fill_their_need.length?`<span class="good">${t.you_fill_their_need.join(', ')}</span>`:'<span class="mute">—</span>'}</td>
     <td>${'●'.repeat(Math.round(t.fit))||'<span class="mute">·</span>'}</td></tr>`).join('');
  const view=g=>g>=0.5?['U','They should like it']:g>=-0.15?['S','Fair in their eyes']:['O','Tough sell'];
  const ideas=L.trade_ideas.map((i,k)=>{const [vc,vt]=view(i.their_gain_week_mkt);return `<div class="idea">
     <div class="idea-top"><b>${esc(i.team)}</b><span class="tag ${vc}">${vt}</span></div>
     <div class="trade"><div><small>You give</small><br>${i.give.map((g,j)=>`${pos(i.give_pos[j])}<b>${esc(g)}</b>`).join('<br>')}</div><div class="arrow">⇄</div>
       <div><small>You get</small><br>${i.get.map((g,j)=>`${pos(i.get_pos[j])}<b>${esc(g)}</b> ${verdict(i.get_verdicts[j])}`).join('<br>')}</div></div>
     <div class="idea-nums"><span>You <b class="good">${sgn(i.my_gain_ros)} pts</b> <span class="mute">(${sgn(i.my_gain_week)}/wk)</span></span>
       <span>Them <b class="${i.their_gain_week_mkt>=0?'good':'bad'}">${sgn(i.their_gain_ros_mkt)}</b> <span class="mute">by consensus · ${sgn(i.their_gain_week*WKS)} by ours</span></span></div>
     ${i.why?`<p class="why" style="margin:6px 0 8px">${esc(i.why)}</p>`:''}
     <a class="btn" onclick="openTrade(${k})">Open in trade analyzer →</a></div>`}).join('');
  return `<div class="card"><h2>Your team's needs</h2><p class="sub">Where your starting lineup ranks in the league by position. Red is a need, green is a strength.</p>
     <div>${['QB','RB','WR','TE'].map(ps=>chip(ps,me.ranks[ps]||0)).join('')}</div>
     <p class="sub" style="margin:10px 0 0">Needs: <b>${list(me.needs)}</b> · Tradeable surplus (bench players who'd start elsewhere): <b>${list(me.surplus)}</b></p></div>
  <div class="card"><h2>Trade partners</h2><p class="sub">Every team's position ranks, whether their bench can fill your needs, and whether yours can fill theirs. More dots = better fit.</p>
     ${`<div class="tw"><table><thead><tr><th class="l">Team</th><th class="l">Their ranks</th><th class="l">Can fill your need at</th><th class="l">You can fill theirs at</th><th>Fit</th></tr></thead><tbody>${partners}</tbody></table></div>`}</div>
  <div class="card"><h2>Trade ideas</h2><p class="sub">Each idea improves your team (starting lineup plus handcuff insurance) using this app's projections, and it does not weaken their lineup by consensus, which is how they'll judge it. Ideas that fill a need on both sides come first.</p>
     <div class="ideas">${ideas||'<p class="mute">No trades clear both bars right now.</p>'}</div></div>
  <div class="card"><h2>Buy low</h2><p class="sub">On other rosters, and we rate them well above consensus.</p>${table(L.trades.buy_low,[{k:'name',h:'Player',l:1,f:nm},{k:'owner_name',h:'Team',l:1},{k:'proj_ppg',h:'Proj',f:x=>f1(x.proj_ppg)},{k:'rank_gap',h:'Us / mkt',f:x=>`${x.position}${f0(x.own_pos_rank)} / ${x.position}${f0(x.consensus_pos_rank)}`},{k:'gap_ppg',h:'Edge/g',f:x=>`<span class="good">${sgn(x.gap_ppg)}</span>`}],{sort:'gap_ppg'})}</div>
  <div class="card"><h2>Sell high</h2><p class="sub">Your players the market likes more than we do.</p>${table(L.trades.sell_high,[{k:'name',h:'Player',l:1,f:nm},{k:'proj_ppg',h:'Proj',f:x=>f1(x.proj_ppg)},{k:'rank_gap',h:'Us / mkt',f:x=>`${x.position}${f0(x.own_pos_rank)} / ${x.position}${f0(x.consensus_pos_rank)}`},{k:'gap_ppg',h:'Edge/g',f:x=>`<span class="bad">${sgn(x.gap_ppg)}</span>`},{k:'note',h:'Note',l:1,f:x=>`<div class="why">${esc(x.note)}</div>`}],{})}</div>`;
 },
 value(){
  const u=P.filter(p=>p.verdict==='Undervalued').sort((a,b)=>b.gap_ppg-a.gap_ppg), o=P.filter(p=>p.verdict==='Overvalued').sort((a,b)=>a.gap_ppg-b.gap_ppg);
  const g=P.filter(p=>p.note&&p.note.startsWith('Star guardrail'));
  const cols=[{k:'name',h:'Player',l:1,f:nm},{k:'proj_ppg',h:'Proj',f:x=>f1(x.proj_ppg)},{k:'own_pos_rank',h:'Us',f:x=>x.position+f0(x.own_pos_rank)},{k:'consensus_pos_rank',h:'Mkt',f:x=>x.position+f0(x.consensus_pos_rank)},{k:'gap_ppg',h:'Edge/g',f:x=>`<span class="${x.gap_ppg>0?'good':'bad'}">${sgn(x.gap_ppg)}</span>`},{k:'owner_name',h:'Rostered',l:1,f:x=>esc(x.owner_name||'FA')}];
  return `<div class="card"><h2>Undervalued</h2><p class="sub">We project at least 1.5 more points per game than the consensus rank implies.</p>${table(u,cols,{})}</div>
  <div class="card"><h2>Overvalued</h2><p class="sub">We project at least 1.5 fewer points per game than consensus.</p>${table(o,cols,{})}</div>
  <div class="card"><h2>Star guardrail</h2><p class="sub">Proven stars off to slow starts with normal health and role. Our model dipped a bit, but we don't call them overvalued; history says they bounce back.</p>${table(g,cols,{})}</div>`;
 },
 rankings(){
  const id='rk';setTimeout(()=>drawRank(),0);
  return `<div class="card"><div class="row chips" id="pf">${['ALL','QB','RB','WR','TE'].map((x,i)=>`<button class="${i?'':'on'}" data-p="${x}">${x}</button>`).join('')}</div>
  <div class="row"><input id="q" placeholder="Search player or team" style="flex:1;min-width:160px"><select id="grp"><option value="proj">Projection</option><option value="use">Usage</option><option value="rz">Red zone</option><option value="prod">Production</option><option value="adv">Advanced (routes)</option><option value="game">This week's game</option></select><label class="mute"><input type="checkbox" id="fa"> Free agents only</label></div><div id="${id}"></div>
  <p class="sub" style="margin-top:8px">Tap any player for details. <a href="rankings.csv" style="color:var(--acc)">Download CSV</a></p></div>`;
 },
 injuries(){
  const qbc=(D.qb_changes||[]).filter(q=>Math.abs(q.factor-1)>=0.01);
  const rel=p=>p.own_pos_rank<=60||p.owner_name||p.fill_in_for;
  const game=P.filter(p=>['LEFT GAME','RETURNED','SNAPS DOWN'].includes(p.inj_status)&&rel(p)).sort((a,b)=>(b.exp_missed||0)-(a.exp_missed||0)||b.ros_value-a.ros_value);
  const all=P.filter(p=>p.inj_status&&rel(p)).sort((a,b)=>b.ros_value-a.ros_value);
  const feeds=Object.entries(D.injury_feeds||{}).map(([k,v])=>`<span class="tag ${/unavailable/.test(v)?'O':'U'}" style="margin:2px">${esc(k)}: ${esc(v)}</span>`).join(' ');
  const fills=(D.fill_ins||[]).map(f=>{const p=byId[f.fill_in_id];return `<div style="padding:6px 0;border-bottom:1px dashed var(--line)">${pos(f.position)}<b>${esc(f.fill_in)}</b> <span class="mute">${esc(f.team)}</span> took over for <b>${esc(f.injured)}</b> <span class="mute">(${f.plays} plays after the injury)</span>${p?` · <a style="color:var(--acc);cursor:pointer" onclick="detail('${p.player_id}')">${p.owner_name?'on '+esc(p.owner_name):'free agent'}</a>`:''}</div>`}).join('');
  const cols=[{k:'name',h:'Player',l:1,f:nm},{k:'inj_detail',h:'Detail',l:1,f:x=>`<div class="why">${esc(x.inj_detail)}</div>`},{k:'play_prob',h:'Play next wk',f:x=>playOdds(x)},{k:'exp_missed',h:'Exp. missed',f:x=>f1(x.exp_missed)},{k:'owner_name',h:'Rostered',l:1,f:x=>esc(x.owner_name||'FA')},{k:'inj_updated',h:'Source',l:1,f:x=>`${esc(x.inj_source)} <span class="mute">${ago(x.inj_updated)}</span>`}];
  return `<div class="card"><h2>Hurt in the last game</h2><p class="sub">Read straight from play-by-play within hours of each game, days before the official injury report. "Left game" means he never came back; how serious it is shows up once ESPN, Sleeper or the practice report weigh in.</p>${table(game,cols,{})}</div>
  ${fills?`<div class="card"><h2>Who stepped in</h2><p class="sub">The teammate who took the injured player's work for the rest of the game. Often the week's best waiver add.</p>${fills}</div>`:''}
  ${depthCard()}
  <div class="card"><h2>Every injury status</h2><p class="sub">The most serious current signal wins; tap a player to see every source. Stale info is dropped automatically (e.g. last week's "Questionable" once he's played, or an in-game injury once the next official report is out).</p>${table(all,[...cols.slice(0,1),{k:'inj_status',h:'Status',l:1,f:x=>inj(x)},...cols.slice(1)],{})}</div>
  ${qbc.length?`<div class="card"><h2>Quarterback changes</h2><p class="sub">When a starting QB goes down, his pass catchers lose value too. The backup is rated on his own history, and everyone who catches passes from him is adjusted by the gap.</p>
  ${qbc.map(q=>`<div style="padding:6px 0;border-bottom:1px dashed var(--line)"><b>${esc(q.team)}</b>: ${esc(q.qb)} in for ${esc(q.was)} <span class="mute">(${f1(q.pass_ppg)} passing pts/start)</span> · <b class="${q.factor<1?'bad':'good'}">${sgn((q.factor-1)*100)}%</b> <span class="mute">for his receivers</span></div>`).join('')}</div>`:''}
  <div class="card"><h2>Sources this update</h2><p>${feeds}</p>
  <p class="sub" style="margin-top:8px">Lines, depth charts and stat pages: ${[['Vegas lines',D.lines_status],...Object.entries(D.depth_status||{}),...Object.entries(D.web_status||{})].filter(x=>x[1]).map(([k,v])=>`<span class="tag ${/unavailable/.test(v)||(/failed/.test(v)&&!/direct|Firecrawl|recent/.test(v))?'O':/failed|saved copy|held back/.test(v)?'I':'U'}" style="margin:2px">${esc(k)}: ${esc(v)}</span>`).join(' ')}</p>
  ${Object.keys(D.data_feeds||{}).length?`<p class="sub" style="margin-top:8px">Core data fallbacks: ${Object.entries(D.data_feeds).map(([k,v])=>`<span class="tag ${/last saved|unavailable/.test(v)?'I':'S'}" style="margin:2px">${esc(k)}: ${esc(v)}</span>`).join(' ')}</p>`:''}</div>`;
 },
 analyzer(){
  if(!L)return noLeague();
  const teams=L.team.strength;
  if(TA.a==null){TA.a=L.team.team_id;TA.b=(teams.find(t=>t.team_id!==TA.a)||{}).team_id}
  setTimeout(taRender);
  return `<div class="card"><h2>Trade analyzer</h2><p class="sub">Pick the players on each side. Every number is rest-of-season starting-lineup points using this app's projections, with injuries, byes and roster fit included.</p>
  <div class="split">
    <div><select id="taA" style="width:100%"></select><div id="taAr" class="taList"></div></div>
    <div><select id="taB" style="width:100%"></select><div id="taBr" class="taList"></div></div>
  </div></div>
  <div class="card"><h2>Verdict</h2><div id="taOut"></div>
  <p class="sub" style="margin-top:10px"><a style="color:var(--acc);cursor:pointer" onclick="TA.give.clear();TA.get.clear();taRender()">Clear selections</a></p></div>`;
 },
 method(){
  return `<div class="card method"><h2>How the ratings work</h2>
  <h3>1. History (the prior)</h3><p>Each player's last three seasons, weighted 50/33/17 toward the most recent, counting only games where he played at least 20% of snaps. Rookies start from how past rookies at the same position and draft round scored. Age curves trim older RBs and WRs slightly.</p>
  <h3>2. This season</h3><p>Actual points blended 50/50 with <b>expected points (xFP)</b>: every target and carry is valued by how many fantasy points the league average gets from that exact opportunity (depth of target, field position, red zone). Workload is far more stable than touchdowns, so xFP tells us whether a hot or cold start is real. Recent games count more: each week back is worth 80% of the one after it, so a player trending up or down moves quickly rather than being averaged flat. Games a player sat while healthy count as zeros.</p>
  <p>This season's share of a projection grows automatically every week: it is the number of games played against the weight on history and draft day. For a typical player that is roughly 20-30% after two games, about half by week 6, and most of the projection by week 10.</p>
  <h3>3. Draft day</h3><p>Where a player went in your league's draft is what the market thought of him in August, and that view carries information the box scores cannot show yet. His pick is mapped onto our own points curve at his position, so "the fifth tight end off the board" becomes the points per game of our fifth-best tight end. It counts as about 4 games of evidence in week 1 and fades to nothing by week 8, so it steadies early-season projections without overriding what actually happens on the field. Undrafted players and later pickups fall back to ESPN's preseason ranking.</p>
  <h3>4. Blending (why one bad week doesn't sink a star)</h3><p>History counts as a number of "phantom games" (roughly 2 to 6 depending on position and how much track record there is; one full recent season counts as a complete record). After two weeks, this season is only about 25-35% of a proven player's projection; by mid-season it's the majority. If he has <b>lost</b> snaps (down 15+ points), history is trusted half as much, because a real role change should move fast. If he has <b>gained</b> snaps, history keeps its weight and the prior is nudged up instead, since his old numbers came from a smaller job and understate him. Tested on the 2025 season, this blend predicted rest-of-season scoring better than history alone, this season alone, or usage alone, at weeks 2, 4 and 8.</p>
  <h3>5. Role ceiling (what stops empty recommendations)</h3><p>Fantasy points come from touches and targets, not reputation. Every game a player was active for counts toward his average, including a 5% snap cameo, because that IS the evidence he has no role. On top of that, his value above replacement is scaled by the job he currently holds: snap share in his last two games, or touches and targets per game against what a starter at his position gets, whichever is kinder. A former starter now playing 10% of snaps keeps about a tenth of his edge; a committee back with 20 carries on few snaps keeps all of it. Waiver suggestions also have to clear a floor: real recent usage, a role that is growing, or a job just inherited from an injured starter.</p>
  <h3>6. Injuries</h3><p><b>Nobody is marked injured on commentary alone.</b> A status must come from ESPN's injury designation, Sleeper, the official report, your league or a roster move, or from in-game evidence; a write-up with no designation only counts if it says outright that he will miss time. ESPN listing a player as "Active" clears older statuses. <b>How signals are weighed:</b> (1) this week's final injury report (Friday's game designations) is the final word, and not being on it means he is fine. Practice participation earlier in the week is not: "limited on Thursday" means nothing has been decided, so a fresher designation from a beat reporter or ESPN wins until the final report is in, and a reporter's "ruled out for Week 5" or "questionable for Week 5" counts as a call on that game; (2) multi-week news (IR, "out 4-6 weeks", season-ending) holds until something newer says he is cleared or activated; (3) an explicit timeline or ESPN return date is definitive, and so is the injury itself: feeds often say only "Knee - ACL: Surgery", so known injuries carry their typical recovery (ACL, Achilles and torn tendons end the season; Lisfranc about 10 games; leg or ankle fractures about 8; collarbone 7; tightrope surgery 6; meniscus 5; MCL 3). As a cross-check, a hurt starter whom the experts still rank long-term (dynasty) but have dropped from rest-of-season rankings is treated as out for the season; (4) otherwise the newest information wins. A live feed still showing "Out" early in the week usually describes the game just played, so before the new report it counts as "status TBD" (about 45% to play) rather than a certain absence, and newer mild news ("minor sprain", "hoping to play", "expected to play") caps the risk. A starter who vanishes early from a game with no injury logged is caught from snap counts and play-by-play. </p><p>Nine sources, fastest first: play-by-play (who got hurt and whether he came back, within hours of the game), snap counts, Rotoworld/NBC player news (blurbs written from beat reporters, coaches' press conferences and practice reports, usually within minutes, each citing the reporter), ESPN's injury desk (status, return date, news comment), Sleeper, ESPN news headlines, your league's ESPN designations, the official injury and practice reports, and NFL roster moves. News text is read for timelines ("2-4 weeks", "season-ending", "week-to-week", "high-ankle sprain", "surgery") and negations ("avoided a torn ACL"). The most serious current signal sets the status; a newer "full practice" or "cleared" overrides older short-term worries. Games a player left injured are left out of his scoring average.</p>
  <h3>7. Rest of season</h3><p>Projected points per game × games left, minus byes and expected missed games from injuries (IR ≈ 4 games, Out 1, Doubtful 0.8, Questionable 0.25, left game injured 1 with a 50% chance to miss next week, or the injury desk's return date and timeline when there is one). </p>
  <h3>7b. Next week's game: Vegas</h3><p>Next week's projection is scaled by the team's <b>implied total</b> from the betting line (over/under ÷ 2 minus its spread ÷ 2) against that team's usual implied total this season: (this week ÷ usual)<sup>e</sup>, with e = 0.5 for QBs, 0.4 for RBs and WRs and 0.6 for TEs, capped at ±20%. Measured on 2022-25 (fit on 2022-24, checked on 2025), this cut weekly projection errors at every position, and once it was in, the old "points allowed by this defense" factor added nothing, so that factor is now only a fallback for games with no line yet. Lines also already price in part of a backup quarterback, so when one is posted the separate QB adjustment is trimmed by the share Vegas already captures (about 25% for WRs, 50% for TEs, 60% for RBs). Lines come from ESPN's scoreboard (DraftKings) with nflverse as backup; the lineup shows each team's total next to the opponent, green when it is well above the team's usual and red when well below.</p>
  <h3>8. Market vs. us</h3><p>The consensus rating is a weighted average of FantasyPros rest-of-season consensus (60%, itself 100+ experts), ESPN's projections (25%) and FantasyPros weekly consensus (15%). Each consensus rank is turned into points using our own projection curve, so the gap is in real points. "Undervalued/Overvalued" needs a gap of at least 1.5 points per game and a meaningful rank difference. <b>Star guardrail:</b> a proven star can't be called overvalued unless something structural changed (injury, lost snaps, new team).</p>
  <h3>9. Who is throwing the ball</h3><p>Each team's reference quarterback is the intended starter: whoever opened the season, unless he has since been healthy and benched. Every quarterback is graded on passing points per start only (his own rushing does nothing for his receivers), blending his history with this season. When the intended starter is out, his receivers move by (backup ÷ starter)<sup>0.55</sup>. That exponent was measured from every backup start in 2023-25: top receivers keep about 84% of their output with a backup at 70% of the starter's passing quality, and about 74% with a much worse one. The adjustment is capped between −40% and +12%, and it is always relative to the starter, so it is exactly zero when he plays. Next week uses the chance the starter misses that game; rest of season uses the share of remaining games he is expected to miss. Tight ends take 90% of the adjustment and running backs 35%. A backup who inherits the job stops being judged by his old bench role, so his own projection reflects starting.</p>
  <h3>10. Handcuffs</h3><p>Each team's backup running back is tagged as the handcuff to its starter: whoever actually took over when the starter left a game, otherwise the next healthy back on the current depth chart, otherwise the next back by workload. When the starter is likely out <i>this</i> week, the handcuff's weekly projection moves toward that fill-in rate in proportion to the chance the starter sits, and he is flagged "next man up" (tight ends get the flag from the depth chart too, without the projection change, since there is no comparable measurement for them). Measured over 2023-25: RB1s miss about 16% of games, and when they do, the backup scores 70-87% of the starter's output. So a handcuff is worth his fill-in rate times the games his starter is expected to miss (current injuries plus that normal rate). Who owns him matters: if you also own the starter, he fills <i>your</i> hole, so he is measured against your next-best bench option; if you don't, he only counts when his fill-in rate would beat your weakest starter. That insurance is part of every team's value in waivers (a handcuff to your own starter is never suggested as a drop), the trade ideas and the trade analyzer.</p>
  <h3>11. Trade ideas</h3><p>Every 1-for-1, 2-for-1 and 1-for-2 swap with every team is scored by what it does to <b>both</b> teams' best lineups plus handcuff insurance, not by player values in isolation, so a player is only worth what he adds to the lineup that team would actually field. An idea is shown only if it improves your team by our numbers and does not weaken their lineup by consensus projections (how they will judge it). Packages with a pointless throw-in are dropped. Ideas that fill a weak spot on both sides rank first, and the trade partners table shows each team's position ranks and whether their bench can fix your needs and vice versa. The trade analyzer runs exactly the same math, so opening an idea there gives identical numbers.</p>
  <h3>12. Trade analyzer</h3><p>Pick any two teams and any set of players. For each side it rebuilds that team's best starting lineup before and after the trade, so a player only counts for what he adds to the lineup you would actually field: a third good running back is worth much less than a first one. It adds a small credit for bench depth, notes which lineup slots move, and counts roster spots gained or lost in an uneven package. Then it re-runs the whole calculation using consensus ranks instead of ours, which approximates how the other manager sees the deal, and that gap is what tells you whether an offer is likely to be accepted.</p>
  <h3>13. Depth charts</h3><p>Two sources: Ourlads (all 32 teams on one page, maintained by hand and updated after each game and on transactions), and ESPN's depth charts as snapshotted twice a day by nflverse. Ourlads is used when its team page was updated in the last 10 days, ESPN otherwise. A "move" is measured within one source only (Ourlads now vs its own copy from 3-10 days ago; ESPN now vs a week ago), because the two often list backups in a different order, and comparing them would invent promotions; a move is shown only if the current chart agrees. Moves appear on the Injuries tab, in player details, and as a waiver reason, and a promoted backup can clear the waiver floor before his snaps catch up. Depth charts decide who the handcuff is; they don't change projections directly (there is no clean history to measure how much a depth-chart move is worth).</p>
  <h3>14. Advanced stats</h3><p>From PlayerProfiler's free player pages: routes run and route participation (share of team dropbacks he ran a route on), targets and yards per route run, first-read target share, separation, slot rate, and for backs opportunity share and weighted opportunities. They are shown in player details and the Rankings "Advanced" view, and used in waiver and trade explanations ("routes up: 88% of dropbacks the last two games, was 60%"). They do not change projections: they exist only for this season, so there is no history to measure how much weight they deserve, and snaps, targets and expected points already capture most of a role. Pages refresh about weekly (PlayerProfiler updates advanced numbers mid-week), rostered players and top free agents first.</p>
  <h3>15. Where the web data comes from</h3><p>Every page (Ourlads, Rotoworld, PlayerProfiler, ESPN) is first requested directly, which is free. Some sites block cloud servers like GitHub's; for those, the page is fetched through <b>Firecrawl</b> (a real browser service) if a FIRECRAWL_API_KEY secret is set. Firecrawl use is metered: one credit per page, a monthly cap (800 of the free plan's 1,000 by default), at most 40 a run, low-priority pages only while most of the month's budget is left, and PlayerProfiler capped at 200 a month. If both routes fail, the last good copy is used for a few days. The Sources card on the Injuries tab shows how each page arrived and the month's Firecrawl usage.</p>
  <h3>16. Your league</h3><p>Value over replacement uses your league's real size and lineup slots. Waiver scores measure how much a player improves your best lineup. Trade ideas must improve your lineup by our numbers while being fair or better for the other team by consensus value, so they're offers that can actually get accepted.</p>
  <p class="mute">Replacement level (pts/game): ${Object.entries(D.replacement).map(([k,v])=>k+' '+f1(v)).join(' · ')} · Reception points: ${D.rec_pts}</p></div>`;
 }
};
function depthCard(){
  const mv=(D.depth_moves||[]).map(m=>Object.assign({},m,{p:byId[m.player_id]})).filter(m=>m.p&&(m.p.own_pos_rank<=80||m.p.owner_name||m.direction==='up'))
    .sort((a,b)=>(a.direction==='up'?0:1)-(b.direction==='up'?0:1)||(b.p.ros_value||0)-(a.p.ros_value||0));
  if(!mv.length)return '';
  return `<div class="card"><h2>Depth chart moves</h2><p class="sub">Players who moved up or down their team's depth chart in the last week (Ourlads vs its earlier copy, or ESPN vs a week ago). A backup moving up is often the first sign of a new role, before the snaps show it.</p>
  ${mv.map(m=>`<div style="padding:6px 0;border-bottom:1px dashed var(--line);cursor:pointer" onclick="detail('${m.player_id}')">${nm(m.p)} <span class="${m.direction==='up'?'good':'bad'}">${m.direction==='up'?'↑':'↓'} ${esc(m.from)} → ${esc(m.to)}</span> <span class="mute">· ${esc(m.source)} · ${m.p.owner_name?'on '+esc(m.p.owner_name):'free agent'}</span></div>`).join('')}</div>`;
}
function ord(n){return n+(['th','st','nd','rd'][(n%100>10&&n%100<14)?0:n%10<4?n%10:0]||'th')}
function noLeague(){return `<div class="banner">League not connected: ${esc(D.league_error||'no ESPN credentials set')}. Rankings, value board and injuries still work. See the README to connect your ESPN league.</div>`}

function drawRank(){
  const box=document.getElementById('rk');if(!box)return;
  const on=document.querySelector('#pf .on').dataset.p, q=$('#q').value.toLowerCase(), g=$('#grp').value, fa=$('#fa').checked;
  const r=P.filter(p=>(on==='ALL'||p.position===on)&&(!q||(p.name+' '+p.team).toLowerCase().includes(q))&&(!fa||!p.owner_name)).slice(0,300);
  const G={proj:[{k:'vor_ppg',h:'VOR/g',f:x=>sgn(x.vor_ppg),t:'Points per game above replacement'},{k:'own_pos_rank',h:'Us',f:x=>x.position+f0(x.own_pos_rank)},{k:'consensus_pos_rank',h:'Mkt',f:x=>x.consensus_pos_rank?x.position+f0(x.consensus_pos_rank):'–'},{k:'verdict',h:'',f:x=>verdict(x.verdict)},{k:'prior_ppg',h:'Hist',f:x=>f1(x.prior_ppg)},{k:'cur_ppg',h:'This yr',f:x=>f1(x.cur_ppg)},{k:'owner_name',h:'Rostered',l:1,f:x=>esc(x.owner_name||'')}],
   use:[{k:'snap_pct',h:'Snap%',f:x=>pct(x.snap_pct)},{k:'target_share',h:'Tgt%',f:x=>pct(x.target_share)},{k:'air_yards_share',h:'Air%',f:x=>pct(x.air_yards_share)},{k:'wopr',h:'WOPR',f:x=>f1(x.wopr)},{k:'touches',h:'Touch',f:x=>f0(x.touches)},{k:'targets',h:'Tgt',f:x=>f0(x.targets)},{k:'carries',h:'Car',f:x=>f0(x.carries)},{k:'xfp_total',h:'xFP',f:x=>f1(x.xfp_total)}],
   rz:[{k:'rz_targets',h:'RZ tgt',f:x=>f0(x.rz_targets)},{k:'rz_tgt_share',h:'RZ tgt%',f:x=>pct(x.rz_tgt_share)},{k:'ez_targets',h:'EZ tgt',f:x=>f0(x.ez_targets)},{k:'rz_carries',h:'RZ car',f:x=>f0(x.rz_carries)},{k:'rz_rush_share',h:'RZ car%',f:x=>pct(x.rz_rush_share)},{k:'i10_carries',h:'In-10',f:x=>f0(x.i10_carries)},{k:'tds',h:'TD',f:x=>f0(x.tds)}],
   adv:[{k:'route_pct',h:'Route%',f:x=>x.route_pct==null?'–':Math.round(x.route_pct)+'%',t:'Share of team dropbacks he ran a route on (PlayerProfiler)'},{k:'routes_pg',h:'Rt/g',f:x=>f1(x.routes_pg)},{k:'tprr',h:'TPRR',f:x=>x.tprr==null?'–':Math.round(x.tprr)+'%',t:'Targets per route run'},{k:'yprr',h:'YPRR',f:x=>x.yprr==null?'–':(+x.yprr).toFixed(2),t:'Yards per route run'},{k:'fr_share',h:'1st read',f:x=>x.fr_share==null?'–':Math.round(x.fr_share)+'%',t:'First-read target share'},{k:'opp_share',h:'Opp%',f:x=>x.opp_share==null?'–':Math.round(x.opp_share)+'%',t:'RB: share of team RB opportunities'},{k:'depth_label',h:'Depth',l:1,f:x=>esc(x.depth_label||'')+(x.depth_dir?` <span class="${x.depth_dir==='up'?'good':'bad'}">${x.depth_dir==='up'?'↑':'↓'}</span>`:'')}],
   game:[{k:'opponent',h:'Opp',l:1,f:x=>x.on_bye?'BYE':esc(x.opponent||'')},{k:'imp_total',h:'Team total',f:x=>f1(x.imp_total),t:'Vegas implied points'},{k:'imp_avg',h:'Usual',f:x=>f1(x.imp_avg),t:'Team average implied total this season'},{k:'spread',h:'Spread',f:x=>x.spread==null?'–':sgn(x.spread)},{k:'game_factor',h:'Game ×',f:x=>x.game_factor==null||x.on_bye?'–':(+x.game_factor).toFixed(2),t:'Vegas factor (or matchup if no line yet)'},{k:'play_prob',h:'Play%',f:x=>playOdds(x)}],
   prod:[{k:'pts_total',h:'Pts',f:x=>f1(x.pts_total)},{k:'receptions',h:'Rec',f:x=>f0(x.receptions)},{k:'rec_yds',h:'RecYd',f:x=>f0(x.rec_yds)},{k:'rush_yds',h:'RuYd',f:x=>f0(x.rush_yds)},{k:'pass_yds',h:'PaYd',f:x=>f0(x.pass_yds)},{k:'tds',h:'TD',f:x=>f0(x.tds)},{k:'l3_ppg',h:'L3',f:x=>f1(x.l3_ppg)}]};
  box.innerHTML=table(r,[...RK,...G[g]],{sort:'ros_points'});
}
document.addEventListener('click',e=>{const b=e.target.closest('#pf button');if(b){document.querySelectorAll('#pf button').forEach(x=>x.classList.remove('on'));b.classList.add('on');drawRank()}});
document.addEventListener('input',e=>{if(['q','grp','fa'].includes(e.target.id))drawRank()});

// ---------------------------------------------------------------- team browser
let TV={id:null};
const SLOT_ORDER=['QB','RB','WR','TE','FLEX','OP','D/ST','K'];
const SLOT_FITS={QB:['QB'],RB:['RB'],WR:['WR'],TE:['TE'],FLEX:['RB','WR','TE'],OP:['QB','RB','WR','TE'],'D/ST':['D/ST'],K:['K']};
const wk2=p=>p.on_bye?'<span class="mute">bye</span>':f1(p.week_proj);
const others=tid=>((L.rosters||{})[String(tid)]||[]).filter(e=>e.pos==='K'||e.pos==='D/ST'||!byId[e.player_id]);
const espnSlot=tid=>{const m={};((L.rosters||{})[String(tid)]||[]).forEach(e=>{if(e.player_id)m[e.player_id]=e.slot});return m};

// Projected starters for the coming week, laid out the way a fantasy lineup reads.
function buildLineup(skill, extra){
  const slots=L.slots||Object.assign({},D.lineup,{'D/ST':1,K:1});
  const rows=skill.map(p=>({p,pos:p.position,v:p.week_proj||0,id:p.player_id}))
     .concat(extra.filter(e=>e.pos==='K'||e.pos==='D/ST').map(e=>({e,pos:e.pos,v:e.espn_week_proj||0,id:'x:'+e.name})));
  const used=new Set(), starters=[];
  for(const slot of SLOT_ORDER){for(let i=0;i<(slots[slot]||0);i++){
    const pick=rows.filter(r=>!used.has(r.id)&&SLOT_FITS[slot].includes(r.pos)).sort((a,b)=>b.v-a.v)[0];
    if(pick)used.add(pick.id); starters.push({slot,r:pick||null});}}
  const bench=rows.filter(r=>!used.has(r.id)).sort((a,b)=>(SLOT_ORDER.indexOf(a.pos)-SLOT_ORDER.indexOf(b.pos))||(b.v-a.v));
  const unrated=extra.filter(e=>e.pos!=='K'&&e.pos!=='D/ST');
  return {starters,bench,unrated,total:starters.reduce((t,s)=>t+(s.r?s.r.v:0),0)};
}
function lineupRow(slot,r,opts={}){
  const isNew=r&&r.p&&opts.newIds&&opts.newIds.has(r.p.player_id);
  if(!r)return `<tr class="lu-empty"><td class="lu-slot">${slot}</td><td class="l mute" colspan="6">Empty: no eligible player</td></tr>`;
  if(r.e)return `<tr><td class="lu-slot">${slot}</td><td class="l"><span class="pos">${r.e.pos}</span><b>${esc(r.e.name)}</b></td><td class="c-opp"></td><td>${r.e.espn_week_proj!=null?f1(r.e.espn_week_proj):'–'}</td><td class="mute c-ros">–</td><td class="l mute c-note" style="font-size:12px" title="ESPN's projection">ESPN</td><td class="c-ver"></td></tr>`;
  const p=r.p;
  return `<tr class="p${isNew?' lu-new':''}" data-id="${p.player_id}"><td class="lu-slot">${slot}</td>
    <td class="l">${nm(p)}${isNew?' <span class="tag S">NEW</span>':''}${p.hc_of?` <span class="tag ${opts.tid&&rosterOf(opts.tid).some(x=>x.player_id===p.hc_of)?'U':'S'}" title="Backup to ${esc(p.hc_of_name)}: about ${f1(p.hc_contingent)} pts/game if he sits">HC · ${esc((p.hc_of_name||'').split(' ').slice(-1)[0])}</span>`:''}</td>
    <td class="mute c-opp" style="font-size:12px" title="${LN[p.team]?'Vegas team total '+f1(LN[p.team].implied)+' (usually '+f1(LN[p.team].team_avg)+')':''}">${p.on_bye?'BYE':(p.opponent?'vs '+esc(p.opponent)+(LN[p.team]?` <span class="${LN[p.team].implied>=LN[p.team].team_avg+1.5?'good':LN[p.team].implied<=LN[p.team].team_avg-1.5?'bad':''}">${f1(LN[p.team].implied)}</span>`:''):'')}</td>
    <td><b>${wk2(p)}</b></td><td class="c-ros">${f1(ppw(p))}</td>
    <td class="l c-note" style="font-size:12px">${p.inj_status&&!['CLEARED','RETURNED'].includes(p.inj_status)?`<span class="${(p.play_prob||0)<0.5?'bad':'mute'}" title="chance to play next week">${p.on_bye?'':pct(p.play_prob)+' play'}</span>`:''}${p.qb_factor_week&&p.qb_factor_week<0.97?` <span class="bad">QB ${sgn((p.qb_factor_week-1)*100)}%</span>`:''}${p.next_up_for?` <span class="good" title="${esc(p.next_up_for)} likely out">next man up</span>`:''}${p.depth_dir?` <span class="${p.depth_dir==='up'?'good':'bad'}" title="Depth chart ${esc(p.depth_move||'')}">depth ${p.depth_dir==='up'?'↑':'↓'}</span>`:''}</td>
    <td class="c-ver">${verdict(p.verdict)}</td></tr>`;
}
function lineupHtml(skill, extra, opts={}){
  const lu=buildLineup(skill, extra);
  const head=`<tr><th class="l">Slot</th><th class="l">Player</th><th class="c-opp" title="Opponent and Vegas team total">Opp · total</th><th>Wk ${D.plan_week}</th><th class="c-ros">ROS/wk</th><th class="l c-note">Notes</th><th class="c-ver"></th></tr>`;
  const bench=lu.bench.map(r=>lineupRow(r.p&&espnSlot(opts.tid||0)[r.p.player_id]==='IR'?'IR':'BN',r,opts)).join('')
     + lu.unrated.map(e=>`<tr><td class="lu-slot">${e.slot==='IR'?'IR':'BN'}</td><td class="l"><span class="pos">${esc(e.pos)}</span>${esc(e.name)}</td><td class="c-opp"></td><td class="mute">–</td><td class="mute c-ros">–</td><td class="l mute c-note" style="font-size:12px">not rated</td><td class="c-ver"></td></tr>`).join('');
  return `<div class="tw"><table class="lineup"><thead>${head}</thead><tbody>
    ${lu.starters.map(s=>lineupRow(s.slot,s.r,opts)).join('')}
    <tr class="lu-total"><td class="lu-slot"></td><td class="l"><b>Projected starters</b></td><td class="c-opp"></td><td><b>${f1(lu.total)}</b></td><td class="c-ros"></td><td class="c-note"></td><td class="c-ver"></td></tr>
    <tr class="lu-div"><td colspan="7">Bench</td></tr>${bench||'<tr><td colspan="7" class="mute">No bench players.</td></tr>'}
  </tbody></table></div>`;
}
function wireRows(root){root.querySelectorAll('tr.p[data-id]').forEach(tr=>tr.onclick=()=>detail(tr.dataset.id))}

function tvRender(){
  const box=document.getElementById('tvBody'); if(!box)return;
  const sel=document.getElementById('tvSel'); if(sel)sel.value=TV.id;
  const mine=TV.id===L.team.team_id;
  const info=(L.team.strength||[]).find(t=>t.team_id===TV.id)||{};
  const roster=rosterOf(TV.id), extra=others(TV.id), n=L.team.strength.length;
  const strengths=['QB','RB','WR','TE'].map(ps=>{
    const v=info[ps+'_ppw']||0, avg=L.team.strength.reduce((t,x)=>t+(x[ps+'_ppw']||0),0)/n;
    const rank=L.team.strength.filter(x=>(x[ps+'_ppw']||0)>v).length+1;
    return `<div class="stat ${rank<=3?'st-good':rank>n-3?'st-bad':''}"><span>${ps} · ${ord(rank)} of ${n}</span><b>${f1(v)}</b><span>vs avg ${f1(avg)} pts/wk</span></div>`}).join('');
  const hurt=roster.filter(p=>p.inj_status&&!['CLEARED','RETURNED'].includes(p.inj_status)).sort((a,b)=>(b.exp_missed||0)-(a.exp_missed||0));
  const under=roster.filter(p=>p.verdict==='Undervalued').sort((a,b)=>b.gap_ppg-a.gap_ppg);
  const over=roster.filter(p=>p.verdict==='Overvalued').sort((a,b)=>a.gap_ppg-b.gap_ppg);
  // lineup changes: ESPN's current lineup vs the projected best one (your team only)
  let moves='';
  if(mine){
    const lu=buildLineup(roster,extra), start=new Set(lu.starters.filter(s=>s.r&&s.r.p).map(s=>s.r.p.player_id)), es=espnSlot(TV.id);
    const ins=roster.filter(p=>start.has(p.player_id)&&['BN','IR'].includes(es[p.player_id]));
    const outs=roster.filter(p=>!start.has(p.player_id)&&es[p.player_id]&&!['BN','IR'].includes(es[p.player_id]));
    if(ins.length||outs.length)moves=`<div class="card"><h2>Lineup changes for week ${D.plan_week}</h2><p class="sub">Your current ESPN lineup vs. the projected best one.</p>
      ${ins.map(p=>`<div class="mv"><b class="good">Start</b> ${nm(p)} <span class="mute">${wk2(p)} proj</span></div>`).join('')}
      ${outs.map(p=>`<div class="mv"><b class="bad">Bench</b> ${nm(p)} <span class="mute">${wk2(p)} proj</span></div>`).join('')}</div>`;
  }
  const pl=(ps,cls)=>ps.map(p=>`<div class="p mv" onclick="detail('${p.player_id}')">${nm(p)} <span class="mute">${p.position}${f0(p.own_pos_rank)} us / ${p.position}${f0(p.consensus_pos_rank)} market · <span class="${cls}">${sgn(p.gap_ppg)}/g</span></span></div>`).join('')||'<p class="mute">None.</p>';
  box.innerHTML=`
  <div class="card"><h2>${esc(info.name||'')}${mine?' <span class="tag S">You</span>':''}</h2>
    <p class="sub">${esc(info.record||'')} · power rank ${info.power_rank} of ${n} · ${f1(info.lineup_ppw)} projected pts/week rest of season</p>
    <div class="grid">${strengths}</div></div>
  ${moves}
  ${hurt.length?`<div class="card"><h2>Injury watch</h2>${hurt.map(p=>`<div class="p mv" onclick="detail('${p.player_id}')">${nm(p)} <span class="mute">${p.on_bye?'on bye':pct(p.play_prob)+' to play next week'}</span><div class="why">${esc(p.inj_detail||'')} · ${esc(p.inj_source||'')} ${ago(p.inj_updated)}</div></div>`).join('')}</div>`:''}
  <div class="card"><h2>Projected lineup, week ${D.plan_week}</h2><p class="sub">Best lineup by next week's projections: injuries, byes, matchups and quarterback situation included. Kickers and defenses use ESPN's projection.</p>
    <div id="tvLineup">${lineupHtml(roster,extra,{tid:TV.id})}</div></div>
  <div class="card"><div class="split">
    <div><h2 style="margin-bottom:8px">${mine?'Hold':'Buy-low targets'}</h2><p class="sub">${mine?'Your':'Their'} players we rate above the market.</p>${pl(under,'good')}</div>
    <div><h2 style="margin-bottom:8px">${mine?'Sell-high candidates':'What they may overrate'}</h2><p class="sub">${mine?'Your':'Their'} players the market likes more than we do.</p>${pl(over,'bad')}</div>
  </div>${mine?'':`<p class="sub" style="margin:14px 0 0"><a style="color:var(--acc);cursor:pointer;font-weight:600" onclick="TA.a=L.team.team_id;TA.b=${TV.id};TA.give.clear();TA.get.clear();go('analyzer')">Build a trade with ${esc(info.name||'this team')} →</a></p>`}</div>`;
  wireRows(box);
}
document.addEventListener('change',e=>{if(e.target.id==='tvSel'){TV.id=+e.target.value;tvRender()}});

// ---------------------------------------------------------------- trade analyzer
const SLOTS=['QB','RB','WR','TE','FLEX','OP'];
const FITS={QB:['QB'],RB:['RB'],WR:['WR'],TE:['TE'],FLEX:['RB','WR','TE'],OP:['QB','RB','WR','TE']};
const WKS=D.weeks_left||1;
const ppw=p=>(p.ros_points||0)/WKS, mppw=p=>((p.market_ros_points!=null?p.market_ros_points:p.ros_points)||0)/WKS;
function lineup(rows,val){
  const pool=rows.slice().sort((a,b)=>val(b)-val(a)); const used=new Set(); let total=0; const filled={};
  for(const slot of SLOTS){for(let i=0;i<(D.lineup[slot]||0);i++){
    const pick=pool.find(r=>!used.has(r.player_id)&&FITS[slot].includes(r.position));
    if(pick){used.add(pick.player_id);total+=val(pick);(filled[slot]=filled[slot]||[]).push(pick)}}}
  return {total,used,filled};
}
const rosterOf=tid=>P.filter(p=>p.owner===tid);
// handcuff insurance: same rules as the Python engine (model.handcuff_bonus)
function hcBonus(rows,val){
  const ids=new Set(rows.map(r=>r.player_id)), lu=lineup(rows,val); let tot=0; const notes=[];
  for(const h of rows){
    if(!h.hc_of||h.hc_contingent==null)continue;
    const own=ids.has(h.hc_of), flex=r=>['RB','WR','TE'].includes(r.position);
    const base=own ? Math.max(0,...rows.filter(r=>!lu.used.has(r.player_id)&&r.player_id!==h.player_id&&flex(r)).map(val))
                   : Math.min(...rows.filter(r=>lu.used.has(r.player_id)&&flex(r)).map(val).concat([99]));
    const gain=Math.max(0,h.hc_contingent-(base===99?0:base))*(h.hc_out_games||0);
    if(gain>0.05){tot+=gain;notes.push({name:h.name,starter:h.hc_of_name,own,pts:gain})}
  }
  return {ppw:tot/WKS,notes};
}
const teamValue=(rows,val)=>lineup(rows,val).total+hcBonus(rows,val).ppw;
function posStrength(rows,val){const lu=lineup(rows,val),o={QB:0,RB:0,WR:0,TE:0};rows.forEach(r=>{if(lu.used.has(r.player_id)&&o[r.position]!=null)o[r.position]+=val(r)});return o}
function leagueRanks(over){ // over: {team_id: rows} replacing those teams' rosters
  const teams=(L.team.strength||[]).map(t=>t.team_id), st={};
  teams.forEach(t=>st[t]=posStrength(over[t]||rosterOf(t),ppw));
  const r={};teams.forEach(t=>r[t]={});
  ['QB','RB','WR','TE'].forEach(ps=>[...teams].sort((a,b)=>st[b][ps]-st[a][ps]).forEach((t,i)=>r[t][ps]=i+1));
  return r;
}
function sideEffect(roster,out,inn){
  const outIds=new Set(out.map(p=>p.player_id));
  const after=roster.filter(p=>!outIds.has(p.player_id)).concat(inn);
  const b=lineup(roster,ppw), a=lineup(after,ppw);
  const hb=hcBonus(roster,ppw), ha=hcBonus(after,ppw);
  const bm=teamValue(roster,mppw), am=teamValue(after,mppw);
  const bench=rs=>rs.filter(p=>!lineup(rs,ppw).used.has(p.player_id)).sort((x,y)=>ppw(y)-ppw(x));
  const depth=rs=>bench(rs).slice(0,4).reduce((t,p)=>t+ppw(p),0);
  const slotNotes=[];
  for(const slot of SLOTS){
    if(!(D.lineup[slot]||0))continue;
    const before=(b.filled[slot]||[]).reduce((t,p)=>t+ppw(p),0), aft=(a.filled[slot]||[]).reduce((t,p)=>t+ppw(p),0);
    if(Math.abs(aft-before)>=0.4)slotNotes.push(`${slot} ${aft>before?'+':''}${(aft-before).toFixed(1)}/wk`);
  }
  return {lineupDelta:a.total-b.total, hcDelta:(ha.ppw-hb.ppw)*WKS, hcNotesAfter:ha.notes, hcNotesBefore:hb.notes,
          rosDelta:((a.total+ha.ppw)-(b.total+hb.ppw))*WKS, marketDelta:(am-bm)*WKS,
          depthDelta:(depth(after)-depth(roster))*WKS*0.3, spots:inn.length-out.length, slotNotes,
          after, starters:a.used, wasStarter:b.used};
}
const ACCEPT=-0.15; // per week, by consensus: same line the Trades tab uses
function tradeVerdict(you,them,fit){
  const y=you.rosDelta, t=them.rosDelta, tm=them.marketDelta, ok=tm>=ACCEPT*WKS;
  let note='';
  if(you.hcDelta<=-3)note+=' You give up handcuff insurance worth about '+f1(-you.hcDelta)+' points.';
  if(you.hcDelta>=3)note+=' Includes about '+f1(you.hcDelta)+' points of handcuff insurance.';
  if(you.depthDelta<=-5)note+=' Your bench gets thinner, so an injury hurts more.';
  const fitTxt=fit?(' '+fit):'';
  if(y>4&&t>4&&ok)return ['good','Both sides win','You gain '+f1(y)+' points rest of season, they gain '+f1(t)+'.'+fitTxt+note];
  if(y>4&&ok)return ['good','Worth offering','You gain '+f1(y)+' points rest of season, and in their lineup it looks like a gain or a wash by consensus, so they have a reason to say yes.'+fitTxt+note];
  if(y>4)return ['warn','Good for you, hard sell','You gain '+f1(y)+' points, but by consensus it weakens their lineup by '+f1(-tm)+'. Expect a no unless they rate someone differently.'+fitTxt+note];
  if(y>-3)return ['warn','Roughly even','Neither lineup moves much ('+sgn(y)+' for you).'+fitTxt+(note||' Only worth doing for bye-week or schedule reasons.')];
  if(y<=-8)return ['bad','Turn this down','You lose '+f1(-y)+' points rest of season.'+fitTxt+note];
  return ['warn','Slightly against you','You lose '+f1(-y)+' points rest of season. Close enough that roster fit could justify it.'+fitTxt+note];
}
let TA={a:null,b:null,give:new Set(),get:new Set()};
function openTrade(k){const i=L.trade_ideas[k];TA.a=L.team.team_id;TA.b=i.team_id;TA.give=new Set(i.give_ids);TA.get=new Set(i.get_ids);go('analyzer');window.scrollTo(0,0)}
function taRosterHtml(tid,which){
  const sel=TA[which], rows=rosterOf(tid).sort((x,y)=>ppw(y)-ppw(x));
  if(!rows.length)return '<p class="mute">No rated players on this roster.</p>';
  return rows.map(p=>`<label class="taRow${sel.has(p.player_id)?' on':''}"><input type="checkbox" data-side="${which}" value="${p.player_id}" ${sel.has(p.player_id)?'checked':''}> <span>${nm(p)}</span> <span class="mute">${f1(ppw(p))}/wk · ${f0(p.ros_points)} ROS</span></label>`).join('');
}
function taRender(){  // full redraw: teams changed
  const teams=(L&&L.team&&L.team.strength)||[];
  const opts=sel=>teams.map(t=>`<option value="${t.team_id}" ${t.team_id===sel?'selected':''}>${esc(t.name)}</option>`).join('');
  $('#taA').innerHTML=opts(TA.a); $('#taB').innerHTML=opts(TA.b);
  $('#taAr').innerHTML=taRosterHtml(TA.a,'give'); $('#taBr').innerHTML=taRosterHtml(TA.b,'get');
  taVerdict();
}
function taVerdict(){  // selections changed: leave the lists alone so nothing jumps
  const teams=(L&&L.team&&L.team.strength)||[];
  document.querySelectorAll('.taRow input').forEach(i=>i.parentElement.classList.toggle('on', i.checked));
  const give=P.filter(p=>TA.give.has(p.player_id)), get=P.filter(p=>TA.get.has(p.player_id));
  const box=$('#taOut');
  if(!give.length||!get.length){box.innerHTML='<p class="mute">Pick at least one player on each side.</p>';return}
  const you=sideEffect(rosterOf(TA.a),give,get), them=sideEffect(rosterOf(TA.b),get,give);
  const r0=leagueRanks({}), r1=leagueRanks({[TA.a]:you.after,[TA.b]:them.after});
  const mv=tid=>['QB','RB','WR','TE'].filter(ps=>r0[tid][ps]!==r1[tid][ps]).map(ps=>({ps,from:r0[tid][ps],to:r1[tid][ps]}));
  const up=tid=>mv(tid).filter(m=>m.to<m.from), fmt=m=>`${m.ps} ${ord(m.from)}→${ord(m.to)}`;
  const fit=[up(TA.a).length?'You improve at '+up(TA.a).map(fmt).join(', ')+'.':'', up(TA.b).length?'They improve at '+up(TA.b).map(fmt).join(', ')+'.':'They don\'t improve at any position, which makes a yes less likely.'].filter(Boolean).join(' ');
  you.moves=mv(TA.a); them.moves=mv(TA.b);
  const [cls,title,line]=tradeVerdict(you,them,fit);
  const nameOf=tid=>(teams.find(t=>t.team_id===tid)||{}).name||'Team';
  const side=(label,s,pkg)=>`<div class="stat"><span>${esc(label)}</span><b class="${s.rosDelta>0?'good':s.rosDelta<0?'bad':''}">${sgn(s.rosDelta)} pts</b><span style="font-size:11px">rest of season, lineup + handcuffs</span>
    <div class="mute" style="font-size:12px">${sgn(s.lineupDelta)}/wk lineup · ${sgn(s.marketDelta)} by consensus · ${s.spots>0?'+':''}${s.spots} roster spot${Math.abs(s.spots)===1?'':'s'}
    ${s.moves&&s.moves.length?'<br>'+s.moves.map(m=>`<span class="${m.to<m.from?'good':'bad'}">${m.ps} ${ord(m.from)}→${ord(m.to)}</span>`).join(' · '):''}
    ${Math.abs(s.hcDelta)>=0.5?'<br>handcuff insurance '+sgn(s.hcDelta):''}${s.depthDelta?'<br>bench depth '+sgn(s.depthDelta):''}</div></div>`;
  const plist=(ps,who)=>ps.map(p=>`<div class="p" onclick="detail('${p.player_id}')">${nm(p)} <span class="mute">${f1(ppw(p))}/wk · ${f0(p.ros_points)} ROS · ${p.position}${f0(p.own_pos_rank)} us / ${p.consensus_pos_rank?p.position+f0(p.consensus_pos_rank):'–'} market${(p.exp_missed||0)>=1?' · out ~'+f1(p.exp_missed)+' games':''}</span></div>`).join('');
  box.innerHTML=`<div class="banner" style="background:${cls==='good'?'var(--good-bg)':cls==='bad'?'var(--bad-bg)':'var(--warn-bg)'};color:${cls==='good'?'var(--good)':cls==='bad'?'var(--bad)':'var(--warn)'}"><b>${title}</b><br>${line}</div>
   <div class="grid">${side(nameOf(TA.a)+' (you)',you)}${side(nameOf(TA.b),them)}</div>
   <div class="split" style="margin-top:14px">
     <div><p class="sub"><b>Out:</b></p>${plist(give)}</div><div><p class="sub"><b>In:</b></p>${plist(get)}</div></div>
   <p class="sub" style="margin-top:12px">Points are rest-of-season starting-lineup points, already adjusted for injuries and byes. "By consensus" re-runs the same calculation using FantasyPros and ESPN ranks instead of ours, which is roughly how the other manager sees it.</p>`;
  // what each roster looks like afterwards
  const giveIds=new Set(give.map(p=>p.player_id)), getIds=new Set(get.map(p=>p.player_id));
  const aAfter=rosterOf(TA.a).filter(p=>!giveIds.has(p.player_id)).concat(get);
  const bAfter=rosterOf(TA.b).filter(p=>!getIds.has(p.player_id)).concat(give);
  const wkA0=buildLineup(rosterOf(TA.a),others(TA.a)).total, wkA1=buildLineup(aAfter,others(TA.a)).total;
  const wkB0=buildLineup(rosterOf(TA.b),others(TA.b)).total, wkB1=buildLineup(bAfter,others(TA.b)).total;
  const afterCard=(tid,rows,newIds,w0,w1)=>`<div><h3 style="margin:0 0 2px;font-size:14px">${esc(nameOf(tid))} after the trade</h3>
     <p class="sub">Week ${D.plan_week} projected starters: ${f1(w0)} → <b class="${w1>w0+0.05?'good':w1<w0-0.05?'bad':''}">${f1(w1)}</b></p>
     ${lineupHtml(rows,others(tid),{newIds,tid})}</div>`;
  box.innerHTML+=`<div class="card" style="margin:16px -18px -16px;border-radius:0 0 var(--radius) var(--radius);border-left:0;border-right:0;border-bottom:0;box-shadow:none">
     <h2>Rosters after the trade</h2><p class="sub">Each team's projected lineup for week ${D.plan_week} with the new players slotted in (highlighted). Bench below the line.</p>
     <div class="split">${afterCard(TA.a,aAfter,getIds,wkA0,wkA1)}${afterCard(TA.b,bAfter,giveIds,wkB0,wkB1)}</div></div>`;
  wireRows(box);
}
document.addEventListener('change',e=>{
  if(e.target.id==='taA'||e.target.id==='taB'){TA[e.target.id==='taA'?'a':'b']=+e.target.value;TA.give.clear();TA.get.clear();taRender()}
  else if(e.target.dataset&&e.target.dataset.side){const k=e.target.dataset.side,set=TA[k];e.target.checked?set.add(e.target.value):set.delete(e.target.value);taVerdict()}
});

const TABS=[['team','Team'],['waivers','Waivers'],['trades','Trades'],['analyzer','Trade analyzer'],['value','Value board'],['rankings','Rankings'],['injuries','Injuries'],['method','How it works']];
function go(k){document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.k===k));$('#main').innerHTML=views[k]();try{localStorage.setItem('tab',k)}catch(e){}}
$('#tabs').innerHTML=TABS.map(([k,h])=>`<button data-k="${k}">${h}</button>`).join('');
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>go(b.dataset.k));
let start='team';try{start=localStorage.getItem('tab')||start}catch(e){}
go(views[start]?start:'team');
</script></body></html>"""


def render(data: dict) -> str:
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload)
