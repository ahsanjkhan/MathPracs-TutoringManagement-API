from datetime import datetime, timezone
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    # AWS
    aws_region: str = "us-east-1"

    # DynamoDB Tables
    tutors_table: str = "TutorsV2"
    tutors_metadata_table: str = "TutorsMetadataV2"
    sessions_table: str = "Sessions"
    calendar_sync_table: str = "CalendarListState"
    students_table: str = "StudentsV2"
    students_metadata_table: str = "StudentsMetadataV2"
    transactions_table: str = "Transactions"

    # Secrets Manager
    google_credentials_secret_name: str = "tutoring-api/google-credentials-cdk"
    dropbox_credentials_secret_name: str = "tutoring-api/dropbox-credentials-cdk"
    discord_credentials_secret_name: str = "tutoring-api/discord-credentials-cdk"
    groq_credentials_secret_name: str = "tutoring-api/groq-credentials-cdk"

    # SSM Parameters
    parent_drive_folder_id_ssm_name: str = "/tutoring-api/parent-drive-folder-id"
    dropbox_parent_folder_ssm_name: str = "/tutoring-api/dropbox-parent-folder"

    # S3 Archive
    dropbox_archive_bucket: str = "mathpracs-dropbox-archive"

    # Google Drive / Dropbox

    # Session sync settings
    session_keyword: str = r"\btutoring\b"  # Regex to match tutoring events
    session_lookahead_days: int = 7  # How many days ahead to sync
    session_lookback_days: int = 30  # How many days back to sync

    class Config:
        env_prefix = "TUTORING_"


# Cutoff date for session sync (only sync sessions on or after this date)
SESSION_CUTOFF_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)


@lru_cache
def get_settings() -> Settings:
    return Settings()
