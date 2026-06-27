import discord
from discord import app_commands
import json
import os
import math

# ── Bot setup ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DATA_FILE = "players.json"
META_FILE = "meta.json"

# ── Title system ──────────────────────────────────────────────────────────────

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
    "Master":     "👑",
    "Ruby":       "💎",
    "Diamond":    "🔷",
    "Platinum":   "⚜️",
    "Gold":       "🥇",
    "Silver":     "🥈",
    "Bronze":     "🥉",
    "Grandmaster":"🌟",
}

GRANDMASTER_THRESHOLD = 2250  # All-time only

DUEL_QUEUE_CHANNEL = 1515670794162802709
DUEL_RESULTS_CHANNEL = 1520400967995097118

def get_title(elo: int) -> str:
    for threshold, title in SEASON_TITLES:
        if elo >= threshold:
            return title
    return "Bronze"

def get_alltime_title(elo: int) -> str:
    if elo >= GRANDMASTER_THRESHOLD:
        return "Grandmaster"
    return get_title(elo)

def next_title_info(elo: int) -> tuple:
    """Returns (next_title, elo_needed) or (None, None) if at Master."""
    for i, (threshold, title) in enumerate(SEASON_TITLES):
        if elo >= threshold:
            if i == 0:
                return None, None  # Already Master
            next_threshold, next_title = SEASON_TITLES[i - 1]
            return next_title, next_threshold - elo
    return "Silver", 1000 - elo

def progress_bar(current: int, target: int, start: int, length: int = 10) -> str:
    total = target - start
    done = current - start
    filled = max(0, min(length, round((done / total) * length))) if total > 0 else length
    return "▓" * filled + "░" * (length - filled)

# ── Data helpers ──────────────────────────────────────────────────────────────

def load_players() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_players(players: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(players, f, indent=2)

def load_meta() -> dict:
    if not os.path.exists(META_FILE):
        return {"season": 1, "recent_duels": [], "registration": False}
    with open(META_FILE, "r") as f:
        meta = json.load(f)
    if "registration" not in meta:
        meta["registration"] = False
    return meta

def save_meta(meta: dict):
    with open(META_FILE, "w") as f:
        json.dump(meta, f, indent=2)

def get_player(players: dict, name: str):
    return players.get(name.lower())

def set_player(players: dict, name: str, data: dict):
    players[name.lower()] = data
    save_players(players)

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

# ── Elo helpers ───────────────────────────────────────────────────────────────

BASE_K = 32
PROVISIONAL_K = 64
PROVISIONAL_MATCHES = 10
ELO_FLOOR = 100
ALLTIME_K_FACTOR = 0.5

def expected_score(player_elo: float, opponent_elo: float) -> float:
    return 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))

def margin_factor(time_diff_seconds: float) -> float:
    max_margin = 180
    factor = min(time_diff_seconds / max_margin, 1.0)
    return 1 + factor

def calculate_k(match_count: int, alltime: bool = False) -> float:
    base = PROVISIONAL_K if match_count < PROVISIONAL_MATCHES else BASE_K
    if alltime:
        base = base * ALLTIME_K_FACTOR
    return base

def calculate_elo_change(player_elo, opponent_elo, player_won, match_count, time_diff, alltime=False):
    k = calculate_k(match_count, alltime) * margin_factor(time_diff)
    expected = expected_score(player_elo, opponent_elo)
    actual = 1.0 if player_won else 0.0
    return round(k * (actual - expected), 2)

def parse_time(time_str: str) -> float:
    time_str = time_str.strip().replace(".", ":", 1) if time_str.count(".") == 2 else time_str.strip()
    parts = time_str.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        else:
            raise ValueError
    except ValueError:
        raise ValueError(f"Cannot parse time '{time_str}'. Use ss, mm:ss, or hh:mm:ss.")

def get_rank_position(players: dict, name: str, alltime: bool = False) -> int:
    key = "alltime_elo" if alltime else "elo"
    sorted_players = sorted(players.values(), key=lambda p: p.get(key, 0), reverse=True)
    for i, p in enumerate(sorted_players):
        if p["name"].lower() == name.lower():
            return i + 1
    return -1

def ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"

def default_player(name: str, starting_elo: int, season: int) -> dict:
    return {
        "name": name,
        "elo": starting_elo,
        "peak_elo": starting_elo,
        "matches": 0,
        "wins": 0,
        "losses": 0,
        "streak": 0,
        "alltime_elo": starting_elo,
        "alltime_peak_elo": starting_elo,
        "alltime_matches": 0,
        "alltime_wins": 0,
        "alltime_losses": 0,
        "season_joined": season,
        "season_history": {},
        "last_duel": None,
        "discord_id": None,
    }

# ── Commands ──────────────────────────────────────────────────────────────────

@tree.command(name="introduce", description="Add a new player to the Elo system.")
@app_commands.describe(player="Player's name", starting_elo="Starting Elo (default: 1000)")
async def introduce(interaction: discord.Interaction, player: str, starting_elo: int = 1000):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    meta = load_meta()
    if get_player(players, player):
        await interaction.response.send_message(f"⚠️ **{player}** is already in the system.", ephemeral=True)
        return
    data = default_player(player, starting_elo, meta["season"])
    set_player(players, player, data)
    embed = discord.Embed(title="✅ Player Introduced", color=discord.Color.green())
    embed.add_field(name="Player", value=player, inline=True)
    embed.add_field(name="Starting Elo", value=str(starting_elo), inline=True)
    embed.add_field(name="Season", value=f"Season {meta['season']}", inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="duel", description="Log a duel result and update both players' Elo.")
