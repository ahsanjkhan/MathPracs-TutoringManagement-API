from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"


class Session(BaseModel):
    """Stored/internal session model (DB + business logic)."""
    tutor_id: str
    session_id: str
    summary: str
    start: datetime
    end: datetime
    utc_start: Optional[datetime] = None
    utc_end: Optional[datetime] = None
    timezone: Optional[str] = None
    status: SessionStatus = SessionStatus.SCHEDULED
    student_info: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dynamodb(self) -> dict:
        data = {
            "tutorId": self.tutor_id,
            "sessionId": self.session_id,
            "summary": self.summary,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "status": self.status.value,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }
        if self.utc_start is not None:
            data["utcStart"] = self.utc_start.isoformat()
        if self.utc_end is not None:
            data["utcEnd"] = self.utc_end.isoformat()
        if self.timezone is not None:
            data["timezone"] = self.timezone
        if self.student_info is not None:
            data["studentInfo"] = self.student_info
        return data

    @classmethod
    def from_dynamodb(cls, item: dict) -> "Session":
        return cls(
            tutor_id=item["tutorId"],
            session_id=item["sessionId"],
            summary=item["summary"],
            start=datetime.fromisoformat(item["start"]),
            end=datetime.fromisoformat(item["end"]),
            utc_start=datetime.fromisoformat(item["utcStart"]) if item.get("utcStart") else None,
            utc_end=datetime.fromisoformat(item["utcEnd"]) if item.get("utcEnd") else None,
            timezone=item.get("timezone"),
            status=SessionStatus(item.get("status", "scheduled")),
            student_info=item.get("studentInfo"),
            created_at=datetime.fromisoformat(item["createdAt"]),
            updated_at=datetime.fromisoformat(item["updatedAt"]),
        )


class SessionCreate(BaseModel):
    """input model. (what clients are allowed to send)"""
    tutor_id: str
    session_id: str
    summary: str
    start: datetime
    end: datetime
    status: SessionStatus = SessionStatus.SCHEDULED  #defaults to "scheduled"
    student_info: Optional[str] = None


class SessionUpdate(BaseModel):
    summary: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    utc_start: Optional[datetime] = None
    utc_end: Optional[datetime] = None
    timezone: Optional[str] = None
    status: Optional[SessionStatus] = None
    student_info: Optional[str] = None


class SessionResponse(BaseModel):
    tutor_id: str
    session_id: str
    summary: str
    start: datetime
    end: datetime
    status: SessionStatus
    student_info: Optional[str]
    created_at: datetime
    updated_at: datetime
