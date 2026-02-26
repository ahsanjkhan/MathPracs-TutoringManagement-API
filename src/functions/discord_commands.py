"""
Discord slash command handlers for serverless HTTP interactions.
These replace the discord.py bot commands.
"""
import calendar
import json
import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

import httpx

from src.config import get_settings
from src.functions import (
    tutor_functions,
    session_functions,
    student_functions,
    sync_functions,
    dynamodb,
    discord_utils,
    groq_utils,
)
from src.functions.google_docs import extract_student_name
from src.models.tutor_model import TutorStatus, TutorUpdate
from src.models.student_model import StudentUpdate, PaymentCollector
from src.models.session_model import SessionStatus

logger = logging.getLogger(__name__)
settings = get_settings()

CALENDAR_LIST_SYNC_TYPE = "calendarList"

# Role names for permission checks
ROLE_ADMIN = "Admin"
ROLE_CHANNEL_ADMIN = "Channel Admin"
ROLE_TUTOR = "Tutor"


def has_role(member_roles: list, role_name: str) -> bool:
    """Check if user has a specific role by name."""
    return any(role.get("name") == role_name for role in member_roles)


def is_tutor_or_above(member_roles: list) -> bool:
    """Check if user has Tutor, Channel Admin, or Admin role."""
    return (
        has_role(member_roles, ROLE_TUTOR)
        or has_role(member_roles, ROLE_CHANNEL_ADMIN)
        or has_role(member_roles, ROLE_ADMIN)
    )


def is_admin(member_roles: list) -> bool:
    """Check if user has Admin role."""
    return has_role(member_roles, ROLE_ADMIN)


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


def send_followup(
    application_id: str,
    interaction_token: str,
    content: str = None,
    embed: dict = None,
    ephemeral: bool = True,
) -> bool:
    """Send a follow-up message after a deferred response. Pass content, embed, or both."""
    flags = 64 if ephemeral else 0
    payload: dict = {"flags": flags}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    try:
        response = httpx.post(
            f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}",
            json=payload,
            timeout=30.0,
        )
        return response.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Failed to send followup: {e}")
        return False


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

def handle_ping_bot(interaction: dict) -> dict:
    """Handle /ping_bot command."""
    member_roles = interaction.get("member", {}).get("roles", [])
    guild_roles = interaction.get("data", {}).get("resolved", {}).get("roles", {})

    # Build role list with names
    roles_with_names = []
    for role_id in member_roles:
        role_info = guild_roles.get(role_id, {"name": "Unknown"})
        roles_with_names.append(role_info)

    # For now, we'll check roles by ID from the guild
    # In production, roles need to be resolved via API or passed differently
    # For simplicity, allow the command for now

    sync_ago = get_last_sync_ago()

    return {
        "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
        "data": {
            "content": f"Pong! (Last sync: {sync_ago})",
            "flags": 64  # EPHEMERAL
        }
    }


def handle_sessions(interaction: dict, application_id: str) -> None:
    """Handle /sessions command — called as a deferred background task."""
    channel_id = interaction.get("channel_id")
    interaction_token = interaction.get("token")
    user_id = interaction.get("member", {}).get("user", {}).get("id")

    tutor = tutor_functions.get_tutor_by_discord_channel_id(channel_id)

    if not tutor:
        send_followup(application_id, interaction_token, content="This channel is not linked to a tutor.")
        return

    tutor_name = tutor.display_name.split()[0] if tutor.display_name else "Tutor"
    tutor_tz = ZoneInfo(tutor.tutor_timezone)

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
        content = f"Hi <@{user_id}>, there are no sessions scheduled for **{tutor_name}** in the next 24 hours.\n\n_Last sync: {sync_ago}_"
    else:
        lines = [f"Hi <@{user_id}>, these are the sessions scheduled for **{tutor_name}**:\n"]
        for s in upcoming:
            session_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
            local_time = session_start.astimezone(tutor_tz)
            time_str = local_time.strftime("%I:%M %p")
            student_name = extract_student_name(s.summary) or "Unknown"
            lines.append(f"- **{student_name}** at {time_str}")
        lines.append(f"\n_Last sync: {sync_ago}_")
        content = "\n".join(lines)

    send_followup(application_id, interaction_token, content=content)


