import logging
from typing import Optional
from googleapiclient.discovery import build
from src.functions.google_calendar import get_google_credentials
from src.functions.utils import retry_on_error

logger = logging.getLogger(__name__)


def get_meet_service():
    """Create a fresh service instance per request to avoid httplib2 thread-safety issues."""
    credentials = get_google_credentials()
    return build("meet", "v2", credentials=credentials)


@retry_on_error()
def create_meet_space(display_name: str) -> Optional[dict]:
    """
    Create a Google Meet space with open access (anyone with link can join).
    Returns {meeting_uri, meeting_code} or None.
    """
    try:
        service = get_meet_service()

        # Create space first
        space = service.spaces().create(body={}).execute()
        space_name = space.get("name")
        meeting_uri = space.get("meetingUri")
        meeting_code = space.get("meetingCode")

        # Update space with open access config
        service.spaces().patch(
            name=space_name,
            updateMask="config.accessType,config.entryPointAccess",
            body={
                "config": {
                    "accessType": "OPEN",
                    "entryPointAccess": "ALL",
                }
            }
        ).execute()

        logger.info(f"Created Meet space for {display_name}: {meeting_uri} (accessType: OPEN)")

        return {
            "meeting_uri": meeting_uri,
            "meeting_code": meeting_code,
            "space_name": space_name,
        }
    except Exception as e:
        logger.error(f"Failed to create Meet space: {e}")
        raise
