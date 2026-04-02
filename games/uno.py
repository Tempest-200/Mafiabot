import discord
from discord.ext import commands
import asyncio
import random

# ================= DECK DEFINITION =================

COLORS = ["red", "green", "blue", "yellow"]
COLOR_EMOJI = {"red": "🔴", "green": "🟢", "blue": "🔵", "yellow": "🟡", "wild": "⚫"}
VALUES = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "skip", "reverse", "draw2"]

def build_deck():
    deck = []
    for color in COLORS:
        deck.append((color, "0"))
        for value in VALUES[1:]:
            deck.append((color, value))
            deck.append((color, value))
    for _ in range(4):
        deck.append(("wild", "wild"))
        deck.append(("wild", "wildraw4"))
    random.shuffle(deck)
    return deck

def card_str(card):
    color, value = card
    emoji = COLOR_EMOJI.get(color, "⚫")
    labels = {
        "draw2": "Draw 2",
        "skip": "Skip",
        "reverse": "Reverse",
        "wild": "Wild",
        "wildraw4": "Wild Draw 4"
    }
    label = labels.get(value, value.upper())
    return f"{emoji} {label}"

def hand_str(hand):
    if not hand:
        return "*(empty)*"
    return "\n".join(f"`{i}.` {card_str(c)}" for i, c in enumerate(hand, 1))

def can_play(card, top_card, current_color):
    color, value = card
    _, top_value = top_card
    if color == "wild":
        return True
    if color == current_color:
        return True
    if value == top_value:
        return True
    return False


# ================= GAME STATE =================

class UnoGame:
    def __init__(self):
        self.running = False
        self.accepting_joins = False
        self.players = []
        self.hands = {}
        self.deck = []
        self.discard = []
        self.current_color = None
        self.current_index = 0
        self.direction = 1          # 1 = clockwise, -1 = counter-clockwise
        self.channel = None
        self.join_message = None
        self.pending_draw = 0       # stacked draw 2 / draw 4 amount

    @property
    def top_card(self):
        return self.discard[-1] if self.discard else None

    @property
    def current_player(self):
        return self.players[self.current_index] if self.players else None

    def draw_card(self):
        if not self.deck:
            if len(self.discard) <= 1:
                return None
            top = self.discard.pop()
            self.deck = self.discard
            random.shuffle(self.deck)
            self.discard = [top]
        return self.deck.pop() if self.deck else None

    def advance_turn(self, steps=1):
        self.current_index = (self.current_index + self.direction * steps) % len(self.players)


# ================= COG =================

