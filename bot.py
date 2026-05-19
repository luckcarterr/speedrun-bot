import discord
from discord import app_commands
import math
 
# ── Bot setup ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
 
 
# ── Helpers ───────────────────────────────────────────────────────────────────
 
def parse_time(time_str: str) -> float:
    """
    Convert a time string to total seconds.
    Accepted formats: ss, mm:ss, hh:mm:ss  (decimals allowed, e.g. 1:23.45)
    """
    time_str = time_str.strip()
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
 
 
def heist_coefficient(median_seconds: float) -> float:
    """Return the HeistCoefficient based on the median run time."""
    if median_seconds < 15:
        return 2.0
    elif median_seconds < 30:
        return 1.85
    elif median_seconds < 60:
        return 1.75
    elif median_seconds < 120:
        return 1.65
    elif median_seconds < 180:
        return 1.57
    elif median_seconds < 300:
        return 1.5
    elif median_seconds < 600:
        return 1.1
    else:
        return 0.9
 
 
def format_seconds(seconds: float) -> str:
    """Format seconds back to a human-readable string."""
    seconds = abs(seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return f"{h}h {m}m {s:.2f}s"
    elif m:
        return f"{m}m {s:.2f}s"
    else:
        return f"{s:.2f}s"
 
 
def calculate_evaluation(t: float, z: float, x: float, y: float, rank: int, timegate_multiplier: float = 1.0, timegate_addition: float = 0.0, timegate_foundation: bool = False) -> dict:
    """
    Final Evaluation Score =
        HeistCoefficient
        * [{100 * ((z - t) / z)} + {75 * ((y - x) / (x + y))}]
        * RankFactor
        * timegate_multiplier + timegate_addition
 
    If timegate_foundation is True, score = (11 - rank) * 5
    then timegate_multiplier and timegate_addition are still applied on top.
    """
    coeff = heist_coefficient(z)
 
    time_component = 100 * ((z - t) / z)
    gap_component  = 75 * ((y - x) / (x + y)) if (x + y) != 0 else 0.0
    performance_value = time_component + gap_component
    rank_factor = (1 / (rank ** (1 / 1.5))) * 1.2
 
    if timegate_foundation:
        score = (11 - rank) * 5
    else:
        score = coeff * performance_value * rank_factor
        if t > 1800:
            score *= 1.5
 
    score = score * timegate_multiplier + timegate_addition
    score = max(0, score)
 
    return {
        "score": score,
        "coeff": coeff,
        "performance_value": performance_value,
        "time_component": time_component,
        "gap_component": gap_component,
        "rank_factor": rank_factor,
        "timegate_multiplier": timegate_multiplier,
        "timegate_addition": timegate_addition,
        "timegate_foundation": timegate_foundation,
    }
 
 
# ── Slash command ─────────────────────────────────────────────────────────────
 
@tree.command(
    name="evaluate",
    description="Calculate the Final Evaluation Score for a speedrun."
)
@app_commands.describe(
    player_time          = "Your run time (e.g. 1:23.45 or 83.45)",
    median_time          = "Median benchmark time for this heist (same format)",
    time_above           = "Time gap between you and the person ranked above you. If 1st place, enter 0.",
    time_below           = "Time gap between you and the person ranked below you. If last place, enter 0.",
    rank                 = "Your placement on the leaderboard (1 = first place)",
    timegate_amount      = "Time to subtract from player time and median (e.g. timegate duration, same format)",
    timegate_foundation  = "Use timegate formula: (11-rank)×5 instead of normal formula (default: False)",
    timegate_multiplier  = "Timegate multiplier applied to final score (default: 1.0)",
    timegate_addition    = "Timegate addition applied after multiplier (default: 0.0)",
    show_breakdown       = "Show the full calculation breakdown (default: True)",
)
async def evaluate(
    interaction: discord.Interaction,
    player_time: str,
    median_time: str,
    time_above: str,
    time_below: str,
    rank: app_commands.Range[int, 1],
    timegate_amount: str = "0",
    timegate_foundation: bool = False,
    timegate_multiplier: float = 1.0,
    timegate_addition: float = 0.0,
    show_breakdown: bool = True,
):
    try:
        t = parse_time(player_time)
        z = parse_time(median_time)
        x = parse_time(time_above)
        y = parse_time(time_below)
        tg = parse_time(timegate_amount)
    except ValueError as e:
        await interaction.response.send_message(f"⚠️ **Input error:** {e}", ephemeral=True)
        return
 
    t = max(0, t - tg)
    z = max(0, z - tg)
 
    if z == 0:
        await interaction.response.send_message(
            "⚠️ Median time cannot be 0.", ephemeral=True
        )
        return
 
    result = calculate_evaluation(t, z, x, y, rank, timegate_multiplier, timegate_addition, timegate_foundation)
 
    embed = discord.Embed(
        title="🏆 Final Evaluation Score",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Score", value=f"**{result['score']:.4f}**", inline=False)
 
    if show_breakdown:
        embed.add_field(
            name="Inputs",
            value=(
                f"**Player time:** {format_seconds(t)}" + (f" *(adjusted from {format_seconds(t + tg)})*" if tg > 0 else "") + "\n"
                f"**Median (z):** {format_seconds(z)}" + (f" *(adjusted from {format_seconds(z + tg)})*" if tg > 0 else "") + "\n"
                f"**Time above (x):** {format_seconds(x)}\n"
                f"**Time below (y):** {format_seconds(y)}\n"
                f"**Rank:** #{rank}"
                + (f"\n**Timegate removed:** {format_seconds(tg)}" if tg > 0 else "")
            ),
            inline=False,
        )
        breakdown = ""
        if timegate_foundation:
            breakdown += f"**Timegate Foundation:** `(11 - {rank}) × 5 = {(11 - rank) * 5}`\n"
        else:
            breakdown += (
                f"**HeistCoefficient:** {result['coeff']}×\n"
                f"**Time component** `100×((z−t)/z)`: {result['time_component']:.4f}\n"
                f"**Gap component** `75×((y−x)/(x+y))`: {result['gap_component']:.4f}\n"
                f"**Performance Value:** {result['performance_value']:.4f}\n"
                f"**Rank factor:** {result['rank_factor']:.4f}\n"
            )
        if timegate_multiplier != 1.0:
            breakdown += f"**Timegate multiplier:** {timegate_multiplier}×\n"
        if timegate_addition != 0.0:
            breakdown += f"**Timegate addition:** +{timegate_addition}"
        embed.add_field(name="Breakdown", value=breakdown, inline=False)
 
    embed.set_footer(text="Formula: HeistCoeff × PerformanceValue × RankFactor × TimegateMultiplier + TimegateAddition")
    await interaction.response.send_message(embed=embed)
 
 
# ── Startup ───────────────────────────────────────────────────────────────────
 
@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user} — slash commands synced.")
 
 
# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set the DISCORD_TOKEN environment variable before running.")
    client.run(token)
 
