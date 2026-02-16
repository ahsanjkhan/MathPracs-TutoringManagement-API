from datetime import datetime
from typing import Optional
from boto3.dynamodb.conditions import Key, Attr
from src.config import get_settings
from src.functions import dynamodb
from src.models.tutor_model import Tutor, TutorStatus, TutorUpdate

settings = get_settings()


def get_all_tutors(status_filter: Optional[TutorStatus] = None) -> list[Tutor]:
    """Get all tutors, optionally filtered by status."""
    if status_filter:
        items = dynamodb.scan_table(
            settings.tutors_table,
            FilterExpression=Attr("status").eq(status_filter.value),
        )
    else:
        items = dynamodb.scan_table(settings.tutors_table)
    return [Tutor.from_dynamodb(item) for item in items]


def get_tutor(tutor_id: str) -> Optional[Tutor]:
    """Get a tutor by tutor_id. Returns None if not found."""
    item = dynamodb.get_item(settings.tutors_table, {"tutorId": tutor_id})
    if item:
        return Tutor.from_dynamodb(item)
    return None


def get_tutor_by_name(name: str) -> Optional[Tutor]:
    """Find tutor by name (case-insensitive partial match on first word before 'Tutoring')."""
    search_term = name.strip().lower()
    tutors = get_all_tutors(status_filter=TutorStatus.ACTIVE)
    for tutor in tutors:
        # Extract first name from display_name (e.g., "Mustafa Tutoring Schedule" -> "mustafa")
        display_lower = tutor.display_name.lower()
        first_word = display_lower.split()[0] if display_lower else ""
        if first_word == search_term:
            return tutor
    return None


def resolve_tutor(identifier: str) -> Optional[Tutor]:
    """Resolve tutor by ID or name. Tries ID first, then name lookup."""
    # Try by tutor_id first
    tutor = get_tutor(identifier)
    if tutor:
        return tutor
    # Try by name (case-insensitive)
    return get_tutor_by_name(identifier)


def get_tutor_by_calendar_id(calendar_id: str) -> Optional[Tutor]:
    """Find a tutor by their Google Calendar ID using GSI."""
    items = dynamodb.query_by_gsi(
        settings.tutors_table,
        "calendarId-index",
        Key("calendarId").eq(calendar_id),
    )
    if items:
        return Tutor.from_dynamodb(items[0])
    return None


def get_tutor_by_discord_channel_id(channel_id: str) -> Optional[Tutor]:
    """Find a tutor by their Discord channel ID."""
    items = dynamodb.scan_table(
        settings.tutors_table,
        FilterExpression=Attr("discordChannelId").eq(channel_id),
    )
    if items:
        return Tutor.from_dynamodb(items[0])
    return None


def create_tutor(display_name: str, calendar_id: str, access_role: str) -> Tutor:
    """Function to create new tutor. Not used for Route, but for sync purposes."""
    tutor = Tutor(display_name=display_name, calendar_id=calendar_id, access_role=access_role)
    dynamodb.put_item(settings.tutors_table, tutor.to_dynamodb())
    return tutor


def update_tutor(tutor_id: str, updates: TutorUpdate) -> Optional[Tutor]:
    """Updates the tutor record in Tutors table using provided tutor_id and updates using TutorUpdate model."""
    existing = get_tutor(tutor_id)
    if not existing:
        return None

    update_data = {}
    if updates.display_name is not None:
        update_data["displayName"] = updates.display_name
    if updates.status is not None:
        update_data["status"] = updates.status.value
    if updates.hourly_rate is not None:
        update_data["hourlyRate"] = updates.hourly_rate
    if updates.tutor_email is not None:
        update_data["tutorEmail"] = updates.tutor_email
    if updates.tutor_phone is not None:
        update_data["tutorPhone"] = updates.tutor_phone
    if updates.discord_channel_id is not None:
        update_data["discordChannelId"] = updates.discord_channel_id
    if updates.discord_onboarding_message_id is not None:
        update_data["discordOnboardingMessageId"] = updates.discord_onboarding_message_id
    if updates.tutor_timezone is not None:
        update_data["tutorTimezone"] = updates.tutor_timezone

    if not update_data:
        return existing

    update_data["updatedAt"] = datetime.utcnow().isoformat()

    updated_item = dynamodb.update_item(
        settings.tutors_table,
        {"tutorId": tutor_id},
        update_data,
    )
    return Tutor.from_dynamodb(updated_item)


def delete_tutor(tutor_id: str) -> bool:
    """Soft-deletes, flags the record of the tutor present in the Tutors table as Inactive."""
    existing_tutor = get_tutor(tutor_id)
    if not existing_tutor:
        return False

    dynamodb.update_item(settings.tutors_table, {"tutorId": tutor_id}, {"status": TutorStatus.INACTIVE.value, "updatedAt": datetime.utcnow().isoformat()})
    return True
