"""
Dropbox webhook endpoint for homework upload notifications.
When a student uploads a file to their Dropbox folder, notifies the tutor via Discord.
"""
import hashlib
import hmac
import logging
from fastapi import APIRouter, Request, Response, HTTPException

from src.config import get_settings
from src.functions import dropbox, discord_utils, tutor_functions, session_functions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dropbox", tags=["Dropbox Webhook"])
settings = get_settings()


@router.get("/webhook")
async def dropbox_webhook_verify(challenge: str):
    """
    Dropbox webhook verification.
    Dropbox sends a GET request with a challenge parameter.
    We must echo back the challenge to verify the endpoint.
    """
    logger.info("Dropbox webhook verification request received")
    return Response(content=challenge, media_type="text/plain")


@router.post("/webhook")
async def dropbox_webhook_notification(request: Request):
    """
    Handle Dropbox webhook notifications.
    Called when files are added/modified in linked Dropbox folders.
    """
    # Verify signature
    signature = request.headers.get("X-Dropbox-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    body = await request.body()

    # Get Dropbox app secret for signature verification
    try:
        creds = dropbox.get_dropbox_credentials()
        app_secret = creds.get("app_secret")
        if not app_secret:
            logger.error("Dropbox app_secret not configured")
            raise HTTPException(status_code=500, detail="Webhook not configured")

        # Verify HMAC signature
        expected_sig = hmac.new(
            app_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("Invalid Dropbox webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying Dropbox signature: {e}")
        raise HTTPException(status_code=500, detail="Signature verification failed")

    # Parse notification
    try:
        data = await request.json()
    except Exception:
        return {"status": "ok"}

    logger.info(f"Dropbox webhook received: {data}")

    # Dropbox sends account IDs that had changes
    # We need to use the Dropbox API to get the actual file changes
    accounts = data.get("list_folder", {}).get("accounts", [])

    if not accounts:
        return {"status": "ok"}

    # Process changes
    try:
        process_dropbox_changes()
    except Exception as e:
        logger.error(f"Error processing Dropbox changes: {e}")

    return {"status": "ok"}


def find_tutor_for_student(student_name: str):
    """
    Find the current tutor for a student by looking at their most recent session.
    Tutors can change over time so we don't store tutor_id on the student record.
    """
    all_sessions = session_functions.get_all_sessions()
    student_sessions = [s for s in all_sessions if student_name.lower() in s.summary.lower()]
    if not student_sessions:
        return None
    most_recent = max(student_sessions, key=lambda s: s.start)
    return tutor_functions.get_tutor(most_recent.tutor_id)


def process_dropbox_changes():
    """
    Check for new files in student folders and notify tutors.
    Uses Dropbox cursor to track changes since last check.
    """
    try:
        # Get recent changes from Dropbox
        changes = dropbox.get_recent_changes()

        if not changes:
            return

        for change in changes:
            path = change.get("path_display", "")
            name = change.get("name", "")

            # Skip if not a file or if it's deleted
            if change.get(".tag") != "file":
                continue

            # Extract student name from path
            # Path format: /Student Folders/StudentName MathPracs/filename.pdf
            student_name = extract_student_from_path(path)

            if not student_name:
                continue

            # Find current tutor via most recent session
            tutor = find_tutor_for_student(student_name)
            if not tutor:
                logger.warning(f"No tutor found for student: {student_name}")
                continue

            if not tutor.dropbox_discord_channel_id:
                logger.warning(f"Tutor {tutor.display_name} has no Dropbox Discord channel for student: {student_name}")
                continue

            # Send notification
            discord_utils.notify_homework_upload(
                student_name=student_name,
                file_name=name,
                tutor_discord_channel_id=tutor.dropbox_discord_channel_id
            )
            logger.info(f"Notified tutor {tutor.display_name} about upload: {student_name} - {name}")

    except Exception as e:
        logger.error(f"Error processing Dropbox changes: {e}")


def extract_student_from_path(path: str) -> str | None:
    """
    Extract student name from Dropbox path.
    Path format: /StudentName MathPracs/filename.pdf
    Returns: StudentName
    """
    if not path:
        return None

    # Remove leading slash and split
    parts = path.lstrip("/").split("/")

    if len(parts) < 3:
        return None

    folder_name = parts[1]

    # Folder name format: "StudentName MathPracs"
    if " MathPracs" in folder_name:
        return folder_name.replace(" MathPracs", "").strip()

    return None
