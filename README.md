# Speedrun Evaluation Bot

A Discord bot with a single `/evaluate` slash command that calculates the **Final Evaluation Score** for a speedrun using your team's formula:

```
Final Evaluation Score =
  HeistCoefficient
  × [100×((z−t)/z) + 75×((y−x)/(x+y))]   ← Performance Value
  × (1 / √rank)
```

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create a Discord application & bot
1. Go to https://discord.com/developers/applications → **New Application**
2. Under **Bot**, click **Add Bot** and copy the **token**
3. Under **OAuth2 → URL Generator**, select scopes: `bot` + `applications.commands`
4. Select bot permission: `Send Messages`
5. Use the generated URL to invite the bot to your server

### 3. Set your bot token
```bash
# Linux / macOS
export DISCORD_TOKEN="your-token-here"

# Windows (cmd)
set DISCORD_TOKEN=your-token-here

# Windows (PowerShell)
$env:DISCORD_TOKEN="your-token-here"
```

### 4. Run the bot
```bash
python bot.py
```

The bot will sync slash commands on startup. It may take up to an hour for Discord to propagate them globally (instant in the server it was last synced to).

---

## Usage

```
/evaluate
  player_time    → Your run time        (e.g.  1:23.45  or  83.45)
  median_time    → Median benchmark     (same format)
  gap_above      → Gap to rank above    (same format)
  gap_below      → Gap to rank below    (same format)
  rank           → Your leaderboard placement (integer ≥ 1)
  show_breakdown → Show full calc breakdown (default: True)
```

### Time format
| Input | Interpreted as |
|-------|----------------|
| `83.45` | 83.45 seconds |
| `1:23.45` | 1 min 23.45 sec |
| `1:02:03` | 1 hr 2 min 3 sec |

---

## HeistCoefficient table

| Median runtime | Coefficient |
|----------------|-------------|
| < 15s          | 5×          |
| < 30s          | 4×          |
| < 1m           | 3×          |
| < 2m           | 1.75×       |
| < 3m           | 1.25×       |
| < 5m           | 1×          |
| < 10m          | 0.85×       |
| 10m+           | 0.7×        |

---

## Variables reference

| Variable | Meaning |
|----------|---------|
| `t` | Player's run time |
| `z` | Median benchmark for the heist (also used to determine HeistCoefficient) |
| `x` | Time difference between player and the rank above |
| `y` | Time difference between player and the rank below |
| `rank` | Player's placement on the leaderboard |