def handle_earnings(interaction: dict, application_id: str) -> None:
    """Handle /earnings command — called as a deferred background task."""
    channel_id = interaction.get("channel_id")
    token = interaction.get("token")

    tutor = tutor_functions.get_tutor_by_discord_channel_id(channel_id)

    if not tutor:
        send_followup(application_id, token, content="This channel is not linked to a tutor.")
        return

    tutor_name = tutor.display_name.split()[0] if tutor.display_name else "Tutor"
    hourly_rate = tutor.hourly_rate or 0

    central_tz = timezone(timedelta(hours=-6))
    now_central = datetime.now(central_tz)
    year = now_central.year
    month = now_central.month

    month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=central_tz)
    last_day = calendar.monthrange(year, month)[1]
    month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=central_tz)

    all_sessions = session_functions.get_sessions_by_tutor(tutor.tutor_id)

    completed_sessions = []
    for s in all_sessions:
        if s.status.value != "completed":
            continue
        session_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
        if month_start <= session_start.astimezone(central_tz) <= month_end:
            completed_sessions.append(s)

    session_count = len(completed_sessions)
    total_hours = sum((s.end - s.start).total_seconds() / 3600 for s in completed_sessions)
    total_earnings = total_hours * hourly_rate
    month_name = now_central.strftime("%B %Y")

    content = f"""**Earnings Report for {tutor_name}**

**Month:** {month_name}
**Completed Sessions:** {session_count}
**Hours Tutored:** {total_hours:.1f}
**Total Earnings:** ${total_earnings:.2f}

_Based on sessions from {month_start.strftime('%b %d')} to {month_end.strftime('%b %d')} (Central Time)_"""

    send_followup(application_id, token, content=content)


def handle_links_student(interaction: dict, application_id: str) -> None:
    """Handle /links_student command — called as a deferred background task."""
    channel_id = interaction.get("channel_id")
    token = interaction.get("token")
    tutor = tutor_functions.get_tutor_by_discord_channel_id(channel_id)

    if not tutor:
        send_followup(application_id, token, content="This command can only be used in a tutor channel.")
        return

    options = interaction.get("data", {}).get("options", [])
    student_name = next((o["value"] for o in options if o["name"] == "name"), None)

    if not student_name:
        send_followup(application_id, token, content="Please provide a student name.")
        return

    student = student_functions.get_student(student_name)

    if not student:
        send_followup(application_id, token, content=f"No student found with name **{student_name}**.")
        return

    meets = student.google_meets_link
    upload = student.hw_upload_link
    request = student.file_request_link

    lines = [f"**Links for {student.student_name}**\n"]
    lines.append(f"📹 **Google Meet:** {f'<{meets}>' if meets else '_Not set_'}")
    lines.append(f"📁 **HW Folder:** {f'<{upload}>' if upload else '_Not set_'}")
    lines.append(f"📤 **Upload Link:** {f'<{request}>' if request else '_Not set_'}")

    send_followup(application_id, token, content="\n".join(lines))


