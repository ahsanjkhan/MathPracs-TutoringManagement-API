from boto3.dynamodb.conditions import Key

from src.config import get_settings
from src.functions import dynamodb
from src.models.business_internal_debt_model import BusinessInternalDebt
from src.models.student_v2_model import PaymentCollector, TransactionType

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


def get_net_outstanding_summary() -> str:
    ahsan = PaymentCollector.AHSAN.value
    muaz = PaymentCollector.MUAZ.value
    net = round(get_outstanding_owed_to(ahsan) - get_outstanding_owed_to(muaz), 2)
    if net > 0:
        return f"{muaz} owes {ahsan} ${net:.2f}"
    if net < 0:
        return f"{ahsan} owes {muaz} ${-net:.2f}"
    return "Nothing owed"
