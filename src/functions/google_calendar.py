import json
import logging
from typing import Optional
import boto3
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from src.config import get_settings
from src.functions.utils import retry_on_error

logger = logging.getLogger(__name__)
settings = get_settings()
_credentials = None

SCOPES = ["https://www.googleapis.com/auth/calendar",
          "https://www.googleapis.com/auth/calendar.events",
          "https://www.googleapis.com/auth/drive.file",
          "https://www.googleapis.com/auth/documents",
          "https://www.googleapis.com/auth/meetings.space.created"]


def get_google_credentials():
    """Get or create cached Google OAuth credentials from Secrets Manager."""
    global _credentials
    if _credentials is None:
        secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
        response = secrets_client.get_secret_value(SecretId=settings.google_credentials_secret_name)
        creds_json = json.loads(response["SecretString"])
        _credentials = Credentials(
            token=None,
            refresh_token=creds_json["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_json["client_id"],
            client_secret=creds_json["client_secret"],
            scopes=SCOPES,
        )
    return _credentials


def get_calendar_service():
    """Create a fresh service instance per request to avoid httplib2 thread-safety issues."""
    credentials = get_google_credentials()
    return build("calendar", "v3", credentials=credentials)


def list_calendars(sync_token: Optional[str] = None) -> tuple[list[dict], Optional[str]]:
    """List all calendars. Returns (calendars, new_sync_token). Handles pagination."""
    service = get_calendar_service()
    calendars = []
    page_token = None

    while True:
        request_params = {"showDeleted": True}
        if sync_token:
            request_params["syncToken"] = sync_token
        if page_token:
            request_params["pageToken"] = page_token

        try:
            response = service.calendarList().list(**request_params).execute()
        except Exception as e:
            if "Sync token" in str(e) and "invalid" in str(e).lower():
                return list_calendars(sync_token=None)
            raise

        calendars.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        new_sync_token = response.get("nextSyncToken")

        if not page_token:
            break

    return calendars, new_sync_token


def get_calendar(calendar_id: str) -> dict:
    """Get a single calendar by ID."""
    service = get_calendar_service()
    return service.calendarList().get(calendarId=calendar_id).execute()


def list_events(calendar_id: str, sync_token: Optional[str] = None, time_min: Optional[str] = None, time_max: Optional[str] = None) -> tuple[list[dict], Optional[str]]:
    """List events from a calendar. Returns (events, new_sync_token). Handles pagination."""
    service = get_calendar_service()
    events = []
    page_token = None

    while True:
        request_params = {"calendarId": calendar_id, "showDeleted": True, "singleEvents": True, "orderBy": "startTime"}

        if sync_token:
            request_params["syncToken"] = sync_token
        else:
            if time_min:
                request_params["timeMin"] = time_min
            if time_max:
                request_params["timeMax"] = time_max
        if page_token:
            request_params["pageToken"] = page_token

        try:
            response = service.events().list(**request_params).execute()
        except Exception as e:
            if "Sync token" in str(e) and "invalid" in str(e).lower():
                return list_events(calendar_id, sync_token=None, time_min=time_min, time_max=time_max)
            raise

        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        new_sync_token = response.get("nextSyncToken")

        if not page_token:
            break

    return events, new_sync_token


@retry_on_error()
def attach_doc_to_event(calendar_id: str, event_id: str, doc_id: str, doc_title: str) -> bool:
    """
    Attach a Google Doc to a calendar event.
    Only attaches if the event has NO existing Google Doc attachments.
    Returns True if successful, False if event already has a doc or failed.
    """
    service = get_calendar_service()

    try:
        # Get current event to check existing attachments
        event = service.events().get(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()

        existing_attachments = event.get("attachments", [])

        # Check if the correct doc is already attached
        for attachment in existing_attachments:
            if (attachment.get("mimeType") == "application/vnd.google-apps.document"
                    and attachment.get("fileId") == doc_id):
                return False  # Correct doc already attached, skip

        # Remove any existing Google Doc attachments (manual or wrong doc)
        filtered = [a for a in existing_attachments if a.get("mimeType") != "application/vnd.google-apps.document"]

        # Add the correct doc
        doc_url = f"https://docs.google.com/document/d/{doc_id}"
        filtered.append({
            "fileUrl": doc_url,
            "mimeType": "application/vnd.google-apps.document",
            "title": doc_title,
            "fileId": doc_id
        })

        # Update event with corrected attachments
        service.events().patch(
            calendarId=calendar_id,
            eventId=event_id,
            supportsAttachments=True,
            body={"attachments": filtered}
        ).execute()

        return True
    except Exception as e:
        logger.warning(f"Failed to attach doc to event {event_id}: {e}")
        raise