def handle_total_earnings(interaction: dict, application_id: str) -> None:
    """Handle /tutor_monthly_payments command — called as a deferred background task."""
    central_tz = timezone(timedelta(hours=-6))
    now_central = datetime.now(central_tz)
    year = now_central.year
    month = now_central.month

    month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=central_tz)
    last_day = calendar.monthrange(year, month)[1]
    month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=central_tz)

    tutors = tutor_functions.get_all_tutors(status_filter=TutorStatus.ACTIVE)
    tutor_map = {t.tutor_id: t for t in tutors}

    # Single DynamoDB scan instead of one query per tutor
    all_sessions = session_functions.get_all_sessions(status_filter=SessionStatus.COMPLETED)

    # Group completed sessions by tutor for current month
    sessions_by_tutor: dict = {}
    for s in all_sessions:
        session_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
        if month_start <= session_start.astimezone(central_tz) <= month_end:
            sessions_by_tutor.setdefault(s.tutor_id, []).append(s)

    grand_total = 0.0
    total_demos = 0
    total_no_shows = 0
    lines = []

    for tutor_id, completed in sessions_by_tutor.items():
        tutor = tutor_map.get(tutor_id)
        if not tutor:
            continue

        demo_count    = sum(1 for s in completed if re.search(r"demo", s.summary, re.IGNORECASE))
        no_show_count = sum(1 for s in completed if re.search(r"\(no-show\)", s.summary, re.IGNORECASE))
        total_demos    += demo_count
        total_no_shows += no_show_count

        hourly_rate = tutor.hourly_rate or 0
        total_hours = sum((s.end - s.start).total_seconds() / 3600 for s in completed)
        earnings = total_hours * hourly_rate
        grand_total += earnings

        tutor_name = tutor.display_name.split()[0] if tutor.display_name else "Tutor"
        line = f"• **{tutor_name}** — {total_hours:.1f}h × ${hourly_rate:.2f} = **${earnings:.2f}**"
        if demo_count:
            line += f"\n  **Demo:** {demo_count} session{'s' if demo_count != 1 else ''}"
        if no_show_count:
            line += f"\n  **No show:** {no_show_count} session{'s' if no_show_count != 1 else ''}"
        lines.append(line)

    month_name = now_central.strftime("%B %Y")

    if not lines:
        content = f"No completed sessions found for {month_name}."
    else:
        breakdown = "\n\n".join(lines)
        content = f"""**Total Earnings Report — {month_name}**

{breakdown}

**Grand Total: ${grand_total:.2f}**
Demo sessions: {total_demos}
No show sessions: {total_no_shows}

_Based on sessions from {month_start.strftime('%b %d')} to {month_end.strftime('%b %d')} (Central Time)_"""

    send_followup(application_id, interaction.get("token"), content=content)


def handle_hours_tutored_chart(interaction: dict, application_id: str) -> None:
    """Handle /hours_tutored_chart command — called as a deferred background task."""
    central_tz = timezone(timedelta(hours=-6))
    now_central = datetime.now(central_tz)
    current_year = now_central.year
    current_month = now_central.month

    # Jan 2026 → current month
    CHART_START_YEAR = 2026
    CHART_START_MONTH = 1

    month_keys = []
    labels = []
    for m in range(CHART_START_MONTH, current_month + 1):
        month_keys.append((CHART_START_YEAR, m))
        labels.append(datetime(CHART_START_YEAR, m, 1).strftime("%b %Y"))

    all_sessions = session_functions.get_all_sessions(status_filter=SessionStatus.COMPLETED)

    hours_by_month: dict = {key: 0.0 for key in month_keys}
    for s in all_sessions:
        session_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
        local_start = session_start.astimezone(central_tz)
        key = (local_start.year, local_start.month)
        if key in hours_by_month:
            hours_by_month[key] += (s.end - s.start).total_seconds() / 3600

    data = [round(hours_by_month[key], 1) for key in month_keys]
    total_hours = sum(data)

    chart_config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": "Hours Tutored",
                "data": data,
                "backgroundColor": "rgba(99, 102, 241, 0.8)",
                "borderColor": "rgba(99, 102, 241, 1)",
                "borderWidth": 1,
            }],
        },
        "options": {
            "plugins": {
                "title": {"display": True, "text": "Total Hours Tutored per Month"},
                "legend": {"display": False},
            },
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "Hours"},
                }
            },
        },
    }

    chart_url = (
        "https://quickchart.io/chart"
        f"?c={urllib.parse.quote(json.dumps(chart_config))}"
        "&width=600&height=400&backgroundColor=white"
    )

    send_followup(
        application_id,
        interaction.get("token"),
        embed={
            "title": "Hours Tutored per Month (2026)",
            "description": (
                "\n".join(f"**{label}:** {hours}h" for label, hours in zip(labels, data))
                + f"\n\n**Total hours so far: {total_hours:.1f}h**"
            ),
            "image": {"url": chart_url},
            "color": 6366241,
        },
    )


