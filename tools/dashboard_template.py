"""The static-dashboard HTML/JS template. Kept separate from build_dashboard.py
so the builder stays readable. `__PAYLOAD__` is replaced with inlined JSON.

Self-contained: Leaflet (map) + Chart.js (charts) from CDN; all incident data
inlined. Works opened directly from disk, served by GitHub Pages, or embedded in
a WordPress <iframe>.

This dashboard is a LIVE MONITOR of recent, automatically-detected incidents —
it shows ONLY monitoring data (source='monitor'), never the paper's 520-row
historical archive. Default view is the last few weeks; the user can widen the
window. Every point carries a bilingual (中文 + English) description, a link to
the original story, and an image thumbnail when the article had one.
"""

_APP_JS = r"""
const $ = s => document.querySelector(s);
const COLORS = DATA.species_colors;
const R = DATA.records;
const TODAY = new Date(DATA.today + "T00:00:00Z");

// header
$("#gen").textContent = DATA.generated;

// ---- time window control ----
// value = days back from today; 0 / "all" means everything.
const WINDOWS = [[21,"3 weeks"],[42,"6 weeks"],[56,"8 weeks"],[84,"3 months"],[182,"6 months"],[365,"1 year"],[0,"All monitored"]];
const defDays = (DATA.recent_weeks||8)*7;
const sel = $("#fWindow");
WINDOWS.forEach(([d,label])=>{ let o=document.createElement("option"); o.value=d; o.textContent=label; sel.appendChild(o); });
// pick the smallest preset >= default, else default
sel.value = String((WINDOWS.find(([d])=>d>=defDays)||[0])[0] || 0);

// species + type filters
const spSet = [...new Set(R.map(r=>r.sp))].sort();
spSet.forEach(s=>{ let o=document.createElement("option"); o.value=s; o.textContent=s; $("#fSpecies").appendChild(o); });
DATA.conflict_types.forEach(t=>{ let o=document.createElement("option"); o.value=t; o.textContent=t; $("#fType").appendChild(o); });
$("#fReview").checked = false;

function daysAgo(dstr){
  if(!dstr) return 1e9;
  const d = new Date(dstr + "T00:00:00Z");
  return Math.round((TODAY - d)/86400000);
}

function current(){
  const win=+sel.value, sp=$("#fSpecies").value, ty=$("#fType").value, showRev=$("#fReview").checked;
  return R.filter(r=>{
    if(win>0 && daysAgo(r.date) > win) return false;
    if(sp && r.sp!==sp) return false;
    if(ty && r.type!==ty) return false;
    if(!showRev && r.review) return false;
    return true;
  });
}

// ---- map ----
const map = L.map('map',{scrollWheelZoom:false}).setView([35,103],4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  {attribution:'&copy; OpenStreetMap, &copy; CARTO', maxZoom:12}).addTo(map);
let markerLayer = L.layerGroup().addTo(map);

function popupHtml(r){
  const c = COLORS[r.sp]||"#333";
  const date = r.date ? r.date.slice(0,7) : "date unknown";
  const loc = [r.prov,r.cty,r.dist].filter(Boolean).join(" ");
  const cas = [];
  if(r.nv) cas.push(`${r.nv} affected`);
  if(r.nd && r.nd!=="0") cas.push(`${r.nd} killed`);
  const casLine = cas.length? `<div class="pcas">${cas.join(" · ")}</div>`:"";
  const img = r.img ? `<img class="pimg" src="${r.img}" referrerpolicy="no-referrer" loading="lazy"
                        onerror="this.style.display='none'">`:"";
  const en = r.sum_en ? `<div class="pen">${r.sum_en}</div>`:"";
  const zh = r.sum_zh ? `<div class="pzh">${r.sum_zh}</div>` : (r.title?`<div class="pzh">${r.title}</div>`:"");
  const link = r.url ? `<a href="${r.url}" target="_blank" rel="noopener">original story ↗</a>`:"";
  const rev = r.review ? ` <span class="rev">under review</span>`:"";
  return `<div class="popup">
    <div class="phead"><span class="pdot" style="background:${c}"></span><b>${r.sp}</b> — ${r.type}${rev}</div>
    <div class="pmeta">${loc} · ${date}</div>
    ${casLine}${img}${en}${zh}
    <div class="plink">${link}</div>
  </div>`;
}

function drawMap(rows){
  markerLayer.clearLayers();
  const pts=[];
  rows.forEach(r=>{
    const c = COLORS[r.sp]||"#333";
    if(r.unc){
      L.circle([r.lat,r.lon],{radius:r.unc,color:c,weight:1,opacity:.3,fillOpacity:.05}).addTo(markerLayer);
    }
    const recency = daysAgo(r.date);
    const fresh = recency <= 42;   // highlight the last 6 weeks
    const m=L.circleMarker([r.lat,r.lon],{radius:fresh?8:5,color:c,weight:fresh?3:1.5,
      fillColor:c,fillOpacity:fresh?.85:.55}).addTo(markerLayer);
    m.bindPopup(popupHtml(r),{maxWidth:300});
    pts.push([r.lat,r.lon]);
  });
  if(pts.length){ try{ map.fitBounds(pts,{padding:[40,40],maxZoom:7}); }catch(e){} }
  else { map.setView([35,103],4); }
}

// ---- recent-events feed ----
function drawFeed(rows){
  const box=$("#feed");
  if(!rows.length){ box.innerHTML=`<div class="empty">No monitored incidents in this window.
    Human–carnivore conflict is rare — quiet periods are expected (see project notes).</div>`; return; }
  box.innerHTML = rows.slice(0,40).map(r=>{
    const c=COLORS[r.sp]||"#333";
    const date=r.date?r.date.slice(0,7):"—";
    const loc=[r.prov,r.cty,r.dist].filter(Boolean).join(" ")||"location unknown";
    const desc=r.sum_en || r.title || "";
    const zh=r.sum_zh||"";
    const img=r.img?`<img src="${r.img}" referrerpolicy="no-referrer" loading="lazy" onerror="this.style.display='none'">`:"";
    const link=r.url?`<a href="${r.url}" target="_blank" rel="noopener">source ↗</a>`:"";
    const rev=r.review?`<span class="rev">under review</span>`:"";
    return `<div class="item">
      <div class="ithumb">${img}</div>
      <div class="ibody">
        <div class="ihead"><span class="pdot" style="background:${c}"></span>
          <b>${r.sp}</b> · ${r.type} <span class="idate">${date}</span> ${rev}</div>
        <div class="iloc">${loc}</div>
        ${desc?`<div class="idesc">${desc}</div>`:""}
        ${zh?`<div class="izh">${zh}</div>`:""}
        <div class="ilink">${link}</div>
      </div></div>`;
  }).join("");
}

// ---- charts ----
let trendChart, spChart;
function drawCharts(rows){
  // monthly trend (running monitor volume), last 18 months or window
  const byMonth={};
  rows.forEach(r=>{ if(r.date){ const k=r.date.slice(0,7); byMonth[k]=(byMonth[k]||0)+1; } });
  const months=Object.keys(byMonth).sort();
  if(trendChart) trendChart.destroy();
  trendChart=new Chart($("#trend"),{type:"bar",
    data:{labels:months,datasets:[{label:"incidents / month",data:months.map(m=>byMonth[m]),
      backgroundColor:"#b5651d"}]},
    options:{responsive:true,plugins:{legend:{display:false}},
      scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
  // by species
  const sp={}; rows.forEach(r=>{sp[r.sp]=(sp[r.sp]||0)+1;});
  const spK=Object.keys(sp).sort((a,b)=>sp[b]-sp[a]);
  if(spChart) spChart.destroy();
  spChart=new Chart($("#bySpecies"),{type:"bar",data:{labels:spK,
    datasets:[{data:spK.map(k=>sp[k]),backgroundColor:spK.map(k=>COLORS[k]||"#333")}]},
    options:{indexAxis:"y",plugins:{legend:{display:false}},scales:{x:{ticks:{precision:0}}}}});
}

function drawCards(rows){
  const nSp=new Set(rows.map(r=>r.sp)).size;
  const nRev=rows.filter(r=>r.review).length;
  const totAll=R.length;                          // running total, all monitored ever
  const cards=[["In this window",rows.length],["Species",nSp],
    ["Total monitored (all time)",totAll],["Flagged for review",nRev]];
  $("#cards").innerHTML=cards.map(([l,n])=>`<div class="card"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
}

function legend(){
  const shown=[...new Set(current().map(r=>r.sp))].sort();
  $("#legend").innerHTML = (shown.length?shown:spSet).map(s=>`<span><span class="dot" style="background:${COLORS[s]||'#333'}"></span>${s}</span>`).join("")
    + `<br><span style="margin-top:4px">Larger, bolder points = last 6 weeks. Rings ≈ location uncertainty.</span>`;
}

let _autoWidened=false;
function refresh(){
  let rows=current();
  // If the recent window is empty but we DO have monitored incidents, widen to the
  // smallest window that has data (once) so the dashboard is never blank-with-data.
  if(rows.length===0 && R.length>0 && !_autoWidened){
    for(const [d] of WINDOWS){
      sel.value=String(d);
      if(current().length>0){ _autoWidened=true; break; }
    }
    rows=current();
    if(rows.length>0) $("#autonote").textContent =
      "No incidents in the default recent window — showing the most recent available instead.";
  }
  drawMap(rows); drawFeed(rows); drawCharts(rows); drawCards(rows); legend();
  $("#winLabel").textContent = sel.options[sel.selectedIndex].text;
}
// clear the auto-note whenever the user changes the window themselves
sel.addEventListener("change",()=>{ _autoWidened=true; $("#autonote").textContent=""; });
["#fWindow","#fSpecies","#fType"].forEach(s=>$(s).addEventListener("change",refresh));
$("#fReview").addEventListener("change",refresh);
$("#reset").addEventListener("click",()=>{ sel.value=String((WINDOWS.find(([d])=>d>=defDays)||[0])[0]||0);
  $("#fSpecies").value="";$("#fType").value="";$("#fReview").checked=false; refresh(); });
refresh();
"""

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { --ink:#1a1a1a; --muted:#666; --line:#e2e2e2; --bg:#fafafa; --accent:#b5651d; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
         color:var(--ink); background:var(--bg); font-size:15px; line-height:1.4; }
  header { padding:16px 20px; background:#fff; border-bottom:1px solid var(--line); }
  h1 { margin:0 0 4px; font-size:20px; }
  .sub { color:var(--muted); font-size:13px; }
  .wrap { max-width:1180px; margin:0 auto; padding:16px 20px 40px; }
  .cards { display:flex; flex-wrap:wrap; gap:12px; margin:16px 0; }
  .card { background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 16px; flex:1; min-width:130px; }
  .card .n { font-size:26px; font-weight:700; }
  .card .l { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.03em; }
  .filters { display:flex; flex-wrap:wrap; gap:14px; align-items:flex-end; margin:8px 0 16px;
             background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 16px; }
  .filters label { font-size:12px; color:var(--muted); display:block; margin-bottom:3px; }
  .filters .chk { font-size:13px; color:var(--ink); }
  select { font-size:14px; padding:3px 6px; }
  .panel { background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:16px; }
  .panel h2 { margin:0 0 10px; font-size:15px; font-weight:600; }
  #map { height:480px; border-radius:8px; }
  .grid2 { display:grid; grid-template-columns:1.15fr .85fr; gap:16px; }
  @media (max-width:820px){ .grid2{ grid-template-columns:1fr; } }
  .legend { font-size:12px; color:var(--muted); margin-top:8px; }
  .legend span { display:inline-block; margin-right:12px; }
  .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; vertical-align:middle; }
  footer { color:var(--muted); font-size:12px; text-align:center; padding:16px; }
  a { color:var(--accent); }
  .rev { font-size:11px; color:#b58900; background:#fdf3d0; padding:1px 6px; border-radius:8px; }
  /* map popup */
  .popup { font-size:13px; max-width:280px; }
  .phead { font-size:14px; margin-bottom:3px; }
  .pdot { display:inline-block; width:9px;height:9px;border-radius:50%; margin-right:5px; vertical-align:middle; }
  .pmeta { color:var(--muted); font-size:12px; }
  .pcas { color:#a0332b; font-size:12px; font-weight:600; margin:2px 0; }
  .pimg { width:100%; max-height:150px; object-fit:cover; border-radius:6px; margin:6px 0; }
  .pen { margin:4px 0 2px; }
  .pzh { color:#333; font-size:13px; }
  .plink { margin-top:5px; }
  /* recent feed */
  #feed { max-height:520px; overflow-y:auto; }
  .item { display:flex; gap:10px; padding:10px 0; border-bottom:1px solid var(--line); }
  .item:last-child{ border-bottom:none; }
  .ithumb img { width:76px; height:76px; object-fit:cover; border-radius:6px; }
  .ithumb:empty { width:0; }
  .ibody { flex:1; min-width:0; }
  .ihead { font-size:14px; }
  .idate { color:var(--muted); font-size:12px; margin-left:4px; }
  .iloc { color:var(--muted); font-size:12px; }
  .idesc { font-size:13px; margin:3px 0 1px; }
  .izh { font-size:13px; color:#444; }
  .ilink { font-size:12px; margin-top:2px; }
  .empty { color:var(--muted); font-size:13px; padding:20px; text-align:center; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="sub">Live monitor of recent news-reported human–large-carnivore conflict in China &amp; Taiwan,
    detected automatically each week. Last updated <b id="gen"></b>.
    Showing <b><span id="winLabel"></span></b>. Historical (2005–2024) paper data is not shown here.
    <span id="autonote" style="color:#a0332b"></span></div>
</header>
<div class="wrap">
  <div class="cards" id="cards"></div>
  <div class="filters">
    <div><label>Time window</label><select id="fWindow"></select></div>
    <div><label>Species</label><select id="fSpecies"><option value="">All species</option></select></div>
    <div><label>Conflict type</label><select id="fType"><option value="">All types</option></select></div>
    <div class="chk"><label>&nbsp;</label><input type="checkbox" id="fReview"> show items under review</div>
    <div style="align-self:flex-end;"><button id="reset">Reset</button></div>
  </div>

  <div class="panel">
    <h2>Recent incidents — where they happened</h2>
    <div id="map"></div>
    <div class="legend" id="legend"></div>
  </div>

  <div class="grid2">
    <div class="panel">
      <h2>Latest incidents</h2>
      <div id="feed"></div>
    </div>
    <div>
      <div class="panel"><h2>Incidents per month</h2><canvas id="trend" height="130"></canvas></div>
      <div class="panel"><h2>By species</h2><canvas id="bySpecies" height="150"></canvas></div>
    </div>
  </div>
</div>
<footer>
  Automated weekly monitor extending <i>Mapping Two Decades of Human-Large Carnivore Conflict in China</i>.
  Incidents are detected from curated Chinese/Taiwan news sources, coded by an LLM against the study's criteria,
  and geocoded with a location-uncertainty estimate. Human–carnivore conflict is rare, so quiet weeks are normal.
  <span class="rev">Items under review</span> are hidden until confirmed.
</footer>
<script>
const DATA = __PAYLOAD__;
""" + _APP_JS + r"""
</script>
</body>
</html>"""
