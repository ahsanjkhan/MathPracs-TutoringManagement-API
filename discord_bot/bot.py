import sys
sys.path.append("..")

import json
import boto3
import discord
from discord import app_commands
from discord.ext import commands
from src.config import get_settings

settings = get_settings()

# Fetch Discord token from Secrets Manager
_discord_token = None


def get_discord_token():
    """Get Discord bot token from AWS Secrets Manager."""
    global _discord_token
    if _discord_token is None:
        secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
        response = secrets_client.get_secret_value(SecretId=settings.discord_credentials_secret_name)
        creds = json.loads(response["SecretString"])
        _discord_token = creds["bot_token"]
    return _discord_token


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    """Called when bot is ready."""
    print(f"Bot is ready! Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


@bot.tree.command(name="ping", description="Test if bot is working")
async def ping(interaction: discord.Interaction):
    """Simple ping command to test bot."""
    await interaction.response.send_message("Pong!")


if __name__ == "__main__":
    print("Fetching Discord token from Secrets Manager...")
    token = get_discord_token()

    print("Starting bot...")
    bot.run(token)
