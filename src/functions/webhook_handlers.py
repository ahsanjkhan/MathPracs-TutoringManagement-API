import logging
from src.functions import dropbox, discord_utils, tutor_functions, session_functions

logger = logging.getLogger(__name__)

# Store cursor in memory (for Lambda, consider storing in DynamoDB for persistence)
_dropbox_cursor = None


def get_or_init_cursor() -> str | None:
    """Get stored cursor or initialize a new one."""
    global _dropbox_cursor
    if _dropbox_cursor is None:
        _dropbox_cursor = dropbox.get_latest_cursor()
    return _dropbox_cursor


def process_dropbox_webhook() -> dict:
    """
    Process Dropbox webhook notification.
    Called when Dropbox notifies us of changes.

    Returns dict with counts of processed files and notifications sent.
    """
    global _dropbox_cursor

    cursor = get_or_init_cursor()
    if not cursor:
        logger.error("Failed to get Dropbox cursor")
        return {"error": "Failed to get cursor", "files_processed": 0, "notifications_sent": 0}

    # Get list of changes
    files, new_cursor = dropbox.list_folder_changes(cursor)

    if new_cursor:
        _dropbox_cursor = new_cursor

    files_processed = 0
    notifications_sent = 0

    for file_info in files:
        files_processed += 1
        student_name = file_info.get("student_name")
        file_name = file_info.get("name")

        if not student_name:
            logger.warning(f"Could not extract student name from: {file_info.get('path')}")
            continue

        # Find the tutor via the most recent completed session for this student
        tutor_id = session_functions.get_most_recent_tutor_id_for_student(student_name)
        if not tutor_id:
            logger.warning(f"No sessions found for student: {student_name}")
            continue

        tutor = tutor_functions.get_tutor(tutor_id)
        if not tutor:
            logger.warning(f"Tutor not found for student: {student_name}")
            continue

        if not tutor.dropbox_discord_channel_id:
            logger.warning(f"Tutor {tutor.display_name} has no Dropbox Discord channel configured")
            continue

        # Send notification
        success = discord_utils.notify_homework_upload(
            student_name=student_name,
            file_name=file_name,
            tutor_discord_channel_id=tutor.dropbox_discord_channel_id
        )

        if success:
            notifications_sent += 1
            logger.info(f"Notified tutor {tutor.display_name} about upload from {student_name}")

    return {
        "files_processed": files_processed,
        "notifications_sent": notifications_sent
    }
