from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PaymentCollector(str, Enum):
    MUAZ = "muaz"
    AHSAN = "ahsan"
    BUSINESS = "business"


class PhoneNumber(BaseModel):
    phone_number: str
    sms_enabled: bool = False


class StudentV2(BaseModel):
    """Operational student data - includes balance field."""
    student_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    doc_id: str
    doc_url: Optional[str] = None
    file_request_link: Optional[str] = None
    google_meets_link: Optional[str] = None
    hw_upload_link: Optional[str] = None
    balance: float = 0.0  # New field for payment tracking

    def to_dynamodb(self) -> dict:
        data = {
            "studentName": self.student_name,
            "createdAt": self.created_at.isoformat(),
            "docId": self.doc_id,
            "balance": self.balance,
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
            created_at=datetime.fromisoformat(item["createdAt"]),
            doc_id=item["docId"],
            doc_url=item.get("docUrl"),
            file_request_link=item.get("fileRequestLink"),
            google_meets_link=item.get("googleMeetsLink"),
            hw_upload_link=item.get("hwUploadLink"),
            balance=float(item.get("balance", 0.0)),
        )


class StudentMetadataV2(BaseModel):
    """Manually configured student data."""
    student_name: str
    hourly_pricing: Optional[dict] = None  # Flexible pricing structure
    phone_numbers: Optional[dict] = None   # Phone numbers with SMS preferences
    student_timezone: Optional[str] = None
    no_show_custom_rate: Optional[float] = None
    payment_collected_by: Optional[PaymentCollector] = None
    discord_channel_reminder_id: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dynamodb(self) -> dict:
        data = {
            "studentName": self.student_name,
            "updatedAt": self.updated_at.isoformat(),
        }
        if self.hourly_pricing:
            data["hourlyPricing"] = self.hourly_pricing
        if self.phone_numbers:
            data["phoneNumbers"] = self.phone_numbers
        if self.student_timezone:
            data["studentTimezone"] = self.student_timezone
        if self.no_show_custom_rate is not None:
            data["noShowCustomRate"] = self.no_show_custom_rate
        if self.payment_collected_by:
            data["paymentCollectedBy"] = self.payment_collected_by.value
        if self.discord_channel_reminder_id:
            data["discordChannelReminderId"] = self.discord_channel_reminder_id
        return data

    @classmethod
    def from_dynamodb(cls, item: dict) -> "StudentMetadataV2":
        return cls(
            student_name=item["studentName"],
            hourly_pricing=item.get("hourlyPricing"),
            phone_numbers=item.get("phoneNumbers"),
            student_timezone=item.get("studentTimezone"),
            no_show_custom_rate=float(item["noShowCustomRate"]) if item.get("noShowCustomRate") is not None else None,
            payment_collected_by=PaymentCollector(item["paymentCollectedBy"]) if item.get("paymentCollectedBy") else None,
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
    action_by: str  # Who performed the action
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_dynamodb(self) -> dict:
        return {
            "studentName": self.student_name,
            "transactionKey": self.transaction_key,  # Sort key
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


class StudentV2Update(BaseModel):
    doc_url: Optional[str] = None
    file_request_link: Optional[str] = None
    google_meets_link: Optional[str] = None
    hw_upload_link: Optional[str] = None


class StudentMetadataV2Update(BaseModel):
    hourly_pricing: Optional[dict] = None
    phone_numbers: Optional[dict] = None
    student_timezone: Optional[str] = None
    no_show_custom_rate: Optional[float] = None
    payment_collected_by: Optional[PaymentCollector] = None


class PaymentRecord(BaseModel):
    """Input model for recording a payment."""
    student_name: str
    amount: float
    action_by: str  # Who recorded the payment
    transaction_type: TransactionType = TransactionType.DEBIT  # Defaults to DEBIT
    
    def to_transaction(self) -> Transaction:
        """Convert to Transaction model with generated transaction_key."""
        timestamp = datetime.utcnow()
        return Transaction(
            student_name=self.student_name,
            transaction_key=Transaction.create_transaction_key(self.transaction_type, timestamp),
            transaction_type=self.transaction_type,
            amount=self.amount,
            action_by=self.action_by,
            timestamp=timestamp
        )
