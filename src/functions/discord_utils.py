import json
import logging
import re
import boto3
import httpx
from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_discord_credentials = None


def get_discord_credentials() -> dict:
    """Get Discord credentials (bot_token, guild_id) from AWS Secrets Manager."""
    global _discord_credentials
    if _discord_credentials is None:
        secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
        response = secrets_client.get_secret_value(SecretId=settings.discord_credentials_secret_name)
        _discord_credentials = json.loads(response["SecretString"])
    return _discord_credentials


def create_tutor_channel(tutor_name: str) -> str | None:
    """
    Create a private Discord channel for a tutor.
    Channel name format: tutor-<name> (e.g., tutor-mustafa)
    Returns the channel ID if created, None if failed.
    """
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")
    guild_id = creds.get("guild_id")
    bot_id = creds.get("bot_id")  # Bot's application/user ID

    if not bot_token or not guild_id:
        logger.error("Discord bot_token or guild_id not configured in Secrets Manager")
        return None

    # Clean tutor name for channel (lowercase, no spaces, alphanumeric only)
    # e.g., "Mustafa Tutoring Schedule" -> "mustafa"
    clean_name = tutor_name.lower().split()[0] if tutor_name else "unknown"
    clean_name = re.sub(r'[^a-z0-9-]', '', clean_name)
    channel_name = f"tutor-{clean_name}"

    # Build permission overwrites
    permission_overwrites = [
        {
            # @everyone role - deny view
            "id": guild_id,
            "type": 0,  # role
            "deny": "1024"  # VIEW_CHANNEL permission
        }
    ]

    if bot_id:
        permission_overwrites.append({
            # Bot user - allow all
            "id": bot_id,
            "type": 1,  # user
            "allow": "1024"  # VIEW_CHANNEL permission
        })

    try:
        response = httpx.post(
            f"https://discord.com/api/v10/guilds/{guild_id}/channels",
            headers={
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json"
            },
            json={
                "name": channel_name,
                "type": 0,  # Text channel
                "topic": f"Private channel for {tutor_name}",
                "permission_overwrites": permission_overwrites
            },
            timeout=30.0
        )

        if response.status_code == 201:
            channel_data = response.json()
            channel_id = channel_data.get("id")
            logger.info(f"Created Discord channel #{channel_name} (ID: {channel_id})")
            return channel_id
        else:
            logger.error(f"Failed to create Discord channel: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error creating Discord channel: {e}")
        return None


def send_channel_message(channel_id: str, message: str) -> str | None:
    """
    Send a message to a Discord channel.
    Returns the message ID if sent successfully, None otherwise.
    """
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")

    if not bot_token:
        logger.error("Discord bot_token not configured")
        return None

    try:
        response = httpx.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json"
            },
            json={"content": message},
            timeout=30.0
        )

        if response.status_code == 200:
            message_data = response.json()
            message_id = message_data.get("id")
            logger.info(f"Sent message to channel {channel_id}")
            return message_id
        else:
            logger.error(f"Failed to send Discord message: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error sending Discord message: {e}")
        return None


def pin_message(channel_id: str, message_id: str) -> bool:
    """Pin a message in a Discord channel."""
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")

    if not bot_token:
        logger.error("Discord bot_token not configured")
        return False

    try:
        response = httpx.put(
            f"https://discord.com/api/v10/channels/{channel_id}/pins/{message_id}",
            headers={"Authorization": f"Bot {bot_token}"},
            timeout=30.0
        )

        if response.status_code == 204:
            logger.info(f"Pinned message {message_id} in channel {channel_id}")
            return True
        else:
            logger.error(f"Failed to pin message: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error pinning message: {e}")
        return False


def notify_homework_upload(student_name: str, file_name: str, tutor_discord_channel_id: str) -> bool:
    """
    Send a notification to the tutor's Discord channel about a homework upload.
    """
    message = f"📁 **New file uploaded!**\nStudent: **{student_name}**\nFile: `{file_name}`"
    return send_channel_message(tutor_discord_channel_id, message) is not None


def send_onboarding_message(channel_id: str, tutor_name: str) -> bool:
    """
    Send a welcome/onboarding message to a newly created tutor channel and pin it.
    """
    # Extract first name
    first_name = tutor_name.split()[0] if tutor_name else "Tutor"

    message = f"""👋 **Welcome, {first_name}!**

This is your private MathPracs tutor channel. Here you'll receive notifications and can manage your tutoring sessions.

**Available Commands:**
• `/sessions` - View your scheduled sessions for the next 24 hours
• `/ping_bot` - Test if the bot is connected

**What to expect:**
• 📁 Notifications when students upload homework files
• 📅 Quick access to your upcoming sessions

Happy tutoring! 🎓"""

    message_id = send_channel_message(channel_id, message)
    if message_id:
        pin_message(channel_id, message_id)
        return True
    return False
