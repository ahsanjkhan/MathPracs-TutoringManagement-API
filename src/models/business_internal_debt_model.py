from datetime import datetime, timezone
from pydantic import BaseModel, Field

from src.models.student_v2_model import PaymentCollector, Transaction, TransactionType

PARTNERS = {PaymentCollector.AHSAN.value, PaymentCollector.MUAZ.value}


class BusinessInternalDebt(BaseModel):
    debt_to: str
    transaction_key: str
    transaction_type: TransactionType
    amount: float
    action_by: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dynamodb(self) -> dict:
        return {
            "debtTo": self.debt_to,
            "transactionKey": self.transaction_key,
            "transactionType": self.transaction_type.value,
            "amount": self.amount,
            "actionBy": self.action_by,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dynamodb(cls, item: dict) -> "BusinessInternalDebt":
        return cls(
            debt_to=item["debtTo"],
            transaction_key=item["transactionKey"],
            transaction_type=TransactionType(item["transactionType"]),
            amount=float(item["amount"]),
            action_by=item["actionBy"],
            timestamp=datetime.fromisoformat(item["timestamp"]),
        )


class PartnerPaymentRecord(BaseModel):
    amount: float
    action_by: str
    transaction_type: TransactionType = TransactionType.CREDIT

    def to_debt(self) -> BusinessInternalDebt:
        timestamp = datetime.now(timezone.utc)
        return BusinessInternalDebt(
            debt_to=self.action_by,
            transaction_key=Transaction.create_transaction_key(self.transaction_type, timestamp),
            transaction_type=self.transaction_type,
            amount=self.amount,
            action_by=self.action_by,
            timestamp=timestamp
        )
