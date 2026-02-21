import json
import logging
import boto3
import dropbox
from dropbox.exceptions import ApiError
from src.config import get_settings
from src.functions.utils import retry_on_error
from src.functions import ssm_utils

settings = get_settings()
logger = logging.getLogger(__name__)

_dropbox_client = None
_dropbox_credentials = None


def get_dropbox_credentials() -> dict:
    """Get Dropbox credentials from AWS Secrets Manager."""
    global _dropbox_credentials
    if _dropbox_credentials is None:
        secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
        response = secrets_client.get_secret_value(SecretId=settings.dropbox_credentials_secret_name)
        _dropbox_credentials = json.loads(response["SecretString"])
    return _dropbox_credentials


def get_dropbox_client():
    """Get or create a cached Dropbox client using credentials from Secrets Manager."""
    global _dropbox_client
    if _dropbox_client is None:
        secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
        response = secrets_client.get_secret_value(SecretId=settings.dropbox_credentials_secret_name)
        creds = json.loads(response["SecretString"])
        _dropbox_client = dropbox.Dropbox(
            app_key=creds["app_key"],
            app_secret=creds["app_secret"],
            oauth2_refresh_token=creds["refresh_token"]
        )
    return _dropbox_client


@retry_on_error()
def create_folder(folder_name: str) -> str | None:
    """Create a folder inside the parent folder. Returns the folder path if created or already exists."""
    try:
        dbx = get_dropbox_client()
        folder_path = f"{ssm_utils.get_dropbox_parent_folder()}/{folder_name}"
        dbx.files_create_folder_v2(folder_path)
        logger.info(f"Created Dropbox folder: {folder_path}")
        return folder_path
    except ApiError as e:
        # If folder already exists, return the path instead of failing
        if e.error.is_path() and e.error.get_path().is_conflict():
            logger.info(f"Dropbox folder already exists: {folder_path}")
            return folder_path
        logger.error(f"Failed to create Dropbox folder: {e}")
        raise


@retry_on_error()
def get_shared_link(folder_path: str) -> str | None:
    """Get or create a shared link for a folder. Returns the URL or None."""
    try:
        dbx = get_dropbox_client()
        shared_link = dbx.sharing_create_shared_link_with_settings(folder_path)
        logger.info(f"Created shared link for: {folder_path}")
        return shared_link.url
    except ApiError as e:
        if e.error.is_shared_link_already_exists():
            links = dbx.sharing_list_shared_links(folder_path, direct_only=True)
            if links.links:
                return links.links[0].url
        logger.error(f"Failed to get shared link: {e}")
        raise


@retry_on_error()
def create_file_request(title: str, folder_path: str) -> str | None:
    """Create a file request for a folder. Returns the file request URL or existing one if already created."""
    try:
        dbx = get_dropbox_client()
        description = "Notes, Homework etc. to be shared between students and MathPracs tutors."
        file_request = dbx.file_requests_create(
            title=title,
            destination=folder_path,
            description=description,
            open=True
        )
        logger.info(f"Created file request: {title}")
        return file_request.url
    except ApiError as e:
        # If file request already exists for this path, find and return it
        if "already a file request" in str(e).lower() or "destination" in str(e).lower():
            try:
                existing_requests = dbx.file_requests_list_v2()
                for req in existing_requests.file_requests:
                    if req.destination == folder_path and req.is_open:
                        logger.info(f"File request already exists for: {folder_path}")
                        return req.url
            except Exception:
                pass
        logger.error(f"Failed to create file request: {e}")
        raise


def get_latest_cursor() -> str | None:
    """Get a cursor for the current state of the parent folder. Used for tracking changes."""
    try:
        dbx = get_dropbox_client()
        result = dbx.files_list_folder_get_latest_cursor(
            path=ssm_utils.get_dropbox_parent_folder(),
            recursive=True
        )
        return result.cursor
    except ApiError as e:
        logger.error(f"Failed to get Dropbox cursor: {e}")
        return None