@app_commands.describe(
    player1="First player's name",
    player2="Second player's name",
    player1_time="Player 1's total time across 4 rounds (mm:ss or ss)",
    player2_time="Player 2's total time across 4 rounds (mm:ss or ss)",
)
async def duel(interaction: discord.Interaction, player1: str, player2: str, player1_time: str, player2_time: str):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    meta = load_meta()
    p1 = get_player(players, player1)
    p2 = get_player(players, player2)
    if not p1:
        await interaction.response.send_message(f"⚠️ **{player1}** is not in the system.", ephemeral=True)
        return
    if not p2:
        await interaction.response.send_message(f"⚠️ **{player2}** is not in the system.", ephemeral=True)
        return
    try:
        t1 = parse_time(player1_time)
        t2 = parse_time(player2_time)
    except ValueError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return

    if meta.get("registration", False):
        await interaction.response.send_message("⏳ The season is in **registration period**. Wait for an admin to use `/startseason`.", ephemeral=True)
        return

    p1_won = t1 < t2
    time_diff = abs(t1 - t2)

    p1_season_change = calculate_elo_change(p1["elo"], p2["elo"], p1_won, p1["matches"], time_diff)
    p2_season_change = calculate_elo_change(p2["elo"], p1["elo"], not p1_won, p2["matches"], time_diff)
    p1_alltime_change = calculate_elo_change(p1["alltime_elo"], p2["alltime_elo"], p1_won, p1["alltime_matches"], time_diff, alltime=True)
    p2_alltime_change = calculate_elo_change(p2["alltime_elo"], p1["alltime_elo"], not p1_won, p2["alltime_matches"], time_diff, alltime=True)

    old_p1_elo = p1["elo"]
    old_p2_elo = p2["elo"]
    old_p1_alltime = p1["alltime_elo"]
    old_p2_alltime = p2["alltime_elo"]

    p1["elo"] = max(ELO_FLOOR, round(p1["elo"] + p1_season_change))
    p2["elo"] = max(ELO_FLOOR, round(p2["elo"] + p2_season_change))
    p1["alltime_elo"] = max(ELO_FLOOR, round(p1["alltime_elo"] + p1_alltime_change))
    p2["alltime_elo"] = max(ELO_FLOOR, round(p2["alltime_elo"] + p2_alltime_change))

    p1["peak_elo"] = max(p1["peak_elo"], p1["elo"])
    p2["peak_elo"] = max(p2["peak_elo"], p2["elo"])
    p1["alltime_peak_elo"] = max(p1["alltime_peak_elo"], p1["alltime_elo"])
    p2["alltime_peak_elo"] = max(p2["alltime_peak_elo"], p2["alltime_elo"])

    p1["matches"] += 1
    p2["matches"] += 1
    p1["alltime_matches"] += 1
    p2["alltime_matches"] += 1

    if p1_won:
        p1["wins"] += 1
        p2["losses"] += 1
        p1["alltime_wins"] += 1
        p2["alltime_losses"] += 1
        p1["streak"] = max(1, p1["streak"] + 1) if p1["streak"] >= 0 else 1
        p2["streak"] = min(-1, p2["streak"] - 1) if p2["streak"] <= 0 else -1
        winner, loser = p1["name"], p2["name"]
    else:
        p2["wins"] += 1
        p1["losses"] += 1
        p2["alltime_wins"] += 1
        p1["alltime_losses"] += 1
        p2["streak"] = max(1, p2["streak"] + 1) if p2["streak"] >= 0 else 1
        p1["streak"] = min(-1, p1["streak"] - 1) if p1["streak"] <= 0 else -1
        winner, loser = p2["name"], p1["name"]

    p1["last_duel"] = {"opponent": player2, "p1_won": p1_won, "p1_season_change": p1_season_change, "p2_season_change": p2_season_change, "p1_alltime_change": p1_alltime_change, "p2_alltime_change": p2_alltime_change, "old_p1_elo": old_p1_elo, "old_p2_elo": old_p2_elo, "old_p1_alltime": old_p1_alltime, "old_p2_alltime": old_p2_alltime}
    p2["last_duel"] = p1["last_duel"]

    set_player(players, player1, p1)
    set_player(players, player2, p2)

    recent = meta.get("recent_duels", [])
    recent.insert(0, {"player1": p1["name"], "player2": p2["name"], "p1_time": player1_time, "p2_time": player2_time, "winner": winner, "loser": loser, "margin": round(time_diff, 2), "season": meta["season"]})
    meta["recent_duels"] = recent[:5]
    save_meta(meta)

    embed = discord.Embed(title="⚔️ Duel Result", color=discord.Color.gold())
    embed.add_field(name="Winner 🏆", value=winner, inline=True)
    embed.add_field(name="Loser", value=loser, inline=True)
    embed.add_field(name="Time Margin", value=f"{time_diff:.2f}s", inline=False)
    embed.add_field(name=f"{p1['name']} Season Elo", value=f"{old_p1_elo} → **{p1['elo']}** ({'+' if p1_season_change >= 0 else ''}{round(p1_season_change)})", inline=True)
    embed.add_field(name=f"{p2['name']} Season Elo", value=f"{old_p2_elo} → **{p2['elo']}** ({'+' if p2_season_change >= 0 else ''}{round(p2_season_change)})", inline=True)
    embed.add_field(name=f"{p1['name']} All-Time Elo", value=f"{old_p1_alltime} → **{p1['alltime_elo']}** ({'+' if p1_alltime_change >= 0 else ''}{round(p1_alltime_change)})", inline=True)
    embed.add_field(name=f"{p2['name']} All-Time Elo", value=f"{old_p2_alltime} → **{p2['alltime_elo']}** ({'+' if p2_alltime_change >= 0 else ''}{round(p2_alltime_change)})", inline=True)
    embed.set_footer(text=f"Season {meta['season']}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="undoduel", description="Revert the last duel between two players.")
@app_commands.describe(player1="First player", player2="Second player")
async def undoduel(interaction: discord.Interaction, player1: str, player2: str):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    p1 = get_player(players, player1)
    p2 = get_player(players, player2)
    if not p1 or not p2:
        await interaction.response.send_message("⚠️ One or both players not found.", ephemeral=True)
        return
    d = p1.get("last_duel")
    if not d or d["opponent"].lower() != player2.lower():
        await interaction.response.send_message(f"⚠️ No recent duel found between **{player1}** and **{player2}**.", ephemeral=True)
        return

    p1["elo"] = d["old_p1_elo"]
    p2["elo"] = d["old_p2_elo"]
    p1["alltime_elo"] = d["old_p1_alltime"]
    p2["alltime_elo"] = d["old_p2_alltime"]
    p1["matches"] = max(0, p1["matches"] - 1)
    p2["matches"] = max(0, p2["matches"] - 1)
    p1["alltime_matches"] = max(0, p1["alltime_matches"] - 1)
    p2["alltime_matches"] = max(0, p2["alltime_matches"] - 1)

    if d["p1_won"]:
        p1["wins"] = max(0, p1["wins"] - 1)
        p2["losses"] = max(0, p2["losses"] - 1)
        p1["alltime_wins"] = max(0, p1["alltime_wins"] - 1)
        p2["alltime_losses"] = max(0, p2["alltime_losses"] - 1)
    else:
        p2["wins"] = max(0, p2["wins"] - 1)
        p1["losses"] = max(0, p1["losses"] - 1)
        p2["alltime_wins"] = max(0, p2["alltime_wins"] - 1)
        p1["alltime_losses"] = max(0, p1["alltime_losses"] - 1)

    p1["last_duel"] = None
    p2["last_duel"] = None
    set_player(players, player1, p1)
    set_player(players, player2, p2)

    embed = discord.Embed(title="↩️ Duel Undone", color=discord.Color.orange())
    embed.add_field(name=f"{p1['name']} Elo restored to", value=str(p1["elo"]), inline=True)
    embed.add_field(name=f"{p2['name']} Elo restored to", value=str(p2["elo"]), inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="profile", description="View a player's full profile across all seasons.")
@app_commands.describe(player="Player's name")
async def profile(interaction: discord.Interaction, player: str):
    players = load_players()
    meta = load_meta()
    p = get_player(players, player)
    if not p:
        await interaction.response.send_message(f"⚠️ **{player}** is not in the system.", ephemeral=True)
        return

    current_season = meta["season"]
    season_rank = get_rank_position(players, player, alltime=False)
    alltime_rank = get_rank_position(players, player, alltime=True)
    title = get_title(p["elo"])
    alltime_title = get_alltime_title(p["alltime_elo"])
    title_emoji = TITLE_EMOJIS.get(title, "")
    alltime_emoji = TITLE_EMOJIS.get(alltime_title, "")
    provisional = p["matches"] < PROVISIONAL_MATCHES
    streak_str = f"🔥 {p['streak']}W" if p["streak"] > 0 else (f"❄️ {abs(p['streak'])}L" if p["streak"] < 0 else "—")
    wl = f"{p['wins'] / p['losses']:.2f}" if p["losses"] > 0 else "∞"

    embed = discord.Embed(
        title=f"{title_emoji} {p['name']}",
        color=discord.Color.gold(),
    )

    # Current season
    current_block = (
        f"**S{current_season}** — {title_emoji} {title}{' ⚠️ Provisional' if provisional else ''}\n"
        f"Elo: **{p['elo']}** (Peak: {p['peak_elo']}) · Rank #{season_rank}\n"
        f"Record: {p['wins']}W / {p['losses']}L · W/L: {wl}\n"
        f"Streak: {streak_str}"
    )
    embed.add_field(name="Current Season", value=current_block, inline=False)

    # Season history
    history = p.get("season_history", {})
    if history:
        lines = []
        for s_num in sorted(history.keys(), key=lambda x: int(x), reverse=True):
            s = history[s_num]
            s_title = s.get("title", "—")
            s_emoji = TITLE_EMOJIS.get(s_title, "")
            s_rank = s.get("rank")
            rank_str = f" / {ordinal(s_rank)}" if s_rank else ""
            lines.append(f"**S{s_num}** — {s_emoji} {s_title}{rank_str}")
        embed.add_field(name="Season History", value="\n".join(lines), inline=False)

    # All-time
    alltime_wl = f"{p['alltime_wins'] / p['alltime_losses']:.2f}" if p["alltime_losses"] > 0 else "∞"
    alltime_block = (
        f"Rank: **#{alltime_rank}** · {alltime_emoji} {alltime_title}\n"
        f"Elo: **{p['alltime_elo']}** (Peak: {p['alltime_peak_elo']})\n"
        f"Record: {p['alltime_wins']}W / {p['alltime_losses']}L · W/L: {alltime_wl}\n"
        f"Total Matches: {p['alltime_matches']}"
    )
    embed.add_field(name="——— ALL TIME ———", value=alltime_block, inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="milestone", description="See your title progress and how far you are from the next rank.")
@app_commands.describe(player="Player's name")
async def milestone(interaction: discord.Interaction, player: str):
    players = load_players()
    p = get_player(players, player)
    if not p:
        await interaction.response.send_message(f"⚠️ **{player}** is not in the system.", ephemeral=True)
        return

    elo = p["elo"]
    alltime_elo = p["alltime_elo"]
    title = get_title(elo)
    title_emoji = TITLE_EMOJIS.get(title, "")
    next_t, elo_needed = next_title_info(elo)

    # Find current bracket floor
    current_floor = 0
    for threshold, t in SEASON_TITLES:
        if elo >= threshold:
            current_floor = threshold
            break

    embed = discord.Embed(title=f"🎯 {p['name']} — Title Progress", color=discord.Color.blurple())

    # Season title progress
    if next_t:
        next_threshold = elo + elo_needed
        bar = progress_bar(elo, next_threshold, current_floor)
        next_emoji = TITLE_EMOJIS.get(next_t, "")
        season_block = (
            f"Current: {title_emoji} **{title}** ({elo} Elo)\n"
            f"Next: {next_emoji} **{next_t}** — **{elo_needed} elo away**\n"
            f"{bar} {elo}/{next_threshold}"
        )
    else:
        season_block = f"{title_emoji} **{title}** — Maximum season title reached! ({elo} Elo)"

    embed.add_field(name="Season", value=season_block, inline=False)

    # All-time title progress
    alltime_title = get_alltime_title(alltime_elo)
    alltime_emoji = TITLE_EMOJIS.get(alltime_title, "")
    if alltime_elo >= GRANDMASTER_THRESHOLD:
        alltime_block = f"{alltime_emoji} **Grandmaster** — All-time peak achieved! ({alltime_elo} Elo)"
    else:
        gm_needed = GRANDMASTER_THRESHOLD - alltime_elo
        next_at, at_needed = next_title_info(alltime_elo)
        at_floor = 0
        for threshold, t in SEASON_TITLES:
            if alltime_elo >= threshold:
                at_floor = threshold
                break
        if next_at and at_needed < gm_needed:
            at_next_threshold = alltime_elo + at_needed
            at_bar = progress_bar(alltime_elo, at_next_threshold, at_floor)
            next_at_emoji = TITLE_EMOJIS.get(next_at, "")
            alltime_block = (
                f"Current: {alltime_emoji} **{alltime_title}** ({alltime_elo} Elo)\n"
                f"Next: {next_at_emoji} **{next_at}** — **{at_needed} elo away**\n"
                f"{at_bar} {alltime_elo}/{at_next_threshold}\n"
                f"🌟 Grandmaster: **{gm_needed} elo away** ({alltime_elo}/{GRANDMASTER_THRESHOLD})"
            )
        else:
            gm_bar = progress_bar(alltime_elo, GRANDMASTER_THRESHOLD, 2000)
            alltime_block = (
                f"Current: {alltime_emoji} **{alltime_title}** ({alltime_elo} Elo)\n"
                f"🌟 **Grandmaster** — **{gm_needed} elo away**\n"
                f"{gm_bar} {alltime_elo}/{GRANDMASTER_THRESHOLD}"
            )

    embed.add_field(name="All-Time", value=alltime_block, inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="leaderboard", description="Show the top 10 players by season Elo.")
async def leaderboard(interaction: discord.Interaction):
    players = load_players()
    meta = load_meta()
    if not players:
        await interaction.response.send_message("No players in the system yet.", ephemeral=True)
        return
    sorted_players = sorted(players.values(), key=lambda p: p["elo"], reverse=True)[:10]
    embed = discord.Embed(title=f"🏆 Leaderboard — Season {meta['season']}", color=discord.Color.gold())
    lines = []
    for i, p in enumerate(sorted_players):
        title = get_title(p["elo"])
        emoji = TITLE_EMOJIS.get(title, "")
        provisional = " ⚠️" if p["matches"] < PROVISIONAL_MATCHES else ""
        lines.append(f"**#{i+1}** {p['name']} — {p['elo']} Elo {emoji} {title} ({p['wins']}W/{p['losses']}L){provisional}")
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed)


