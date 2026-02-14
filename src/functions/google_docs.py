import logging
import re
from typing import Optional
from googleapiclient.discovery import build
from src.functions.google_calendar import get_google_credentials
from src.functions.utils import retry_on_error
from src.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def get_drive_service():
    """Create a fresh service instance per request to avoid httplib2 thread-safety issues."""
    credentials = get_google_credentials()
    return build("drive", "v3", credentials=credentials)


def get_docs_service():
    """Create a fresh service instance per request to avoid httplib2 thread-safety issues."""
    credentials = get_google_credentials()
    return build("docs", "v1", credentials=credentials)


def extract_student_name(summary: str) -> Optional[str]:
    """Extract student name from session summary. E.g., 'Ved Tutoring' -> 'Ved'. Returns title case."""
    match = re.match(r"^(.+?)\s+[Tt]utoring", summary)
    if match:
        return match.group(1).strip().title()
    return None


def extract_tutor_folder_name(display_name: str) -> str:
    """Extract folder name from tutor display name. E.g., 'Shabbar Tutoring Schedule' -> 'Tutor_Shabbar'"""
    name = re.sub(r"\s*[Tt]utoring.*$", "", display_name).strip()
    first_name = name.split()[0] if name else display_name.split()[0]
    return f"Tutor_{first_name}"


@retry_on_error()
def create_folder(folder_name: str, parent_id: str) -> Optional[str]:
    """Create a folder. Returns folder ID or None."""
    try:
        service = get_drive_service()
        folder = service.files().create(
            body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
            fields="id",
        ).execute()
        logger.info(f"Created folder '{folder_name}'")
        return folder.get("id")
    except Exception as e:
        logger.error(f"Failed to create folder: {e}")
        raise


def get_existing_student_doc(student_name: str, parent_folder_id: str) -> Optional[dict]:
    """Check if a student doc exists with MathPracs suffix. Returns {id, url} or None."""
    try:
        service = get_drive_service()
        doc_name = f"{student_name} MathPracs"
        escaped_name = doc_name.replace("'", "\\'")
        query = f"name = '{escaped_name}' and '{parent_folder_id}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false"
        results = service.files().list(q=query, fields="files(id, webViewLink)").execute()
        files = results.get("files", [])
        if files:
            return {"id": files[0].get("id"), "url": files[0].get("webViewLink")}
        return None
    except Exception as e:
        logger.error(f"Failed to search for student doc: {e}")
        return None


@retry_on_error()
def create_doc(doc_name: str, parent_folder_id: str) -> Optional[dict]:
    """Create a Google Doc. Returns {id, url} or None."""
    try:
        service = get_drive_service()
        doc = service.files().create(
            body={"name": doc_name, "mimeType": "application/vnd.google-apps.document", "parents": [parent_folder_id]},
            fields="id, webViewLink",
        ).execute()
        logger.info(f"Created doc '{doc_name}'")
        return {"id": doc.get("id"), "url": doc.get("webViewLink")}
    except Exception as e:
        logger.error(f"Failed to create doc: {e}")
        raise


@retry_on_error()
def get_doc(doc_id: str) -> Optional[dict]:
    """Get a Google Doc by ID. Returns {id, name, url} or None."""
    try:
        service = get_drive_service()
        doc = service.files().get(fileId=doc_id, fields="id, name, webViewLink").execute()
        return {"id": doc.get("id"), "name": doc.get("name"), "url": doc.get("webViewLink")}
    except Exception as e:
        logger.error(f"Failed to get doc: {e}")
        raise


@retry_on_error()
def delete_doc(doc_id: str) -> bool:
    """Delete a Google Doc. Returns True if successful."""
    try:
        service = get_drive_service()
        service.files().delete(fileId=doc_id).execute()
        logger.info(f"Deleted doc {doc_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete doc: {e}")
        raise


@retry_on_error()
def write_links_to_doc(doc_id: str, student_name: str, view_url: str, upload_url: str, meet_url: Optional[str] = None) -> bool:
    """Write student name, Meet link, and Dropbox links to the Google Doc with formatting."""
    try:
        service = get_docs_service()

        # Build the text content
        name_section = student_name + "\n\n"

        meet_label = "Google Meet Link:\n" if meet_url else ""
        meet_section = meet_label + (meet_url or "") + ("\n\n" if meet_url else "")

        send_label = "Link to Send Notes, Packets, Homework:\n"
        view_label = "\n\nLink to View Homework, Notes:\n"

        full_text = name_section + meet_section + send_label + upload_url + view_label + view_url

        requests = [
            # Insert all text
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": full_text
                }
            },
        ]

        # Bold and underline student name
        name_start = 1
        name_end = 1 + len(student_name)
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": name_start, "endIndex": name_end},
                "textStyle": {
                    "bold": True,
                    "underline": True,
                },
                "fields": "bold,underline"
            }
        })

        # Calculate positions and add formatting
        name_offset = len(name_section)

        if meet_url:
            # Bold and yellow highlight "Google Meet Link"
            meet_text_start = 1 + name_offset
            meet_text_end = meet_text_start + len("Google Meet Link")
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": meet_text_start, "endIndex": meet_text_end},
                    "textStyle": {
                        "bold": True,
                        "backgroundColor": {"color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}}
                    },
                    "fields": "bold,backgroundColor"
                }
            })
            # Hyperlink meet URL
            meet_link_start = 1 + name_offset + len(meet_label)
            meet_link_end = meet_link_start + len(meet_url)
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": meet_link_start, "endIndex": meet_link_end},
                    "textStyle": {"link": {"url": meet_url}},
                    "fields": "link"
                }
            })

        # Calculate positions for Dropbox links (offset by name + meet section)
        offset = name_offset + len(meet_section)

        send_notes_start = 1 + offset + len("Link to ")
        send_notes_end = send_notes_start + len("Send Notes")

        upload_link_start = 1 + offset + len(send_label)
        upload_link_end = upload_link_start + len(upload_url)

        view_homework_start = 1 + offset + len(send_label) + len(upload_url) + len("\n\nLink to ")
        view_homework_end = view_homework_start + len("View Homework")

        view_link_start = 1 + offset + len(send_label) + len(upload_url) + len(view_label)
        view_link_end = view_link_start + len(view_url)

        # Add Dropbox formatting requests
        requests.extend([
            # Hyperlink upload URL
            {
                "updateTextStyle": {
                    "range": {"startIndex": upload_link_start, "endIndex": upload_link_end},
                    "textStyle": {"link": {"url": upload_url}},
                    "fields": "link"
                }
            },
            # Hyperlink view URL
            {
                "updateTextStyle": {
                    "range": {"startIndex": view_link_start, "endIndex": view_link_end},
                    "textStyle": {"link": {"url": view_url}},
                    "fields": "link"
                }
            },
            # Bold and yellow highlight "Send Notes"
            {
                "updateTextStyle": {
                    "range": {"startIndex": send_notes_start, "endIndex": send_notes_end},
                    "textStyle": {
                        "bold": True,
                        "backgroundColor": {"color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}}
                    },
                    "fields": "bold,backgroundColor"
                }
            },
            # Bold and yellow highlight "View Homework"
            {
                "updateTextStyle": {
                    "range": {"startIndex": view_homework_start, "endIndex": view_homework_end},
                    "textStyle": {
                        "bold": True,
                        "backgroundColor": {"color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}}
                    },
                    "fields": "bold,backgroundColor"
                }
            }
        ])

        service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
        logger.info(f"Wrote links to doc {doc_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to write to doc: {e}")
        raise