def list_folder_changes(cursor: str) -> tuple[list[dict], str | None]:
    """
    List changes since the given cursor.
    Returns (list of new/modified files, new_cursor).
    Each file dict contains: name, path, student_name (extracted from path).
    """
    try:
        dbx = get_dropbox_client()
        result = dbx.files_list_folder_continue(cursor)

        files = []
        for entry in result.entries:
            # Only process file additions (not deletions or folders)
            if hasattr(entry, 'name') and hasattr(entry, 'path_display'):
                # Skip if it's a folder
                if hasattr(entry, 'is_downloadable') or entry.__class__.__name__ == 'FileMetadata':
                    # Extract student name from path
                    # Path format: /Student Folders/Aiden MathPracs/homework.pdf
                    path_parts = entry.path_display.split('/')
                    student_name = None
                    if len(path_parts) >= 3:
                        folder_name = path_parts[2]  # "Aiden MathPracs"
                        # Extract first name before "MathPracs"
                        if "mathpracs" in folder_name.lower():
                            student_name = folder_name.lower().replace("mathpracs", "").strip().title()

                    files.append({
                        "name": entry.name,
                        "path": entry.path_display,
                        "student_name": student_name
                    })

        new_cursor = result.cursor if result.has_more else result.cursor
        return files, new_cursor

    except ApiError as e:
        logger.error(f"Failed to list Dropbox changes: {e}")
        return [], None


def extract_student_name_from_path(path: str) -> str | None:
    """
    Extract student name from Dropbox path.
    Path format: /Student Folders/Aiden MathPracs/homework.pdf -> "Aiden"
    """
    path_parts = path.split('/')
    if len(path_parts) >= 3:
        folder_name = path_parts[2]  # "Aiden MathPracs"
        if "mathpracs" in folder_name.lower():
            return folder_name.lower().replace("mathpracs", "").strip().title()
    return None


def get_recent_changes() -> list[dict]:
    """
    Get recent file changes from Dropbox.
    Stores cursor in DynamoDB to track processed changes.
    Returns list of file entries with path_display, name, and .tag
    """
    from src.functions import dynamodb

    CURSOR_KEY = {"syncType": "dropboxCursor"}

    # Get stored cursor from DynamoDB
    cursor_item = dynamodb.get_item(settings.calendar_sync_table, CURSOR_KEY)
    cursor = cursor_item.get("cursor") if cursor_item else None

    try:
        dbx = get_dropbox_client()
        parent_folder = ssm_utils.get_dropbox_parent_folder()

        if cursor:
            # Get changes since last cursor
            result = dbx.files_list_folder_continue(cursor)
        else:
            # First time - get current state and save cursor
            result = dbx.files_list_folder(parent_folder, recursive=True)

        # Collect all entries
        entries = []
        for entry in result.entries:
            entry_dict = {
                "path_display": getattr(entry, "path_display", ""),
                "name": getattr(entry, "name", ""),
                ".tag": entry.__class__.__name__.lower().replace("metadata", "")
            }
            entries.append(entry_dict)

        # Handle pagination
        while result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
            for entry in result.entries:
                entry_dict = {
                    "path_display": getattr(entry, "path_display", ""),
                    "name": getattr(entry, "name", ""),
                    ".tag": entry.__class__.__name__.lower().replace("metadata", "")
                }
                entries.append(entry_dict)

        # Save new cursor to DynamoDB
        dynamodb.put_item(settings.calendar_sync_table, {
            "syncType": "dropboxCursor",
            "cursor": result.cursor
        })

        logger.info(f"Dropbox changes found: {len(entries)} entries")
        return entries

    except ApiError as e:
        # If cursor is invalid, reset and start fresh
        if "reset" in str(e).lower() or "expired" in str(e).lower():
            logger.warning("Dropbox cursor expired, resetting...")
            dynamodb.delete_item(settings.calendar_sync_table, CURSOR_KEY)
            return []
        logger.error(f"Failed to get Dropbox changes: {e}")
        return []
