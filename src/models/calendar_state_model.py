from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CalendarListState(BaseModel):
    sync_type: str
    sync_token: Optional[str] = None
    last_sync_at: Optional[datetime] = None

    def to_dynamodb(self) -> dict:
        data = {"syncType": self.sync_type}
        if self.sync_token:
            data["syncToken"] = self.sync_token
        if self.last_sync_at:
            data["lastSyncAt"] = self.last_sync_at.isoformat()
        return data

    @classmethod
    def from_dynamodb(cls, item: dict) -> "CalendarListState":
        return cls(
            sync_type=item["syncType"],
            sync_token=item.get("syncToken"),
            last_sync_at=datetime.fromisoformat(item["lastSyncAt"]) if item.get("lastSyncAt") else None,
        )