@tree.command(name="alltimeleaderboard", description="Show the top 10 players by all-time Elo.")
async def alltimeleaderboard(interaction: discord.Interaction):
    players = load_players()
    if not players:
        await interaction.response.send_message("No players in the system yet.", ephemeral=True)
        return
    sorted_players = sorted(players.values(), key=lambda p: p["alltime_elo"], reverse=True)[:10]
    embed = discord.Embed(title="🌟 All-Time Leaderboard", color=discord.Color.gold())
    lines = []
    for i, p in enumerate(sorted_players):
        title = get_alltime_title(p["alltime_elo"])
        emoji = TITLE_EMOJIS.get(title, "")
        lines.append(f"**#{i+1}** {p['name']} — {p['alltime_elo']} Elo {emoji} {title} ({p['alltime_wins']}W/{p['alltime_losses']}L)")
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed)


@tree.command(name="compare", description="Compare two players and predict elo swing if they dueled.")
@app_commands.describe(player1="First player", player2="Second player")
async def compare(interaction: discord.Interaction, player1: str, player2: str):
    players = load_players()
    p1 = get_player(players, player1)
    p2 = get_player(players, player2)
    if not p1:
        await interaction.response.send_message(f"⚠️ **{player1}** not found.", ephemeral=True)
        return
    if not p2:
        await interaction.response.send_message(f"⚠️ **{player2}** not found.", ephemeral=True)
        return

    p1_win_chance = round(expected_score(p1["elo"], p2["elo"]) * 100, 1)
    p2_win_chance = round(100 - p1_win_chance, 1)
    p1_if_win = round(calculate_elo_change(p1["elo"], p2["elo"], True, p1["matches"], 60))
    p1_if_loss = round(calculate_elo_change(p1["elo"], p2["elo"], False, p1["matches"], 60))
    p2_if_win = round(calculate_elo_change(p2["elo"], p1["elo"], True, p2["matches"], 60))
    p2_if_loss = round(calculate_elo_change(p2["elo"], p1["elo"], False, p2["matches"], 60))
    t1 = get_title(p1["elo"])
    t2 = get_title(p2["elo"])

    embed = discord.Embed(title=f"⚔️ {p1['name']} vs {p2['name']}", color=discord.Color.blurple())
    embed.add_field(name=p1["name"], value=f"{TITLE_EMOJIS.get(t1,'')} {t1} · {p1['elo']} Elo\nWin chance: {p1_win_chance}%\nIf win: +{p1_if_win} · If loss: {p1_if_loss}", inline=True)
    embed.add_field(name=p2["name"], value=f"{TITLE_EMOJIS.get(t2,'')} {t2} · {p2['elo']} Elo\nWin chance: {p2_win_chance}%\nIf win: +{p2_if_win} · If loss: {p2_if_loss}", inline=True)
    embed.set_footer(text="Elo swing estimated at 60s margin. Actual swing depends on real time difference.")
    await interaction.response.send_message(embed=embed)


