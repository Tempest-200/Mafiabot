from keep_alive import keep_alive
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import os
from collections import Counter

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# ================= GAME STATE =================

class MafiaGame:
    def __init__(self):
        self.running = False
        self.players = []
        self.alive_players = []
        self.mafias = []
        self.medics = []
        self.villagers = []
        self.roles = {}
        self.join_message = None
        self.channel = None
        self.mafia_count = 1
        self.medic_count = 1
        self.votes = {}
        self.day = 0

game = MafiaGame()


# ================= UTIL =================

def reset_game():
    global game
    game = MafiaGame()


def check_win():
    mafias_alive = [p for p in game.mafias if p in game.alive_players]
    villagers_alive = [p for p in game.alive_players if p not in game.mafias]

    if len(mafias_alive) == 0:
        return "villagers"

    if len(mafias_alive) >= len(villagers_alive):
        return "mafia"

    return None


def player_list_text():
    """Returns a numbered list of alive players for DM prompts."""
    lines = []
    for i, p in enumerate(game.alive_players, 1):
        lines.append(f"{i}. {p.display_name}")
    return "\n".join(lines)


# ================= SLASH COMMAND GROUP =================

class GameGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="game", description="Mafia game commands")

    @app_commands.command(name="start", description="Start a mafia game")
    async def start(self, interaction: discord.Interaction, mafias: int, medics: int):
        global game

        if game.running:
            await interaction.response.send_message("A game is already running!", ephemeral=True)
            return

        game.running = True
        game.players = []
        game.channel = interaction.channel
        game.mafia_count = mafias
        game.medic_count = medics

        # FIX #1: removed invalid wait=True parameter
        await interaction.response.send_message("A game has now started! Users joined: 0")
        game.join_message = await interaction.original_response()

        # Wait 30 seconds for joins
        await asyncio.sleep(30)

        if len(game.players) < mafias + medics + 1:
            await game.channel.send("Not enough players joined. Game cancelled.")
            reset_game()
            return

        await assign_roles()

    @app_commands.command(name="join", description="Join the current mafia game")
    async def join(self, interaction: discord.Interaction):
        if not game.running:
            await interaction.response.send_message(
                "A game is not currently running", ephemeral=True
            )
            return

        # FIX #2: guard against join_message being None
        if game.join_message is None:
            await interaction.response.send_message(
                "The game is still starting up, try again in a moment!", ephemeral=True
            )
            return

        if interaction.user in game.players:
            await interaction.response.send_message("You already joined!", ephemeral=True)
            return

        game.players.append(interaction.user)

        await game.join_message.edit(
            content=f"A game has now started! Users joined: {len(game.players)}"
        )

        await interaction.response.send_message("You joined the game!", ephemeral=True)


tree.add_command(GameGroup())


# ================= ROLE ASSIGNMENT =================

async def assign_roles():
    await game.channel.send(
        "Assigning roles to players. Check your DMs for your respective role!"
    )

    game.alive_players = game.players.copy()
    shuffled = game.players.copy()
    random.shuffle(shuffled)

    game.mafias = shuffled[:game.mafia_count]
    game.medics = shuffled[game.mafia_count:game.mafia_count + game.medic_count]
    game.villagers = shuffled[game.mafia_count + game.medic_count:]

    for player in game.players:
        if player in game.mafias:
            game.roles[player] = "Mafia"
        elif player in game.medics:
            game.roles[player] = "Medic"
        else:
            game.roles[player] = "Villager"

    # DM roles
    for player in game.players:
        role = game.roles[player]
        try:
            if role == "Mafia":
                others = [m.display_name for m in game.mafias if m != player]
                msg = "You are **Mafia**."
                if others:
                    msg += f"\nYour fellow mafias: {', '.join(others)}"
                await player.send(msg)

            elif role == "Medic":
                others = [m.display_name for m in game.medics if m != player]
                msg = "You are a **Medic**."
                if others:
                    msg += f"\nYour fellow medics: {', '.join(others)}"
                await player.send(msg)

            else:
                await player.send("You are a **Villager**. Find and vote out the Mafia!")

        except discord.Forbidden:
            await game.channel.send(
                f"⚠️ Could not DM {player.mention}. Please enable DMs from server members."
            )

    await start_day()


# ================= DAY/NIGHT LOOP =================

async def start_day():
    game.day += 1
    # FIX #3: added a 60-second discussion window before night phase
    await game.channel.send(
        f"**☀️ Day {game.day}**\nDiscuss among yourselves! You have 60 seconds before voting begins."
    )
    await asyncio.sleep(60)
    await discussion_phase()


