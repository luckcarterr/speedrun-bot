from flask import Flask, jsonify, render_template_string
import json
import os

app = Flask(__name__)

DATA_FILE = "players.json"
META_FILE = "meta.json"

SEASON_TITLES = [
    (2000, "Master"),
    (1849, "Ruby"),
    (1700, "Diamond"),
    (1500, "Platinum"),
    (1200, "Gold"),
    (1000, "Silver"),
    (0,    "Bronze"),
]

TITLE_EMOJIS = {
    "Master":      "👑",
    "Ruby":        "💎",
    "Diamond":     "🔷",
    "Platinum":    "⚜️",
    "Gold":        "🥇",
    "Silver":      "🥈",
    "Bronze":      "🥉",
    "Grandmaster": "🌟",
}

GRANDMASTER_THRESHOLD = 2250

def get_title(elo):
    for threshold, title in SEASON_TITLES:
        if elo >= threshold:
            return title
    return "Bronze"

def get_alltime_title(elo):
    if elo >= GRANDMASTER_THRESHOLD:
        return "Grandmaster"
    return get_title(elo)

def load_data():
    players = {}
    meta = {"season": 1, "recent_duels": [], "registration": False}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            players = json.load(f)
    if os.path.exists(META_FILE):
        with open(META_FILE) as f:
            meta = json.load(f)
    return players, meta

@app.route("/api/data")
def api_data():
    players, meta = load_data()
    sorted_season = sorted(players.values(), key=lambda p: p["elo"], reverse=True)
    sorted_alltime = sorted(players.values(), key=lambda p: p["alltime_elo"], reverse=True)

    for i, p in enumerate(sorted_season):
        p["season_rank"] = i + 1
        p["season_title"] = get_title(p["elo"])
        p["season_title_emoji"] = TITLE_EMOJIS.get(p["season_title"], "")
    for i, p in enumerate(sorted_alltime):
        p["alltime_rank"] = i + 1
        p["alltime_title"] = get_alltime_title(p["alltime_elo"])
        p["alltime_title_emoji"] = TITLE_EMOJIS.get(p["alltime_title"], "")

    return jsonify({
        "season": meta.get("season", 1),
        "registration": meta.get("registration", False),
        "recent_duels": meta.get("recent_duels", []),
        "leaderboard": sorted_season,
        "alltime_leaderboard": sorted_alltime,
    })

HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Speedrun Duel Leaderboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f0f13; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; min-height: 100vh; }
  header { background: #1a1a24; border-bottom: 2px solid #f0c040; padding: 24px 32px; display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 1.8rem; color: #f0c040; letter-spacing: 1px; }
  header .season-badge { background: #2a2a3a; border: 1px solid #444; border-radius: 20px; padding: 4px 14px; font-size: 0.85rem; color: #aaa; }
  header .reg-badge { background: #3a2a00; border: 1px solid #f0c040; border-radius: 20px; padding: 4px 14px; font-size: 0.85rem; color: #f0c040; }
  .container { max-width: 1100px; margin: 0 auto; padding: 32px 16px; }
  .tabs { display: flex; gap: 8px; margin-bottom: 24px; }
  .tab { padding: 8px 22px; border-radius: 8px; border: 1px solid #333; background: #1a1a24; color: #aaa; cursor: pointer; font-size: 0.95rem; transition: all 0.2s; }
  .tab.active { background: #f0c040; color: #0f0f13; border-color: #f0c040; font-weight: 700; }
  .tab:hover:not(.active) { border-color: #f0c040; color: #f0c040; }
  .panel { display: none; }
  .panel.active { display: block; }
  table { width: 100%; border-collapse: collapse; background: #1a1a24; border-radius: 12px; overflow: hidden; }
  th { background: #22223a; color: #f0c040; padding: 12px 16px; text-align: left; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; }
  td { padding: 12px 16px; border-bottom: 1px solid #2a2a3a; font-size: 0.95rem; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #22223a; }
  .rank-1 td:first-child { color: #ffd700; font-weight: 700; }
  .rank-2 td:first-child { color: #c0c0c0; font-weight: 700; }
  .rank-3 td:first-child { color: #cd7f32; font-weight: 700; }
  .elo { font-weight: 700; color: #f0c040; }
  .title-badge { font-size: 0.8rem; background: #2a2a3a; border-radius: 12px; padding: 2px 10px; margin-left: 6px; }
  .provisional { font-size: 0.75rem; color: #f0c040; margin-left: 6px; }
  .recent-duels { display: flex; flex-direction: column; gap: 12px; }
  .duel-card { background: #1a1a24; border-radius: 10px; padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; border: 1px solid #2a2a3a; }
  .duel-winner { color: #4ade80; font-weight: 700; }
  .duel-loser { color: #aaa; }
  .duel-margin { background: #2a2a3a; border-radius: 8px; padding: 4px 12px; font-size: 0.85rem; color: #f0c040; }
  .duel-season { font-size: 0.75rem; color: #666; }
  .section-title { font-size: 1.1rem; font-weight: 700; color: #f0c040; margin-bottom: 16px; letter-spacing: 1px; }
  .empty { color: #555; text-align: center; padding: 40px; }
  .wl { color: #aaa; font-size: 0.88rem; }
  .streak-w { color: #4ade80; font-size: 0.85rem; }
  .streak-l { color: #f87171; font-size: 0.85rem; }
  .refresh-btn { margin-left: auto; background: #2a2a3a; border: 1px solid #444; color: #aaa; border-radius: 8px; padding: 6px 16px; cursor: pointer; font-size: 0.85rem; transition: all 0.2s; }
  .refresh-btn:hover { border-color: #f0c040; color: #f0c040; }
  footer { text-align: center; color: #444; padding: 32px; font-size: 0.8rem; }
</style>
</head>
<body>
<header>
  <h1>🏆 Speedrun Duels</h1>
  <span class="season-badge" id="season-badge">Season 1</span>
  <span class="reg-badge" id="reg-badge" style="display:none">🟡 Registration Period</span>
  <button class="refresh-btn" onclick="loadData()">↻ Refresh</button>
</header>
<div class="container">
  <div class="tabs">
    <div class="tab active" onclick="switchTab('season')">Season Leaderboard</div>
    <div class="tab" onclick="switchTab('alltime')">All-Time Leaderboard</div>
    <div class="tab" onclick="switchTab('recent')">Recent Duels</div>
  </div>

  <div class="panel active" id="panel-season">
    <div class="section-title">Season Standings</div>
    <table>
      <thead><tr><th>#</th><th>Player</th><th>Elo</th><th>Title</th><th>W / L</th><th>Streak</th><th>Matches</th></tr></thead>
      <tbody id="season-tbody"><tr><td colspan="7" class="empty">Loading...</td></tr></tbody>
    </table>
  </div>

  <div class="panel" id="panel-alltime">
    <div class="section-title">All-Time Standings</div>
    <table>
      <thead><tr><th>#</th><th>Player</th><th>All-Time Elo</th><th>Title</th><th>W / L</th><th>Peak Elo</th><th>Matches</th></tr></thead>
      <tbody id="alltime-tbody"><tr><td colspan="7" class="empty">Loading...</td></tr></tbody>
    </table>
  </div>

  <div class="panel" id="panel-recent">
    <div class="section-title">Recent Duels</div>
    <div class="recent-duels" id="recent-list"><div class="empty">Loading...</div></div>
  </div>
</div>
<footer>Speedrun Duel System · Powered by Discord Bot</footer>

<script>
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', ['season','alltime','recent'][i] === name);
  });
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
}

async function loadData() {
  try {
    const res = await fetch('/api/data');
    const data = await res.json();

    document.getElementById('season-badge').textContent = 'Season ' + data.season;
    document.getElementById('reg-badge').style.display = data.registration ? 'inline' : 'none';

    // Season leaderboard
    const sb = document.getElementById('season-tbody');
    if (!data.leaderboard.length) {
      sb.innerHTML = '<tr><td colspan="7" class="empty">No players yet.</td></tr>';
    } else {
      sb.innerHTML = data.leaderboard.map((p, i) => {
        const streak = p.streak > 0 ? `<span class="streak-w">🔥${p.streak}W</span>` : p.streak < 0 ? `<span class="streak-l">❄️${Math.abs(p.streak)}L</span>` : '—';
        const prov = p.matches < 10 ? '<span class="provisional">⚠️</span>' : '';
        return `<tr class="rank-${i+1}">
          <td>#${i+1}</td>
          <td>${p.name}${prov}</td>
          <td class="elo">${p.elo}</td>
          <td>${p.season_title_emoji} ${p.season_title}</td>
          <td class="wl">${p.wins}W / ${p.losses}L</td>
          <td>${streak}</td>
          <td>${p.matches}</td>
        </tr>`;
      }).join('');
    }

    // All-time leaderboard
    const ab = document.getElementById('alltime-tbody');
    if (!data.alltime_leaderboard.length) {
      ab.innerHTML = '<tr><td colspan="7" class="empty">No players yet.</td></tr>';
    } else {
      ab.innerHTML = data.alltime_leaderboard.map((p, i) => `<tr class="rank-${i+1}">
        <td>#${i+1}</td>
        <td>${p.name}</td>
        <td class="elo">${p.alltime_elo}</td>
        <td>${p.alltime_title_emoji} ${p.alltime_title}</td>
        <td class="wl">${p.alltime_wins}W / ${p.alltime_losses}L</td>
        <td class="elo">${p.alltime_peak_elo}</td>
        <td>${p.alltime_matches}</td>
      </tr>`).join('');
    }

    // Recent duels
    const rl = document.getElementById('recent-list');
    if (!data.recent_duels.length) {
      rl.innerHTML = '<div class="empty">No duels logged yet.</div>';
    } else {
      rl.innerHTML = data.recent_duels.map(d => `
        <div class="duel-card">
          <div>
            <span class="duel-winner">🏆 ${d.winner}</span>
            <span style="color:#555; margin: 0 8px">def.</span>
            <span class="duel-loser">${d.loser}</span>
            <span class="duel-season"> · S${d.season}</span>
          </div>
          <span class="duel-margin">${d.margin}s margin</span>
        </div>`).join('');
    }
  } catch(e) {
    console.error(e);
  }
}

loadData();
setInterval(loadData, 30000);
</script>
</body>
</html>'''

@app.route("/")
def index():
    return HTML

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
