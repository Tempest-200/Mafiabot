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

        msg = await interaction.response.send_message(
            "A game has now started! Users joined: 0",
            wait=True
        )

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
                others = [m.mention for m in game.mafias if m != player]
                msg = "You are a Mafia."
                if others:
                    msg += f"\nYour fellow mafias: {', '.join(others)}"
                await player.send(msg)

            elif role == "Medic":
                others = [m.mention for m in game.medics if m != player]
                msg = "You are a Medic."
                if others:
                    msg += f"\nYour fellow medics: {', '.join(others)}"
                await player.send(msg)

            else:
                await player.send("You are a Villager.")

        except:
            pass

    await start_day()


# ================= DAY/NIGHT LOOP =================

async def start_day():
    await game.channel.send("**Day 1**\nDiscuss among yourselves...")

    await night_phase()


async def night_phase():
    mafia_targets = []
    medic_saves = []

    # ---- MAFIA ----
    for mafia in game.mafias:
        if mafia not in game.alive_players:
            continue

        try:
            await mafia.send("Who do you want to kill? Send their User ID.")

            def check(m):
                return m.author == mafia and isinstance(m.channel, discord.DMChannel)

            msg = await bot.wait_for("message", check=check, timeout=30)
            target = game.channel.guild.get_member(int(msg.content))

            if target in game.alive_players:
                mafia_targets.append(target)
                await mafia.send("Target confirmed.")

        except:
            pass

    # ---- MEDIC ----
    for medic in game.medics:
        if medic not in game.alive_players:
            continue

        try:
            await medic.send("Who do you want to save? Send their User ID.")

            def check(m):
                return m.author == medic and isinstance(m.channel, discord.DMChannel)

            msg = await bot.wait_for("message", check=check, timeout=30)
            target = game.channel.guild.get_member(int(msg.content))

            if target in game.alive_players:
                medic_saves.append(target)
                await medic.send("Save confirmed.")

        except:
            pass

    await resolve_night(mafia_targets, medic_saves)


async def resolve_night(mafia_targets, medic_saves):
    await game.channel.send("The night is now over...")

    if not mafia_targets:
        await discussion_phase()
        return

    target = Counter(mafia_targets).most_common(1)[0][0]

    if target in medic_saves:
        await game.channel.send(
            "An attempt on someone's life was made, but the medic managed to save them."
        )
    else:
        game.alive_players.remove(target)
        await game.channel.send(f"{target.mention} was killed and is now out of the game.")

    winner = check_win()
    if winner:
        await end_game(winner)
        return

    await discussion_phase()


# ================= DISCUSSION & VOTING =================

async def discussion_phase():
    await game.channel.send("You have 1 minute to discuss.")
    await asyncio.sleep(60)

    await game.channel.send("You have 15 seconds to vote! Use `!vote @user`")

    game.votes = {}

    def vote_check(m):
        return (
            m.content.startswith("!vote")
            and m.author in game.alive_players
            and m.channel == game.channel
        )

    try:
        while True:
            msg = await bot.wait_for("message", timeout=15, check=vote_check)
            if msg.mentions:
                game.votes[msg.author] = msg.mentions[0]
    except asyncio.TimeoutError:
        pass

    if not game.votes:
        await game.channel.send("No votes were made.")
        await night_phase()
        return

    voted = Counter(game.votes.values()).most_common(1)[0][0]
    game.alive_players.remove(voted)

    if voted in game.mafias:
        remaining = len([m for m in game.mafias if m in game.alive_players])
        if remaining > 0:
            await game.channel.send(
                f"{voted.mention} has been voted out! He was the Mafia. There are still {remaining} mafia(s) remaining."
            )
        else:
            await game.channel.send(
                f"{voted.mention} has been voted out! He was the Mafia."
            )
    elif voted in game.medics:
        await game.channel.send(
            f"{voted.mention} has been voted out! He was the Medic. You have now lost a lifesaver."
        )
    else:
        await game.channel.send(
            f"{voted.mention} has been voted out! He was a Villager."
        )

    winner = check_win()
    if winner:
        await end_game(winner)
        return

    await night_phase()


# ================= END GAME =================

async def end_game(winner):
    if winner == "mafia":
        await game.channel.send("Mafia wins!")
    else:
        await game.channel.send("Villagers win!")

    reset_game()


# ================= RUN =================

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
