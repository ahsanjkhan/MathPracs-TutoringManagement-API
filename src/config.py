from datetime import datetime, timezone
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    # AWS
    aws_region: str = "us-east-1"

    # DynamoDB Tables
    tutors_table: str = "Tutors"
    sessions_table: str = "Sessions"
    calendar_sync_table: str = "CalendarListState"
    students_table: str = "Students"

    # Secrets Manager
    google_credentials_secret_name: str = "tutoring-api/google-credentials"
    dropbox_credentials_secret_name: str = "tutoring-api/dropbox-credentials"
    discord_credentials_secret_name: str = "tutoring-api/discord-credentials"

    # Google Drive / Dropbox
    dropbox_parent_folder: str = "/Student Folders"
    parent_drive_folder_id: str = "1DIoIcOLHN-9J6JtZDbU1aMafTy3KEj_N"

    # Session sync settings
    session_keyword: str = r"\btutoring\b"  # Regex to match tutoring events
    session_lookahead_days: int = 7  # How many days ahead to sync

    class Config:
        env_prefix = "TUTORING_"


# Cutoff date for session sync (only sync sessions on or after this date)
SESSION_CUTOFF_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)


@lru_cache
def get_settings() -> Settings:
    return Settings()