@tree.command(name="alltimecompare", description="Compare two players by all-time Elo.")
@app_commands.describe(player1="First player", player2="Second player")
async def alltimecompare(interaction: discord.Interaction, player1: str, player2: str):
    players = load_players()
    p1 = get_player(players, player1)
    p2 = get_player(players, player2)
    if not p1:
        await interaction.response.send_message(f"⚠️ **{player1}** not found.", ephemeral=True)
        return
    if not p2:
        await interaction.response.send_message(f"⚠️ **{player2}** not found.", ephemeral=True)
        return

    p1_win_chance = round(expected_score(p1["alltime_elo"], p2["alltime_elo"]) * 100, 1)
    p2_win_chance = round(100 - p1_win_chance, 1)
    t1 = get_alltime_title(p1["alltime_elo"])
    t2 = get_alltime_title(p2["alltime_elo"])

    embed = discord.Embed(title=f"🌟 {p1['name']} vs {p2['name']} — All-Time", color=discord.Color.gold())
    embed.add_field(name=p1["name"], value=f"{TITLE_EMOJIS.get(t1,'')} {t1} · {p1['alltime_elo']} Elo\nPeak: {p1['alltime_peak_elo']}\nWin chance: {p1_win_chance}%\nRecord: {p1['alltime_wins']}W/{p1['alltime_losses']}L", inline=True)
    embed.add_field(name=p2["name"], value=f"{TITLE_EMOJIS.get(t2,'')} {t2} · {p2['alltime_elo']} Elo\nPeak: {p2['alltime_peak_elo']}\nWin chance: {p2_win_chance}%\nRecord: {p2['alltime_wins']}W/{p2['alltime_losses']}L", inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="recentduels", description="Show the last 5 duels logged.")
