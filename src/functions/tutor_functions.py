from datetime import datetime, timezone
from typing import Optional
from boto3.dynamodb.conditions import Key, Attr
from src.config import get_settings
from src.functions import dynamodb
from src.models.tutor_v2_model import TutorV2, TutorMetadataV2, TutorStatus, TutorV2Update, TutorMetadataV2Update, \
    TutorMetadataV2UpdateNameOnly

settings = get_settings()


def get_all_tutors(status_filter: Optional[TutorStatus] = None) -> list[TutorV2]:
    """Get all tutors, optionally filtered by status."""
    print(f"Entered get_all_tutors")
    if status_filter:
        items = dynamodb.scan_table(
            settings.tutors_table,
            FilterExpression=Attr("status").eq(status_filter.value),
        )
    else:
        items = dynamodb.scan_table(settings.tutors_table)
    return [TutorV2.from_dynamodb(item) for item in items]


def get_tutor(tutor_id: str) -> Optional[TutorV2]:
    """Get a tutor by tutor_id. Returns None if not found."""
    item = dynamodb.get_item(settings.tutors_table, {"tutorId": tutor_id})
    if item:
        return TutorV2.from_dynamodb(item)
    return None


def get_tutor_metadata(tutor_id: str) -> Optional[TutorMetadataV2]:
    """Get tutor metadata by tutor_id. Returns None if not found."""
    item = dynamodb.get_item(settings.tutors_metadata_table, {"tutorId": tutor_id})
    if item:
        return TutorMetadataV2.from_dynamodb(item)
    return None


def get_all_tutors_metadata() -> dict[str, TutorMetadataV2]:
    """Scan TutorsMetadataV2 and return a dict keyed by tutor_id."""
    items = dynamodb.scan_table(settings.tutors_metadata_table)
    return {item["tutorId"]: TutorMetadataV2.from_dynamodb(item) for item in items}


def get_tutor_by_name(name: str) -> Optional[TutorV2]:
    """Find tutor by name (case-insensitive partial match on first word)."""
    search_term = name.strip().lower()
    tutors = get_all_tutors(status_filter=TutorStatus.ACTIVE)
    for tutor in tutors:
        if tutor.tutor_name.lower() == search_term:
            return tutor
    return None


def resolve_tutor(identifier: str) -> Optional[TutorV2]:
    """Resolve tutor by ID or name. Tries ID first, then name lookup."""
    tutor = get_tutor(identifier)
    if tutor:
        return tutor
    return get_tutor_by_name(identifier)


def get_tutor_by_calendar_id(calendar_id: str) -> Optional[TutorV2]:
    """Find a tutor by their Google Calendar ID using GSI."""
    items = dynamodb.query_by_gsi(
        settings.tutors_table,
        "calendarId-index",
        Key("calendarId").eq(calendar_id),
    )
    if items:
        return TutorV2.from_dynamodb(items[0])
    return None


def get_tutor_by_discord_channel_id(channel_id: str) -> Optional[TutorV2]:
    """Find a tutor by their Discord channel ID."""
    items = dynamodb.scan_table(
        settings.tutors_table,
        FilterExpression=Attr("discordChannelId").eq(channel_id),
    )
    if items:
        return TutorV2.from_dynamodb(items[0])
    return None


def create_tutor(display_name: str, calendar_id: str, access_role: str) -> TutorV2:
    """Create a new tutor in TutorsV2 and an empty metadata entry in TutorsMetadataV2."""
    extracted_tutor_name = extract_tutor_name_from_display_name(display_name)
    tutor = TutorV2(
        display_name=display_name,
        tutor_name=extracted_tutor_name,
        calendar_id=calendar_id,
        access_role=access_role,
    )
    dynamodb.put_item(settings.tutors_table, tutor.to_dynamodb())
    meta = TutorMetadataV2(
        tutor_id=tutor.tutor_id,
        display_name=display_name,
        tutor_name=extracted_tutor_name,
    )
    dynamodb.put_item(settings.tutors_metadata_table, meta.to_dynamodb())
    return tutor


