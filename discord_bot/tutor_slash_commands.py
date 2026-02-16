from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from discord.ext import commands
from src.functions import tutor_functions, session_functions, dynamodb, discord_utils
from src.functions.google_docs import extract_student_name
from src.config import get_settings

settings = get_settings()

CALENDAR_LIST_SYNC_TYPE = "calendarList"

ROLE_ADMIN = "Admin"
ROLE_CHANNEL_ADMIN = "Channel Admin"
ROLE_TUTOR = "Tutor"


def has_role(interaction: discord.Interaction, role_name: str) -> bool:
    """Check if user has a specific role."""
    if not interaction.guild:
        return False
    return any(role.name == role_name for role in interaction.user.roles)


def is_tutor_or_above(interaction: discord.Interaction) -> bool:
    """Check if user has Tutor, Channel Admin, or Admin role."""
    return has_role(interaction, ROLE_TUTOR) or has_role(interaction, ROLE_CHANNEL_ADMIN) or has_role(interaction,
                                                                                                      ROLE_ADMIN)


def is_channel_admin_or_above(interaction: discord.Interaction) -> bool:
    """Check if user has Channel Admin or Admin role."""
    return has_role(interaction, ROLE_CHANNEL_ADMIN) or has_role(interaction, ROLE_ADMIN)


def is_admin(interaction: discord.Interaction) -> bool:
    """Check if user has Admin role."""
    return has_role(interaction, ROLE_ADMIN)


TIMEZONE_OFFSETS = {
    "karachi": 5,
    "lahore": 5,
    "islamabad": 5,
    "berlin": 1,
}

# Tutor commands - add new commands here and they'll auto-appear in onboarding message
TUTOR_COMMANDS = {
    "sessions": "View your scheduled sessions for the next 24 hours",
    "refresh_commands": "Update the pinned message with latest commands",
    "ping_bot": "Test if the bot is connected",
}


def get_last_sync_ago() -> str:
    """Get how long ago the last sync happened."""
    try:
        item = dynamodb.get_item(settings.calendar_sync_table, {"syncType": CALENDAR_LIST_SYNC_TYPE})
        if item and item.get("lastSyncAt"):
            last_sync = datetime.fromisoformat(item["lastSyncAt"])
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = now - last_sync

            minutes = int(delta.total_seconds() / 60)
            if minutes < 1:
                return "just now"
            elif minutes < 60:
                return f"{minutes} min ago"
            elif minutes < 1440:
                hours = minutes // 60
                return f"{hours} hr ago"
            else:
                days = minutes // 1440
                return f"{days} day{'s' if days > 1 else ''} ago"
        return "never"
    except Exception:
        return "unknown"


class TutorCommands(commands.Cog):
    """Base commands available to tutors."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping_bot", description="Test if MathPracs Tutoring Bot is connected")
    async def ping(self, interaction: discord.Interaction):
        if not is_tutor_or_above(interaction):
            await interaction.response.send_message("You need the Tutor role to use this command.", ephemeral=True)
            return
        sync_ago = get_last_sync_ago()
        await interaction.response.send_message(f"Pong! (Last sync: {sync_ago})", ephemeral=True)

    @app_commands.command(name="sessions", description="View your scheduled sessions for the next 24 hours")
    async def sessions(self, interaction: discord.Interaction):
        if not is_tutor_or_above(interaction):
            await interaction.response.send_message("You need the Tutor role to use this command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        channel_id = str(interaction.channel_id)
        tutor = tutor_functions.get_tutor_by_discord_channel_id(channel_id)
        if not tutor:
            await interaction.followup.send("This channel is not linked to a tutor.", ephemeral=True)
            return

        tutor_name = tutor.display_name.split()[0] if tutor.display_name else "Tutor"
        user_mention = interaction.user.mention

        tz_offset = TIMEZONE_OFFSETS.get(tutor.tutor_timezone.lower(), 5)
        tutor_tz = timezone(timedelta(hours=tz_offset))

        all_sessions = session_functions.get_sessions_by_tutor(tutor.tutor_id)

        now = datetime.now(timezone.utc)
        next_24h = now + timedelta(hours=24)

        upcoming = []
        for s in all_sessions:
            session_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
            if now <= session_start <= next_24h:
                upcoming.append(s)

        upcoming.sort(key=lambda x: x.start)
        sync_ago = get_last_sync_ago()

        if not upcoming:
            await interaction.followup.send(
                f"Hi {user_mention}, there are no sessions scheduled for **{tutor_name}** in the next 24 hours.\n\n_Last sync: {sync_ago}_",
                ephemeral=True
            )
            return

        lines = [f"Hi {user_mention}, these are the sessions scheduled for **{tutor_name}**:\n"]
        for s in upcoming:
            session_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
            local_time = session_start.astimezone(tutor_tz)
            time_str = local_time.strftime("%I:%M %p")
            student_name = extract_student_name(s.summary) or "Unknown"
            lines.append(f"• **{student_name}** at {time_str}")

        lines.append(f"\n_Last sync: {sync_ago}_")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="refresh_commands",
                          description="Update the pinned onboarding message with latest commands")
    async def refresh_commands(self, interaction: discord.Interaction):
        if not is_tutor_or_above(interaction):
            await interaction.response.send_message("You need the Tutor role to use this command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        channel_id = str(interaction.channel_id)
        tutor = tutor_functions.get_tutor_by_discord_channel_id(channel_id)

        if not tutor:
            await interaction.followup.send("This channel is not linked to a tutor.", ephemeral=True)
            return

        if not tutor.discord_onboarding_message_id:
            await interaction.followup.send("No onboarding message found to update.", ephemeral=True)
            return

        success = discord_utils.update_onboarding_message(
            channel_id,
            tutor.discord_onboarding_message_id,
            tutor.display_name
        )

        if success:
            await interaction.followup.send("Pinned commands message updated!", ephemeral=True)
        else:
            await interaction.followup.send("Failed to update the pinned message.", ephemeral=True)
