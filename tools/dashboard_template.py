"""The static-dashboard HTML/JS template. Kept separate from build_dashboard.py
so the builder stays readable. `__PAYLOAD__` is replaced with inlined JSON.

Self-contained: Leaflet (map) + Chart.js (charts) from CDN; all incident data
inlined. Works opened directly from disk, served by GitHub Pages, or embedded in
a WordPress <iframe>. Client-side filters drive every panel.
"""

_APP_JS = r"""
const $ = s => document.querySelector(s);
const COLORS = DATA.species_colors;
const R = DATA.records;
const years = R.map(r=>r.yr).filter(v=>v!=null);
const YMIN = Math.min(...years), YMAX = Math.max(...years);

// header
$("#gen").textContent = DATA.generated;
$("#counts").textContent = `${DATA.n_total} incidents shown (${DATA.n_hist} historical, ${DATA.n_new} newly monitored).`;

// filter controls
const spSet = [...new Set(R.map(r=>r.sp))].sort();
const tySet = DATA.conflict_types;
spSet.forEach(s=>{ let o=document.createElement("option"); o.value=s; o.textContent=s; $("#fSpecies").appendChild(o); });
tySet.forEach(t=>{ let o=document.createElement("option"); o.value=t; o.textContent=t; $("#fType").appendChild(o); });
const yMin=$("#fYearMin"), yMax=$("#fYearMax");
[yMin,yMax].forEach(el=>{ el.min=YMIN; el.max=YMAX; });
yMin.value=YMIN; yMax.value=YMAX;

// map
const map = L.map('map',{scrollWheelZoom:false}).setView([35,103],4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  {attribution:'&copy; OpenStreetMap, &copy; CARTO', maxZoom:12}).addTo(map);
let markerLayer = L.layerGroup().addTo(map);

function current(){
  const sp=$("#fSpecies").value, ty=$("#fType").value, src=$("#fSrc").value;
  const y0=+yMin.value, y1=+yMax.value;
  const lo=Math.min(y0,y1), hi=Math.max(y0,y1);
  $("#yrLabel").textContent = `${lo}–${hi}`;
  return R.filter(r=>
    (!sp||r.sp===sp) && (!ty||r.type===ty) && (!src||r.src===src) &&
    (r.yr==null || (r.yr>=lo && r.yr<=hi)));
}

function drawMap(rows){
  markerLayer.clearLayers();
  rows.forEach(r=>{
    const c = COLORS[r.sp]||"#333";
    if(r.src==="new" && r.unc){
      L.circle([r.lat,r.lon],{radius:r.unc,color:c,weight:1,opacity:.35,fillOpacity:.05}).addTo(markerLayer);
    }
    const m=L.circleMarker([r.lat,r.lon],{radius:r.src==="new"?6:4,color:c,weight:r.src==="new"?2:1,
      fillColor:c,fillOpacity:.7}).addTo(markerLayer);
    const date=(r.yr?r.yr:"?")+(r.mo?("-"+String(r.mo).padStart(2,"0")):"");
    const link=r.url?`<br><a href="${r.url}" target="_blank" rel="noopener">source</a>`:"";
    m.bindPopup(`<b>${r.sp}</b> — ${r.type}<br>${r.prov}${r.cty} · ${date}`+
      (r.vic?`<br>victim: ${r.vic}`:"")+(r.src==="new"?` <span class="rev">[new]</span>`:"")+link);
  });
}

// charts
let trendChart, spChart, tyChart;
function countBy(rows,key){ const m={}; rows.forEach(r=>{const k=r[key]; if(k!=null&&k!=="") m[k]=(m[k]||0)+1;}); return m; }

function drawCharts(rows){
  // trend stacked by type
  const yrs=[]; for(let y=YMIN;y<=YMAX;y++) yrs.push(y);
  const byType={};
  tySet.forEach(t=>byType[t]=yrs.map(()=>0));
  rows.forEach(r=>{ if(r.yr!=null && byType[r.type]) byType[r.type][r.yr-YMIN]++; });
  const typePalette=["#b5651d","#e0a458","#7a9e7e","#4c6e91","#a0524d","#c9b458","#8a6d9e"];
  const dsT=tySet.map((t,i)=>({label:t,data:byType[t],backgroundColor:typePalette[i%typePalette.length]}));
  if(trendChart) trendChart.destroy();
  trendChart=new Chart($("#trend"),{type:"bar",data:{labels:yrs,datasets:dsT},
    options:{responsive:true,scales:{x:{stacked:true},y:{stacked:true}},plugins:{legend:{position:"bottom",labels:{boxWidth:12,font:{size:11}}}}}});
  // species
  const sp=countBy(rows,"sp"); const spK=Object.keys(sp).sort((a,b)=>sp[b]-sp[a]);
  if(spChart) spChart.destroy();
  spChart=new Chart($("#bySpecies"),{type:"bar",data:{labels:spK,
    datasets:[{data:spK.map(k=>sp[k]),backgroundColor:spK.map(k=>COLORS[k]||"#333")}]},
    options:{indexAxis:"y",plugins:{legend:{display:false}}}});
  // type
  const ty=countBy(rows,"type"); const tyK=Object.keys(ty).sort((a,b)=>ty[b]-ty[a]);
  if(tyChart) tyChart.destroy();
  tyChart=new Chart($("#byType"),{type:"bar",data:{labels:tyK,
    datasets:[{data:tyK.map(k=>ty[k]),backgroundColor:"#4c6e91"}]},
    options:{indexAxis:"y",plugins:{legend:{display:false}}}});
}

function drawCards(rows){
  const deaths=rows.reduce((a,r)=>a,0);
  const nSp=new Set(rows.map(r=>r.sp)).size;
  const cards=[["Incidents",rows.length],["Species",nSp],
    ["Newly monitored",rows.filter(r=>r.src==="new").length],
    ["Provinces",new Set(rows.map(r=>r.prov).filter(Boolean)).size]];
  $("#cards").innerHTML=cards.map(([l,n])=>`<div class="card"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
}

function legend(){
  $("#legend").innerHTML = spSet.map(s=>`<span><span class="dot" style="background:${COLORS[s]||'#333'}"></span>${s}</span>`).join("")
    + `<br><span style="margin-top:4px">Larger ringed points = newly monitored (ring ≈ location uncertainty); small points = historical.</span>`;
}

function refresh(){ const rows=current(); drawMap(rows); drawCharts(rows); drawCards(rows); }
["#fSpecies","#fType","#fSrc"].forEach(s=>$(s).addEventListener("change",refresh));
[yMin,yMax].forEach(el=>el.addEventListener("input",refresh));
$("#reset").addEventListener("click",()=>{ $("#fSpecies").value="";$("#fType").value="";$("#fSrc").value="";
  yMin.value=YMIN;yMax.value=YMAX; refresh(); });
legend(); refresh();
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
  .filters { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:8px 0 16px;
             background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 16px; }
  .filters label { font-size:12px; color:var(--muted); display:block; margin-bottom:3px; }
  select, input[type=range] { font-size:14px; }
  .panel { background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:16px; }
  .panel h2 { margin:0 0 10px; font-size:15px; font-weight:600; }
  #map { height:460px; border-radius:8px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  @media (max-width:820px){ .grid2{ grid-template-columns:1fr; } }
  .legend { font-size:12px; color:var(--muted); margin-top:8px; }
  .legend span { display:inline-block; margin-right:12px; }
  .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; vertical-align:middle; }
  footer { color:var(--muted); font-size:12px; text-align:center; padding:16px; }
  a { color:var(--accent); }
  .rev { font-size:11px; color:#b58900; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="sub">Automated weekly monitor of news-reported human–large-carnivore conflict.
    Last updated <b id="gen"></b>. <span id="counts"></span></div>
</header>
<div class="wrap">
  <div class="cards" id="cards"></div>
  <div class="filters">
    <div><label>Species</label><select id="fSpecies"><option value="">All species</option></select></div>
    <div><label>Conflict type</label><select id="fType"><option value="">All types</option></select></div>
    <div><label>Source</label><select id="fSrc">
      <option value="">Historical + new</option><option value="hist">Historical (2005–2024)</option>
      <option value="new">Newly monitored</option></select></div>
    <div style="flex:1; min-width:220px;">
      <label>Year: <span id="yrLabel"></span></label>
      <input type="range" id="fYearMin" style="width:45%"><input type="range" id="fYearMax" style="width:45%">
    </div>
    <div style="align-self:flex-end;"><button id="reset">Reset</button></div>
  </div>

  <div class="panel">
    <h2>Where conflicts occur</h2>
    <div id="map"></div>
    <div class="legend" id="legend"></div>
  </div>

  <div class="panel">
    <h2>Conflicts reported per year</h2>
    <canvas id="trend" height="90"></canvas>
  </div>

  <div class="grid2">
    <div class="panel"><h2>By species</h2><canvas id="bySpecies" height="150"></canvas></div>
    <div class="panel"><h2>By conflict type</h2><canvas id="byType" height="150"></canvas></div>
  </div>
</div>
<footer>
  Data: 520 historical incidents (2005–2024, Mapping Two Decades of Human-Large Carnivore Conflict in China)
  extended weekly by automated news monitoring. New points carry a location-uncertainty estimate; historical
  points were geocoded manually. <span class="rev">Incidents under review are not shown until confirmed.</span>
</footer>
<script>
const DATA = __PAYLOAD__;
""" + _APP_JS + r"""
</script>
</body>
</html>"""