def set_tutor_discord_channel(tutor_id: str, channel_id: str, onboarding_msg_id: Optional[str] = None) -> bool:
    """Set discord channel fields on a tutor. Called once by the sync flow after channel creation."""
    existing = get_tutor(tutor_id)
    if not existing:
        return False
    update_data = {
        "discordChannelId": channel_id,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if onboarding_msg_id:
        update_data["discordOnboardingMessageId"] = onboarding_msg_id
    dynamodb.update_item(settings.tutors_table, {"tutorId": tutor_id}, update_data)
    return True


def set_tutor_feedback_channel(tutor_id: str, channel_id: str) -> bool:
    """Set the feedback Discord channel for a tutor."""
    existing = get_tutor(tutor_id)
    if not existing:
        return False
    dynamodb.update_item(
        settings.tutors_table,
        {"tutorId": tutor_id},
        {"feedbackDiscordChannelId": channel_id, "updatedAt": datetime.now(timezone.utc).isoformat()},
    )
    return True


def set_tutor_session_reminders_channel(tutor_id: str, channel_id: str) -> bool:
    """Set the session reminders Discord channel for a tutor."""
    existing = get_tutor(tutor_id)
    if not existing:
        return False
    dynamodb.update_item(
        settings.tutors_table,
        {"tutorId": tutor_id},
        {"sessionRemindersDiscordChannelId": channel_id, "updatedAt": datetime.now(timezone.utc).isoformat()},
    )
    return True


def set_tutor_dropbox_channel(tutor_id: str, channel_id: str) -> bool:
    """Set the dropbox notification Discord channel for a tutor."""
    existing = get_tutor(tutor_id)
    if not existing:
        return False
    dynamodb.update_item(
        settings.tutors_table,
        {"tutorId": tutor_id},
        {"dropboxDiscordChannelId": channel_id, "updatedAt": datetime.now(timezone.utc).isoformat()},
    )
    return True


def update_tutor(tutor_id: str, updates: TutorV2Update) -> Optional[TutorV2]:
    """Update operational tutor fields in TutorsV2 (display_name, tutor_name, status).
    Used when refreshing tutors from G Cal or when sync notices that the calendar name has changed"""
    existing = get_tutor(tutor_id)
    if not existing:
        return None

    update_data = {}
    if updates.display_name is not None:
        update_data["displayName"] = updates.display_name
    if updates.tutor_name is not None:
        update_data["tutorName"] = updates.tutor_name
    if updates.status is not None:
        update_data["status"] = updates.status.value

    if not update_data:
        return existing

    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    dynamodb.update_item(settings.tutors_table, {"tutorId": tutor_id}, update_data)
    return get_tutor(tutor_id)

def update_tutor_metadata_name(tutor_id: str, updates: TutorMetadataV2UpdateNameOnly) -> Optional[TutorMetadataV2]:
    """Update tutor name and display name metadata fields in TutorsMetadataV2.
    Used when refreshing tutors from G Cal or when sync notices that the calendar name has changed"""
    existing = get_tutor_metadata(tutor_id)
    if not existing:
        return None

    update_data = {}
    if updates.display_name is not None:
        update_data["displayName"] = updates.display_name
    if updates.tutor_name is not None:
        update_data["tutorName"] = updates.tutor_name

    if not update_data:
        return get_tutor_metadata(tutor_id)

    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    dynamodb.update_item(settings.tutors_metadata_table, {"tutorId": tutor_id}, update_data)
    return get_tutor_metadata(tutor_id)


def update_tutor_metadata(tutor_id: str, updates: TutorMetadataV2Update) -> Optional[TutorMetadataV2]:
    """Update tutor metadata fields in TutorsMetadataV2 (hourly_rate, email, phone, timezone)."""
    existing = get_tutor(tutor_id)
    if not existing:
        return None

    update_data = {}
    if updates.hourly_rate is not None:
        update_data["hourlyRate"] = updates.hourly_rate
    if updates.tutor_email is not None:
        update_data["tutorEmail"] = updates.tutor_email
    if updates.tutor_phone is not None:
        update_data["tutorPhone"] = updates.tutor_phone
    if updates.tutor_timezone is not None:
        update_data["tutorTimezone"] = updates.tutor_timezone

    if not update_data:
        return get_tutor_metadata(tutor_id)

    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    dynamodb.update_item(settings.tutors_metadata_table, {"tutorId": tutor_id}, update_data)
    return get_tutor_metadata(tutor_id)


def delete_tutor(tutor_id: str) -> bool:
    """Soft-delete: mark tutor as INACTIVE in TutorsV2."""
    existing = get_tutor(tutor_id)
    if not existing:
        return False
    dynamodb.update_item(
        settings.tutors_table,
        {"tutorId": tutor_id},
        {"status": TutorStatus.INACTIVE.value, "updatedAt": datetime.now(timezone.utc).isoformat()},
    )
    return True

def extract_tutor_name_from_display_name(display_name: str) -> str:
    """Takes input of calendar name like Jacob Tutoring Schedule and extracts Jacob."""
    return display_name.split()[0] if display_name and display_name.split() else ""