def handle_help(interaction: dict) -> dict:
    """Handle /help command — lists all commands grouped by role."""
    tutor_commands = [
        ("sessions",         "View your scheduled sessions for the next 24 hours"),
        ("earnings",         "View your earnings for the current month"),
        ("links_student",    "Get meeting, upload, and file request links for a student"),
        ("refresh_commands", "Update your pinned commands message"),
    ]
    admin_commands = [
        ("ping_bot",               "Test if the bot is connected"),
        ("active_tutors",          "List all active tutors"),
        ("get_tutor",              "Get details for a tutor"),
        ("get_student",            "Get details for a student"),
        ("update_tutor",           "Update tutor details"),
        ("update_student",         "Update student details"),
        ("manual_sync",            "Manually trigger a calendar sync"),
        ("tutor_monthly_payments", "View total earnings across all tutors for the current month"),
        ("hours_tutored_chart",    "Bar chart of total hours tutored per month"),
        ("help",                   "Show all commands and descriptions"),
    ]

    tutor_lines  = "\n".join(f"`/{cmd}` — {desc}" for cmd, desc in tutor_commands)
    admin_lines  = "\n".join(f"`/{cmd}` — {desc}" for cmd, desc in admin_commands)

    content = (
        "**MathPracs Bot — All Commands**\n\n"
        f"**👤 Tutor Commands**\n{tutor_lines}\n\n"
        f"**🔧 Admin Commands**\n{admin_lines}"
    )

    return {"type": 4, "data": {"content": content, "flags": 64}}


def handle_refresh_commands(interaction: dict) -> dict:
    """Handle /refresh_commands command."""
    channel_id = interaction.get("channel_id")

    tutor = tutor_functions.get_tutor_by_discord_channel_id(channel_id)

    if not tutor:
        return {
            "type": 4,
            "data": {"content": "This channel is not linked to a tutor.", "flags": 64}
        }

    if not tutor.discord_onboarding_message_id:
        return {
            "type": 4,
            "data": {"content": "No onboarding message found to update.", "flags": 64}
        }

    success = discord_utils.update_onboarding_message(
        channel_id,
        tutor.discord_onboarding_message_id,
        tutor.display_name
    )

    if success:
        return {"type": 4, "data": {"content": "Pinned commands message updated!", "flags": 64}}
    else:
        return {"type": 4, "data": {"content": "Failed to update the pinned message.", "flags": 64}}


def handle_manual_sync(interaction: dict, application_id: str) -> dict:
    """Handle /manual_sync command - requires admin role."""
    interaction_token = interaction.get("token")

    # Return deferred response first
    # Note: In a real implementation, we'd use background tasks
    # For Lambda, we process synchronously but quickly

    try:
        cal_result = sync_functions.sync_calendar_list()
        events_result = sync_functions.sync_events_list("ALL")

        content = (
            f"**Sync completed!**\n"
            f"Calendars: {cal_result['created']} created, {cal_result['updated']} updated, {cal_result['deactivated']} deactivated\n"
            f"Events: {events_result['created']} created, {events_result['updated']} updated, {events_result['deleted']} deleted, {events_result['docs_created']} docs created"
        )
    except Exception as e:
        content = f"Sync failed: {str(e)}"

    return {"type": 4, "data": {"content": content, "flags": 64}}


def handle_active_tutors(interaction: dict) -> dict:
    """Handle /active_tutors command."""
    tutors = tutor_functions.get_all_tutors(status_filter=TutorStatus.ACTIVE)

    if not tutors:
        return {"type": 4, "data": {"content": "No active tutors found.", "flags": 64}}

    lines = ["**Active Tutors:**\n"]
    for t in tutors:
        channel_status = "linked" if t.discord_channel_id else "no channel"
        lines.append(f"- **{t.display_name}** ({channel_status})")

    return {"type": 4, "data": {"content": "\n".join(lines), "flags": 64}}


def handle_get_tutor(interaction: dict) -> dict:
    """Handle /get_tutor command."""
    options = interaction.get("data", {}).get("options", [])
    tutor_name = None
    for opt in options:
        if opt.get("name") == "tutor_name":
            tutor_name = opt.get("value")
            break

    if not tutor_name:
        return {"type": 4, "data": {"content": "Please provide a tutor name.", "flags": 64}}

    tutor = tutor_functions.resolve_tutor(tutor_name)
    if not tutor:
        return {"type": 4, "data": {"content": f"Tutor '{tutor_name}' not found.", "flags": 64}}

    info = f"""**Tutor: {tutor.display_name}**
```
ID:           {tutor.tutor_id}
Calendar ID:  {tutor.calendar_id}
Status:       {tutor.status.value}
Hourly Rate:  ${tutor.hourly_rate}
Timezone:     {tutor.tutor_timezone}
Email:        {tutor.tutor_email or 'Not set'}
Phone:        {tutor.tutor_phone or 'Not set'}
Discord Ch:   {tutor.discord_channel_id or 'Not set'}
Created:      {tutor.created_at.strftime('%Y-%m-%d %H:%M')}
Updated:      {tutor.updated_at.strftime('%Y-%m-%d %H:%M')}
```"""

    return {"type": 4, "data": {"content": info, "flags": 64}}