class Uno(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.game = UnoGame()

    def reset_game(self):
        self.game = UnoGame()

    # ---- Commands ----

    @commands.command(name="game")
    @commands.has_permissions(administrator=True)
    async def game_start(self, ctx):
        if self.game.running:
            await ctx.send("A game is already running!")
            return

        self.game.running = True
        self.game.accepting_joins = True
        self.game.channel = ctx.channel

        self.game.join_message = await ctx.send(
            "🎴 A game of **Uno** is starting! Players joined: 0\n"
            "Type `.ujoin` to join! (30 seconds)\n"
            "*(2–6 players)*"
        )

        await asyncio.sleep(30)
        self.game.accepting_joins = False

        if len(self.game.players) < 2:
            await self.game.channel.send("Not enough players joined. Game cancelled.")
            self.reset_game()
            return

        await self.start_game()

    @commands.command(name="ujoin")
    async def ujoin(self, ctx):
        if not self.game.running or not self.game.accepting_joins:
            await ctx.send("No Uno game is currently accepting players.", delete_after=5)
            return
        if ctx.author in self.game.players:
            await ctx.send("You already joined!", delete_after=5)
            return
        if len(self.game.players) >= 6:
            await ctx.send("The game is full! (max 6 players)", delete_after=5)
            return

        self.game.players.append(ctx.author)
        await self.game.join_message.edit(
            content=(
                f"🎴 A game of **Uno** is starting! Players joined: {len(self.game.players)}\n"
                f"Type `.ujoin` to join! (30 seconds)\n"
                f"*(2–6 players)*"
            )
        )
        await ctx.message.add_reaction("✅")

    @commands.command(name="play")
    async def play(self, ctx, color: str, value: str = None):
        if not self.game.running or self.game.accepting_joins:
            return
        if ctx.author != self.game.current_player:
            await ctx.send(f"It's not your turn, {ctx.author.mention}!", delete_after=5)
            return

        color = color.lower()
        value = value.lower() if value else None

        # Wild cards: .play wild red OR .play wildraw4 blue
        if color in ("wild", "wildraw4"):
            if value is None or value not in COLORS:
                await ctx.send(
                    f"Specify a valid color after the wild: `.play {color} <red/green/blue/yellow>`",
                    delete_after=7
                )
                return
            card_to_play = ("wild", color)
            chosen_color = value
        else:
            if value is None:
                await ctx.send("Specify the card value: `.play <color> <value>`", delete_after=5)
                return
            card_to_play = (color, value)
            chosen_color = color

        hand = self.game.hands.get(ctx.author, [])
        if card_to_play not in hand:
            await ctx.send(f"You don't have that card! Use `.hand` to check your hand.", delete_after=7)
            return

        if not can_play(card_to_play, self.game.top_card, self.game.current_color):
            await ctx.send(
                f"You can't play that! Top card: {card_str(self.game.top_card)} | "
                f"Current color: {COLOR_EMOJI[self.game.current_color]} {self.game.current_color.capitalize()}",
                delete_after=7
            )
            return

        # Handle stacked draw — if pending draw exists, only draw cards of same type can be played
        if self.game.pending_draw > 0:
            _, card_value = card_to_play
            if card_value not in ("draw2", "wildraw4"):
                await ctx.send(
                    f"You must stack a Draw 2 or Wild Draw 4, or use `.draw` to take {self.game.pending_draw} cards!",
                    delete_after=7
                )
                return

        # Play the card
        hand.remove(card_to_play)
        self.game.discard.append(card_to_play)
        _, card_value = card_to_play

        if color == "wild":
            self.game.current_color = chosen_color
        else:
            self.game.current_color = color

        await ctx.message.add_reaction("✅")

        # Uno announcement
        if len(hand) == 1:
            await self.game.channel.send(f"🔔 **UNO!** {ctx.author.mention} has one card left!")

        # Win check
        if len(hand) == 0:
            await self.game.channel.send(f"🎉 **{ctx.author.display_name} wins Uno!** Congratulations!")
            self.reset_game()
            return

        await self.apply_effect(card_to_play, chosen_color)

    @commands.command(name="draw")
    async def draw_cmd(self, ctx):
        if not self.game.running or self.game.accepting_joins:
            return
        if ctx.author != self.game.current_player:
            await ctx.send(f"It's not your turn, {ctx.author.mention}!", delete_after=5)
            return

        # If there's a pending stacked draw, they take all of it
        amount = self.game.pending_draw if self.game.pending_draw > 0 else 1
        self.game.pending_draw = 0

        drawn = []
        for _ in range(amount):
            card = self.game.draw_card()
            if card:
                self.game.hands[ctx.author].append(card)
                drawn.append(card)

        try:
            drawn_str = "\n".join(card_str(c) for c in drawn)
            await ctx.author.send(
                f"You drew {amount} card(s):\n{drawn_str}\n\n"
                f"**Your hand:**\n{hand_str(self.game.hands[ctx.author])}"
            )
        except discord.Forbidden:
            pass

        suffix = "s" if amount != 1 else ""
        await self.game.channel.send(f"{ctx.author.mention} drew **{amount}** card{suffix}.")
        self.game.advance_turn()
        await self.announce_turn()

    @commands.command(name="hand")
    async def hand_cmd(self, ctx):
        if not self.game.running or ctx.author not in self.game.hands:
            return
        try:
            await ctx.author.send(
                f"**Your current hand:**\n{hand_str(self.game.hands[ctx.author])}"
            )
            await ctx.message.add_reaction("📬")
        except discord.Forbidden:
            await ctx.send("I couldn't DM you. Please enable DMs.", delete_after=5)

    # ---- Game Setup ----

    async def start_game(self):
        self.game.deck = build_deck()
        self.game.hands = {p: [] for p in self.game.players}

        # Deal 7 cards each
        for _ in range(7):
            for player in self.game.players:
                card = self.game.draw_card()
                if card:
                    self.game.hands[player].append(card)

        # Flip starting card — reroll if it's a wild
        while True:
            first = self.game.draw_card()
            if first[0] != "wild":
                break
            self.game.deck.insert(0, first)

        self.game.discard.append(first)
        self.game.current_color = first[0]

        player_names = ", ".join(p.display_name for p in self.game.players)
        await self.game.channel.send(
            f"🎴 **Uno begins!**\n"
            f"Players: {player_names}\n"
            f"Starting card: {card_str(first)}\n"
            f"Sending everyone their hands now..."
        )

        for player in self.game.players:
            try:
                await player.send(
                    f"🎴 **Uno has started!**\n\n"
                    f"**Your hand:**\n{hand_str(self.game.hands[player])}\n\n"
                    f"**How to play:**\n"
                    f"`.play <color> <value>` — e.g. `.play red 5`, `.play blue skip`\n"
                    f"`.play wild <color>` — e.g. `.play wild red`\n"
                    f"`.play wildraw4 <color>` — e.g. `.play wildraw4 blue`\n"
                    f"`.draw` — Draw a card\n"
                    f"`.hand` — See your hand again"
                )
            except discord.Forbidden:
                await self.game.channel.send(f"⚠️ Could not DM {player.mention}. Please enable DMs.")

        await asyncio.sleep(3)

        # Apply first card effect if special
        _, first_value = first
        if first_value == "skip":
            skipped = self.game.players[self.game.current_index]
            await self.game.channel.send(f"First card is a Skip — {skipped.mention} is skipped!")
            self.game.advance_turn()
        elif first_value == "reverse":
            self.game.direction = -1
            await self.game.channel.send("First card is a Reverse — turn order reversed!")
        elif first_value == "draw2":
            self.game.pending_draw += 2

        await self.announce_turn()

    # ---- Turn Announcement ----

    async def announce_turn(self):
        if not self.game.running:
            return

        player = self.game.current_player
        top = card_str(self.game.top_card)
        color_emoji = COLOR_EMOJI.get(self.game.current_color, "⚫")

        draw_warning = ""
        if self.game.pending_draw > 0:
            draw_warning = (
                f"\n⚠️ Stack a Draw card or use `.draw` to take **{self.game.pending_draw} cards**!"
            )

        await self.game.channel.send(
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎴 {player.mention}'s turn!\n"
            f"Top card: {top} | Color: {color_emoji} {self.game.current_color.capitalize()}"
            f"{draw_warning}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )

        try:
            await player.send(
                f"**It's your turn!**\n"
                f"Top card: {top} | Color: {self.game.current_color.capitalize()}\n\n"
                f"**Your hand:**\n{hand_str(self.game.hands[player])}"
            )
        except discord.Forbidden:
            pass

    # ---- Card Effects ----

    async def apply_effect(self, card, chosen_color):
        _, value = card
        channel = self.game.channel

        if value == "skip":
            self.game.advance_turn()
            skipped = self.game.current_player
            await channel.send(f"⏭️ {skipped.mention} is **skipped**!")
            self.game.advance_turn()

        elif value == "reverse":
            self.game.direction *= -1
            if len(self.game.players) == 2:
                await channel.send("🔄 **Reverse!** (2 players — acts as skip)")
                self.game.advance_turn()
                self.game.advance_turn()
            else:
                await channel.send("🔄 Turn order **reversed!**")
                self.game.advance_turn()

        elif value == "draw2":
            self.game.advance_turn()
            target = self.game.current_player
            self.game.pending_draw += 2
            await channel.send(
                f"➕ **Draw 2!** {target.mention} must stack a Draw 2 or use `.draw` to take **{self.game.pending_draw}** cards!"
            )

        elif value == "wild":
            await channel.send(
                f"🌈 **Wild!** Color changed to {COLOR_EMOJI[chosen_color]} **{chosen_color.capitalize()}**"
            )
            self.game.advance_turn()

        elif value == "wildraw4":
            self.game.advance_turn()
            target = self.game.current_player
            self.game.pending_draw += 4
            await channel.send(
                f"🌈 **Wild Draw 4!** Color → {COLOR_EMOJI[chosen_color]} **{chosen_color.capitalize()}**\n"
                f"➕ {target.mention} must stack a Wild Draw 4 or use `.draw` to take **{self.game.pending_draw}** cards!"
            )

        else:
            # Normal number card
            self.game.advance_turn()

        await self.announce_turn()


async def setup(bot):
    await bot.add_cog(Uno(bot))
