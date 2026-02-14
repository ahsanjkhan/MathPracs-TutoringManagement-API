import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional
import re

from src.config import get_settings
from src.constants import SESSION_KEYWORD, SESSION_CUTOFF_DATE, SESSION_LOOKAHEAD_DAYS
from src.functions import dynamodb, google_calendar, google_docs, google_meet, tutor_functions, session_functions, dropbox
from src.models.tutor_model import TutorUpdate, TutorStatus
from src.models.session_model import SessionUpdate, SessionStatus
from src.models.calendar_state_model import CalendarListState
from src.models.student_model import Student

logger = logging.getLogger(__name__)
settings = get_settings()
CALENDAR_LIST_SYNC_TYPE = "calendarList"

# Module-level cache for verified students (persists across syncs, resets on app restart)
_verified_students = set()

# Sync lock to prevent concurrent syncs (thread-safe)
_sync_lock = threading.Lock()
_sync_in_progress = False


def get_sync_state(sync_type: str) -> Optional[CalendarListState]:
    """Get the sync state for a given sync type from DynamoDB."""
    item = dynamodb.get_item(settings.calendar_sync_table, {"syncType": sync_type})
    if item:
        return CalendarListState.from_dynamodb(item)
    return None


def save_sync_state(sync_state: CalendarListState) -> None:
    """Save sync state to DynamoDB."""
    dynamodb.put_item(settings.calendar_sync_table, sync_state.to_dynamodb())


def refresh_tracked_tutors() -> tuple[int, int]:
    """Check all active tutors and update/deactivate based on calendar status. Returns (updated, deactivated)."""
    updated = 0
    deactivated = 0

    for t in tutor_functions.get_all_tutors(status_filter=TutorStatus.ACTIVE):
        try:
            cal = google_calendar.get_calendar(t.calendar_id)
        except Exception as e:
            if "404" in str(e) or "notFound" in str(e):
                tutor_functions.delete_tutor(t.tutor_id)
                deactivated += 1
                continue
            raise

        new_name = cal.get("summary", t.calendar_id)
        if new_name != t.display_name:
            tutor_functions.update_tutor(t.tutor_id, TutorUpdate(display_name=new_name))
            updated += 1

    return updated, deactivated


def sync_calendar_list() -> dict:
    """Sync calendars from Google. Discovers tutors with 'tutoring' in the name. Returns counts."""
    logger.info("Syncing calendar list...")
    sync_state = get_sync_state(CALENDAR_LIST_SYNC_TYPE)
    sync_token = sync_state.sync_token if sync_state else None

    calendars, new_sync_token = google_calendar.list_calendars(sync_token=sync_token)

    created = 0
    updated = 0
    deactivated = 0

    for cal in calendars:
        calendar_id = cal.get("id")
        display_name = cal.get("summary", calendar_id)
        access_role = cal.get("accessRole", "reader")
        deleted = cal.get("deleted", False)

        if not deleted:
            if access_role not in ("writer", "owner"):
                continue

            if not re.search(SESSION_KEYWORD, display_name, flags=re.IGNORECASE):
                continue

        existing_tutor = tutor_functions.get_tutor_by_calendar_id(calendar_id)

        if deleted:
            if existing_tutor and existing_tutor.status == TutorStatus.ACTIVE:
                tutor_functions.delete_tutor(existing_tutor.tutor_id)
                deactivated += 1
        elif existing_tutor:
            tutor_functions.update_tutor(
                existing_tutor.tutor_id,
                TutorUpdate(display_name=display_name),
            )
            updated += 1
        else:
            logger.info(f"Creating new tutor: {display_name}")
            tutor = tutor_functions.create_tutor(
                display_name=display_name,
                calendar_id=calendar_id,
                access_role=access_role,
            )
            created += 1

    if not calendars:
        u2, d2 = refresh_tracked_tutors()
        updated += u2
        deactivated += d2

    if new_sync_token is not None:
        final_token = new_sync_token
    else:
        final_token = sync_token

    new_state = CalendarListState(
        sync_type=CALENDAR_LIST_SYNC_TYPE,
        sync_token=final_token,
        last_sync_at=datetime.utcnow(),
    )
    save_sync_state(new_state)

    return {"created": created, "updated": updated, "deactivated": deactivated}


def sync_events_list(tutor_cal_id: str) -> dict:
    """Sync events from Google Calendar. Uses lock to prevent concurrent syncs. Pass 'ALL' for all tutors."""
    global _sync_in_progress

    # Try to acquire lock (non-blocking) - if another sync is running, skip
    acquired = _sync_lock.acquire(blocking=False)
    if not acquired:
        logger.warning("Sync already in progress, skipping this request")
        return {"created": 0, "updated": 0, "deleted": 0, "docs_created": 0, "skipped": True}

    try:
        _sync_in_progress = True
        return _sync_events_list_impl(tutor_cal_id)
    finally:
        _sync_in_progress = False
        _sync_lock.release()


