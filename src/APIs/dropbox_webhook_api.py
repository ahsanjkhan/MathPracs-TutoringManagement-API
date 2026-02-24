"""
Dropbox webhook endpoint for homework upload notifications.
When a student uploads a file to their Dropbox folder, notifies the tutor via Discord.
"""
import hashlib
import hmac
import logging
from fastapi import APIRouter, Request, Response, HTTPException

from src.config import get_settings
from src.functions import dropbox, discord_utils, student_functions, tutor_functions

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
            # Path format: /StudentName MathPracs/filename.pdf
            student_name = extract_student_from_path(path)

            if not student_name:
                continue

            # Look up student to get tutor
            student = student_functions.get_student(student_name)
            if not student:
                logger.warning(f"Student not found for upload: {student_name}")
                continue

            # Get tutor's Discord channel
            tutor = tutor_functions.get_tutor(student.tutor_id)
            if not tutor or not tutor.discord_channel_id:
                logger.warning(f"Tutor or Discord channel not found for student: {student_name}")
                continue

            # Send notification
            discord_utils.notify_homework_upload(
                student_name=student_name,
                file_name=name,
                tutor_discord_channel_id=tutor.discord_channel_id
            )
            logger.info(f"Notified tutor about upload: {student_name} - {name}")

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
