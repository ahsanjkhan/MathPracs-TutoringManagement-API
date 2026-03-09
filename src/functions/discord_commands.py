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
from src.models.session_model import SessionStatus
from src.models.student_v2_model import StudentMetadataV2Update, PaymentCollector, PaymentRecord, TransactionType
from src.models.tutor_v2_model import TutorStatus, TutorMetadataV2Update

from decimal import Decimal

logger = logging.getLogger(__name__)
settings = get_settings()


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        return float(o) if isinstance(o, Decimal) else super().default(o)

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
        send_followup(application_id, interaction_token, content="This channel is not linked to a tutor. Are you in your tutor channel?")
        return

    tutor_name = tutor.tutor_name
    tutor_meta = tutor_functions.get_tutor_metadata(tutor.tutor_id)

    if not tutor_meta:
        send_followup(application_id, interaction_token, content="Internal Error: TutorMetadata not found. Please reach out to Muaz or Ahsan")
        return

    tutor_tz = ZoneInfo(tutor_meta.tutor_timezone)

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
        send_followup(application_id, token, content="This channel is not linked to a tutor. Are you in your tutor channel?")
        return

    tutor_name = tutor.tutor_name
    tutor_meta = tutor_functions.get_tutor_metadata(tutor.tutor_id)

    if not tutor_meta:
        send_followup(application_id, token, content="Internal Error: TutorMetadata not found. Please reach out to Muaz or Ahsan")
        return

    hourly_rate = tutor_meta.hourly_rate

    central_tz = ZoneInfo("America/Chicago")
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
    central_tz = ZoneInfo("America/Chicago")
    now_central = datetime.now(central_tz)
    year = now_central.year
    month = now_central.month

    month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=central_tz)
    last_day = calendar.monthrange(year, month)[1]
    month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=central_tz)

    tutors = tutor_functions.get_all_tutors(status_filter=TutorStatus.ACTIVE)
    tutor_map = {t.tutor_id: t for t in tutors}
    meta_map = tutor_functions.get_all_tutors_metadata()

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

        tutor_meta = meta_map.get(tutor_id)
        hourly_rate = (tutor_meta.hourly_rate if tutor_meta else 0) or 0
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
    central_tz = ZoneInfo("America/Chicago")
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


# Students whose profit goes 100% to Muaz (not split with Ahsan)
_MUAZ_ONLY_STUDENTS = {"Felix", "Jay"}


def _is_demo(s) -> bool:
    return bool(re.search(r"demo", s.summary, re.IGNORECASE))


def _is_no_show(s) -> bool:
    return bool(re.search(r"\(no-show\)", s.summary, re.IGNORECASE))


def _compute_monthly_student_profits(month_start: datetime, month_end: datetime, central_tz) -> list[dict]:
    """
    Returns a list of per-student profit dicts for the given month.
    Revenue/cost per session type:
      - Regular:  revenue = hours × weekly_tier_rate,       cost = hours × tutor_rate
      - No-show:  revenue = hours × weekly_tier_rate × 0.5, cost = hours × tutor_rate
      - Demo:     revenue = $0,                             cost = hours × tutor_rate
    Split (Felix/Jay vs 50/50) is applied in _handle_profit, not here.
    """
    student_meta_map = {m.student_name: m for m in student_functions.get_all_student_metadata()}
    tutor_meta_map = tutor_functions.get_all_tutors_metadata()

    all_sessions = session_functions.get_all_sessions(status_filter=SessionStatus.COMPLETED)

    # Group completed month sessions by student
    student_sessions: dict = {}
    for s in all_sessions:
        s_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
        if not (month_start <= s_start.astimezone(central_tz) <= month_end):
            continue
        raw_name = extract_student_name(s.summary)
        if not raw_name:
            continue
        normalized = student_functions.normalize_student_name(raw_name)
        student_sessions.setdefault(normalized, []).append(s)

    results = []
    for student_name, sessions in sorted(student_sessions.items()):
        meta = student_meta_map.get(student_name)
        hourly_pricing = (meta.hourly_pricing if meta else None) or {}

        # All sessions count toward the weekly pricing tier (including no-shows and demos)
        weeks: dict = {}
        for s in sessions:
            s_start = s.start if s.start.tzinfo else s.start.replace(tzinfo=timezone.utc)
            local_date = s_start.astimezone(central_tz).date()
            days_since_sunday = (local_date.weekday() + 1) % 7
            week_key = local_date - timedelta(days=days_since_sunday)
            weeks.setdefault(week_key, []).append(s)

        # Build per-session lookup: session_id -> (student_rate, tutor_rate, hours)
        session_info: dict = {}
        for week_sessions in weeks.values():
            tier = str(min(len(week_sessions), 5))
            rate = float(hourly_pricing.get(tier, 0))
            for s in week_sessions:
                hours = (s.end - s.start).total_seconds() / 3600
                tutor_meta = tutor_meta_map.get(s.tutor_id)
                tutor_rate = float(tutor_meta.hourly_rate) if tutor_meta and tutor_meta.hourly_rate else 0.0
                session_info[s.session_id] = (rate, tutor_rate, hours)

        reg_rev = reg_cost = 0.0
        ns_rev  = ns_cost  = 0.0
        demo_cost = 0.0
        reg_count = ns_count = demo_count = 0

        for s in sessions:
            rate, tutor_rate, hours = session_info[s.session_id]
            if _is_demo(s):
                demo_cost  += hours * tutor_rate
                demo_count += 1
            elif _is_no_show(s):
                ns_rate = float(meta.no_show_custom_rate) if meta and meta.no_show_custom_rate is not None else rate * 0.5
                ns_rev  += hours * ns_rate
                ns_cost += hours * tutor_rate
                ns_count += 1
            else:
                reg_rev  += hours * rate
                reg_cost += hours * tutor_rate
                reg_count += 1

        results.append({
            "student_name": student_name,
            "reg_count": reg_count, "reg_rev": reg_rev, "reg_cost": reg_cost,
            "ns_count":  ns_count,  "ns_rev":  ns_rev,  "ns_cost":  ns_cost,
            "demo_count": demo_count, "demo_cost": demo_cost,
        })

    return results