def handle_get_student(interaction: dict) -> dict:
    """Handle /get_student command."""
    options = interaction.get("data", {}).get("options", [])
    student_name = None
    for opt in options:
        if opt.get("name") == "student_name":
            student_name = opt.get("value")
            break

    if not student_name:
        return {"type": 4, "data": {"content": "Please provide a student name.", "flags": 64}}

    student = student_functions.get_student(student_name)
    if not student:
        return {"type": 4, "data": {"content": f"Student '{student_name}' not found.", "flags": 64}}

    payment = student.payment_collected_by.value if student.payment_collected_by else "Not set"

    info = f"""**Student: {student.student_name}**
```
Email:        {student.student_email or 'Not set'}
Timezone:     {student.student_timezone or 'Not set'}
Doc ID:       {student.doc_id}
Meet Link:    {student.google_meets_link or 'Not set'}
Payment By:   {payment}

Hourly Prices:
  Standard:   {student.hourly_price_standard or 'Not set'}
  Price 1:    {student.hourly_price_1 or 'Not set'}
  Price 2:    {student.hourly_price_2 or 'Not set'}
  Price 3:    {student.hourly_price_3 or 'Not set'}
  Price 4:    {student.hourly_price_4 or 'Not set'}
  Price 5:    {student.hourly_price_5 or 'Not set'}
  No Show:    {student.hourly_price_no_show or 'Not set'}

Created:      {student.created_at.strftime('%Y-%m-%d %H:%M')}
```"""

    return {"type": 4, "data": {"content": info, "flags": 64}}


def handle_update_tutor(interaction: dict) -> dict:
    """Handle /update_tutor command - returns a modal."""
    options = interaction.get("data", {}).get("options", [])
    tutor_name = None
    for opt in options:
        if opt.get("name") == "tutor_name":
            tutor_name = opt.get("value")
            break

    if not tutor_name:
        return {"type": 4, "data": {"content": "Please provide a tutor name.", "flags": 64}}

    tutor = tutor_functions.resolve_tutor(tutor_name)
    if not tutor:
        return {"type": 4, "data": {"content": f"Tutor '{tutor_name}' not found.", "flags": 64}}

    # Build current data for pre-population
    current_data = {
        "display_name": tutor.display_name,
        "status": tutor.status.value,
        "hourly_rate": tutor.hourly_rate,
        "tutor_email": tutor.tutor_email,
        "tutor_phone": tutor.tutor_phone,
        "tutor_timezone": tutor.tutor_timezone,
    }

    return {
        "type": 9,  # MODAL
        "data": {
            "custom_id": f"update_tutor_modal:{tutor.tutor_id}",
            "title": f"Update {tutor.display_name}",
            "components": [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 4,  # Text Input
                            "custom_id": "tutor_json",
                            "label": "Tutor Data (JSON)",
                            "style": 2,  # Paragraph
                            "placeholder": '{"hourly_rate": 15.0, "tutor_email": "email@example.com"}',
                            "value": json.dumps(current_data, indent=2),
                            "required": True,
                            "max_length": 2000
                        }
                    ]
                }
            ]
        }
    }


