"""Full-featured BigQuery dashboard — Looker-style analytics."""
import os, json
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)
PROJECT = os.environ.get("PROJECT_ID", "xtremetag-1984")
DATASET = os.environ.get("BQ_DATASET", "dj_funk")
TABLE = f"`{PROJECT}.{DATASET}.tracks`"

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DJ Funk — Looker Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root{--bg:#f8f9fa;--card:#fff;--text:#1a1a2e;--muted:#6c757d;--accent:#e94560;--border:#e9ecef}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,sans-serif}
.header{background:var(--card);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;gap:16px}
.header h1{font-size:20px;font-weight:600;color:var(--accent)}
.header .badge{background:var(--accent);color:#fff;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;padding:20px 24px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px}
.kpi .val{font-size:32px;font-weight:700;color:var(--accent)}
.kpi .lbl{font-size:12px;color:var(--muted);margin-top:4px;text-transform:uppercase;letter-spacing:.5px}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:0 24px 20px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px}
.chart-card h3{font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px}
.chart-card canvas{max-height:300px}
.table-card{background:var(--card);border:1px solid var(--border);border-radius:8px;margin:0 24px 20px;overflow:hidden}
.table-card h3{padding:16px 20px 0;font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:10px 20px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;border-bottom:2px solid var(--border);background:#fafbfc}
td{padding:10px 20px;font-size:13px;border-bottom:1px solid var(--border)}
tr:hover td{background:#f0f4ff}
.tag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}
.tag-gemini{background:#fce4ec;color:var(--accent)}
.tag-genre{background:#e3f2fd;color:#1565c0}
.tag-key{font-family:monospace;font-size:11px;background:#f3e5f5;color:#7b1fa2;padding:2px 6px;border-radius:4px}
input,select{padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:#fff}
input:focus,select:focus{outline:none;border-color:var(--accent)}
.filters{display:flex;gap:12px;padding:16px 24px;flex-wrap:wrap;align-items:center}
.conv-ai{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:20px 24px;margin:0 24px 20px;border-radius:8px}
.conv-ai h3{font-size:14px;margin-bottom:8px}
.conv-ai input{width:100%;padding:12px;border:none;border-radius:6px;font-size:14px;background:rgba(255,255,255,.1);color:#fff}
.conv-ai input::placeholder{color:rgba(255,255,255,.4)}
.conv-ai .result{margin-top:12px;font-size:13px;color:rgba(255,255,255,.8);min-height:24px}
@media(max-width:900px){.charts{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="header">
    <h1>🎧 DJ Funk Analytics</h1>
    <span class="badge">BigQuery</span>
    <span style="color:var(--muted);font-size:12px;margin-left:auto">Live · {{PROJECT}}</span>
</div>
<div class="grid" id="kpis"></div>
<div class="filters">
    <input type="text" id="search" placeholder="Search tracks..." oninput="render()">
    <select id="genreFilter" onchange="render()"><option value="">All Genres</option></select>
    <select id="geminiFilter" onchange="render()">
        <option value="">All Sources</option>
        <option value="1">Gemini Tagged</option>
        <option value="0">Tag Only</option>
    </select>
    <span style="color:var(--muted);font-size:12px" id="rowCount"></span>
</div>
<div class="conv-ai">
    <h3>💬 Conversational Analytics</h3>
    <input type="text" id="nlQuery" placeholder="Ask anything... e.g. 'show me tech house tracks around 128 BPM in Am' or 'what genres have the highest energy?'" onkeydown="if(event.key==='Enter')askNL()">
    <div class="result" id="nlResult"></div>
</div>
<div class="charts" id="charts"></div>
<div class="table-card">
    <h3>Tracks</h3>
    <table><thead><tr><th>Title</th><th>Artist</th><th>Genre</th><th>BPM</th><th>Key</th><th>Energy</th><th>Gemini</th></tr></thead><tbody id="tbody"></tbody></table>
</div>
<script>
let allTracks=[],allGenres=[],stats={};

async function load(){
    const r=await fetch('/api/data');
    const d=await r.json();
    allTracks=d.tracks;allGenres=d.genres;stats=d.stats;
    document.getElementById('genreFilter').innerHTML='<option value="">All Genres</option>'+allGenres.map(g=>`<option>${g}</option>`).join('');
    render();
}
function filterTracks(){
    let t=allTracks;
    const s=document.getElementById('search').value.toLowerCase();
    const g=document.getElementById('genreFilter').value;
    const gm=document.getElementById('geminiFilter').value;
    if(s) t=t.filter(x=>(x.title||'').toLowerCase().includes(s)||(x.artist||'').toLowerCase().includes(s));
    if(g) t=t.filter(x=>x.genre===g);
    if(gm==='1') t=t.filter(x=>x.gemini_genre);
    if(gm==='0') t=t.filter(x=>!x.gemini_genre);
    return t;
}
function render(){
    const t=filterTracks();
    document.getElementById('rowCount').textContent=t.length+' tracks';
    document.getElementById('kpis').innerHTML=`
        <div class="kpi"><div class="val">${stats.total||0}</div><div class="lbl">Total Tracks</div></div>
        <div class="kpi"><div class="val">${allGenres.length}</div><div class="lbl">Genres</div></div>
        <div class="kpi"><div class="val">${stats.gemini||0}</div><div class="lbl">Gemini Tagged</div></div>
        <div class="kpi"><div class="val">${Math.round(stats.avg_bpm||0)}</div><div class="lbl">Avg BPM</div></div>
    `;
    document.getElementById('tbody').innerHTML=t.slice(0,100).map(x=>`
        <tr>
            <td><strong>${x.title||'—'}</strong></td>
            <td>${x.artist||'—'}</td>
            <td><span class="tag tag-genre">${x.genre||'Unknown'}</span></td>
            <td>${x.bpm?Math.round(x.bpm):'—'}</td>
            <td>${x.key?`<span class="tag-key">${x.key}</span>`:'—'}</td>
            <td>${x.spotify_energy?`${Math.round(x.spotify_energy*100)}%`:'—'}</td><td>${x.energy_level || '—'}</td>
            <td>${x.gemini_genre?`<span class="tag tag-gemini">${x.gemini_genre} ${Math.round(x.gemini_genre_confidence*100)}%</span>`:'—'}</td>
        </tr>
    `).join('');
    drawCharts();
}
async function askNL(){
    const q=document.getElementById('nlQuery').value;
    if(!q)return;
    document.getElementById('nlResult').textContent='Thinking...';
    const r=await fetch('/api/ask?q='+encodeURIComponent(q));
    const d=await r.json();
    document.getElementById('nlResult').innerHTML='<strong>SQL:</strong> <code>'+d.sql+'</code><br><br><strong>Answer:</strong> '+d.answer;
}
let charts={};
function drawCharts(){
    // Destroy old charts
    Object.values(charts).forEach(c=>c.destroy());
    charts={};
    document.getElementById('charts').innerHTML=`
        <div class="chart-card"><h3>Genre Distribution</h3><canvas id="genreChart"></canvas></div>
        <div class="chart-card"><h3>BPM Distribution</h3><canvas id="bpmChart"></canvas></div>
    `;
    // Genre pie
    const gc={};allTracks.forEach(t=>{const g=t.genre||'Unknown';gc[g]=(gc[g]||0)+1});
    const glabels=Object.keys(gc).slice(0,10),gdata=glabels.map(k=>gc[k]);
    charts.genre=new Chart(document.getElementById('genreChart'),{type:'doughnut',data:{labels:glabels,datasets:[{data:gdata,backgroundColor:['#e94560','#0f3460','#16213e','#533483','#e23e57','#1a1a2e','#a239ca','#4717f6','#00b4d8','#e76f51']}]},options:{plugins:{legend:{position:'right',labels:{boxWidth:12,font:{size:11}}}}}});
    // BPM histogram
    const bpms=allTracks.map(t=>t.bpm).filter(b=>b>0);
    const bins=10,min=Math.min(...bpms),max=Math.max(...bpms),step=(max-min)/bins;
    const bdata=Array(bins).fill(0);
    bpms.forEach(b=>{const i=Math.min(Math.floor((b-min)/step),bins-1);bdata[i]++});
    const blabels=Array.from({length:bins},(_,i)=>Math.round(min+i*step)+'-'+Math.round(min+(i+1)*step));
    charts.bpm=new Chart(document.getElementById('bpmChart'),{type:'bar',data:{labels:blabels,datasets:[{data:bdata,backgroundColor:'#e94560',borderRadius:4}]},options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'#e9ecef'}},x:{grid:{display:false}}}}});
}
load();
</script>
</body></html>"""

@app.route("/")
def index():
    return render_template_string(HTML, PROJECT=PROJECT)

@app.route("/api/data")
def api_data():
    from google.cloud import bigquery
    client = bigquery.Client(project=PROJECT)
    # Stats
    stats = client.query(f"""
        SELECT
            COUNT(*) as total,
            COUNT(DISTINCT genre) as genres,
            COUNTIF(gemini_genre IS NOT NULL) as gemini,
            ROUND(AVG(bpm),0) as avg_bpm,
            ROUND(AVG(spotify_energy),2) as avg_energy
        FROM `{PROJECT}.dj_funk_marts.dim_tracks`
    """).result().to_dataframe().iloc[0].to_dict()

    # Genres
    genres = client.query(f"""
        SELECT genre FROM `{PROJECT}.dj_funk_marts.dim_tracks`
        WHERE genre IS NOT NULL AND genre != 'Unknown'
        GROUP BY genre ORDER BY COUNT(*) DESC LIMIT 30
    """).result().to_dataframe()["genre"].tolist()

    # Tracks
    tracks = client.query(f"""
        SELECT title, artist, genre, bpm, key, key_camelot,
               spotify_energy, spotify_danceability, spotify_valence,
               gemini_genre, gemini_genre_confidence,
               energy_level, energy_label,
               duration_sec, file_size_mb, ingested_at
        FROM `{PROJECT}.dj_funk_marts.dim_tracks`
        ORDER BY ingested_at DESC LIMIT 500
    """).result().to_dataframe().to_dict(orient="records")
    # Convert NaN floats to null for valid JSON
    for t in tracks:
        for k, v in list(t.items()):
            if isinstance(v, float) and (v != v):  # NaN check
                t[k] = None
        if t.get("ingested_at"):
            t["ingested_at"] = str(t["ingested_at"])

    return jsonify({"stats": stats, "genres": genres, "tracks": tracks})

@app.route("/api/ask")
def api_ask():
    """Conversational analytics — NL to SQL using simple keyword matching.
    In production, this would use Gemini for NL→SQL."""
    q = __import__("flask").request.args.get("q", "")
    if not q:
        return jsonify({"sql": "", "answer": "Ask a question!"})

    q_lower = q.lower()

    # Simple NL→SQL patterns
    if "tech house" in q_lower and "bpm" in q_lower:
        bpm_match = __import__("re").search(r"(\d+)\s*bpm", q_lower)
        bpm = int(bpm_match.group(1)) if bpm_match else 128
        sql = f"SELECT title, artist, bpm, key, genre FROM {TABLE} WHERE LOWER(genre) LIKE '%tech house%' AND bpm BETWEEN {bpm-5} AND {bpm+5} ORDER BY bpm LIMIT 20"
    elif "genres" in q_lower and ("energy" in q_lower or "highest" in q_lower):
        sql = f"SELECT genre, ROUND(AVG(spotify_energy),2) as avg_energy, COUNT(*) as tracks FROM {TABLE} WHERE spotify_energy IS NOT NULL GROUP BY genre ORDER BY avg_energy DESC LIMIT 10"
    elif "gemini" in q_lower:
        sql = f"SELECT title, artist, genre, gemini_genre, gemini_genre_confidence, energy_level, comment FROM {TABLE} WHERE gemini_genre IS NOT NULL ORDER BY gemini_genre_confidence DESC LIMIT 20"
    elif "genre" in q_lower and "count" in q_lower:
        sql = f"SELECT genre, COUNT(*) as count FROM {TABLE} WHERE genre IS NOT NULL GROUP BY genre ORDER BY count DESC LIMIT 15"
    elif "bpm" in q_lower and "key" in q_lower:
        sql = f"SELECT title, artist, bpm, key, genre FROM {TABLE} ORDER BY bpm DESC LIMIT 30"
    else:
        sql = f"SELECT title, artist, genre, bpm, key FROM {TABLE} ORDER BY ingested_at DESC LIMIT 10"

    from google.cloud import bigquery
    client = bigquery.Client(project=PROJECT)
    try:
        df = client.query(sql).result().to_dataframe()
        answer = f"Found {len(df)} tracks. " + ", ".join(
            f"{r.get('title','?')} ({r.get('genre','?')}@{int(r.get('bpm',0))}BPM)"
            for _, r in df.head(5).iterrows()
        )
    except Exception as e:
        answer = f"Error: {e}"

    return jsonify({"sql": sql, "answer": answer})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
