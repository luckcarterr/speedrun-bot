from flask import Flask, jsonify, request
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
    "Ruby":        "♦️",
    "Diamond":     "💎",
    "Platinum":    "⚜️",
    "Gold":        "🟡",
    "Silver":      "⚪",
    "Bronze":      "🟤",
    "Grandmaster": "🌟",
}

TITLE_COLORS = {
    "Master":      "#FFD700",
    "Ruby":        "#FF4C6A",
    "Diamond":     "#4FC3F7",
    "Platinum":    "#B0BEC5",
    "Gold":        "#FFA726",
    "Silver":      "#90A4AE",
    "Bronze":      "#A1887F",
    "Grandmaster": "#AA00FF",
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
    meta = {"season": 1, "recent_duels": [], "registration": False, "tags": {}, "all_duels": []}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            players = json.load(f)
    if os.path.exists(META_FILE):
        with open(META_FILE) as f:
            meta = json.load(f)
    return players, meta

def enrich_player(p, season_rank, alltime_rank):
    p = dict(p)
    p["season_rank"] = season_rank
    p["alltime_rank"] = alltime_rank
    p["season_title"] = get_title(p["elo"])
    p["season_title_emoji"] = TITLE_EMOJIS.get(p["season_title"], "")
    p["season_title_color"] = TITLE_COLORS.get(p["season_title"], "#aaa")
    p["alltime_title"] = get_alltime_title(p["alltime_elo"])
    p["alltime_title_emoji"] = TITLE_EMOJIS.get(p["alltime_title"], "")
    p["alltime_title_color"] = TITLE_COLORS.get(p["alltime_title"], "#aaa")
    p["highlighted_tag"] = p.get("highlighted_tag") or ""
    p["tags"] = p.get("tags", [])
    p["wl_ratio"] = round(p["wins"] / p["losses"], 2) if p.get("losses", 0) > 0 else None
    p["alltime_wl_ratio"] = round(p["alltime_wins"] / p["alltime_losses"], 2) if p.get("alltime_losses", 0) > 0 else None
    p["discord_avatar"] = p.get("discord_avatar") or ""
    p["discord_username"] = p.get("discord_username") or ""
    return p

@app.route("/api/data")
def api_data():
    players, meta = load_data()
    sorted_season = sorted(players.values(), key=lambda p: p["elo"], reverse=True)
    sorted_alltime = sorted(players.values(), key=lambda p: p["alltime_elo"], reverse=True)
    enriched_season = [enrich_player(p, i+1, next((j+1 for j, x in enumerate(sorted_alltime) if x["name"] == p["name"]), -1)) for i, p in enumerate(sorted_season)]
    enriched_alltime = [enrich_player(p, next((j+1 for j, x in enumerate(sorted_season) if x["name"] == p["name"]), -1), i+1) for i, p in enumerate(sorted_alltime)]

    # Server stats
    all_duels = meta.get("all_duels", [])
    total_duels = len(all_duels)
    biggest_upset = None
    biggest_margin = 0
    for d in all_duels:
        winner_p = players.get(d["winner"].lower())
        loser_p = players.get(d["loser"].lower())
        if winner_p and loser_p:
            diff = loser_p["alltime_elo"] - winner_p["alltime_elo"]
            if diff > biggest_upset_diff if biggest_upset else True:
                biggest_upset_diff = diff
                biggest_upset = d
    longest_streak = max((abs(p.get("streak", 0)) for p in players.values()), default=0)
    streak_holder = next((p["name"] for p in players.values() if abs(p.get("streak", 0)) == longest_streak and longest_streak > 0), None)
    highest_elo_ever = max((p.get("alltime_peak_elo", 0) for p in players.values()), default=0)
    highest_elo_player = next((p["name"] for p in players.values() if p.get("alltime_peak_elo", 0) == highest_elo_ever), None)

    return jsonify({
        "season": meta.get("season", 1),
        "registration": meta.get("registration", False),
        "recent_duels": meta.get("recent_duels", []),
        "all_duels": all_duels[-20:],
        "leaderboard": enriched_season,
        "alltime_leaderboard": enriched_alltime,
        "tags": meta.get("tags", {}),
        "stats": {
            "total_players": len(players),
            "total_duels": total_duels,
            "longest_streak": longest_streak,
            "streak_holder": streak_holder,
            "highest_elo_ever": highest_elo_ever,
            "highest_elo_player": highest_elo_player,
            "biggest_upset": biggest_upset,
        }
    })

@app.route("/api/player/<name>")
def api_player(name):
    players, meta = load_data()
    p = players.get(name.lower())
    if not p:
        return jsonify({"error": "Player not found"}), 404
    sorted_season = sorted(players.values(), key=lambda x: x["elo"], reverse=True)
    sorted_alltime = sorted(players.values(), key=lambda x: x["alltime_elo"], reverse=True)
    season_rank = next((i+1 for i, x in enumerate(sorted_season) if x["name"].lower() == name.lower()), -1)
    alltime_rank = next((i+1 for i, x in enumerate(sorted_alltime) if x["name"].lower() == name.lower()), -1)
    result = enrich_player(p, season_rank, alltime_rank)
    result["tags_detail"] = [{"name": t, "description": meta["tags"].get(t.lower(), {}).get("description", ""), "highlighted": (p.get("highlighted_tag") or "").lower() == t.lower()} for t in p.get("tags", [])]
    # Player duel history
    all_duels = meta.get("all_duels", [])
    player_duels = [d for d in all_duels if d["player1"].lower() == name.lower() or d["player2"].lower() == name.lower()]
    result["duel_history"] = player_duels[-10:]
    return jsonify(result)

@app.route("/api/h2h/<p1>/<p2>")
def api_h2h(p1, p2):
    players, meta = load_data()
    player1 = players.get(p1.lower())
    player2 = players.get(p2.lower())
    if not player1 or not player2:
        return jsonify({"error": "Player not found"}), 404
    all_duels = meta.get("all_duels", [])
    h2h = [d for d in all_duels if
           (d["player1"].lower() == p1.lower() and d["player2"].lower() == p2.lower()) or
           (d["player1"].lower() == p2.lower() and d["player2"].lower() == p1.lower())]
    p1_wins = sum(1 for d in h2h if d["winner"].lower() == p1.lower())
    p2_wins = sum(1 for d in h2h if d["winner"].lower() == p2.lower())
    return jsonify({
        "player1": enrich_player(player1, 0, 0),
        "player2": enrich_player(player2, 0, 0),
        "p1_wins": p1_wins,
        "p2_wins": p2_wins,
        "total": len(h2h),
        "duels": h2h[-10:],
    })

HTML = open("index.html").read() if os.path.exists("index.html") else "<h1>Loading...</h1>"

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    return open("index.html").read() if os.path.exists("index.html") else "<h1>Site loading...</h1>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