async def night_phase():
    await game.channel.send("**🌙 Night falls...** The Mafia and Medic are making their moves.")
    mafia_targets = []
    medic_saves = []

    # ---- MAFIA ----
    # FIX #4: replaced raw User ID input with a numbered player list
    for mafia in game.mafias:
        if mafia not in game.alive_players:
            continue

        try:
            player_list = player_list_text()
            await mafia.send(
                f"**Choose a target to eliminate.** Reply with the player's number:\n{player_list}"
            )

            def mafia_check(m):
                return m.author == mafia and isinstance(m.channel, discord.DMChannel)

            msg = await bot.wait_for("message", check=mafia_check, timeout=60)
            choice = int(msg.content.strip()) - 1

            if 0 <= choice < len(game.alive_players):
                target = game.alive_players[choice]
                mafia_targets.append(target)
                await mafia.send(f"Target confirmed: **{target.display_name}**")
            else:
                await mafia.send("Invalid choice. No target selected.")

        except (asyncio.TimeoutError, ValueError):
            await mafia.send("Time ran out or invalid input. No target selected.")

    # ---- MEDIC ----
    for medic in game.medics:
        if medic not in game.alive_players:
            continue

        try:
            player_list = player_list_text()
            await medic.send(
                f"**Choose someone to save.** Reply with the player's number:\n{player_list}"
            )

            def medic_check(m):
                return m.author == medic and isinstance(m.channel, discord.DMChannel)

            msg = await bot.wait_for("message", check=medic_check, timeout=60)
            choice = int(msg.content.strip()) - 1

            if 0 <= choice < len(game.alive_players):
                target = game.alive_players[choice]
                medic_saves.append(target)
                await medic.send(f"Save confirmed: **{target.display_name}**")
            else:
                await medic.send("Invalid choice. No one saved.")

        except (asyncio.TimeoutError, ValueError):
            await medic.send("Time ran out or invalid input. No one saved.")

    await resolve_night(mafia_targets, medic_saves)


async def resolve_night(mafia_targets, medic_saves):
    await game.channel.send("The night is over...")

    if not mafia_targets:
        await game.channel.send("The Mafia couldn't decide on a target. No one was killed.")
        await start_day()
        return

    target = Counter(mafia_targets).most_common(1)[0][0]

    if target in medic_saves:
        await game.channel.send(
            "☠️ An attempt was made on someone's life, but the Medic saved them!"
        )
    else:
        game.alive_players.remove(target)
        await game.channel.send(f"💀 **{target.display_name}** was killed during the night.")

    winner = check_win()
    if winner:
        await end_game(winner)
        return

    await start_day()


# ================= DISCUSSION & VOTING =================

async def discussion_phase():
    await game.channel.send("🗳️ **Voting time!** You have 30 seconds. Use `!vote @user`")

    game.votes = {}

    def vote_check(m):
        return (
            m.content.startswith("!vote")
            and m.author in game.alive_players
            and m.channel == game.channel
        )

    try:
        while True:
            msg = await bot.wait_for("message", timeout=30, check=vote_check)
            if msg.mentions:
                voted_for = msg.mentions[0]
                if voted_for in game.alive_players:
                    game.votes[msg.author] = voted_for
                    await msg.add_reaction("✅")
    except asyncio.TimeoutError:
        pass

    if not game.votes:
        await game.channel.send("No votes were cast. Moving to night phase.")
        await night_phase()
        return

    voted_out = Counter(game.votes.values()).most_common(1)[0][0]
    game.alive_players.remove(voted_out)
    role = game.roles.get(voted_out, "Unknown")

    # FIX #6: removed hardcoded "He was" pronoun
    if voted_out in game.mafias:
        remaining = len([m for m in game.mafias if m in game.alive_players])
        extra = f" There are still **{remaining}** Mafia remaining." if remaining > 0 else ""
        await game.channel.send(
            f"🗳️ **{voted_out.display_name}** was voted out. They were **Mafia**.{extra}"
        )
    elif voted_out in game.medics:
        await game.channel.send(
            f"🗳️ **{voted_out.display_name}** was voted out. They were the **Medic**. You've lost a lifesaver!"
        )
    else:
        await game.channel.send(
            f"🗳️ **{voted_out.display_name}** was voted out. They were a **Villager**."
        )

    winner = check_win()
    if winner:
        await end_game(winner)
        return

    await night_phase()


# ================= END GAME =================

async def end_game(winner):
    mafia_names = ", ".join(m.display_name for m in game.mafias)
    if winner == "mafia":
        await game.channel.send(f"🔴 **Mafia wins!** The Mafia were: {mafia_names}")
    else:
        await game.channel.send(f"🟢 **Villagers win!** The Mafia were: {mafia_names}")

    reset_game()


# ================= RUN =================

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")

keep_alive()
bot.run(TOKEN)
