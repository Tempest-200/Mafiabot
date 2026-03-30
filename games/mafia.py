import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import os
from collections import Counter


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


# ================= COG =================

class Mafia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.game = MafiaGame()
        # Register the slash command group
        self.bot.tree.add_command(self.GameGroup(self))

    def cog_unload(self):
        self.bot.tree.remove_command("game")

    # ---- Util ----

    def reset_game(self):
        self.game = MafiaGame()

    def check_win(self):
        mafias_alive = [p for p in self.game.mafias if p in self.game.alive_players]
        villagers_alive = [p for p in self.game.alive_players if p not in self.game.mafias]
        if len(mafias_alive) == 0:
            return "villagers"
        if len(mafias_alive) >= len(villagers_alive):
            return "mafia"
        return None

    def player_list_text(self):
        return "\n".join(f"{i}. {p.display_name}" for i, p in enumerate(self.game.alive_players, 1))

    # ---- Slash Command Group ----

    class GameGroup(app_commands.Group):
        def __init__(self, cog):
            super().__init__(name="game", description="Mafia game commands")
            self.cog = cog

        @app_commands.command(name="start", description="Start a mafia game")
        async def start(self, interaction: discord.Interaction, mafias: int, medics: int):
            cog = self.cog
            if cog.game.running:
                await interaction.response.send_message("A game is already running!", ephemeral=True)
                return

            cog.game.running = True
            cog.game.players = []
            cog.game.channel = interaction.channel
            cog.game.mafia_count = mafias
            cog.game.medic_count = medics

            await interaction.response.send_message("A game of Mafia has started! Players joined: 0")
            cog.game.join_message = await interaction.original_response()

            await asyncio.sleep(30)

            if len(cog.game.players) < mafias + medics + 1:
                await cog.game.channel.send("Not enough players joined. Game cancelled.")
                cog.reset_game()
                return

            await cog.assign_roles()

        @app_commands.command(name="join", description="Join the current mafia game")
        async def join(self, interaction: discord.Interaction):
            cog = self.cog
            if not cog.game.running:
                await interaction.response.send_message("A game is not currently running.", ephemeral=True)
                return
            if cog.game.join_message is None:
                await interaction.response.send_message("The game is still starting up, try again in a moment!", ephemeral=True)
                return
            if interaction.user in cog.game.players:
                await interaction.response.send_message("You already joined!", ephemeral=True)
                return

            cog.game.players.append(interaction.user)
            await cog.game.join_message.edit(content=f"A game of Mafia has started! Players joined: {len(cog.game.players)}")
            await interaction.response.send_message("You joined the game!", ephemeral=True)

    # ---- Text Commands ----

    @commands.command(name="vote")
    async def vote(self, ctx):
        if not self.game.running or ctx.author not in self.game.alive_players:
            return
        if ctx.mentions:
            voted_for = ctx.mentions[0]
            if voted_for in self.game.alive_players and voted_for != ctx.author:
                self.game.votes[ctx.author] = voted_for
                await ctx.message.add_reaction("✅")

    @commands.command(name="skip")
    async def skip(self, ctx):
        if not self.game.running or ctx.author not in self.game.alive_players:
            return
        if self.game.day <= 2:
            self.game.votes.pop(ctx.author, None)
            await ctx.message.add_reaction("⏭️")
        else:
            await ctx.send("Skipping is only allowed in rounds 1 and 2.", delete_after=5)

    # ---- Role Assignment ----

    async def assign_roles(self):
        await self.game.channel.send("Assigning roles to players. Check your DMs for your role!")

        self.game.alive_players = self.game.players.copy()
        shuffled = self.game.players.copy()
        random.shuffle(shuffled)

        self.game.mafias = shuffled[:self.game.mafia_count]
        self.game.medics = shuffled[self.game.mafia_count:self.game.mafia_count + self.game.medic_count]
        self.game.villagers = shuffled[self.game.mafia_count + self.game.medic_count:]

        for player in self.game.players:
            if player in self.game.mafias:
                self.game.roles[player] = "Mafia"
            elif player in self.game.medics:
                self.game.roles[player] = "Medic"
            else:
                self.game.roles[player] = "Villager"

        for player in self.game.players:
            role = self.game.roles[player]
            try:
                if role == "Mafia":
                    others = [m.display_name for m in self.game.mafias if m != player]
                    msg = "You are **Mafia**."
                    if others:
                        msg += f"\nYour fellow mafias: {', '.join(others)}"
                    await player.send(msg)
                elif role == "Medic":
                    others = [m.display_name for m in self.game.medics if m != player]
                    msg = "You are a **Medic**."
                    if others:
                        msg += f"\nYour fellow medics: {', '.join(others)}"
                    await player.send(msg)
                else:
                    await player.send("You are a **Villager**. Find and vote out the Mafia!")
            except discord.Forbidden:
                await self.game.channel.send(f"⚠️ Could not DM {player.mention}. Please enable DMs.")

        await self.night_phase()

    # ---- Night Phase ----

    async def night_phase(self):
        await self.game.channel.send("**🌙 Night falls...** The Mafia and Medic are making their moves.")

        player_list = self.player_list_text()
        results = {"mafia_targets": [], "medic_saves": []}
        deadline = asyncio.get_event_loop().time() + 30

        async def ask_mafia(mafia):
            try:
                await mafia.send(f"**Choose a target to eliminate.** Reply with the player's number (30 seconds):\n{player_list}")
                def check(m): return m.author == mafia and isinstance(m.channel, discord.DMChannel)
                time_left = max(deadline - asyncio.get_event_loop().time(), 1)
                msg = await self.bot.wait_for("message", check=check, timeout=time_left)
                choice = int(msg.content.strip()) - 1
                if 0 <= choice < len(self.game.alive_players):
                    target = self.game.alive_players[choice]
                    results["mafia_targets"].append(target)
                    await mafia.send(f"Target confirmed: **{target.display_name}**")
                else:
                    await mafia.send("Invalid choice. No target selected.")
            except (asyncio.TimeoutError, ValueError):
                await mafia.send("Time ran out or invalid input. No target selected.")

        async def ask_medic(medic):
            try:
                await medic.send(f"**Choose someone to save.** Reply with the player's number (30 seconds):\n{player_list}")
                def check(m): return m.author == medic and isinstance(m.channel, discord.DMChannel)
                time_left = max(deadline - asyncio.get_event_loop().time(), 1)
                msg = await self.bot.wait_for("message", check=check, timeout=time_left)
                choice = int(msg.content.strip()) - 1
                if 0 <= choice < len(self.game.alive_players):
                    target = self.game.alive_players[choice]
                    results["medic_saves"].append(target)
                    await medic.send(f"Save confirmed: **{target.display_name}**")
                else:
                    await medic.send("Invalid choice. No one saved.")
            except (asyncio.TimeoutError, ValueError):
                await medic.send("Time ran out or invalid input. No one saved.")

        tasks = []
        for mafia in self.game.mafias:
            if mafia in self.game.alive_players:
                tasks.append(ask_mafia(mafia))
        for medic in self.game.medics:
            if medic in self.game.alive_players:
                tasks.append(ask_medic(medic))

        await asyncio.gather(*tasks)
        await self.resolve_night(results["mafia_targets"], results["medic_saves"])

    async def resolve_night(self, mafia_targets, medic_saves):
        await self.game.channel.send("The night is over...")

        if not mafia_targets:
            await self.game.channel.send("The Mafia couldn't decide on a target. No one was killed.")
        else:
            target = Counter(mafia_targets).most_common(1)[0][0]
            if target in medic_saves:
                await self.game.channel.send("☠️ An attempt was made on someone's life, but the Medic saved them!")
            else:
                self.game.alive_players.remove(target)
                await self.game.channel.send(f"💀 **{target.display_name}** was killed during the night.")

        winner = self.check_win()
        if winner:
            await self.end_game(winner)
            return

        await asyncio.sleep(10)
        await self.start_day()

    # ---- Day Phase ----

    async def start_day(self):
        self.game.day += 1
        await self.game.channel.send(
            f"**☀️ Day {self.game.day}**\nDiscuss among yourselves! You have 60 seconds before voting begins."
        )
        await asyncio.sleep(60)
        await self.discussion_phase()

    async def discussion_phase(self):
        can_skip = self.game.day <= 2
        skip_note = " You may also `.skip` your vote." if can_skip else ""
        await self.game.channel.send(f"🗳️ **Voting time!** You have 30 seconds. Use `.vote @user`.{skip_note}")

        self.game.votes = {}

        def vote_check(m):
            return (
                (m.content.startswith(".vote") or (can_skip and m.content.strip() == ".skip"))
                and m.author in self.game.alive_players
                and m.channel == self.game.channel
            )

        try:
            while True:
                msg = await self.bot.wait_for("message", timeout=30, check=vote_check)
                if msg.content.strip() == ".skip" and can_skip:
                    self.game.votes.pop(msg.author, None)
                    await msg.add_reaction("⏭️")
                elif msg.mentions:
                    voted_for = msg.mentions[0]
                    if voted_for in self.game.alive_players and voted_for != msg.author:
                        self.game.votes[msg.author] = voted_for
                        await msg.add_reaction("✅")
        except asyncio.TimeoutError:
            pass

        if not self.game.votes:
            await self.game.channel.send("No votes were cast. Moving to night phase.")
            await asyncio.sleep(10)
            await self.night_phase()
            return

        voted_out = Counter(self.game.votes.values()).most_common(1)[0][0]
        self.game.alive_players.remove(voted_out)

        if voted_out in self.game.mafias:
            remaining = len([m for m in self.game.mafias if m in self.game.alive_players])
            extra = f" There are still **{remaining}** Mafia remaining." if remaining > 0 else ""
            await self.game.channel.send(f"🗳️ **{voted_out.display_name}** was voted out. They were **Mafia**.{extra}")
        elif voted_out in self.game.medics:
            await self.game.channel.send(f"🗳️ **{voted_out.display_name}** was voted out. They were the **Medic**. You've lost a lifesaver!")
        else:
            await self.game.channel.send(f"🗳️ **{voted_out.display_name}** was voted out. They were a **Villager**.")

        winner = self.check_win()
        if winner:
            await self.end_game(winner)
            return

        await asyncio.sleep(10)
        await self.night_phase()

    # ---- End Game ----

    async def end_game(self, winner):
        mafia_names = ", ".join(m.display_name for m in self.game.mafias)
        if winner == "mafia":
            await self.game.channel.send(f"🔴 **Mafia wins!** The Mafia were: {mafia_names}")
        else:
            await self.game.channel.send(f"🟢 **Villagers win!** The Mafia were: {mafia_names}")
        self.reset_game()


async def setup(bot):
    await bot.add_cog(Mafia(bot))