def _handle_profit(recipient: str, interaction: dict, application_id: str) -> None:
    """
    Profit report for 'muaz' or 'ahsan'.

    Split rule is based solely on the student, not session type:
      - Felix / Jay → 100% Muaz, 0% Ahsan
      - All others  → 50/50

    Revenue/cost per session type:
      - Regular:  revenue = hours × weekly_tier_rate,       cost = hours × tutor_rate
      - No-show:  revenue = hours × weekly_tier_rate × 0.5, cost = hours × tutor_rate
      - Demo:     revenue = $0,                             cost = hours × tutor_rate
    """
    token = interaction.get("token")
    central_tz = ZoneInfo("America/Chicago")
    now_central = datetime.now(central_tz)
    year = now_central.year
    month = now_central.month

    month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=central_tz)
    last_day = calendar.monthrange(year, month)[1]
    month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=central_tz)

    rows = _compute_monthly_student_profits(month_start, month_end, central_tz)

    if not rows:
        send_followup(application_id, token, content=f"No completed sessions found for {now_central.strftime('%B %Y')}.")
        return

    total_share = 0.0
    lines = []

    for row in rows:
        name = row["student_name"]
        muaz_only = name in _MUAZ_ONLY_STUDENTS

        if muaz_only and recipient == "ahsan":
            continue

        total_rev  = row["reg_rev"]  + row["ns_rev"]
        total_cost = row["reg_cost"] + row["ns_cost"] + row["demo_cost"]
        gross_profit = total_rev - total_cost

        split = 1.0 if muaz_only else 0.5
        share = gross_profit * split
        total_share += share

        # Build session count summary
        parts = []
        if row["reg_count"]:
            parts.append(f"{row['reg_count']} reg")
        if row["ns_count"]:
            parts.append(f"{row['ns_count']} no-show")
        if row["demo_count"]:
            parts.append(f"{row['demo_count']} demo")
        session_summary = ", ".join(parts)

        split_label = "100%" if muaz_only else "50%"
        lines.append(
            f"• **{name}** — {session_summary} | "
            f"Rev: ${total_rev:.2f} | Cost: ${total_cost:.2f} | "
            f"Profit: ${gross_profit:.2f} → **Your share: ${share:.2f}** ({split_label})"
        )

    month_name = now_central.strftime("%B %Y")
    name_label = recipient.capitalize()

    if not lines:
        content = f"No sessions to report for {name_label} in {month_name}."
    else:
        breakdown = "\n".join(lines)
        content = (
            f"**Profit Report — {name_label} — {month_name}**\n\n"
            f"{breakdown}\n\n"
            f"**Net Profit ({name_label}): ${total_share:.2f}**\n\n"
            f"_Based on sessions from {month_start.strftime('%b %d')} to {month_end.strftime('%b %d')} (Central Time)_"
        )

    send_followup(application_id, token, content=content)


