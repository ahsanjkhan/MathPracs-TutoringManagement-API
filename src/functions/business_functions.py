from boto3.dynamodb.conditions import Key

from src.config import get_settings
from src.functions import dynamodb
from src.models.business_internal_debt_model import BusinessInternalDebt
from src.models.student_v2_model import TransactionType

settings = get_settings()


def get_outstanding_owed_to(partner: str) -> float:
    items = dynamodb.query_table(settings.business_internal_debts_table, Key("debtTo").eq(partner))
    outstanding = 0.0
    for item in items:
        debt = BusinessInternalDebt.from_dynamodb(item)
        if debt.transaction_type == TransactionType.DEBIT:
            outstanding += debt.amount
        else:
            outstanding -= debt.amount
    return round(outstanding, 2)
