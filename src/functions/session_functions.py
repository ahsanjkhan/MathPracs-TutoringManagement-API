from datetime import datetime, timezone
from typing import Optional
import re
from boto3.dynamodb.conditions import Key

from src.config import get_settings
from src.config import SESSION_CUTOFF_DATE
from src.functions import dynamodb
from src.models.session_model import Session, SessionStatus, SessionCreate, SessionUpdate

settings = get_settings()


def is_session_after_cutoff(session_start: datetime) -> bool:
    """Check if session start date is on or after Jan 1, 2026."""
    if session_start.tzinfo is not None:
        cutoff = SESSION_CUTOFF_DATE
    else:
        cutoff = SESSION_CUTOFF_DATE.replace(tzinfo=None)
    return session_start >= cutoff


def create_session(session_data: SessionCreate) -> Optional[Session]:
    """Create a new session. Returns None if session is before cutoff date."""
    if not is_session_after_cutoff(session_data.start):
        return None

    session = Session(
        tutor_id=session_data.tutor_id,
        session_id=session_data.session_id,
        summary=session_data.summary,
        start=session_data.start,
        end=session_data.end,
        status=session_data.status,
        student_info=session_data.student_info,
    )
    dynamodb.put_item(settings.sessions_table, session.to_dynamodb())
    return session


def get_all_sessions(status_filter: Optional[SessionStatus] = None) -> list[Session]:
    """Returns all sessions."""
    items = dynamodb.scan_table(settings.sessions_table)
    sessions = [Session.from_dynamodb(i) for i in items]

    if status_filter:
        sessions = [s for s in sessions if s.status == status_filter]

    return sessions


def get_sessions_by_tutor(tutor_id: str, status_filter: Optional[SessionStatus] = None) -> list[Session]:
    """Gets all sessions for a specific tutor"""
    items = dynamodb.query_table(
        settings.sessions_table,
        Key("tutorId").eq(tutor_id),
    )
    sessions = [Session.from_dynamodb(i) for i in items]

    if status_filter:
        sessions = [s for s in sessions if s.status == status_filter]

    return sessions


def get_session(tutor_id: str, session_id: str) -> Optional[Session]:
    """Gets a specific session"""
    item = dynamodb.get_item(
        settings.sessions_table,
        {"tutorId": tutor_id, "sessionId": session_id},
    )
    if item:
        return Session.from_dynamodb(item)
    return None


def patch_session(tutor_id: str, session_id: str, updates: SessionUpdate) -> Optional[Session]:
    """Update specific fields on a session. Returns None if not found."""
    existing = get_session(tutor_id, session_id)
    if not existing:
        return None

    update_data = {}
    if updates.summary is not None:
        update_data["summary"] = updates.summary
    if updates.start is not None:
        update_data["start"] = updates.start.isoformat()
    if updates.end is not None:
        update_data["end"] = updates.end.isoformat()
    if updates.utc_start is not None:
        update_data["utcStart"] = updates.utc_start.isoformat()
    if updates.utc_end is not None:
        update_data["utcEnd"] = updates.utc_end.isoformat()
    if updates.timezone is not None:
        update_data["timezone"] = updates.timezone
    if updates.status is not None:
        update_data["status"] = updates.status.value
    if updates.student_info is not None:
        update_data["studentInfo"] = updates.student_info

    if not update_data:
        return existing

    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    updated_item = dynamodb.update_item(
        settings.sessions_table,
        {"tutorId": tutor_id, "sessionId": session_id},
        update_data,
    )
    return Session.from_dynamodb(updated_item)


def delete_session(tutor_id: str, session_id: str) -> bool:
    """Delete a session from the database."""
    existing = get_session(tutor_id, session_id)
    if not existing:
        return False
    dynamodb.delete_item(settings.sessions_table, {"tutorId": tutor_id, "sessionId": session_id})
    return True


