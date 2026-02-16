import sys
sys.path.append("..")

import json
import boto3
import discord
from datetime import datetime, timedelta, timezone
from discord import app_commands
from discord.ext import commands
from src.config import get_settings
from src.functions import tutor_functions, session_functions, dynamodb
from src.functions.google_docs import extract_student_name

settings = get_settings()

CALENDAR_LIST_SYNC_TYPE = "calendarList"


def get_last_sync_ago() -> str:
    """Get how long ago the last sync happened, formatted as a human-readable string."""
    try:
        item = dynamodb.get_item(settings.calendar_sync_table, {"syncType": CALENDAR_LIST_SYNC_TYPE})
        if item and item.get("lastSyncAt"):
            last_sync = datetime.fromisoformat(item["lastSyncAt"])
            # Make timezone-aware if not already
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = now - last_sync

            minutes = int(delta.total_seconds() / 60)
            if minutes < 1:
                return "just now"
            elif minutes < 60:
                return f"{minutes} min ago"
            elif minutes < 1440:  # 24 hours
                hours = minutes // 60
                return f"{hours} hr ago"
            else:
                days = minutes // 1440
                return f"{days} day{'s' if days > 1 else ''} ago"
        return "never"
    except Exception:
        return "unknown"


# Timezone mappings (UTC offset in hours)
TIMEZONE_OFFSETS = {
    "karachi": 5,      # UTC+5
    "lahore": 5,       # UTC+5
    "islamabad": 5,    # UTC+5
    "berlin": 1,    # UTC+1
}

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


@bot.tree.command(name="ping_bot", description="Test if MathPracs Tutoring Bot is connected")
async def ping(interaction: discord.Interaction):
    """Simple ping command to test bot."""
    sync_ago = get_last_sync_ago()
    await interaction.response.send_message(f"Pong! (Last sync: {sync_ago})", ephemeral=True)


@bot.tree.command(name="sessions", description="View your scheduled sessions for the next 24 hours")
async def sessions(interaction: discord.Interaction):
    """Show tutor's sessions in the next 24 hours."""
    await interaction.response.defer(ephemeral=True)

    # Get the channel where command was invoked
    channel_id = str(interaction.channel_id)

    # Look up tutor by Discord channel ID
    tutor = tutor_functions.get_tutor_by_discord_channel_id(channel_id)
    if not tutor:
        await interaction.followup.send("This channel is not linked to a tutor.", ephemeral=True)
        return

    # Get tutor's first name from database
    tutor_name = tutor.display_name.split()[0] if tutor.display_name else "Tutor"
    # Discord mention for whoever invoked the command
    user_mention = interaction.user.mention

    # Get timezone offset
    tz_offset = TIMEZONE_OFFSETS.get(tutor.tutor_timezone.lower(), 5)  # Default to Karachi
    tutor_tz = timezone(timedelta(hours=tz_offset))

    # Get sessions for this tutor
    all_sessions = session_functions.get_sessions_by_tutor(tutor.tutor_id)

    # Filter to next 24 hours
    now = datetime.now(timezone.utc)
    next_24h = now + timedelta(hours=24)

    upcoming = []
    for s in all_sessions:
        session_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
        if now <= session_start <= next_24h:
            upcoming.append(s)

    # Sort by start time
    upcoming.sort(key=lambda x: x.start)

    sync_ago = get_last_sync_ago()

    if not upcoming:
        await interaction.followup.send(
            f"Hi {user_mention}, there are no sessions scheduled for **{tutor_name}** in the next 24 hours.\n\n_Last sync: {sync_ago}_",
            ephemeral=True
        )
        return

    # Format response
    lines = [f"Hi {user_mention}, these are the sessions scheduled for **{tutor_name}**:\n"]
    for s in upcoming:
        session_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
        local_time = session_start.astimezone(tutor_tz)
        time_str = local_time.strftime("%I:%M %p")
        student_name = extract_student_name(s.summary) or "Unknown"
        lines.append(f"• **{student_name}** at {time_str}")

    lines.append(f"\n_Last sync: {sync_ago}_")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


if __name__ == "__main__":
    print("Fetching Discord token from Secrets Manager...")
    token = get_discord_token()

    print("Starting bot...")
    bot.run(token)
