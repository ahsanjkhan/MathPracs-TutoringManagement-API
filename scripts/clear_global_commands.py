"""
Clear all global Discord commands.
Run this if you see duplicate commands (global + guild).
"""
import sys
sys.path.insert(0, ".")

import json
import boto3
import httpx
from src.config import get_settings

settings = get_settings()


def clear_global_commands():
    secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
    response = secrets_client.get_secret_value(SecretId=settings.discord_credentials_secret_name)
    creds = json.loads(response["SecretString"])

    bot_token = creds.get("bot_token")
    app_id = creds.get("application_id")

    if not bot_token or not app_id:
        print("ERROR: bot_token or application_id not found")
        return

    print("Clearing all global commands...")

    r = httpx.put(
        f"https://discord.com/api/v10/applications/{app_id}/commands",
        headers={"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"},
        json=[],
        timeout=30.0
    )

    if r.status_code == 200:
        print("SUCCESS! Global commands cleared.")
        print("Only guild-specific commands will remain.")
    else:
        print(f"FAILED: {r.status_code}")
        print(r.text)


if __name__ == "__main__":
    clear_global_commands()
