import json
import logging
import os
import re
import boto3
import httpx
from src.config import get_settings
from src.models.student_v2_model import PaymentCollector

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

def get_discord_payment_channel_id(collector: str) -> str:
    """Get Discord credentials (bot_token, guild_id) from AWS Secrets Manager."""
    global _discord_credentials
    if _discord_credentials is None:
        secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
        response = secrets_client.get_secret_value(SecretId=settings.discord_credentials_secret_name)
        _discord_credentials = json.loads(response["SecretString"])

    if collector == PaymentCollector.MUAZ.value:
        return _discord_credentials.get("muaz_student_payment_channel_id", "")
    elif collector == PaymentCollector.AHSAN.value:
        return _discord_credentials.get("ahsan_student_payment_channel_id", "")
    else:
        return ""


def invoke_discord_task(command: str, interaction: dict, application_id: str) -> None:
    """
    Asynchronously invoke this same Lambda to process a slow Discord command.
    The caller returns DEFERRED (type 5) immediately; the second invocation
    does the real work and calls send_followup.
    """
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not function_name:
        logger.error("AWS_LAMBDA_FUNCTION_NAME not set — cannot defer Discord task")
        return
    try:
        boto3.client("lambda", region_name=settings.aws_region).invoke(
            FunctionName=function_name,
            InvocationType="Event",  # fire-and-forget
            Payload=json.dumps({
                "discord_task": {
                    "command": command,
                    "interaction": interaction,
                    "application_id": application_id,
                }
            }).encode(),
        )
    except Exception as e:
        logger.error(f"Failed to invoke async Discord task for '{command}': {e}")


def normalize_tutor_name(name: str) -> str:
    """Normalize a name for use in a Discord channel name (lowercase, alphanumeric and hyphens only)."""
    return re.sub(r'[^a-z0-9-]', '', name.strip().lower()) if name else "unknown"


def create_tutor_channel(tutor_name: str) -> str | None:
    """
    Create a private Discord channel for a tutor.
    Channel name format: tutor-<name> (e.g., tutor-mustafa)
    Expects tutor_name to already be a clean first name (e.g. "mustafa").
    Returns the channel ID if created, None if failed.
    """
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")
    guild_id = creds.get("guild_id")
    bot_id = creds.get("bot_id")  # Bot's application/user ID

    if not bot_token or not guild_id:
        logger.error("Discord bot_token or guild_id not configured in Secrets Manager")
        return None

    clean_name = normalize_tutor_name(tutor_name)
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
                "parent_id": "1475262651197296680",
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


def create_dropbox_channel(tutor_name: str) -> str | None:
    """
    Create a private Discord channel for Dropbox notifications for a tutor.
    Channel name format: dropbox-<name> (e.g., dropbox-mustafa)
    Returns the channel ID if created, None if failed.
    """
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")
    guild_id = creds.get("guild_id")
    bot_id = creds.get("bot_id")

    if not bot_token or not guild_id:
        logger.error("Discord bot_token or guild_id not configured in Secrets Manager")
        return None

    clean_name = normalize_tutor_name(tutor_name)
    channel_name = f"dropbox-{clean_name}"

    permission_overwrites = [
        {
            "id": guild_id,
            "type": 0,
            "deny": "1024"
        }
    ]

    if bot_id:
        permission_overwrites.append({
            "id": bot_id,
            "type": 1,
            "allow": "1024"
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
                "type": 0,
                "topic": f"Dropbox upload notifications for {tutor_name}",
                "parent_id": "1477999257318457436",
                "permission_overwrites": permission_overwrites
            },
            timeout=30.0
        )

        if response.status_code == 201:
            channel_id = response.json().get("id")
            logger.info(f"Created Dropbox Discord channel #{channel_name} (ID: {channel_id})")
            return channel_id
        else:
            logger.error(f"Failed to create Dropbox Discord channel: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error creating Dropbox Discord channel: {e}")
        return None


def create_feedback_channel(tutor_name: str) -> str | None:
    """
    Create a private Discord channel for session feedback for a tutor.
    Channel name format: feedback-<name> (e.g., feedback-mustafa)
    Returns the channel ID if created, None if failed.
    """
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")
    guild_id = creds.get("guild_id")
    bot_id = creds.get("bot_id")

    if not bot_token or not guild_id:
        logger.error("Discord bot_token or guild_id not configured in Secrets Manager")
        return None

    clean_name = normalize_tutor_name(tutor_name)
    channel_name = f"feedback-{clean_name}"

    permission_overwrites = [
        {
            "id": guild_id,
            "type": 0,
            "deny": "1024"
        }
    ]

    if bot_id:
        permission_overwrites.append({
            "id": bot_id,
            "type": 1,
            "allow": "1024"
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
                "type": 0,
                "topic": f"Session feedback forms for {tutor_name}",
                "parent_id": "1478000275708186694",
                "permission_overwrites": permission_overwrites
            },
            timeout=30.0
        )

        if response.status_code == 201:
            channel_id = response.json().get("id")
            logger.info(f"Created feedback Discord channel #{channel_name} (ID: {channel_id})")
            return channel_id
        else:
            logger.error(f"Failed to create feedback Discord channel: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error creating feedback Discord channel: {e}")
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


