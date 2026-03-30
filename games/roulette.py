import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random


# ================= GAME STATE =================

class RouletteGame:
    def __init__(self):
        self.running = False
        self.players = []
        self.alive_players = []
        self.join_message = None
        self.channel = None
        self.bullets = 0
        self.chambers = 0
        self.cylinder = []   # list of booleans: True = bullet


# ================= COG =================

class Roulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.game = RouletteGame()
        self.bot.tree.add_command(self.RouletteGroup(self))

    def cog_unload(self):
        self.bot.tree.remove_command("roulette")

    def reset_game(self):
        self.game = RouletteGame()

    def calculate_chambers(self, players: int, bullets: int) -> int:
        # Chambers = at least 2x bullets, scaled up with player count
        # More players → more chambers so game lasts longer
        # Minimum 6 chambers, scales up by 2 per extra player beyond 3
        base = max(6, bullets * 2)
        extra = max(0, players - 3) * 2
        return base + extra

    def build_cylinder(self):
        cylinder = [True] * self.game.bullets + [False] * (self.game.chambers - self.game.bullets)
        random.shuffle(cylinder)
        return cylinder

    # ---- Slash Command Group ----

    class RouletteGroup(app_commands.Group):
        def __init__(self, cog):
            super().__init__(name="roulette", description="Russian Roulette commands")
            self.cog = cog

        @app_commands.command(name="start", description="Start a Russian Roulette game")
        async def start(self, interaction: discord.Interaction, bullets: int):
            cog = self.cog

            if cog.game.running:
                await interaction.response.send_message("A game is already running!", ephemeral=True)
                return

            if bullets < 1:
                await interaction.response.send_message("There must be at least 1 bullet.", ephemeral=True)
                return

            cog.game.running = True
            cog.game.bullets = bullets
            cog.game.channel = interaction.channel

            await interaction.response.send_message("🔫 A game of **Russian Roulette** is starting! Players joined: 0\nType `.rjoin` to join! (30 seconds)")
            cog.game.join_message = await interaction.original_response()

            await asyncio.sleep(30)

            if len(cog.game.players) < 2:
                await cog.game.channel.send("Not enough players joined. Game cancelled.")
                cog.reset_game()
                return

            await cog.start_game()

    # ---- Text Commands ----

    @commands.command(name="rjoin")
    async def rjoin(self, ctx):
        if not self.game.running:
            await ctx.send("No Russian Roulette game is running.", delete_after=5)
            return
        if self.game.join_message is None:
            await ctx.send("The game is still starting up, try again in a moment!", delete_after=5)
            return
        if ctx.author in self.game.players:
            await ctx.send("You already joined!", delete_after=5)
            return

        self.game.players.append(ctx.author)
        await self.game.join_message.edit(
            content=f"🔫 A game of **Russian Roulette** is starting! Players joined: {len(self.game.players)}\nType `.rjoin` to join! (30 seconds)"
        )
        await ctx.message.add_reaction("✅")

    # ---- Game Logic ----

    async def start_game(self):
        players = self.game.players
        self.game.alive_players = players.copy()
        self.game.chambers = self.calculate_chambers(len(players), self.game.bullets)
        self.game.cylinder = self.build_cylinder()

        await self.game.channel.send(
            f"**A game of Russian Roulette is starting**\n"
            f"*{len(players)} players have entered the room...*"
        )
        await asyncio.sleep(10)

        await self.game.channel.send(
            f"The executioner loads a revolver with **{self.game.bullets}** bullet(s) "
            f"in a total of **{self.game.chambers}** chambers. 🔫"
        )
        await asyncio.sleep(5)

        await self.play_round()

    async def play_round(self):
        # Spin the cylinder fresh each full rotation through players
        cylinder = self.build_cylinder()
        cylinder_index = [0]  # use list so inner scope can mutate it

        player_queue = list(self.game.alive_players)
        random.shuffle(player_queue)

        for player in player_queue:
            if player not in self.game.alive_players:
                continue

            await self.game.channel.send(
                f"{player.mention} *holds the revolver to their head...*"
            )
            await asyncio.sleep(5)

            # Pull the trigger
            fired = cylinder[cylinder_index[0] % len(cylinder)]
            cylinder_index[0] += 1

            if fired:
                # Dead
                bang = random.choice(["**BANG!** 💥", "**BLAM!** 💥", "**CRACK!** 💥"])
                await self.game.channel.send(
                    f"{bang}\n💀 **{player.display_name}** has been eliminated."
                )
                self.game.alive_players.remove(player)
                await asyncio.sleep(7)

                if len(self.game.alive_players) == 1:
                    winner = self.game.alive_players[0]
                    await self.game.channel.send(
                        f"🏆 **{winner.display_name}** is the last one standing and wins Russian Roulette!"
                    )
                    self.reset_game()
                    return

                if len(self.game.alive_players) == 0:
                    await self.game.channel.send("Everyone is dead. No winners today.")
                    self.reset_game()
                    return

            else:
                # Survived
                await self.game.channel.send(
                    f"*Click!* 😮‍💨 **{player.display_name}** survives. The revolver is passed to the next person."
                )
                await asyncio.sleep(7)

        # All alive players have gone once — start next round
        await self.game.channel.send(
            f"--- **End of round.** {len(self.game.alive_players)} players remain. The cylinder is spun again... ---"
        )
        await asyncio.sleep(5)
        await self.play_round()


async def setup(bot):
    await bot.add_cog(Roulette(bot))
