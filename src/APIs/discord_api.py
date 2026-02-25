"""
Discord Interactions endpoint for serverless slash commands.
Handles signature verification and routes interactions to handlers.
"""
import logging
from fastapi import APIRouter, Request, HTTPException

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

from src.functions import discord_utils, discord_commands

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discord", tags=["Discord"])

# Discord interaction types
PING = 1
APPLICATION_COMMAND = 2
MESSAGE_COMPONENT = 3
APPLICATION_COMMAND_AUTOCOMPLETE = 4
MODAL_SUBMIT = 5


def verify_signature(body: bytes, signature: str, timestamp: str, public_key: str) -> bool:
    """Verify Discord request signature using Ed25519."""
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
        key.verify(bytes.fromhex(signature), timestamp.encode() + body)
        return True
    except InvalidSignature:
        return False
    except Exception as e:
        logger.warning(f"Signature verification failed: {e}")
        return False


DEFERRED = {"type": 5, "data": {"flags": 64}}


@router.post("/interactions")
async def discord_interactions(request: Request):
    """
    Handle all Discord interactions (slash commands, buttons, modals).
    Discord sends POST requests here when users interact with the bot.
    """
    # Get signature headers
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")

    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing signature headers")

    # Get raw body for signature verification
    body = await request.body()

    # Get public key from Discord credentials
    creds = discord_utils.get_discord_credentials()
    public_key = creds.get("public_key")

    if not public_key:
        logger.error("Discord public_key not configured in Secrets Manager")
        raise HTTPException(status_code=500, detail="Bot not configured")

    # Verify signature
    if not verify_signature(body, signature, timestamp, public_key):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse interaction
    interaction = await request.json()
    interaction_type = interaction.get("type")

    logger.info(f"Discord interaction received: type={interaction_type}")

    # Handle PING (required for Discord to verify endpoint)
    if interaction_type == PING:
        return {"type": 1}  # PONG

    # Get application ID for follow-ups
    application_id = interaction.get("application_id")

    # Handle slash commands
    if interaction_type == APPLICATION_COMMAND:
        command_name = interaction.get("data", {}).get("name")
        logger.info(f"Slash command: {command_name}")

        if command_name == "help":
            return discord_commands.handle_help(interaction)
        elif command_name == "ping_bot":
            return discord_commands.handle_ping_bot(interaction)
        elif command_name == "sessions":
            discord_utils.invoke_discord_task("sessions", interaction, application_id)
            return DEFERRED
        elif command_name == "earnings":
            discord_utils.invoke_discord_task("earnings", interaction, application_id)
            return DEFERRED
        elif command_name == "refresh_commands":
            return discord_commands.handle_refresh_commands(interaction)
        elif command_name == "manual_sync":
            return discord_commands.handle_manual_sync(interaction, application_id)
        elif command_name == "active_tutors":
            return discord_commands.handle_active_tutors(interaction)
        elif command_name == "get_tutor":
            return discord_commands.handle_get_tutor(interaction)
        elif command_name == "get_student":
            return discord_commands.handle_get_student(interaction)
        elif command_name == "update_tutor":
            return discord_commands.handle_update_tutor(interaction)
        elif command_name == "update_student":
            return discord_commands.handle_update_student(interaction)
        elif command_name == "tutor_monthly_payments":
            discord_utils.invoke_discord_task("tutor_monthly_payments", interaction, application_id)
            return DEFERRED
        elif command_name == "links_student":
            discord_utils.invoke_discord_task("links_student", interaction, application_id)
            return DEFERRED
        elif command_name == "hours_tutored_chart":
            discord_utils.invoke_discord_task("hours_tutored_chart", interaction, application_id)
            return DEFERRED
        else:
            return {
                "type": 4,
                "data": {"content": f"Unknown command: {command_name}", "flags": 64}
            }

    # Handle button clicks
    if interaction_type == MESSAGE_COMPONENT:
        custom_id = interaction.get("data", {}).get("custom_id")
        logger.info(f"Button click: {custom_id}")

        if custom_id == "feedback_button":
            return discord_commands.handle_feedback_button(interaction)
        else:
            return {
                "type": 4,
                "data": {"content": "Unknown button.", "flags": 64}
            }

    # Handle modal submissions
    if interaction_type == MODAL_SUBMIT:
        custom_id = interaction.get("data", {}).get("custom_id", "")
        logger.info(f"Modal submit: {custom_id}")

        if custom_id.startswith("update_tutor_modal:"):
            return discord_commands.handle_tutor_modal_submit(interaction)
        elif custom_id.startswith("update_student_modal:"):
            return discord_commands.handle_student_modal_submit(interaction)
        elif custom_id.startswith("feedback_modal:"):
            return discord_commands.handle_feedback_modal_submit(interaction)
        else:
            return {
                "type": 4,
                "data": {"content": "Unknown modal.", "flags": 64}
            }

    # Unknown interaction type
    logger.warning(f"Unknown interaction type: {interaction_type}")
    return {"type": 1}