def get_onboarding_message_content(tutor_name: str) -> str:
    """Get the onboarding message content. Commands list is dynamically generated from TUTOR_COMMANDS."""
    TUTOR_COMMANDS = {
        "my_sessions": "View your scheduled sessions for the next 24 hours",
        "my_earnings": "View your earnings for the current month",
        "student_links": "Get meeting, upload, and file request links for a student",
        "refresh_commands": "Update the pinned message with latest commands",
    }

    first_name = tutor_name.split()[0] if tutor_name else "Tutor"

    # Build commands list dynamically
    commands_list = "\n".join([f"• `/{cmd}` - {desc}" for cmd, desc in TUTOR_COMMANDS.items()])

    return f"""👋 **Welcome, {first_name}!**

This is your private MathPracs tutor channel. Here you'll receive notifications and can manage your tutoring sessions.

**Available Commands:**
{commands_list}

**What to expect:**
• 📁 Notifications when students upload homework files
• 📅 Quick access to your upcoming sessions

Happy tutoring! 🎓"""


def send_onboarding_message(channel_id: str, tutor_name: str) -> str | None:
    """
    Send a welcome/onboarding message to a newly created tutor channel and pin it.
    Returns the message ID if successful, None otherwise.
    """
    message = get_onboarding_message_content(tutor_name)
    message_id = send_channel_message(channel_id, message)
    if message_id:
        pinned = pin_message(channel_id, message_id)
        if not pinned:
            logger.warning(f"Message sent but failed to pin in channel {channel_id}")
        return message_id
    return None


def edit_message(channel_id: str, message_id: str, new_content: str) -> bool:
    """Edit an existing message in a Discord channel."""
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")

    if not bot_token:
        logger.error("Discord bot_token not configured")
        return False

    try:
        response = httpx.patch(
            f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
            headers={
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json"
            },
            json={"content": new_content},
            timeout=30.0
        )

        if response.status_code == 200:
            logger.info(f"Edited message {message_id} in channel {channel_id}")
            return True
        else:
            logger.error(f"Failed to edit message: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error editing message: {e}")
        return False


def update_onboarding_message(channel_id: str, message_id: str, tutor_name: str) -> bool:
    """Update the onboarding message with the latest slash_commands list."""
    new_content = get_onboarding_message_content(tutor_name)
    return edit_message(channel_id, message_id, new_content)


def send_feedback_request(
    channel_id: str,
    session_id: str,
    student_name: str,
    tutor_name: str,
    session_time: str
) -> bool:
    """
    Send a feedback request message with a button to the tutor's channel.
    Uses Discord embeds and components (button).
    """
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")

    if not bot_token:
        logger.error("Discord bot_token not configured")
        return False

    # Build embed with session info
    embed = {
        "title": "📝 Session Completed!",
        "description": f"Please provide feedback for **{student_name}**'s session.",
        "color": 5814783,  # Blue color
        "fields": [
            {"name": "Student", "value": student_name, "inline": True},
            {"name": "Tutor", "value": tutor_name, "inline": True},
            {"name": "Time", "value": session_time, "inline": True},
        ]
    }

    # Button component
    components = [
        {
            "type": 1,  # Action row
            "components": [
                {
                    "type": 2,  # Button
                    "style": 1,  # Primary (blue)
                    "label": "Leave Feedback",
                    "emoji": {"name": "📝"},
                    "custom_id": "feedback_button"
                }
            ]
        }
    ]

    try:
        response = httpx.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json"
            },
            json={
                "embeds": [embed],
                "components": components
            },
            timeout=30.0
        )

        if response.status_code == 200:
            logger.info(f"Sent feedback request for session {session_id} to channel {channel_id}")
            return True
        else:
            logger.error(f"Failed to send feedback request: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error sending feedback request: {e}")
        return False


def post_feedback_to_channel(
    student_name: str,
    tutor_name: str,
    session_time: str,
    summary: str
) -> bool:
    """
    Post the AI-generated feedback summary to the session feedback channel.
    """
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")
    feedback_channel_id = creds.get("session_feedback_channel_id")

    if not bot_token:
        logger.error("Discord bot_token not configured")
        return False

    if not feedback_channel_id:
        logger.error("session_feedback_channel_id not configured in Discord credentials")
        return False

    embed = {
        "title": "📚 Session Feedback",
        "color": 3066993,  # Green color
        "fields": [
            {"name": "Tutor", "value": tutor_name, "inline": True},
            {"name": "Student", "value": student_name, "inline": True},
            {"name": "Time", "value": session_time, "inline": True},
            {"name": "Summary", "value": summary, "inline": False},
        ]
    }

    try:
        response = httpx.post(
            f"https://discord.com/api/v10/channels/{feedback_channel_id}/messages",
            headers={
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json"
            },
            json={"embeds": [embed]},
            timeout=30.0
        )

        if response.status_code == 200:
            logger.info(f"Posted feedback for {student_name} to feedback channel")
            return True
        else:
            logger.error(f"Failed to post feedback: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error posting feedback: {e}")
        return False