def handle_update_student(interaction: dict) -> dict:
    """Handle /update_student command - returns a modal."""
    options = interaction.get("data", {}).get("options", [])
    student_name = None
    for opt in options:
        if opt.get("name") == "student_name":
            student_name = opt.get("value")
            break

    if not student_name:
        return {"type": 4, "data": {"content": "Please provide a student name.", "flags": 64}}

    student = student_functions.get_student(student_name)
    if not student:
        return {"type": 4, "data": {"content": f"Student '{student_name}' not found.", "flags": 64}}

    # Build current data for pre-population
    current_data = {
        "student_email": student.student_email,
        "student_timezone": student.student_timezone,
        "hourly_price_standard": student.hourly_price_standard,
        "hourly_price_1": student.hourly_price_1,
        "hourly_price_2": student.hourly_price_2,
        "hourly_price_3": student.hourly_price_3,
        "hourly_price_4": student.hourly_price_4,
        "hourly_price_5": student.hourly_price_5,
        "hourly_price_no_show": student.hourly_price_no_show,
        "payment_collected_by": student.payment_collected_by.value if student.payment_collected_by else None,
    }

    return {
        "type": 9,  # MODAL
        "data": {
            "custom_id": f"update_student_modal:{student.student_name}",
            "title": f"Update {student.student_name}",
            "components": [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 4,  # Text Input
                            "custom_id": "student_json",
                            "label": "Student Data (JSON)",
                            "style": 2,  # Paragraph
                            "placeholder": '{"hourly_price_standard": 25.0}',
                            "value": json.dumps(current_data, indent=2),
                            "required": True,
                            "max_length": 2000
                        }
                    ]
                }
            ]
        }
    }


# =============================================================================
# MODAL SUBMIT HANDLERS
# =============================================================================

def handle_tutor_modal_submit(interaction: dict) -> dict:
    """Handle tutor update modal submission."""
    custom_id = interaction.get("data", {}).get("custom_id", "")
    tutor_id = custom_id.split(":")[-1] if ":" in custom_id else None

    if not tutor_id:
        return {"type": 4, "data": {"content": "Invalid modal submission.", "flags": 64}}

    # Extract JSON from modal components
    components = interaction.get("data", {}).get("components", [])
    json_value = None
    for row in components:
        for comp in row.get("components", []):
            if comp.get("custom_id") == "tutor_json":
                json_value = comp.get("value")
                break

    if not json_value:
        return {"type": 4, "data": {"content": "No data provided.", "flags": 64}}

    try:
        data = json.loads(json_value)

        # Handle status enum conversion
        if "status" in data and data["status"]:
            data["status"] = TutorStatus(data["status"])

        update = TutorUpdate(**data)
        result = tutor_functions.update_tutor(tutor_id, update)

        if result:
            return {"type": 4, "data": {"content": f"Successfully updated tutor!", "flags": 64}}
        else:
            return {"type": 4, "data": {"content": "Failed to update tutor.", "flags": 64}}

    except json.JSONDecodeError as e:
        return {"type": 4, "data": {"content": f"Invalid JSON: {e}", "flags": 64}}
    except Exception as e:
        return {"type": 4, "data": {"content": f"Error: {e}", "flags": 64}}


def handle_student_modal_submit(interaction: dict) -> dict:
    """Handle student update modal submission."""
    custom_id = interaction.get("data", {}).get("custom_id", "")
    student_name = custom_id.split(":")[-1] if ":" in custom_id else None

    if not student_name:
        return {"type": 4, "data": {"content": "Invalid modal submission.", "flags": 64}}

    # Extract JSON from modal components
    components = interaction.get("data", {}).get("components", [])
    json_value = None
    for row in components:
        for comp in row.get("components", []):
            if comp.get("custom_id") == "student_json":
                json_value = comp.get("value")
                break

    if not json_value:
        return {"type": 4, "data": {"content": "No data provided.", "flags": 64}}

    try:
        data = json.loads(json_value)

        # Handle payment_collected_by enum conversion
        if "payment_collected_by" in data and data["payment_collected_by"]:
            data["payment_collected_by"] = PaymentCollector(data["payment_collected_by"])

        update = StudentUpdate(**data)
        result = student_functions.update_student(student_name, update)

        if result:
            return {"type": 4, "data": {"content": f"Successfully updated **{student_name}**!", "flags": 64}}
        else:
            return {"type": 4, "data": {"content": "Failed to update student.", "flags": 64}}

    except json.JSONDecodeError as e:
        return {"type": 4, "data": {"content": f"Invalid JSON: {e}", "flags": 64}}
    except Exception as e:
        return {"type": 4, "data": {"content": f"Error: {e}", "flags": 64}}