async def recentduels(interaction: discord.Interaction):
    meta = load_meta()
    recent = meta.get("recent_duels", [])
    if not recent:
        await interaction.response.send_message("No duels logged yet.", ephemeral=True)
        return
    embed = discord.Embed(title="🕘 Recent Duels", color=discord.Color.blurple())
    lines = []
    for d in recent:
        lines.append(f"**{d['winner']}** def. **{d['loser']}** — {d['margin']}s margin (S{d['season']})")
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed)


@tree.command(name="rename", description="Rename a player.")
@app_commands.describe(player="Current name", new_name="New name")
async def rename(interaction: discord.Interaction, player: str, new_name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    p = get_player(players, player)
    if not p:
        await interaction.response.send_message(f"⚠️ **{player}** not found.", ephemeral=True)
        return
    if get_player(players, new_name):
        await interaction.response.send_message(f"⚠️ **{new_name}** already exists.", ephemeral=True)
        return
    p["name"] = new_name
    players[new_name.lower()] = p
    del players[player.lower()]
    save_players(players)
    embed = discord.Embed(title="✏️ Player Renamed", color=discord.Color.green())
    embed.add_field(name="Old Name", value=player, inline=True)
    embed.add_field(name="New Name", value=new_name, inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="remove", description="Remove a player from the system.")
@app_commands.describe(player="Player's name")
async def remove(interaction: discord.Interaction, player: str):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    if not get_player(players, player):
        await interaction.response.send_message(f"⚠️ **{player}** not found.", ephemeral=True)
        return
    del players[player.lower()]
    save_players(players)
    embed = discord.Embed(title="🗑️ Player Removed", color=discord.Color.red())
    embed.add_field(name="Player", value=player, inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="setelo", description="[Admin] Manually set a player's season Elo.")
@app_commands.describe(player="Player's name", elo="New Elo value")
async def setelo(interaction: discord.Interaction, player: str, elo: int):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    p = get_player(players, player)
    if not p:
        await interaction.response.send_message(f"⚠️ **{player}** not found.", ephemeral=True)
        return
    old_elo = p["elo"]
    p["elo"] = elo
    p["peak_elo"] = max(p["peak_elo"], elo)
    set_player(players, player, p)
    embed = discord.Embed(title="🔧 Elo Updated", color=discord.Color.orange())
    embed.add_field(name="Player", value=player, inline=True)
    embed.add_field(name="Old Elo", value=str(old_elo), inline=True)
    embed.add_field(name="New Elo", value=str(elo), inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="setalltimeelo", description="[Admin] Manually set a player's all-time Elo.")
@app_commands.describe(player="Player's name", elo="New all-time Elo value")
async def setalltimeelo(interaction: discord.Interaction, player: str, elo: int):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    p = get_player(players, player)
    if not p:
        await interaction.response.send_message(f"⚠️ **{player}** not found.", ephemeral=True)
        return
    old_elo = p["alltime_elo"]
    p["alltime_elo"] = elo
    p["alltime_peak_elo"] = max(p["alltime_peak_elo"], elo)
    set_player(players, player, p)
    embed = discord.Embed(title="🔧 All-Time Elo Updated", color=discord.Color.orange())
    embed.add_field(name="Player", value=player, inline=True)
    embed.add_field(name="Old All-Time Elo", value=str(old_elo), inline=True)
    embed.add_field(name="New All-Time Elo", value=str(elo), inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="setseason", description="[Admin] Manually set the current season number without resetting anything.")
@app_commands.describe(season="Season number to set")
async def setseason(interaction: discord.Interaction, season: int):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    meta = load_meta()
    old_season = meta["season"]
    meta["season"] = season
    save_meta(meta)
    embed = discord.Embed(title="🔧 Season Updated", color=discord.Color.orange())
    embed.add_field(name="Old Season", value=f"Season {old_season}", inline=True)
    embed.add_field(name="New Season", value=f"Season {season}", inline=True)
    embed.set_footer(text="No player data or history was changed.")
    await interaction.response.send_message(embed=embed)


@tree.command(name="seasonreset", description="[Admin] End the current season and start a new one.")
async def seasonreset(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    meta = load_meta()
    old_season = meta["season"]
    new_season = old_season + 1

    sorted_players = sorted(players.values(), key=lambda p: p["elo"], reverse=True)
    rank_map = {p["name"].lower(): i + 1 for i, p in enumerate(sorted_players)}

    for key, p in players.items():
        final_title = get_title(p["elo"])
        final_rank = rank_map.get(p["name"].lower())
        if "season_history" not in p:
            p["season_history"] = {}
        p["season_history"][str(old_season)] = {
            "title": final_title,
            "elo": p["elo"],
            "rank": final_rank,
            "wins": p["wins"],
            "losses": p["losses"],
        }
        p["elo"] = round(p["elo"] + (1000 - p["elo"]) * 0.25)
        p["peak_elo"] = p["elo"]
        p["wins"] = 0
        p["losses"] = 0
        p["matches"] = 0
        p["streak"] = 0
        p["last_duel"] = None
        players[key] = p

    meta["season"] = new_season
    meta["recent_duels"] = []
    meta["registration"] = True
    save_meta(meta)
    save_players(players)

    embed = discord.Embed(title="🔄 Season Ended — Registration Open", color=discord.Color.purple())
    embed.add_field(name="Season Ended", value=f"Season {old_season}", inline=True)
    embed.add_field(name="Upcoming Season", value=f"Season {new_season}", inline=True)
    embed.add_field(name="Status", value="🟡 Registration period open. Duels are disabled until an admin uses `/startseason`.", inline=False)
    embed.add_field(name="Notes", value="Season history saved. Elos soft reset 25% toward 1000. All-time stats unchanged.", inline=False)
    await interaction.response.send_message(embed=embed)



@tree.command(name="startseason", description="[Admin] Start the new season and open duels.")
async def startseason(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    meta = load_meta()
    if not meta.get("registration", False):
        await interaction.response.send_message("⚠️ No registration period is active.", ephemeral=True)
        return
    meta["registration"] = False
    save_meta(meta)
    embed = discord.Embed(title="✅ Season Started!", color=discord.Color.green())
    embed.add_field(name="Season", value=f"Season {meta['season']}", inline=True)
    embed.add_field(name="Status", value="🟢 Duels are now open!", inline=True)
    await interaction.response.send_message(embed=embed)



@tree.command(name="purgechannel", description="[Admin] Delete all messages in this channel.")
async def purgechannel(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    await interaction.response.send_message("🗑️ Purging all messages...", ephemeral=True)
    deleted = await interaction.channel.purge(limit=None)
    await interaction.followup.send(f"✅ Deleted **{len(deleted)}** messages.", ephemeral=True)




@tree.command(name="link", description="Link your Discord account to your player profile.")
@app_commands.describe(player="Your player name in the system")
async def link(interaction: discord.Interaction, player: str):
    players = load_players()
    p = get_player(players, player)
    if not p:
        await interaction.response.send_message(f"⚠️ **{player}** is not in the system. Ask an admin to introduce you first.", ephemeral=True)
        return

    # Check if this Discord account is already linked to someone else
    for key, pl in players.items():
        if pl.get("discord_id") == interaction.user.id and pl["name"].lower() != player.lower():
            await interaction.response.send_message(f"⚠️ Your Discord account is already linked to **{pl['name']}**. Ask an admin to unlink you first.", ephemeral=True)
            return

    # Check if this player is already linked to a different Discord account
    if p.get("discord_id") and p["discord_id"] != interaction.user.id:
        await interaction.response.send_message(f"⚠️ **{player}** is already linked to a different Discord account. Ask an admin to unlink them first.", ephemeral=True)
        return

    p["discord_id"] = interaction.user.id
    set_player(players, player, p)

    embed = discord.Embed(title="✅ Account Linked", color=discord.Color.green())
    embed.add_field(name="Player", value=player, inline=True)
    embed.add_field(name="Discord", value=interaction.user.display_name, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="unlink", description="[Admin] Unlink a Discord account from a player profile.")
@app_commands.describe(player="Player name to unlink")
async def unlink(interaction: discord.Interaction, player: str):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    p = get_player(players, player)
    if not p:
        await interaction.response.send_message(f"⚠️ **{player}** not found.", ephemeral=True)
        return
    p["discord_id"] = None
    set_player(players, player, p)
    embed = discord.Embed(title="🔓 Account Unlinked", color=discord.Color.orange())
    embed.add_field(name="Player", value=player, inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="queue", description="Join the matchmaking queue.")
async def queue(interaction: discord.Interaction):
    meta = load_meta()
    if meta.get("registration", False):
        await interaction.response.send_message("⏳ Season is in registration period, matchmaking is disabled.", ephemeral=True)
        return
    q = meta.get("queue", [])
    players = load_players()
    # Find player by discord_id
    p = next((pl for pl in players.values() if pl.get("discord_id") == interaction.user.id), None)
    if not p:
        await interaction.response.send_message("⚠️ Your Discord account is not linked to any player. Use `/link YourName` first.", ephemeral=True)
        return
    player_name = p["name"]
    if any(pl["name"] == player_name for pl in q):
        await interaction.response.send_message("⚠️ You are already in the queue!", ephemeral=True)
        return

    q.append({"name": player_name, "elo": p["elo"]})
    meta["queue"] = q
    save_meta(meta)

    # Try to find a match
    if len(q) >= 2:
        # Sort by elo and find closest pair
        q_sorted = sorted(q, key=lambda x: x["elo"])
        best_pair = None
        best_diff = float("inf")
        for i in range(len(q_sorted) - 1):
            diff = abs(q_sorted[i]["elo"] - q_sorted[i+1]["elo"])
            if diff < best_diff:
                best_diff = diff
                best_pair = (q_sorted[i], q_sorted[i+1])

        if best_pair:
            p1, p2 = best_pair
            q = [p for p in q if p["name"] not in (p1["name"], p2["name"])]
            meta["queue"] = q
            save_meta(meta)

            embed = discord.Embed(title="⚔️ Match Found!", color=discord.Color.green())
            embed.add_field(name="Player 1", value=f"{p1['name']} ({p1['elo']} Elo)", inline=True)
            embed.add_field(name="Player 2", value=f"{p2['name']} ({p2['elo']} Elo)", inline=True)
            embed.add_field(name="Elo Difference", value=str(best_diff), inline=True)
            embed.set_footer(text="Join a Discord call, screen share, and post your screenshot proof in duel-results!")

            # Post in duel-queue channel and ping both players
            queue_channel = interaction.guild.get_channel(DUEL_QUEUE_CHANNEL)
            results_channel = interaction.guild.get_channel(DUEL_RESULTS_CHANNEL)

            # Find discord IDs for both players
            all_players = load_players()
            p1_data = get_player(all_players, p1["name"])
            p2_data = get_player(all_players, p2["name"])
            p1_mention = f"<@{p1_data['discord_id']}>" if p1_data and p1_data.get("discord_id") else p1["name"]
            p2_mention = f"<@{p2_data['discord_id']}>" if p2_data and p2_data.get("discord_id") else p2["name"]

            if queue_channel:
                await queue_channel.send(
                    content=f"{p1_mention} vs {p2_mention} — your match is ready! Join a Discord call, screen share your gameplay, and post your proof in <#{DUEL_RESULTS_CHANNEL}>.",
                    embed=embed
                )

            # Create a forum thread in duel-results
            if results_channel and hasattr(results_channel, "create_thread"):
                thread_embed = discord.Embed(
                    title=f"Duel: {p1['name']} vs {p2['name']}",
                    description="Post your end screen screenshots here after the duel! An admin will log the result with /duel once both screenshots are submitted.",
                    color=discord.Color.gold()
                )
                thread_embed.add_field(name=p1["name"], value=f"{p1['elo']} Elo", inline=True)
                thread_embed.add_field(name=p2["name"], value=f"{p2['elo']} Elo", inline=True)
                await results_channel.create_thread(
                    name=f"{p1['name']} vs {p2['name']}",
                    embed=thread_embed,
                    reason="Duel match created"
                )

            await interaction.response.send_message("✅ Match found and announced!", ephemeral=True)
            return

    embed = discord.Embed(title="✅ Joined Queue", color=discord.Color.blurple())
    embed.add_field(name="Player", value=player_name, inline=True)
    embed.add_field(name="Your Elo", value=str(p["elo"]), inline=True)
    embed.add_field(name="Queue Size", value=str(len(q)), inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="leavequeue", description="Leave the matchmaking queue.")
async def leavequeue(interaction: discord.Interaction):
    meta = load_meta()
    q = meta.get("queue", [])
    players = load_players()
    p = next((pl for pl in players.values() if pl.get("discord_id") == interaction.user.id), None)
    if not p:
        await interaction.response.send_message("⚠️ Your Discord account is not linked to any player.", ephemeral=True)
        return
    player_name = p["name"]
    new_q = [pl for pl in q if pl["name"] != player_name]
    if len(new_q) == len(q):
        await interaction.response.send_message("⚠️ You are not in the queue.", ephemeral=True)
        return
    meta["queue"] = new_q
    save_meta(meta)
    embed = discord.Embed(title="👋 Left Queue", color=discord.Color.orange())
    embed.add_field(name="Player", value=player_name, inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="showqueue", description="Show all players currently in the matchmaking queue.")
async def showqueue(interaction: discord.Interaction):
    meta = load_meta()
    q = meta.get("queue", [])
    if not q:
        await interaction.response.send_message("The queue is currently empty.", ephemeral=True)
        return
    embed = discord.Embed(title="🎯 Matchmaking Queue", color=discord.Color.blurple())
    lines = [f"**#{i+1}** {p['name']} — {p['elo']} Elo" for i, p in enumerate(sorted(q, key=lambda x: x["elo"], reverse=True))]
    embed.description = "\n".join(lines)
    embed.set_footer(text=f"{len(q)} player(s) waiting")
    await interaction.response.send_message(embed=embed)


@tree.command(name="highlightedmatch", description="[Admin] Announce a highlighted match between two high-elo players.")
@app_commands.describe(
    player1="First player",
    player2="Second player",
    player1_stream="Player 1 stream link",
    player2_stream="Player 2 stream link",
    scheduled_time="When the match is happening (e.g. 'Saturday 8PM UTC')",
)
async def highlightedmatch(
    interaction: discord.Interaction,
    player1: str,
    player2: str,
    player1_stream: str,
    player2_stream: str,
    scheduled_time: str,
):
    if not is_admin(interaction):
        await interaction.response.send_message("⛔ Administrator permissions required.", ephemeral=True)
        return
    players = load_players()
    meta = load_meta()
    p1 = get_player(players, player1)
    p2 = get_player(players, player2)
    if not p1:
        await interaction.response.send_message(f"⚠️ **{player1}** not found.", ephemeral=True)
        return
    if not p2:
        await interaction.response.send_message(f"⚠️ **{player2}** not found.", ephemeral=True)
        return

    t1 = get_title(p1["elo"])
    t2 = get_title(p2["elo"])
    p1_win_chance = round(expected_score(p1["elo"], p2["elo"]) * 100, 1)
    p2_win_chance = round(100 - p1_win_chance, 1)

    embed = discord.Embed(
        title="🌟 HIGHLIGHTED MATCH",
        description=f"**{p1['name']}** vs **{p2['name']}**",
        color=discord.Color.gold(),
    )
    embed.add_field(
        name=f"{TITLE_EMOJIS.get(t1,'')} {p1['name']}",
        value=f"{t1} - {p1['elo']} Elo\nWin chance: {p1_win_chance}%\n[Watch Live]({player1_stream})",
        inline=True
    )
    embed.add_field(
        name=f"{TITLE_EMOJIS.get(t2,'')} {p2['name']}",
        value=f"{t2} - {p2['elo']} Elo\nWin chance: {p2_win_chance}%\n[Watch Live]({player2_stream})",
        inline=True
    )
    embed.add_field(name="🕐 Scheduled", value=scheduled_time, inline=False)
    embed.set_footer(text=f"Season {meta['season']} · Highlighted Match")
    await interaction.response.send_message(embed=embed)


# ── Startup ───────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user} — slash commands synced.")


if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set the DISCORD_TOKEN environment variable before running.")
    client.run(token)