def handle_profit_muaz(interaction: dict, application_id: str) -> None:
    """Handle /profit_muaz command."""
    _handle_profit("muaz", interaction, application_id)


def handle_profit_ahsan(interaction: dict, application_id: str) -> None:
    """Handle /profit_ahsan command."""
    _handle_profit("ahsan", interaction, application_id)


def handle_help(interaction: dict) -> dict:
    """Handle /help command — lists all commands grouped by role."""
    tutor_commands = [
        ("my_sessions",      "View your scheduled sessions for the next 24 hours"),
        ("my_earnings",      "View your earnings for the current month"),
        ("student_links",    "Get meeting, upload, and file request links for a student"),
        ("refresh_commands", "Update your pinned commands message"),
    ]
    admin_commands = [
        ("ping_bot",             "Test if the bot is connected"),
        ("get_tutor",            "Get details for a tutor"),
        ("get_student",          "Get details for a student"),
        ("update_tutor",         "Update tutor details"),
        ("update_student",       "Update student details"),
        ("record_payment",       "Record a payment transaction for a student"),
        ("earnings_all_tutors",  "View total earnings across all tutors for the current month"),
        ("hours_tutored_chart",  "Bar chart of total hours tutored per month"),
        ("profit_muaz",          "Profit report for Muaz's students (revenue minus tutor cost)"),
        ("profit_ahsan",         "Profit report for Ahsan's students (revenue minus tutor cost)"),
        ("help",                 "Show all commands and descriptions"),
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

    tutor = tutor_functions.get_tutor_by_name(tutor_name)
    if not tutor:
        return {"type": 4, "data": {"content": f"Tutor '{tutor_name}' not found.", "flags": 64}}

    meta = tutor_functions.get_tutor_metadata(tutor.tutor_id)
    if not meta:
        return {"type": 4, "data": {"content": f"InternalError: Tutor '{tutor_name}' meta not found.", "flags": 64}}

    info = f"""**Tutor: {tutor.tutor_name}**
```
ID:           {tutor.tutor_id}
Display Name: {tutor.display_name}
Tutor Name:   {tutor.tutor_name}
Calendar ID:  {tutor.calendar_id}
Access Role:  {tutor.access_role}
Status:       {tutor.status.value}
DiscordChId:  {tutor.discord_channel_id}
DiscOnMsgId:  {tutor.discord_onboarding_message_id}
Created At:   {tutor.created_at.strftime('%Y-%m-%d %H:%M')}
Updated At:   {tutor.updated_at.strftime('%Y-%m-%d %H:%M')}
Hourly Rate:  ${meta.hourly_rate}
Email:        {meta.tutor_email}
Phone:        {meta.tutor_phone}
Timezone:     {meta.tutor_timezone}
UpdAt Meta:   {meta.updated_at}

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

    meta = student_functions.get_student_metadata(student_name)
    if not meta:
        return {"type": 4, "data": {"content": f"InternalError: Student '{student_name}' meta not found.", "flags": 64}}

    payment = meta.payment_collected_by if meta.payment_collected_by else "Not set"
    pricing = json.dumps(meta.hourly_pricing, indent=2, cls=_DecimalEncoder) if meta.hourly_pricing else "Not set"

    info = f"""**Student: {student.student_name}**
```
StudentName:  {student.student_name}
createdAt:    {student.created_at.strftime('%Y-%m-%d %H:%M')}
Doc ID:       {student.doc_id}
Doc URL:      {student.doc_url}
FileReqLink:  {student.file_request_link}
GMeetLink:    {student.google_meets_link}
hwUploadLink: {student.hw_upload_link}
balance:      ${student.balance:.2f}
phoneNums:    {meta.phone_numbers}
studentTZ:    {meta.student_timezone}
noShowCstRt:  {meta.no_show_custom_rate}
pmtCltBy:     {payment}
dscChnlRemId: {meta.discord_channel_reminder_id}
updtAtMeta:   {meta.updated_at}

Hourly Pricing:
{pricing}

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

    tutor = tutor_functions.get_tutor_by_name(tutor_name)
    if not tutor:
        return {"type": 4, "data": {"content": f"Tutor '{tutor_name}' not found.", "flags": 64}}

    # Prepopulate with metadata fields only (hourly_rate, email, phone, timezone)
    tutor_meta = tutor_functions.get_tutor_metadata(tutor.tutor_id)
    if not tutor_meta:
        return {"type": 4, "data": {"content": f"InternalError: Tutor '{tutor_name}' meta not found.", "flags": 64}}
    current_data = {}
    for field_name in TutorMetadataV2Update.model_fields:
        current_data[field_name] = getattr(tutor_meta, field_name, None)

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

    # Build current data from StudentMetadataV2Update fields (metadata)
    student_meta = student_functions.get_student_metadata(student.student_name)
    if not student_meta:
        return {"type": 4, "data": {"content": f"InternalError: Student '{student_name}' meta not found.", "flags": 64}}
    current_data = {}
    for field_name in StudentMetadataV2Update.model_fields:
        value = getattr(student_meta, field_name, None) if student_meta else None
        current_data[field_name] = value

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
                            "value": json.dumps(current_data, indent=2, cls=_DecimalEncoder),
                            "required": True,
                            "max_length": 2000
                        }
                    ]
                }
            ]
        }
    }


def handle_record_payment(interaction: dict) -> dict:
    """Handle /record_payment command."""
    options = interaction.get("data", {}).get("options", [])

    student_name = None
    amount = None
    action_by = None
    transaction_type = TransactionType.CREDIT

    for opt in options:
        name = opt.get("name")
        value = opt.get("value")
        if name == "student_name":
            student_name = value
        elif name == "amount":
            amount = abs(float(value))
        elif name == "action_by":
            action_by = value if value else None
            # Validate it's a valid enum value
            if action_by and action_by not in [e.value for e in PaymentCollector]:
                return {"type": 4, "data": {"content": f"Invalid action_by. Must be one of: {', '.join([e.value for e in PaymentCollector])}", "flags": 64}}

    if not all([student_name, amount is not None, action_by]):
        return {"type": 4, "data": {"content": "Please provide student_name, amount, and action_by.", "flags": 64}}

    # Verify student exists
    student = student_functions.get_student(student_name)
    if not student:
        return {"type": 4, "data": {"content": f"Student '{student_name}' not found.", "flags": 64}}

    normalized_student_name = student.student_name

    try:
        # Create payment record
        payment_record = PaymentRecord(
            student_name=normalized_student_name,
            amount=amount,
            action_by=action_by,
            transaction_type=transaction_type
        )

        # Convert to transaction and save
        transaction = payment_record.to_transaction()

        # Save to DynamoDB (assuming we have a transactions table)
        dynamodb.put_item(settings.transactions_table, transaction.to_dynamodb())

        # Update student balance
        new_balance = student.balance - amount

        student_functions.update_student_balance(student_name, new_balance)

        action_text = "payment"
        return {
            "type": 4,
            "data": {
                "content": f"Successfully recorded: **{student_name}** {action_text} of **${amount:.2f}** to {action_by}\nNew balance: **${new_balance:.2f}**",
                "flags": 64
            }
        }

    except Exception as e:
        return {"type": 4, "data": {"content": f"Error recording payment: {str(e)}", "flags": 64}}


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
        data = json.loads(json_value.replace('\r', ''))

        meta_update = TutorMetadataV2Update(
            hourly_rate=data.get("hourly_rate"),
            tutor_email=data.get("tutor_email"),
            tutor_phone=data.get("tutor_phone"),
            tutor_timezone=data.get("tutor_timezone"),
        )

        tutor_functions.update_tutor_metadata(tutor_id, meta_update)

        return {"type": 4, "data": {"content": "Successfully updated tutor!", "flags": 64}}

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
        data = json.loads(json_value.replace('\r', ''))

        payment_collected_by = data.get("payment_collected_by")
        # Validate it's a valid enum value
        if payment_collected_by and payment_collected_by not in [e.value for e in PaymentCollector]:
            return {"type": 4, "data": {"content": f"Invalid payment_collected_by. Must be one of: {', '.join([e.value for e in PaymentCollector])}", "flags": 64}}

        if payment_collected_by:
            meta_update = StudentMetadataV2Update(
                hourly_pricing=data.get("hourly_pricing"),
                phone_numbers=data.get("phone_numbers"),
                student_timezone=data.get("student_timezone"),
                no_show_custom_rate=data.get("no_show_custom_rate"),
                payment_collected_by=payment_collected_by,
            )
        else:
            meta_update = StudentMetadataV2Update(
                hourly_pricing=data.get("hourly_pricing"),
                phone_numbers=data.get("phone_numbers"),
                student_timezone=data.get("student_timezone"),
                no_show_custom_rate=data.get("no_show_custom_rate"),
            )

        student_functions.update_student_metadata(student_name, meta_update)

        return {"type": 4, "data": {"content": f"Successfully updated **{student_name}**!", "flags": 64}}

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
