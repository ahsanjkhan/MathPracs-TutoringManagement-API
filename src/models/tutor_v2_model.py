from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class TutorStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TutorV2(BaseModel):
    """Auto-generated tutor data - never manually updated."""
    tutor_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str
    tutor_name: str
    calendar_id: str
    access_role: str
    status: TutorStatus = TutorStatus.ACTIVE
    discord_channel_id: Optional[str] = None
    discord_onboarding_message_id: Optional[str] = None
    dropbox_discord_channel_id: Optional[str] = None
    feedback_discord_channel_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dynamodb(self) -> dict:
        data = {
            "tutorId": self.tutor_id,
            "displayName": self.display_name,
            "tutorName": self.tutor_name,
            "calendarId": self.calendar_id,
            "accessRole": self.access_role,
            "status": self.status.value,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }
        if self.discord_channel_id:
            data["discordChannelId"] = self.discord_channel_id
        if self.discord_onboarding_message_id:
            data["discordOnboardingMessageId"] = self.discord_onboarding_message_id
        if self.dropbox_discord_channel_id:
            data["dropboxDiscordChannelId"] = self.dropbox_discord_channel_id
        if self.feedback_discord_channel_id:
            data["feedbackDiscordChannelId"] = self.feedback_discord_channel_id
        return data

    @classmethod
    def from_dynamodb(cls, item: dict) -> "TutorV2":
        print(f"Attempting TutorV2 from_dynamodb on {item}")
        return cls(
            tutor_id=item["tutorId"],
            display_name=item["displayName"],
            tutor_name=item.get("tutorName"),
            calendar_id=item["calendarId"],
            access_role=item["accessRole"],
            status=TutorStatus(item["status"]),
            discord_channel_id=item.get("discordChannelId"),
            discord_onboarding_message_id=item.get("discordOnboardingMessageId"),
            dropbox_discord_channel_id=item.get("dropboxDiscordChannelId"),
            feedback_discord_channel_id=item.get("feedbackDiscordChannelId"),
            created_at=datetime.fromisoformat(item["createdAt"]),
            updated_at=datetime.fromisoformat(item["updatedAt"]),
        )


class TutorMetadataV2(BaseModel):
    """Manually generated tutor metadata."""
    tutor_id: str
    display_name: str
    tutor_name: str
    hourly_rate: float = 10.0
    tutor_timezone: str = "Asia/Karachi"
    tutor_email: Optional[str] = None
    tutor_phone: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dynamodb(self) -> dict:
        data = {
            "tutorId": self.tutor_id,
            "tutorName": self.tutor_name,
            "displayName": self.display_name,
            "hourlyRate": self.hourly_rate,
            "tutorTimezone": self.tutor_timezone,
            "updatedAt": self.updated_at.isoformat(),
        }
        if self.tutor_email:
            data["tutorEmail"] = self.tutor_email
        if self.tutor_phone:
            data["tutorPhone"] = self.tutor_phone
        return data

    @classmethod
    def from_dynamodb(cls, item: dict) -> "TutorMetadataV2":
        return cls(
            tutor_id=item["tutorId"],
            display_name=item["displayName"],
            tutor_name=item.get("tutorName"),
            hourly_rate=float(item.get("hourlyRate", 10.0)),
            tutor_timezone=item.get("tutorTimezone", "Asia/Karachi"),
            tutor_email=item.get("tutorEmail"),
            tutor_phone=item.get("tutorPhone"),
            updated_at=datetime.fromisoformat(item["updatedAt"]),
        )

class TutorV2Update(BaseModel):
    display_name: Optional[str] = None
    tutor_name: Optional[str] = None
    status: Optional[TutorStatus] = None

class TutorMetadataV2UpdateNameOnly(BaseModel):
    display_name: Optional[str] = None
    tutor_name: Optional[str] = None

class TutorMetadataV2Update(BaseModel):
    hourly_rate: Optional[float] = None
    tutor_email: Optional[str] = None
    tutor_phone: Optional[str] = None
    tutor_timezone: Optional[str] = None
