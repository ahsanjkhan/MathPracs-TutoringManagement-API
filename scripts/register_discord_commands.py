"""
Register Discord slash commands with the Discord API.
Run this script once whenever you add or update slash commands.

Usage:
    python -m scripts.register_discord_commands
"""
import json
import sys
import boto3
import httpx
from src.config import get_settings

settings = get_settings()

ADMIN_ONLY = {"default_member_permissions": "0"}

COMMANDS = [
    # ── Tutor commands ──────────────────────────────────────────────────────
    {
        "name": "my_sessions",
        "description": "View your scheduled sessions for the next 24 hours",
    },
    {
        "name": "my_earnings",
        "description": "View your earnings for the current month",
    },
    {
        "name": "student_links",
        "description": "Get meeting, homework folder and upload links for a student",
        "options": [
            {
                "name": "name",
                "description": "Student name",
                "type": 3,  # STRING
                "required": True,
            }
        ],
    },
    {
        "name": "refresh_commands",
        "description": "Update the pinned message with latest commands",
    },
    {
        "name": "get_archived_files",
        "description": "Get download links for a student's archived files from Cloud",
        "options": [
            {
                "name": "student_name",
                "description": "Student name",
                "type": 3,  # STRING
                "required": True,
            }
        ],
    },
    # ── Admin commands ───────────────────────────────────────────────────────
    {
        "name": "ping_bot",
        "description": "Test if the bot is connected",
        **ADMIN_ONLY,
    },
    {
        "name": "get_tutor",
        "description": "Get details for a tutor",
        "options": [
            {
                "name": "tutor_name",
                "description": "Tutor name or ID",
                "type": 3,  # STRING
                "required": True,
            }
        ],
        **ADMIN_ONLY,
    },
    {
        "name": "get_student",
        "description": "Get details for a student",
        "options": [
            {
                "name": "student_name",
                "description": "Student name",
                "type": 3,  # STRING
                "required": True,
            }
        ],
        **ADMIN_ONLY,
    },
    {
        "name": "update_tutor",
        "description": "Update tutor details",
        "options": [
            {
                "name": "tutor_name",
                "description": "Tutor name or ID",
                "type": 3,  # STRING
                "required": True,
            }
        ],
        **ADMIN_ONLY,
    },
    {
        "name": "update_student",
        "description": "Update student details",
        "options": [
            {
                "name": "student_name",
                "description": "Student name",
                "type": 3,  # STRING
                "required": True,
            }
        ],
        **ADMIN_ONLY,
    },
    {
        "name": "earnings_all_tutors",
        "description": "View total earnings across all tutors for the current month",
        **ADMIN_ONLY,
    },
    {
        "name": "hours_tutored_chart",
        "description": "Bar chart of total hours tutored per month (2026)",
        **ADMIN_ONLY,
    },
    {
        "name": "record_payment",
        "description": "Record a payment transaction for a student",
        "options": [
            {
                "name": "student_name",
                "description": "Student name",
                "type": 3,  # STRING
                "required": True,
            },
            {
                "name": "amount",
                "description": "Payment amount (positive number)",
                "type": 10,  # NUMBER
                "required": True,
            },
            {
                "name": "action_by",
                "description": "Who collected the payment (muaz, ahsan, business)",
                "type": 3,  # STRING
                "required": True,
            },
        ],
        **ADMIN_ONLY,
    },
    {
        "name": "profit_muaz",
        "description": "Profit report for Muaz for the current month",
        **ADMIN_ONLY,
    },
    {
        "name": "profit_ahsan",
        "description": "Profit report for Ahsan for the current month",
        **ADMIN_ONLY,
    },
    {
        "name": "help",
        "description": "Show all commands and their descriptions",
        **ADMIN_ONLY,
    },
]


def get_discord_credentials() -> dict:
    secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
    response = secrets_client.get_secret_value(SecretId=settings.discord_credentials_secret_name)
    return json.loads(response["SecretString"])


def register_commands():
    creds = get_discord_credentials()
    bot_token = creds.get("bot_token")
    application_id = creds.get("application_id") or creds.get("bot_id")
    guild_id = creds.get("guild_id")

    if not bot_token or not application_id or not guild_id:
        print("ERROR: bot_token, application_id/bot_id, or guild_id not found in Secrets Manager")
        sys.exit(1)

    url = f"https://discord.com/api/v10/applications/{application_id}/guilds/{guild_id}/commands"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    response = httpx.put(url, headers=headers, json=COMMANDS, timeout=30.0)

    if response.status_code == 200:
        registered = response.json()
        print(f"Successfully registered {len(registered)} commands:")
        for cmd in registered:
            print(f"  /{cmd['name']}")
    else:
        print(f"ERROR: {response.status_code} - {response.text}")
        sys.exit(1)


if __name__ == "__main__":
    register_commands()
