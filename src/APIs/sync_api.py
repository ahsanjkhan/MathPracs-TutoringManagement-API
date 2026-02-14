from fastapi import APIRouter
from src.functions import sync_functions
import logging

router = APIRouter(prefix="/sync", tags=["Manual-SYNCs"])
logger = logging.getLogger(__name__)


@router.post("/calendars")
def sync_calendars():
    """This api syncs all calendars manually, determines list of tutors & flags whether active/inactive."""
    result = sync_functions.sync_calendar_list()
    logger.info(f"Calendar Sync completed: {result}")
    return {"message": "Calendar sync completed", **result}


@router.post("/sessions", summary="Sync Calendars + Sessions")
def sync_sessions():
    """
    Syncs calendars (discovers tutors) then syncs all sessions/events.
    Run by EventBridge at a certain time interval. (Currently set to 3 minutes)
    """
    calendar_result = sync_functions.sync_calendar_list()
    sessions_result = sync_functions.sync_events_list(tutor_cal_id="ALL")
    logger.info(f"Full sync completed - calendars: {calendar_result}, sessions: {sessions_result}")
    return {
        "message": "Sync completed",
        "calendars": calendar_result,
        "sessions": sessions_result,
    }
