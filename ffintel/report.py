"""Renders the single-file dashboard (data embedded, no external requests)."""
import json

TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Fantasy Intel</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--mute:#667085;--line:#e4e7ec;--acc:#2563eb;--good:#15803d;--goodbg:#dcfce7;--bad:#b91c1c;--badbg:#fee2e2;--warn:#a16207;--warnbg:#fef3c7;--chip:#eef2f7}
@media (prefers-color-scheme:dark){:root{--bg:#0e1116;--card:#161b22;--ink:#e6edf3;--mute:#8b949e;--line:#262d36;--acc:#60a5fa;--good:#4ade80;--goodbg:#12301f;--bad:#f87171;--badbg:#3a1616;--warn:#fbbf24;--warnbg:#3a2e0d;--chip:#1f2630}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:18px 16px 8px;max-width:1200px;margin:auto}h1{margin:0;font-size:22px}header p{margin:4px 0 0;color:var(--mute);font-size:13px}
nav{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line)}
nav div{display:flex;gap:4px;overflow-x:auto;max-width:1200px;margin:auto;padding:8px 16px}
nav button{flex:none;border:0;background:none;color:var(--mute);padding:8px 12px;border-radius:8px;font:inherit;font-weight:600;cursor:pointer}
nav button.on{background:var(--chip);color:var(--ink)}
main{max-width:1200px;margin:auto;padding:12px 16px 60px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}
.card h2{margin:0 0 4px;font-size:16px}.sub{color:var(--mute);font-size:13px;margin:0 0 10px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{color:var(--mute);font-weight:600;font-size:12px;cursor:pointer;user-select:none;position:sticky;top:0;background:var(--card)}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--card)}td.l,th.l{text-align:left}
tr.p{cursor:pointer}tr.p:hover td{background:var(--chip)}
.pos{display:inline-block;min-width:26px;text-align:center;font-size:11px;font-weight:700;border-radius:5px;padding:1px 4px;background:var(--chip);color:var(--mute);margin-right:6px}
.tag{display:inline-block;font-size:11px;font-weight:700;border-radius:999px;padding:2px 8px}
.U{background:var(--goodbg);color:var(--good)}.O{background:var(--badbg);color:var(--bad)}.I{background:var(--warnbg);color:var(--warn)}.S{background:var(--chip);color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.stat{background:var(--chip);border-radius:10px;padding:10px}.stat b{display:block;font-size:20px}.stat span{color:var(--mute);font-size:12px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
input,select{font:inherit;padding:7px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.chips button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:5px 12px;font:inherit;cursor:pointer}.chips button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.trade{display:grid;grid-template-columns:1fr auto 1fr;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}
.trade:last-child{border:0}.trade .arrow{color:var(--mute);font-size:18px}.trade small{color:var(--mute)}
.why{color:var(--mute);font-size:12px;white-space:normal;text-align:left;min-width:220px}
.good{color:var(--good)}.bad{color:var(--bad)}.mute{color:var(--mute)}
.bars{display:flex;gap:3px;align-items:flex-end;height:60px}.bars div{flex:1;background:var(--acc);border-radius:3px 3px 0 0;min-width:10px;position:relative}
.bars div span{position:absolute;top:-16px;left:0;right:0;text-align:center;font-size:10px;color:var(--mute)}
dialog{border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--ink);max-width:560px;width:calc(100% - 32px);padding:18px}
dialog::backdrop{background:rgba(0,0,0,.5)}.x{float:right;border:0;background:none;color:var(--mute);font-size:22px;cursor:pointer}
.kv{display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;font-size:13px}.kv div{display:flex;justify-content:space-between;border-bottom:1px dashed var(--line);padding:3px 0}
.banner{background:var(--warnbg);color:var(--warn);border-radius:10px;padding:10px 12px;margin-bottom:14px;font-size:13px}
.taList{max-height:340px;overflow:auto;margin-top:8px;border:1px solid var(--line);border-radius:10px;padding:4px}
.taRow{display:flex;gap:8px;align-items:center;padding:6px;border-radius:8px;font-size:13px;cursor:pointer;flex-wrap:wrap}
.taRow:hover{background:var(--chip)}.taRow.on{background:var(--chip)}.taRow span:last-child{margin-left:auto;font-size:12px}
@media(max-width:640px){.card>div[style*='1fr 1fr']{grid-template-columns:1fr!important}}
.method p{margin:6px 0;max-width:760px}.method h3{margin:14px 0 4px;font-size:14px}
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
const INJ_LABEL={QUESTIONABLE:'Q',DOUBTFUL:'D','LEFT GAME':'Left game','SNAPS DOWN':'Snaps ↓',RETURNED:'Returned',CLEARED:'Cleared',SEASON:'Out for season',UNAVAILABLE:'Unavail.',SUSPENSION:'Susp.',INACTIVE:'Inactive'};
const INJ_CLASS={CLEARED:'U',RETURNED:'S','SNAPS DOWN':'S',SEASON:'O',IR:'O',OUT:'O','LEFT GAME':'O'};
const inj=p=>p.inj_status?`<span class="tag ${INJ_CLASS[p.inj_status]||'I'}" title="${esc(p.inj_detail)}">${INJ_LABEL[p.inj_status]||p.inj_status}</span>`:'';
const ago=t=>{if(!t)return '';const d=new Date(t);if(isNaN(d))return '';const h=(Date.now()-d)/36e5;return h<1?'just now':h<24?Math.round(h)+'h ago':Math.round(h/24)+'d ago'};
const sigList=p=>(p.inj_signals||[]).map(s=>`<div style="padding:6px 0;border-bottom:1px dashed var(--line)"><b>${esc(INJ_LABEL[s.status]||s.status)}</b> <span class="mute">· ${esc(s.source)}${s.when?' · '+ago(s.when):''}</span><br><span style="font-size:13px">${esc(s.detail)}</span></div>`).join('');
const star=p=>p.star?'<span class="tag S" title="Proven star">★</span>':'';
const bye=p=>p.on_bye?'<span class="tag" style="background:var(--chip);color:var(--mute)">BYE</span>':'';
const nm=p=>`${pos(p.position)}<b>${esc(p.name)}</b> <span class="mute">${esc(p.team||'')}</span> ${star(p)} ${bye(p)} ${inj(p)}`;
const playOdds=p=>p.on_bye?'bye':pct(p.play_prob);
const wk=p=>p.on_bye?'<span class="mute">bye</span>':f1(p.week_proj);
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
  ${p.fill_in_for?`<div class="banner" style="background:var(--goodbg);color:var(--good)">Took over for injured ${esc(p.fill_in_for)} last game</div>`:''}
  ${p.note?`<p class="sub">${esc(p.note)}</p>`:''}
  <div class="grid" style="margin-bottom:12px">
   <div class="stat"><b>${f1(p.proj_ppg)}</b><span>Our proj. PPG</span></div>
   <div class="stat"><b>${f0(p.ros_points)}</b><span>Rest-of-season pts</span></div>
   <div class="stat"><b>${p.position}${f0(p.own_pos_rank)} / ${p.consensus_pos_rank?p.position+f0(p.consensus_pos_rank):'–'}</b><span>Our rank / consensus</span></div>
  </div>
  ${p.role_factor!=null&&p.role_factor<0.95&&p.proj_ppg_raw>p.proj_ppg?`<p class="sub">Role ceiling: with his current workload he keeps ${pct(p.role_factor)} of the value above replacement, trimming ${f1(p.proj_ppg_raw)} to ${f1(p.proj_ppg)} per game.</p>`:''}
  <p class="sub" style="margin-bottom:18px">How we got ${f1(p.proj_ppg_raw??p.proj_ppg)}: history says <b>${f1(p.prior_ppg)}</b> (${esc(p.prior_source)}, worth ${f1(p.prior_weight_games)} games), this season says <b>${f1(p.cur_ppg)}</b> actual / <b>${f1((p.xfp_total||0)/Math.max(p.all_games||1,1))}</b> expected from usage. This season gets ${pct(p.current_weight)} of the weight.</p>
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
   <div><span>Next opp. / matchup</span><b>${p.on_bye?'BYE':esc(p.opponent||'—')} ${p.matchup?'×'+(+p.matchup).toFixed(2):''}</b></div>
   <div><span>FantasyPros ROS rank</span><b>${p.fp_ros?f1(p.fp_ros):'–'} <span class="mute">(${p.fp_ros_best??'–'}–${p.fp_ros_worst??'–'})</span></b></div>
   <div><span>ESPN ROS proj.</span><b>${f0(p.espn_proj)}</b></div>
  </div>`;
  $('#dlg').showModal();
}

const RK=[{k:'name',h:'Player',l:1,f:nm},{k:'proj_ppg',h:'Proj',f:x=>f1(x.proj_ppg),t:'Our projected points per game'},
 {k:'week_proj',h:'Next wk',f:x=>wk(x)},{k:'ros_points',h:'ROS',f:x=>f0(x.ros_points),t:'Rest-of-season points (injuries & byes included)'}];

const views={
 team(){
  if(!L)return noLeague();
  const t=L.team, me=t.strength.find(s=>s.team_id===t.team_id)||{};
  const needs=t.needs.map(n=>`<div class="stat"><b>${n.position} · ${ord(n.rank)}</b><span>${f1(n.my_ppw)} vs avg ${f1(n.league_avg)} pts/wk</span></div>`).join('');
  const moves=t.players.filter(p=>p.lineup_note);
  const hurt=t.players.filter(p=>p.inj_status&&!['CLEARED','RETURNED'].includes(p.inj_status)).sort((a,b)=>(b.exp_missed||0)-(a.exp_missed||0));
  return `${L.mock?'<div class="banner">Demo mode: the league below is made up. Real players and stats, fake rosters.</div>':''}
  ${L.note?`<div class="banner">${esc(L.note)}</div>`:''}
  ${hurt.length?`<div class="card"><h2>Injury alerts on your roster</h2>${hurt.map(p=>`<div class="p" style="padding:6px 0;cursor:pointer" onclick="detail('${p.player_id}')">${nm(p)} <span class="mute">${p.on_bye?'on bye next week':pct(p.play_prob)+' to play next week'}</span><div class="why">${esc(p.inj_detail)} · ${esc(p.inj_source)} ${ago(p.inj_updated)}</div></div>`).join('')}</div>`:''}
  <div class="card"><h2>${esc(L.my_team)}</h2><p class="sub">Power rank ${me.power_rank} of ${t.strength.length} by projected rest-of-season lineup (${f1(me.lineup_ppw)} pts/week). Position ranks, weakest first:</p><div class="grid">${needs}</div></div>
  ${moves.length?`<div class="card"><h2>Lineup changes for week ${D.plan_week}</h2><p class="sub">Your ESPN lineup vs. our best lineup.</p>${moves.map(p=>`<div>${p.lineup_note==='Start'?'<b class="good">Start</b>':'<b class="bad">Bench</b>'} ${nm(p)} <span class="mute">${p.on_bye?'on bye':f1(p.week_proj)+' proj'}</span></div>`).join('')}</div>`:''}
  <div class="card"><h2>Roster</h2>${table(t.players,[...RK,{k:'start_this_week',h:'Start?',f:x=>x.start_this_week?'✓':''},{k:'consensus_pos_rank',h:'Rank us/mkt',f:x=>`${x.position}${f0(x.own_pos_rank)} / ${x.consensus_pos_rank?x.position+f0(x.consensus_pos_rank):'–'}`},{k:'verdict',h:'Market',f:x=>verdict(x.verdict)}],{sort:'ros_points'})}</div>
  <div class="card"><h2>League power rankings</h2>${table(t.strength,[{k:'name',h:'Team',l:1,f:x=>x.team_id===t.team_id?`<b>${esc(x.name)}</b>`:esc(x.name)},{k:'record',h:'Rec'},{k:'lineup_ppw',h:'Lineup/wk',f:x=>f1(x.lineup_ppw)},{k:'QB_ppw',h:'QB',f:x=>f1(x.QB_ppw)},{k:'RB_ppw',h:'RB',f:x=>f1(x.RB_ppw)},{k:'WR_ppw',h:'WR',f:x=>f1(x.WR_ppw)},{k:'TE_ppw',h:'TE',f:x=>f1(x.TE_ppw)}],{sort:'lineup_ppw'})}</div>`;
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
  const ideas=L.trade_ideas.map(i=>`<div class="trade"><div><small>You give</small><br>${i.give.map((g,j)=>`${pos(i.give_pos[j])}<b>${esc(g)}</b>`).join('<br>')}</div><div class="arrow">⇄</div><div><small>${esc(i.team)} gives</small><br>${pos(i.get_pos)}<b>${esc(i.get)}</b> ${verdict(i.get_verdict)}<br><small class="good">+${f1(i.my_gain_week)} pts/wk for you</small> <small>· market balance ${(+i.market_balance).toFixed(2)}</small></div></div>`).join('');
  return `<div class="card"><h2>Trade ideas</h2><p class="sub">Offers that improve your lineup by our numbers while looking fair by consensus value, so the other manager has a reason to accept. Market balance 1.00 = even by consensus; above 1 means you give a little more.</p>${ideas||'<p class="mute">No clear wins right now.</p>'}</div>
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
  <div class="row"><input id="q" placeholder="Search player or team" style="flex:1;min-width:160px"><select id="grp"><option value="proj">Projection</option><option value="use">Usage</option><option value="rz">Red zone</option><option value="prod">Production</option></select><label class="mute"><input type="checkbox" id="fa"> Free agents only</label></div><div id="${id}"></div>
  <p class="sub" style="margin-top:8px">Tap any player for details. <a href="rankings.csv" style="color:var(--acc)">Download CSV</a></p></div>`;
 },
 injuries(){
  const rel=p=>p.own_pos_rank<=60||p.owner_name||p.fill_in_for;
  const game=P.filter(p=>['LEFT GAME','RETURNED','SNAPS DOWN'].includes(p.inj_status)&&rel(p)).sort((a,b)=>(b.exp_missed||0)-(a.exp_missed||0)||b.ros_value-a.ros_value);
  const all=P.filter(p=>p.inj_status&&rel(p)).sort((a,b)=>b.ros_value-a.ros_value);
  const feeds=Object.entries(D.injury_feeds||{}).map(([k,v])=>`<span class="tag ${/unavailable/.test(v)?'O':'U'}" style="margin:2px">${esc(k)}: ${esc(v)}</span>`).join(' ');
  const fills=(D.fill_ins||[]).map(f=>{const p=byId[f.fill_in_id];return `<div style="padding:6px 0;border-bottom:1px dashed var(--line)">${pos(f.position)}<b>${esc(f.fill_in)}</b> <span class="mute">${esc(f.team)}</span> took over for <b>${esc(f.injured)}</b> <span class="mute">(${f.plays} plays after the injury)</span>${p?` · <a style="color:var(--acc);cursor:pointer" onclick="detail('${p.player_id}')">${p.owner_name?'on '+esc(p.owner_name):'free agent'}</a>`:''}</div>`}).join('');
  const cols=[{k:'name',h:'Player',l:1,f:nm},{k:'inj_detail',h:'Detail',l:1,f:x=>`<div class="why">${esc(x.inj_detail)}</div>`},{k:'play_prob',h:'Play next wk',f:x=>playOdds(x)},{k:'exp_missed',h:'Exp. missed',f:x=>f1(x.exp_missed)},{k:'owner_name',h:'Rostered',l:1,f:x=>esc(x.owner_name||'FA')},{k:'inj_updated',h:'Source',l:1,f:x=>`${esc(x.inj_source)} <span class="mute">${ago(x.inj_updated)}</span>`}];
  return `<div class="card"><h2>Hurt in the last game</h2><p class="sub">Read straight from play-by-play within hours of each game, days before the official injury report. "Left game" means he never came back; how serious it is shows up once ESPN, Sleeper or the practice report weigh in.</p>${table(game,cols,{})}</div>
  ${fills?`<div class="card"><h2>Who stepped in</h2><p class="sub">The teammate who took the injured player's work for the rest of the game. Often the week's best waiver add.</p>${fills}</div>`:''}
  <div class="card"><h2>Every injury status</h2><p class="sub">The most serious current signal wins; tap a player to see every source. Stale info is dropped automatically (e.g. last week's "Questionable" once he's played, or an in-game injury once the next official report is out).</p>${table(all,[...cols.slice(0,1),{k:'inj_status',h:'Status',l:1,f:x=>inj(x)},...cols.slice(1)],{})}</div>
  <div class="card"><h2>Sources this update</h2><p>${feeds}</p></div>`;
 },
 analyzer(){
  if(!L)return noLeague();
  const teams=L.team.strength;
  if(TA.a==null){TA.a=L.team.team_id;TA.b=(teams.find(t=>t.team_id!==TA.a)||{}).team_id}
  setTimeout(taRender);
  return `<div class="card"><h2>Trade analyzer</h2><p class="sub">Pick the players on each side. Every number is rest-of-season starting-lineup points using this app's projections, with injuries, byes and roster fit included.</p>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
    <div><select id="taA" style="width:100%"></select><div id="taAr" class="taList"></div></div>
    <div><select id="taB" style="width:100%"></select><div id="taBr" class="taList"></div></div>
  </div></div>
  <div class="card"><h2>Verdict</h2><div id="taOut"></div>
  <p class="sub" style="margin-top:10px"><a style="color:var(--acc);cursor:pointer" onclick="TA.give.clear();TA.get.clear();taRender()">Clear selections</a></p></div>`;
 },
 method(){
  return `<div class="card method"><h2>How the ratings work</h2>
  <h3>1. History (the prior)</h3><p>Each player's last three seasons, weighted 50/33/17 toward the most recent, counting only games where he played at least 20% of snaps. Rookies start from how past rookies at the same position and draft round scored. Age curves trim older RBs and WRs slightly.</p>
  <h3>2. This season</h3><p>Actual points blended 50/50 with <b>expected points (xFP)</b>: every target and carry is valued by how many fantasy points the league average gets from that exact opportunity (depth of target, field position, red zone). Workload is far more stable than touchdowns, so xFP tells us whether a hot or cold start is real. Games a player sat while healthy count as zeros.</p>
  <h3>3. Blending (why one bad week doesn't sink a star)</h3><p>History counts as a number of "phantom games" (roughly 2 to 6 depending on position and how much track record there is). After two weeks, this season is only about 25-35% of a proven player's projection; by mid-season it's the majority. If snap share has clearly changed (±15 points), history is trusted half as much, because a real role change should move fast. Tested on the 2025 season, this blend predicted rest-of-season scoring better than history alone, this season alone, or usage alone, at weeks 2, 4 and 8.</p>
  <h3>4. Role ceiling (what stops empty recommendations)</h3><p>Fantasy points come from touches and targets, not reputation. Every game a player was active for counts toward his average, including a 5% snap cameo, because that IS the evidence he has no role. On top of that, his value above replacement is scaled by the job he currently holds: snap share in his last two games, or touches and targets per game against what a starter at his position gets, whichever is kinder. A former starter now playing 10% of snaps keeps about a tenth of his edge; a committee back with 20 carries on few snaps keeps all of it. Waiver suggestions also have to clear a floor: real recent usage, a role that is growing, or a job just inherited from an injured starter.</p>
  <h3>5. Injuries</h3><p>Eight sources, fastest first: play-by-play (who got hurt and whether he came back, within hours of the game), snap counts, ESPN's injury desk (status, return date, news comment), Sleeper, ESPN news headlines, your league's ESPN designations, the official injury and practice reports, and NFL roster moves. News text is read for timelines ("2-4 weeks", "season-ending", "week-to-week", "high-ankle sprain", "surgery") and negations ("avoided a torn ACL"). The most serious current signal sets the status; a newer "full practice" or "cleared" overrides older short-term worries. Games a player left injured are left out of his scoring average.</p>
  <h3>6. Rest of season</h3><p>Projected points per game × games left, minus byes and expected missed games from injuries (IR ≈ 4 games, Out 1, Doubtful 0.8, Questionable 0.25, left game injured 1 with a 50% chance to miss next week, or the injury desk's return date and timeline when there is one). Next week's projection also adjusts for the opponent's points allowed to that position (shrunk toward average, capped at ±15%).</p>
  <h3>7. Market vs. us</h3><p>The consensus rating is a weighted average of FantasyPros rest-of-season consensus (60%, itself 100+ experts), ESPN's projections (25%) and FantasyPros weekly consensus (15%). Each consensus rank is turned into points using our own projection curve, so the gap is in real points. "Undervalued/Overvalued" needs a gap of at least 1.5 points per game and a meaningful rank difference. <b>Star guardrail:</b> a proven star can't be called overvalued unless something structural changed (injury, lost snaps, new team).</p>
  <h3>8. Trade analyzer</h3><p>Pick any two teams and any set of players. For each side it rebuilds that team's best starting lineup before and after the trade, so a player only counts for what he adds to the lineup you would actually field: a third good running back is worth much less than a first one. It adds a small credit for bench depth, notes which lineup slots move, and counts roster spots gained or lost in an uneven package. Then it re-runs the whole calculation using consensus ranks instead of ours, which approximates how the other manager sees the deal, and that gap is what tells you whether an offer is likely to be accepted.</p>
  <h3>9. Your league</h3><p>Value over replacement uses your league's real size and lineup slots. Waiver scores measure how much a player improves your best lineup. Trade ideas must improve your lineup by our numbers while being fair or better for the other team by consensus value, so they're offers that can actually get accepted.</p>
  <p class="mute">Replacement level (pts/game): ${Object.entries(D.replacement).map(([k,v])=>k+' '+f1(v)).join(' · ')} · Reception points: ${D.rec_pts}</p></div>`;
 }
};
function ord(n){return n+(['th','st','nd','rd'][(n%100>10&&n%100<14)?0:n%10<4?n%10:0]||'th')}
function noLeague(){return `<div class="banner">League not connected: ${esc(D.league_error||'no ESPN credentials set')}. Rankings, value board and injuries still work. See the README to connect your ESPN league.</div>`}

function drawRank(){
  const box=document.getElementById('rk');if(!box)return;
  const on=document.querySelector('#pf .on').dataset.p, q=$('#q').value.toLowerCase(), g=$('#grp').value, fa=$('#fa').checked;
  const r=P.filter(p=>(on==='ALL'||p.position===on)&&(!q||(p.name+' '+p.team).toLowerCase().includes(q))&&(!fa||!p.owner_name)).slice(0,300);
  const G={proj:[{k:'vor_ppg',h:'VOR/g',f:x=>sgn(x.vor_ppg),t:'Points per game above replacement'},{k:'own_pos_rank',h:'Us',f:x=>x.position+f0(x.own_pos_rank)},{k:'consensus_pos_rank',h:'Mkt',f:x=>x.consensus_pos_rank?x.position+f0(x.consensus_pos_rank):'–'},{k:'verdict',h:'',f:x=>verdict(x.verdict)},{k:'prior_ppg',h:'Hist',f:x=>f1(x.prior_ppg)},{k:'cur_ppg',h:'This yr',f:x=>f1(x.cur_ppg)},{k:'owner_name',h:'Rostered',l:1,f:x=>esc(x.owner_name||'')}],
   use:[{k:'snap_pct',h:'Snap%',f:x=>pct(x.snap_pct)},{k:'target_share',h:'Tgt%',f:x=>pct(x.target_share)},{k:'air_yards_share',h:'Air%',f:x=>pct(x.air_yards_share)},{k:'wopr',h:'WOPR',f:x=>f1(x.wopr)},{k:'touches',h:'Touch',f:x=>f0(x.touches)},{k:'targets',h:'Tgt',f:x=>f0(x.targets)},{k:'carries',h:'Car',f:x=>f0(x.carries)},{k:'xfp_total',h:'xFP',f:x=>f1(x.xfp_total)}],
   rz:[{k:'rz_targets',h:'RZ tgt',f:x=>f0(x.rz_targets)},{k:'rz_tgt_share',h:'RZ tgt%',f:x=>pct(x.rz_tgt_share)},{k:'ez_targets',h:'EZ tgt',f:x=>f0(x.ez_targets)},{k:'rz_carries',h:'RZ car',f:x=>f0(x.rz_carries)},{k:'rz_rush_share',h:'RZ car%',f:x=>pct(x.rz_rush_share)},{k:'i10_carries',h:'In-10',f:x=>f0(x.i10_carries)},{k:'tds',h:'TD',f:x=>f0(x.tds)}],
   prod:[{k:'pts_total',h:'Pts',f:x=>f1(x.pts_total)},{k:'receptions',h:'Rec',f:x=>f0(x.receptions)},{k:'rec_yds',h:'RecYd',f:x=>f0(x.rec_yds)},{k:'rush_yds',h:'RuYd',f:x=>f0(x.rush_yds)},{k:'pass_yds',h:'PaYd',f:x=>f0(x.pass_yds)},{k:'tds',h:'TD',f:x=>f0(x.tds)},{k:'l3_ppg',h:'L3',f:x=>f1(x.l3_ppg)}]};
  box.innerHTML=table(r,[...RK,...G[g]],{sort:'ros_points'});
}
document.addEventListener('click',e=>{const b=e.target.closest('#pf button');if(b){document.querySelectorAll('#pf button').forEach(x=>x.classList.remove('on'));b.classList.add('on');drawRank()}});
document.addEventListener('input',e=>{if(['q','grp','fa'].includes(e.target.id))drawRank()});

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
function sideEffect(roster,out,inn){
  const outIds=new Set(out.map(p=>p.player_id));
  const after=roster.filter(p=>!outIds.has(p.player_id)).concat(inn);
  const b=lineup(roster,ppw), a=lineup(after,ppw);
  const bm=lineup(roster,mppw), am=lineup(after,mppw);
  const bench=rs=>rs.filter(p=>!lineup(rs,ppw).used.has(p.player_id)).sort((x,y)=>ppw(y)-ppw(x));
  const depth=rs=>bench(rs).slice(0,4).reduce((t,p)=>t+ppw(p),0);
  const slotNotes=[];
  for(const slot of SLOTS){
    if(!(D.lineup[slot]||0))continue;
    const before=(b.filled[slot]||[]).reduce((t,p)=>t+ppw(p),0), aft=(a.filled[slot]||[]).reduce((t,p)=>t+ppw(p),0);
    if(Math.abs(aft-before)>=0.4)slotNotes.push(`${slot} ${aft>before?'+':''}${(aft-before).toFixed(1)}/wk`);
  }
  return {lineupDelta:a.total-b.total, rosDelta:(a.total-b.total)*WKS, marketDelta:(am.total-bm.total)*WKS,
          depthDelta:(depth(after)-depth(roster))*WKS*0.3, spots:inn.length-out.length, slotNotes,
          starters:a.used, wasStarter:b.used};
}
function tradeVerdict(you,them){
  const y=you.rosDelta, t=them.rosDelta, tm=them.marketDelta;
  let note='';
  if(you.depthDelta<=-5)note=' You also thin your bench by about '+f1(-you.depthDelta)+' points of cover, so an injury hurts more.';
  else if(you.depthDelta>=5)note=' It also adds about '+f1(you.depthDelta)+' points of bench cover.';
  if(y>8&&t>8)return ['good','Both sides win','You gain '+f1(y)+' starting-lineup points rest of season, they gain '+f1(t)+'.'+note];
  if(y>8&&tm>-8)return ['good','Worth offering','You gain '+f1(y)+' points rest of season, and by consensus value they are not clearly losing, so they have a reason to say yes.'+note];
  if(y>8)return ['warn','Good for you, hard sell','You gain '+f1(y)+' points, but they lose '+f1(-t)+' by our numbers and '+f1(-tm)+' by consensus. Expect a no unless they rate someone differently.'+note];
  if(y>=3)return [tm>-8?'good':'warn','Small win for you','You gain '+f1(y)+' starting-lineup points rest of season'+(tm>-8?', and it is defensible for them by consensus value.':', but they lose '+f1(-tm)+' by consensus, so they may not bite.')+note];
  if(y>-3&&y<3)return ['warn','Roughly even','Neither lineup moves much ('+sgn(y)+' for you).'+(note||' Only worth doing for bye-week or schedule reasons.')];
  if(y<=-8)return ['bad','Turn this down','You lose '+f1(-y)+' starting-lineup points rest of season.'+note];
  return ['warn','Slightly against you','You lose '+f1(-y)+' points rest of season. Close enough that roster fit could justify it.'+note];
}
let TA={a:null,b:null,give:new Set(),get:new Set()};
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
  const [cls,title,line]=tradeVerdict(you,them);
  const nameOf=tid=>(teams.find(t=>t.team_id===tid)||{}).name||'Team';
  const side=(label,s,pkg)=>`<div class="stat"><span>${esc(label)}</span><b class="${s.rosDelta>0?'good':s.rosDelta<0?'bad':''}">${sgn(s.rosDelta)} pts</b>
    <div class="mute" style="font-size:12px">${sgn(s.lineupDelta)}/wk lineup · ${sgn(s.marketDelta)} by consensus · ${s.spots>0?'+':''}${s.spots} roster spot${Math.abs(s.spots)===1?'':'s'}
    ${s.slotNotes.length?'<br>'+esc(s.slotNotes.join(' · ')):''}${s.depthDelta?'<br>bench depth '+sgn(s.depthDelta):''}</div></div>`;
  const plist=(ps,who)=>ps.map(p=>`<div class="p" onclick="detail('${p.player_id}')">${nm(p)} <span class="mute">${f1(ppw(p))}/wk · ${f0(p.ros_points)} ROS · ${p.position}${f0(p.own_pos_rank)} us / ${p.consensus_pos_rank?p.position+f0(p.consensus_pos_rank):'–'} market${(p.exp_missed||0)>=1?' · out ~'+f1(p.exp_missed)+' games':''}</span></div>`).join('');
  box.innerHTML=`<div class="banner" style="background:${cls==='good'?'var(--goodbg)':cls==='bad'?'var(--badbg)':'var(--warnbg)'};color:${cls==='good'?'var(--good)':cls==='bad'?'var(--bad)':'var(--warn)'}"><b>${title}</b><br>${line}</div>
   <div class="grid">${side(nameOf(TA.a)+' (you)',you)}${side(nameOf(TA.b),them)}</div>
   <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px">
     <div><p class="sub"><b>Out:</b></p>${plist(give)}</div><div><p class="sub"><b>In:</b></p>${plist(get)}</div></div>
   <p class="sub" style="margin-top:12px">Points are rest-of-season starting-lineup points, already adjusted for injuries and byes. "By consensus" re-runs the same calculation using FantasyPros and ESPN ranks instead of ours, which is roughly how the other manager sees it.</p>`;
}
document.addEventListener('change',e=>{
  if(e.target.id==='taA'||e.target.id==='taB'){TA[e.target.id==='taA'?'a':'b']=+e.target.value;TA.give.clear();TA.get.clear();taRender()}
  else if(e.target.dataset&&e.target.dataset.side){const k=e.target.dataset.side,set=TA[k];e.target.checked?set.add(e.target.value):set.delete(e.target.value);taVerdict()}
});

const TABS=[['team','My team'],['waivers','Waivers'],['trades','Trades'],['analyzer','Trade analyzer'],['value','Value board'],['rankings','Rankings'],['injuries','Injuries'],['method','How it works']];
function go(k){document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.k===k));$('#main').innerHTML=views[k]();try{localStorage.setItem('tab',k)}catch(e){}}
$('#tabs').innerHTML=TABS.map(([k,h])=>`<button data-k="${k}">${h}</button>`).join('');
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>go(b.dataset.k));
let start='team';try{start=localStorage.getItem('tab')||start}catch(e){}
go(views[start]?start:'team');
</script></body></html>"""


def render(data: dict) -> str:
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload)
