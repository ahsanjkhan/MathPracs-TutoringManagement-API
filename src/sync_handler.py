import logging

from src.functions import sync_functions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.WARNING)


def lambda_handler(event, context):
    """Handle EventBridge scheduled sync events."""
    logger.info("EventBridge sync triggered")
    try:
        calendar_result = sync_functions.sync_calendar_list()
        logger.info("sync_calendar_list done, starting sync_events_list")
        sessions_result = sync_functions.sync_events_list(tutor_cal_id="ALL")
        logger.info(f"Sync completed - calendars: {calendar_result}, sessions: {sessions_result}")
        return {
            "statusCode": 200,
            "body": {
                "message": "Sync completed",
                "calendars": calendar_result,
                "sessions": sessions_result,
            }
        }
    except Exception as e:
        logger.error(f"Sync failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": {"error": str(e)}
        }
