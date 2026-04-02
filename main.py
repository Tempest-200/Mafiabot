import discord
from discord.ext import commands
import asyncio
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

AVAILABLE_GAMES = ["mafia", "roulette", "uno"]
loaded_game = None  # only one game at a time


# ================= LOAD / UNLOAD =================

@bot.command(name="load")
@commands.has_permissions(administrator=True)
async def load_game(ctx, game_name: str):
    global loaded_game

    game_name = game_name.lower()

    if game_name not in AVAILABLE_GAMES:
        await ctx.send(f"❌ Unknown game `{game_name}`. Available: {', '.join(f'`{g}`' for g in AVAILABLE_GAMES)}")
        return

    if loaded_game is not None:
        await ctx.send(f"❌ `{loaded_game}` is already loaded. Use `.unload {loaded_game}` first.")
        return

    try:
        await bot.load_extension(f"games.{game_name}")
        loaded_game = game_name
        await ctx.send(f"Loaded game: `{game_name}`")
    except commands.ExtensionAlreadyLoaded:
        await ctx.send(f"Game `{game_name}` is already loaded.")
    except Exception as e:
        await ctx.send(f"❌ Failed to load `{game_name}`: {e}")


@bot.command(name="unload")
@commands.has_permissions(administrator=True)
async def unload_game(ctx, game_name: str):
    global loaded_game

    game_name = game_name.lower()

    try:
        await bot.unload_extension(f"games.{game_name}")
        loaded_game = None
        await ctx.send(f"Unloaded game: `{game_name}`")
    except commands.ExtensionNotLoaded:
        await ctx.send(f"Game `{game_name}` is not currently loaded.")
    except Exception as e:
        await ctx.send(f"❌ Failed to unload `{game_name}`: {e}")


# ================= PING & HELP =================

@bot.command(name="ping")
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! `{latency}ms`")


@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="Mystic's Game Bot",
        color=discord.Color.purple()
    )

    embed.description = (
        "Hello! I'm **Mystic's Game Bot**, developed by **AM10/Mystic** for private use. "
        "This bot is intended solely for authorized servers and may not be added elsewhere "
        "without the explicit permission of its owner. Unauthorized use or distribution may "
        "result in legal consequences under applicable laws, including the CFAA and data "
        "protection regulations such as GDPR and CCPA.\n\n"
        "Please note that, at times, the bot may process or utilize in-game information to "
        "improve performance and enhance user experience."
    )

    embed.add_field(
        name="⚙️ General Commands",
        value=(
            "`.ping` — Check if the bot is online and its response time\n"
            "`.help` — Show this help menu"
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 Game Management (Admin Only)",
        value=(
            "`.load <game>` — Load a game (e.g. `.load mafia`)\n"
            "`.unload <game>` — Unload the current game (e.g. `.unload mafia`)\n"
            f"Available games: {', '.join(f'`{g}`' for g in AVAILABLE_GAMES)}\n"
            "⚠️ Only one game can be loaded at a time."
        ),
        inline=False
    )

    embed.add_field(
        name="🃏 Mafia *(`.load mafia` first)*",
        value=(
            "`.game <mafias> <medics>` — Start a Mafia game (e.g. `.game 2 1`)\n"
            "`.mjoin` — Join during the join window\n"
            "`.vote @user` — Vote to eliminate a player\n"
            "`.skip` — Skip your vote (rounds 1 & 2 only)"
        ),
        inline=False
    )

    embed.add_field(
        name="🔫 Russian Roulette *(`.load roulette` first)*",
        value=(
            "`.game <bullets>` — Start a Russian Roulette game (e.g. `.game 2`)\n"
            "`.rjoin` — Join during the join window"
        ),
        inline=False
    )

    embed.add_field(
        name="🎴 Uno *(`.load uno` first)*",
        value=(
            "`.game` — Start an Uno game\n"
            "`.ujoin` — Join during the join window\n"
            "`.play <color> <value>` — Play a card (e.g. `.play red 5`, `.play blue skip`)\n"
            "`.play wild <color>` — Play a wild (e.g. `.play wild red`)\n"
            "`.play wildraw4 <color>` — Play a Wild Draw 4 (e.g. `.play wildraw4 blue`)\n"
            "`.draw` — Draw a card from the deck\n"
            "`.hand` — Bot re-sends your current hand via DM"
        ),
        inline=False
    )

    embed.set_footer(text="Mystic's Game Bot • For authorized use only")
    await ctx.send(embed=embed)


# ================= RUN =================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
