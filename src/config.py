from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
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

    # Discord Bot (optional - only needed when running bot)
    api_base_url: str = "http://localhost:8000"

    class Config:
        env_prefix = "TUTORING_"


@lru_cache
def get_settings() -> Settings:
    return Settings()
