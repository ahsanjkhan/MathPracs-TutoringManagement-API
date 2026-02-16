from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class TutorStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Tutor(BaseModel):
    tutor_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str
    calendar_id: str
    hourly_rate: float = 10.0
    access_role: str
    status: TutorStatus = TutorStatus.ACTIVE
    tutor_timezone: Optional[str] = None
    tutor_email: Optional[str] = None
    tutor_phone: Optional[str] = None
    discord_channel_id: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dynamodb(self) -> dict:
        data = {
            "tutorId": self.tutor_id,
            "displayName": self.display_name,
            "calendarId": self.calendar_id,
            "hourlyRate": self.hourly_rate,
            "accessRole": self.access_role,
            "status": self.status.value,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }
        if self.tutor_timezone:
            data["tutorTimezone"] = self.tutor_timezone
        if self.tutor_email:
            data["tutorEmail"] = self.tutor_email
        if self.tutor_phone:
            data["tutorPhone"] = self.tutor_phone
        if self.discord_channel_id:
            data["discordChannelId"] = self.discord_channel_id
        return data

    @classmethod
    def from_dynamodb(cls, item: dict) -> "Tutor":
        return cls(
            tutor_id=item["tutorId"],
            display_name=item["displayName"],
            calendar_id=item["calendarId"],
            hourly_rate=float(item.get("hourlyRate", 10.0)),
            access_role=item["accessRole"],
            status=TutorStatus(item["status"]),
            tutor_timezone=item.get("tutorTimezone"),
            tutor_email=item.get("tutorEmail"),
            tutor_phone=item.get("tutorPhone"),
            discord_channel_id=item.get("discordChannelId"),
            created_at=datetime.fromisoformat(item["createdAt"]),
            updated_at=datetime.fromisoformat(item["updatedAt"]),
        )


class TutorUpdate(BaseModel):
    display_name: Optional[str] = None
    status: Optional[TutorStatus] = None
    hourly_rate: Optional[float] = None
    tutor_timezone: Optional[str] = None
    tutor_email: Optional[str] = None
    tutor_phone: Optional[str] = None
    discord_channel_id: Optional[str] = None


class TutorResponse(BaseModel):
    tutor_id: str
    display_name: str
    calendar_id: str
    hourly_rate: float
    access_role: str
    status: TutorStatus
    tutor_timezone: Optional[str] = None
    tutor_email: Optional[str] = None
    tutor_phone: Optional[str] = None
    discord_channel_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
