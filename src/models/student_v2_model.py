from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PaymentCollector(str, Enum):
    MUAZ = "muaz"
    AHSAN = "ahsan"
    BUSINESS = "business"


class StudentV2(BaseModel):
    """Auto-generated student data."""
    student_name: str
    doc_id: str
    balance: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    doc_url: Optional[str] = None
    file_request_link: Optional[str] = None
    google_meets_link: Optional[str] = None
    hw_upload_link: Optional[str] = None

    def to_dynamodb(self) -> dict:
        data = {
            "studentName": self.student_name,
            "docId": self.doc_id,
            "balance": self.balance,
            "createdAt": self.created_at.isoformat(),
        }
        if self.doc_url:
            data["docUrl"] = self.doc_url
        if self.file_request_link:
            data["fileRequestLink"] = self.file_request_link
        if self.google_meets_link:
            data["googleMeetsLink"] = self.google_meets_link
        if self.hw_upload_link:
            data["hwUploadLink"] = self.hw_upload_link
        return data

    @classmethod
    def from_dynamodb(cls, item: dict) -> "StudentV2":
        return cls(
            student_name=item["studentName"],
            doc_id=item["docId"],
            balance=float(item.get("balance", 0.0)),
            created_at=datetime.fromisoformat(item["createdAt"]),
            doc_url=item.get("docUrl"),
            file_request_link=item.get("fileRequestLink"),
            google_meets_link=item.get("googleMeetsLink"),
            hw_upload_link=item.get("hwUploadLink"),
        )


class StudentMetadataV2(BaseModel):
    """Manually generated student data."""
    student_name: str
    student_timezone: Optional[str] = None
    hourly_pricing: Optional[dict] = None
    phone_numbers: Optional[dict] = None
    no_show_custom_rate: Optional[float] = None
    payment_collected_by: Optional[str] = None
    discord_channel_reminder_id: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dynamodb(self) -> dict:
        data = {
            "studentName": self.student_name,
            "updatedAt": self.updated_at.isoformat(),
        }
        if self.student_timezone:
            data["studentTimezone"] = self.student_timezone
        if self.hourly_pricing:
            data["hourlyPricing"] = self.hourly_pricing
        if self.phone_numbers:
            data["phoneNumbers"] = self.phone_numbers
        if self.no_show_custom_rate is not None:
            data["noShowCustomRate"] = self.no_show_custom_rate
        if self.payment_collected_by:
            data["paymentCollectedBy"] = self.payment_collected_by
        if self.discord_channel_reminder_id:
            data["discordChannelReminderId"] = self.discord_channel_reminder_id
        return data

    @classmethod
    def from_dynamodb(cls, item: dict) -> "StudentMetadataV2":
        return cls(
            student_name=item["studentName"],
            student_timezone=item.get("studentTimezone"),
            hourly_pricing=item.get("hourlyPricing"),
            phone_numbers=item.get("phoneNumbers"),
            no_show_custom_rate=float(item["noShowCustomRate"]) if item.get("noShowCustomRate") is not None else None,
            payment_collected_by=item["paymentCollectedBy"] if item.get("paymentCollectedBy") else None,
            discord_channel_reminder_id=item.get("discordChannelReminderId"),
            updated_at=datetime.fromisoformat(item["updatedAt"]),
        )


class TransactionType(str, Enum):
    DEBIT = "DEBIT"    # Student owes money (weekly billing)
    CREDIT = "CREDIT"  # Student paid money

class Transaction(BaseModel):
    """Payment transaction record."""
    student_name: str  # Partition key
    transaction_key: str  # Sort key: "DEBIT#2026-03-01T18:00:00Z" or "CREDIT#2026-03-01T18:00:00Z"
    transaction_type: TransactionType
    amount: float
    action_by: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dynamodb(self) -> dict:
        return {
            "studentName": self.student_name,
            "transactionKey": self.transaction_key,
            "transactionType": self.transaction_type.value,
            "amount": self.amount,
            "actionBy": self.action_by,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dynamodb(cls, item: dict) -> "Transaction":
        return cls(
            student_name=item["studentName"],
            transaction_key=item["transactionKey"],
            transaction_type=TransactionType(item["transactionType"]),
            amount=float(item["amount"]),
            action_by=item["actionBy"],
            timestamp=datetime.fromisoformat(item["timestamp"]),
        )

    @classmethod
    def create_transaction_key(cls, transaction_type: TransactionType, timestamp: datetime) -> str:
        """Helper to create composite sort key."""
        return f"{transaction_type.value}#{timestamp.isoformat()}"


class StudentMetadataV2Update(BaseModel):
    student_timezone: Optional[str] = None
    hourly_pricing: Optional[dict] = None
    phone_numbers: Optional[dict] = None
    no_show_custom_rate: Optional[float] = None
    payment_collected_by: Optional[str] = None

class PaymentRecord(BaseModel):
    """Input model for recording a payment."""
    student_name: str
    amount: float
    action_by: str
    transaction_type: TransactionType = TransactionType.DEBIT
    
    def to_transaction(self) -> Transaction:
        """Convert to Transaction model with generated transaction_key."""
        timestamp = datetime.now(timezone.utc)
        return Transaction(
            student_name=self.student_name,
            transaction_key=Transaction.create_transaction_key(self.transaction_type, timestamp),
            transaction_type=self.transaction_type,
            amount=self.amount,
            action_by=self.action_by,
            timestamp=timestamp
        )
