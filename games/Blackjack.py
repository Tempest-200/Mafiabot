import discord
from discord.ext import commands
import asyncio
import random


SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def new_deck():
    deck = [(r, s) for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck


def card_value(card):
    r = card[0]
    if r == "A":
        return 11
    if r in ("J", "Q", "K"):
        return 10
    return int(r)


def hand_value(hand):
    total = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[0] == "A")
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def format_hand(hand, hide_first=False):
    if hide_first:
        cards = ["🂠"] + [f"{c[0]}{c[1]}" for c in hand[1:]]
    else:
        cards = [f"{c[0]}{c[1]}" for c in hand]
    return " ".join(cards)


def is_blackjack(hand):
    return len(hand) == 2 and hand_value(hand) == 21


# ================= GAME STATE =================

class BlackjackGame:
    def __init__(self):
        self.running = False
        self.channel = None
        self.player = None
        self.deck = []
        self.player_hand = []
        self.dealer_hand = []


# ================= COG =================

class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.game = BlackjackGame()

    def reset_game(self):
        self.game = BlackjackGame()

    # ---- Commands ----

    @commands.command(name="game")
    async def game_start(self, ctx):
        if self.game.running:
            await ctx.send("A game of Blackjack is already running!")
            return

        self.game.running = True
        self.game.channel = ctx.channel
        self.game.player = ctx.author
        self.game.deck = new_deck()
        self.game.player_hand = [self.game.deck.pop(), self.game.deck.pop()]
        self.game.dealer_hand = [self.game.deck.pop(), self.game.deck.pop()]

        await ctx.send(
            f"🃏 **Blackjack** — {ctx.author.mention} vs the Dealer\n\n"
            f"**Dealer's hand:** {format_hand(self.game.dealer_hand, hide_first=True)}\n"
            f"**Your hand:** {format_hand(self.game.player_hand)} (Total: {hand_value(self.game.player_hand)})\n\n"
            f"Use `.hit` to draw a card or `.stand` to hold."
        )

        if is_blackjack(self.game.player_hand):
            await self.resolve_blackjack(ctx)

    @commands.command(name="hit")
    async def hit(self, ctx):
        if not self.game.running:
            await ctx.send("No Blackjack game is running.", delete_after=5)
            return
        if ctx.author != self.game.player:
            await ctx.send("You're not in this game.", delete_after=5)
            return

        self.game.player_hand.append(self.game.deck.pop())
        total = hand_value(self.game.player_hand)

        await ctx.send(
            f"**Your hand:** {format_hand(self.game.player_hand)} (Total: {total})"
        )

        if total > 21:
            await ctx.send(f"💥 **Bust!** You went over 21. Dealer wins.")
            self.reset_game()
        elif total == 21:
            await self.dealer_turn(ctx)

    @commands.command(name="stand")
    async def stand(self, ctx):
        if not self.game.running:
            await ctx.send("No Blackjack game is running.", delete_after=5)
            return
        if ctx.author != self.game.player:
            await ctx.send("You're not in this game.", delete_after=5)
            return

        await ctx.send(f"You stand with a total of **{hand_value(self.game.player_hand)}**.")
        await self.dealer_turn(ctx)

    # ---- Resolution ----

    async def resolve_blackjack(self, ctx):
        player_total = hand_value(self.game.player_hand)
        dealer_total = hand_value(self.game.dealer_hand)

        await ctx.send(
            f"**Dealer's hand:** {format_hand(self.game.dealer_hand)} (Total: {dealer_total})"
        )

        if is_blackjack(self.game.dealer_hand):
            await ctx.send("🤝 Both have **Blackjack**! It's a push (tie).")
        else:
            await ctx.send(f"🎉 **Blackjack!** {self.game.player.mention} wins!")

        self.reset_game()

    async def dealer_turn(self, ctx):
        await asyncio.sleep(1)
        await ctx.send(f"**Dealer reveals:** {format_hand(self.game.dealer_hand)} (Total: {hand_value(self.game.dealer_hand)})")
        await asyncio.sleep(1)

        while hand_value(self.game.dealer_hand) < 17:
            self.game.dealer_hand.append(self.game.deck.pop())
            total = hand_value(self.game.dealer_hand)
            await ctx.send(f"Dealer draws: {format_hand(self.game.dealer_hand)} (Total: {total})")
            await asyncio.sleep(1)

        player_total = hand_value(self.game.player_hand)
        dealer_total = hand_value(self.game.dealer_hand)

        if dealer_total > 21:
            await ctx.send(f"💥 Dealer busts! 🎉 {self.game.player.mention} wins!")
        elif dealer_total > player_total:
            await ctx.send(f"Dealer wins with **{dealer_total}** vs your **{player_total}**.")
        elif dealer_total < player_total:
            await ctx.send(f"🎉 {self.game.player.mention} wins with **{player_total}** vs dealer's **{dealer_total}**!")
        else:
            await ctx.send(f"🤝 It's a push (tie) at **{player_total}**.")

        self.reset_game()


async def setup(bot):
    await bot.add_cog(Blackjack(bot))
