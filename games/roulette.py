import discord
from discord.ext import commands
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


# ================= COG =================

class Roulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.game = RouletteGame()

    def reset_game(self):
        self.game = RouletteGame()

    def calculate_chambers(self, players: int, bullets: int) -> int:
        base = max(6, bullets * 2)
        extra = max(0, players - 3) * 2
        return base + extra

    def build_cylinder(self):
        cylinder = [True] * self.game.bullets + [False] * (self.game.chambers - self.game.bullets)
        random.shuffle(cylinder)
        return cylinder

    # ---- Commands ----

    @commands.command(name="game")
    @commands.has_permissions(administrator=True)
    async def game_start(self, ctx, bullets: int):
        if self.game.running:
            await ctx.send("A game is already running!")
            return

        if bullets < 1:
            await ctx.send("There must be at least 1 bullet.")
            return

        self.game.running = True
        self.game.bullets = bullets
        self.game.channel = ctx.channel

        self.game.join_message = await ctx.send(
            f"🔫 A game of **Russian Roulette** is starting! Players joined: 0\nType `.rjoin` to join! (30 seconds)"
        )

        await asyncio.sleep(30)

        if len(self.game.players) < 2:
            await self.game.channel.send("Not enough players joined. Game cancelled.")
            self.reset_game()
            return

        await self.start_game()

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
        cylinder = self.build_cylinder()
        cylinder_index = [0]

        player_queue = list(self.game.alive_players)
        random.shuffle(player_queue)

        for player in player_queue:
            if player not in self.game.alive_players:
                continue

            await self.game.channel.send(f"{player.mention} *holds the revolver to their head...*")
            await asyncio.sleep(5)

            fired = cylinder[cylinder_index[0] % len(cylinder)]
            cylinder_index[0] += 1

            if fired:
                bang = random.choice(["**BANG!** 💥", "**BLAM!** 💥", "**CRACK!** 💥"])
                await self.game.channel.send(f"{bang}\n💀 **{player.display_name}** has been eliminated.")
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
                await self.game.channel.send(
                    f"*Click!* 😮‍💨 **{player.display_name}** survives. The revolver is passed to the next person."
                )
                await asyncio.sleep(7)

        await self.game.channel.send(
            f"--- **End of round.** {len(self.game.alive_players)} players remain. The cylinder is spun again... ---"
        )
        await asyncio.sleep(5)
        await self.play_round()


async def setup(bot):
    await bot.add_cog(Roulette(bot))