# =============================================================================
# BUTTON HANDLERS
# =============================================================================

def handle_feedback_button(interaction: dict) -> dict:
    """Handle feedback button click - returns a modal."""
    message = interaction.get("message", {})
    embeds = message.get("embeds", [])

    if not embeds:
        return {"type": 4, "data": {"content": "Could not find session info.", "flags": 64}}

    embed = embeds[0]

    # Check if feedback was already submitted
    if embed.get("title") and "Feedback Submitted" in embed.get("title", ""):
        return {"type": 4, "data": {"content": "Feedback has already been submitted for this session.", "flags": 64}}

    # Extract info from embed fields
    fields = embed.get("fields", [])
    student_name = None
    tutor_name = None
    session_time = None

    for field in fields:
        name = field.get("name")
        value = field.get("value")
        if name == "Student":
            student_name = value
        elif name == "Tutor":
            tutor_name = value
        elif name == "Time":
            session_time = value

    if not all([student_name, tutor_name, session_time]):
        return {"type": 4, "data": {"content": "Missing session information.", "flags": 64}}

    # Return modal for feedback input
    return {
        "type": 9,  # MODAL
        "data": {
            "custom_id": f"feedback_modal:{student_name}:{tutor_name}:{session_time}",
            "title": "Session Feedback",
            "components": [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 4,  # Text Input
                            "custom_id": "feedback_input",
                            "label": "How did the session go?",
                            "style": 2,  # Paragraph
                            "placeholder": "Describe what was covered and how the student performed...",
                            "required": True,
                            "max_length": 250
                        }
                    ]
                }
            ]
        }
    }


def handle_feedback_modal_submit(interaction: dict) -> dict:
    """Handle feedback modal submission."""
    custom_id = interaction.get("data", {}).get("custom_id", "")
    parts = custom_id.split(":")

    if len(parts) < 4:
        return {"type": 4, "data": {"content": "Invalid feedback submission.", "flags": 64}}

    student_name = parts[1]
    tutor_name = parts[2]
    session_time = ":".join(parts[3:])  # Rejoin in case time has colons

    # Extract feedback from modal components
    components = interaction.get("data", {}).get("components", [])
    raw_feedback = None
    for row in components:
        for comp in row.get("components", []):
            if comp.get("custom_id") == "feedback_input":
                raw_feedback = comp.get("value")
                break

    if not raw_feedback:
        return {"type": 4, "data": {"content": "No feedback provided.", "flags": 64}}

    # Generate AI summary
    summary = groq_utils.generate_feedback_summary(raw_feedback, student_name)

    if not summary:
        return {"type": 4, "data": {"content": "Failed to generate summary. Please try again.", "flags": 64}}

    # Post to feedback channel
    success = discord_utils.post_feedback_to_channel(
        student_name=student_name,
        tutor_name=tutor_name,
        session_time=session_time,
        summary=summary
    )

    if success:
        # Update the original message to show feedback was submitted
        message = interaction.get("message", {})
        channel_id = message.get("channel_id")
        message_id = message.get("id")

        if channel_id and message_id:
            _update_feedback_message_to_completed(channel_id, message_id, student_name, session_time)

        return {"type": 4, "data": {"content": "Feedback submitted successfully!", "flags": 64}}
    else:
        return {"type": 4, "data": {"content": "Failed to post feedback. Please try again.", "flags": 64}}


def _update_feedback_message_to_completed(channel_id: str, message_id: str, student_name: str, session_time: str):
    """Update the original feedback request message to show it was completed."""
    creds = discord_utils.get_discord_credentials()
    bot_token = creds.get("bot_token")

    if not bot_token:
        return

    # Updated embed showing completion
    embed = {
        "title": "Feedback Submitted",
        "description": f"Thank you for providing feedback for **{student_name}**'s session.",
        "color": 3066993,  # Green
        "fields": [
            {"name": "Student", "value": student_name, "inline": True},
            {"name": "Time", "value": session_time, "inline": True},
        ]
    }

    try:
        httpx.patch(
            f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
            headers={
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json"
            },
            json={"embeds": [embed], "components": []},  # Remove button
            timeout=30.0
        )
    except Exception as e:
        logger.warning(f"Failed to update feedback message: {e}")
