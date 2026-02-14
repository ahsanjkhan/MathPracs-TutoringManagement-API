from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    tutors_table: str = "Tutors"
    sessions_table: str = "Sessions"
    calendar_sync_table: str = "CalendarListState"
    students_table: str = "Students"
    google_credentials_secret_name: str = "tutoring-api/google-credentials"
    dropbox_credentials_secret_name: str = "tutoring-api/dropbox-credentials"
    dropbox_parent_folder: str = "/Student Folders"
    parent_drive_folder_id: str = "1DIoIcOLHN-9J6JtZDbU1aMafTy3KEj_N"

    class Config:
        env_prefix = "TUTORING_"


@lru_cache
def get_settings() -> Settings:
    return Settings()