def get_most_recent_tutor_id_for_student(student_name: str) -> Optional[str]:
    """Find the tutor_id from the most recent session for a given student.
    Prefers completed sessions, falls back to scheduled if none found."""
    from boto3.dynamodb.conditions import Attr
    items = dynamodb.scan_table(
        settings.sessions_table,
        FilterExpression=Attr("summary").contains(student_name),
    )
    if not items:
        return None
    sessions = [Session.from_dynamodb(i) for i in items]
    completed = [s for s in sessions if s.status == SessionStatus.COMPLETED]
    pool = completed if completed else sessions
    most_recent = max(pool, key=lambda s: s.utc_start or s.start)
    return most_recent.tutor_id


def parse_calendar_datetime(dt_info: dict) -> Optional[datetime]:
    """Parse datetime from Google Calendar event. Normalizes Google's two time formats into one Python datetime"""
    if "dateTime" in dt_info:
        dt_str = dt_info["dateTime"]
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    elif "date" in dt_info:
        return datetime.fromisoformat(dt_info["date"])
    return None


def get_event_timezone(event: dict) -> Optional[str]:
    """Extract timezone from Google Calendar event."""
    # Try start.timeZone first, then end.timeZone, then fall back to None
    tz = event.get("start", {}).get("timeZone")
    if not tz:
        tz = event.get("end", {}).get("timeZone")
    return tz


def to_utc(dt: datetime) -> datetime:
    """Convert a datetime to UTC."""
    if dt.tzinfo is None:
        # Assume UTC if no timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def event_to_session(tutor_id: str, event: dict) -> Optional[Session]:
    """Convert a Google Calendar event to a Session object. Returns None if not a tutoring event."""
    event_id = event.get("id")
    if not event_id:
        return None

    summary = event.get("summary", "")
    # Only sync events with "tutoring" in the title (case-insensitive)
    if not re.search(settings.session_keyword, summary, flags=re.IGNORECASE):
        return None

    start = parse_calendar_datetime(event.get("start", {}))
    end = parse_calendar_datetime(event.get("end", {}))
    if not start or not end or not is_session_after_cutoff(start):
        return None

    # Get UTC times and timezone
    utc_start = to_utc(start)
    utc_end = to_utc(end)
    event_timezone = get_event_timezone(event)

    if not summary:
        summary = "Untitled Session"
    description = event.get("description")

    now = datetime.now(timezone.utc)
    status = SessionStatus.COMPLETED if utc_end < now else SessionStatus.SCHEDULED

    return Session(
        tutor_id=tutor_id,
        session_id=event_id,
        summary=summary,
        start=start,
        end=end,
        utc_start=utc_start,
        utc_end=utc_end,
        timezone=event_timezone,
        status=status,
        student_info=description,
    )


def upsert_session_from_calendar(
    tutor_id: str,
    session_id: str,
    summary: str,
    start: datetime,
    end: datetime,
    student_info: Optional[str] = None,
    utc_start: Optional[datetime] = None,
    utc_end: Optional[datetime] = None,
    event_timezone: Optional[str] = None,
) -> Optional[Session]:
    """Create or update a session from calendar data. Auto-sets status based on end time."""
    if not is_session_after_cutoff(start):
        return None

    now = datetime.now(timezone.utc)
    # Calculate UTC times if not provided
    if utc_start is None:
        utc_start = to_utc(start)
    if utc_end is None:
        utc_end = to_utc(end)
    status = SessionStatus.COMPLETED if utc_end < now else SessionStatus.SCHEDULED

    existing = get_session(tutor_id, session_id)

    if existing:
        updates = SessionUpdate(
            summary=summary,
            start=start,
            end=end,
            utc_start=utc_start,
            utc_end=utc_end,
            timezone=event_timezone,
            status=status,
            student_info=student_info
        )
        return patch_session(tutor_id, session_id, updates)

    session_data = SessionCreate(
        tutor_id=tutor_id,
        session_id=session_id,
        summary=summary,
        start=start,
        end=end,
        status=status,
        student_info=student_info,
    )
    session = create_session(session_data)
    if session:
        # Update with extra fields (not in SessionCreate)
        updates = SessionUpdate(utc_start=utc_start, utc_end=utc_end, timezone=event_timezone)
        return patch_session(tutor_id, session_id, updates)
    return session
