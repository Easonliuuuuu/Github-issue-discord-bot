from __future__ import annotations

import asyncio
import logging

import aiohttp
import discord
from discord.ext import commands

from config import DISCORD_BOT_TOKEN, get_github_headers
from utils.persistence import load_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


intents = discord.Intents.default()
intents.message_content = True  # Required to read messages for commands

# Create the bot instance and remove the default help command
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# These will hold the bot's state, loaded on startup
bot.watched_repos = {}
bot.notified_issues = set()
bot.http_session: aiohttp.ClientSession | None = None


@bot.event
async def on_ready():
    """Called when the bot successfully logs in."""
    logger.info("Logged in as %s (%s)", bot.user.name, bot.user.id)

    bot.watched_repos, bot.notified_issues = load_data()

    bot.http_session = aiohttp.ClientSession(headers=get_github_headers())

    try:
        await bot.load_extension("cogs.github")
        logger.info("Loaded 'github' cog.")
        await bot.load_extension("cogs.help")
        logger.info("Loaded 'help' cog.")
    except Exception:
        logger.exception("Failed to load a cog")
        await bot.close()

@bot.event
async def on_close():
    """Called when the bot is shutting down."""
    if bot.http_session:
        await bot.http_session.close()
    logger.info("Bot session closed.")

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Global error handler for all commands."""

    # Check if the error is a CommandNotFound
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(":question: Unknown command. Type `!help` to see all available commands.")
    # Check for permissions errors
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(":no_entry_sign: You don't have permission to use that command.")
    # Handle other errors (and log them for debugging)
    else:
        logger.error("An unhandled error occurred: %s", error)
        await ctx.send(":warning: An unexpected error occurred. Please try again later.")
        # Re-raise the error so we can see the full traceback in the console
        raise error


async def main():
    """Main function to start the bot."""
    async with bot:
        if not DISCORD_BOT_TOKEN:
            logger.error("Please set your DISCORD_BOT_TOKEN in config.py or as an environment variable.")
            return

        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":

    logger.info("Starting bot...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shut down by user.")