def _sync_events_list_impl(tutor_cal_id: str) -> dict:
    """Internal implementation of event sync. Creates sessions, student docs, Meet links, and Dropbox folders."""
    logger.info(f"Syncing events for: {tutor_cal_id}")

    tutors = tutor_functions.get_all_tutors(status_filter=TutorStatus.ACTIVE)
    if tutor_cal_id != "ALL":
        tutors = [t for t in tutors if t.calendar_id == tutor_cal_id]

    created = 0
    docs_created = 0
    updated = 0
    deleted = 0
    time_min = SESSION_CUTOFF_DATE.isoformat().replace("+00:00", "Z")
    time_max = (datetime.now(timezone.utc) + timedelta(days=SESSION_LOOKAHEAD_DAYS)).isoformat().replace("+00:00", "Z")

    # First pass: collect all events from all tutors
    events_by_tutor = {}
    for tutor in tutors:
        events, _ = google_calendar.list_events(tutor.calendar_id, time_min=time_min, time_max=time_max)
        events_by_tutor[tutor.tutor_id] = events

    # Second pass: process events
    for tutor in tutors:
        for event in events_by_tutor.get(tutor.tutor_id, []):
            event_id = event.get("id")
            if not event_id:
                continue

            # If Google says cancelled/deleted, delete from DB
            if event.get("status") == "cancelled":
                existing = session_functions.get_session(tutor.tutor_id, event_id)
                if existing:
                    session_functions.delete_session(tutor.tutor_id, event_id)
                    deleted += 1
                continue

            # Check if event has "tutoring" keyword
            summary = event.get("summary", "")
            has_tutoring_keyword = bool(re.search(SESSION_KEYWORD, summary, flags=re.IGNORECASE))

            # If no "tutoring" keyword, delete from DB if it exists
            if not has_tutoring_keyword:
                existing = session_functions.get_session(tutor.tutor_id, event_id)
                if existing:
                    session_functions.delete_session(tutor.tutor_id, event_id)
                    deleted += 1
                continue

            s = session_functions.event_to_session(tutor.tutor_id, event)
            if not s:
                continue

            existing = session_functions.get_session(tutor.tutor_id, s.session_id)

            out = session_functions.upsert_session_from_calendar(
                tutor_id=tutor.tutor_id,
                session_id=s.session_id,
                summary=s.summary,
                start=s.start,
                end=s.end,
                student_info=s.student_info,
            )

            if out:
                if existing:
                    updated += 1
                else:
                    created += 1

                # Create student doc if it doesn't exist, and attach doc to event
                student_name = google_docs.extract_student_name(s.summary)
                if student_name:
                    try:
                        # Check DynamoDB first (source of truth)
                        existing_student = dynamodb.get_item(settings.students_table, {"studentName": student_name})
                        if existing_student:
                            # Student exists - attach their doc to this event if not already attached
                            doc_id = existing_student.get("docId")
                            if doc_id:
                                doc_title = f"{student_name} MathPracs"
                                try:
                                    attached = google_calendar.attach_doc_to_event(
                                        tutor.calendar_id, s.session_id, doc_id, doc_title
                                    )
                                    if attached:
                                        logger.info(f"Attached doc to event: {s.summary}")
                                except Exception as attach_err:
                                    logger.warning(f"Could not attach doc to {s.summary}: {attach_err}")
                            _verified_students.add(student_name)
                        # Also check if doc exists in Drive (fallback for manual docs)
                        elif student_name not in _verified_students and google_docs.get_existing_student_doc(student_name, settings.parent_drive_folder_id):
                            _verified_students.add(student_name)  # Doc exists, remember it
                        elif student_name not in _verified_students:
                            logger.info(f"Creating student doc for: {student_name}")
                            doc_name = f"{student_name} MathPracs"
                            doc = google_docs.create_doc(doc_name, settings.parent_drive_folder_id)
                            if doc:
                                # Create Google Meet space
                                meet_url = None
                                meet_space = google_meet.create_meet_space(student_name)
                                if meet_space:
                                    meet_url = meet_space.get("meeting_uri")

                                # Create Dropbox folder, get view link, and create file request
                                view_link = None
                                upload_link = None
                                dropbox_folder_name = f"{student_name} MathPracs"
                                dropbox_path = dropbox.create_folder(dropbox_folder_name)
                                if dropbox_path:
                                    view_link = dropbox.get_shared_link(dropbox_path)
                                    upload_link = dropbox.create_file_request(dropbox_folder_name, dropbox_path)
                                    if view_link and upload_link:
                                        google_docs.write_links_to_doc(doc["id"], student_name, view_link, upload_link, meet_url)

                                student = Student(
                                    tutor_id=tutor.tutor_id,
                                    student_name=student_name,
                                    doc_id=doc["id"],
                                    doc_url=doc.get("url"),
                                    google_meets_link=meet_url,
                                    hw_upload_link=view_link,
                                    file_request_link=upload_link,
                                )
                                dynamodb.put_item(settings.students_table, student.to_dynamodb())
                                docs_created += 1
                                _verified_students.add(student_name)  # Doc created, remember it

                                # Attach doc to all calendar events for this student
                                doc_title = f"{student_name} MathPracs"
                                for t in tutors:
                                    for evt in events_by_tutor.get(t.tutor_id, []):
                                        evt_summary = evt.get("summary", "")
                                        evt_id = evt.get("id")
                                        # Only attach to tutoring events for this student
                                        if (evt_id and
                                            evt.get("status") != "cancelled" and
                                            re.search(SESSION_KEYWORD, evt_summary, flags=re.IGNORECASE) and
                                            student_name.lower() in evt_summary.lower()):
                                            try:
                                                attached = google_calendar.attach_doc_to_event(
                                                    t.calendar_id, evt_id, doc["id"], doc_title
                                                )
                                                if attached:
                                                    logger.info(f"Attached doc to event: {evt_summary}")
                                            except Exception as attach_err:
                                                logger.warning(f"Could not attach doc to {evt_summary}: {attach_err}")
                    except Exception as e:
                        logger.error(f"Failed to create student doc for {student_name} after retries: {e}")

    return {"created": created, "updated": updated, "deleted": deleted, "docs_created": docs_created}