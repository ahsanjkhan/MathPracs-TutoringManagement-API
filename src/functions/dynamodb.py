import boto3
from typing import Any
from src.config import get_settings
from decimal import Decimal
import json

settings = get_settings()
_dynamodb = None


def _to_dynamodb_safe(obj: Any) -> Any:
    """Convert floats to Decimal for DynamoDB compatibility."""
    return json.loads(json.dumps(obj), parse_float=Decimal)


def get_dynamodb():
    """Get or create a cached DynamoDB resource instance."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    return _dynamodb


def get_table(table_name: str):
    """Get a DynamoDB table by name."""
    return get_dynamodb().Table(table_name)


def put_item(table_name: str, item: dict[str, Any]) -> None:
    """Insert or replace an item in a DynamoDB table."""
    table = get_table(table_name)
    table.put_item(Item=_to_dynamodb_safe(item))


def get_item(table_name: str, key: dict[str, Any]) -> dict[str, Any] | None:
    """Get a single item by primary key. Returns None if not found."""
    table = get_table(table_name)
    response = table.get_item(Key=key)
    return response.get("Item")


def query_table(table_name: str, key_condition, **kwargs) -> list[dict[str, Any]]:
    """Query a table by key condition. Handles pagination automatically."""
    table = get_table(table_name)

    items = []
    query_kwargs = {"KeyConditionExpression": key_condition, **kwargs}

    response = table.query(**query_kwargs)
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.query(**query_kwargs)
        items.extend(response.get("Items", []))

    return items


def update_item(table_name: str, key: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Update specific fields on an item. Returns the updated item."""
    table = get_table(table_name)
    update_expr_parts = []
    expr_attr_names = {}
    expr_attr_values = {}

    for i, (k, v) in enumerate(updates.items()):
        update_expr_parts.append(f"#{k} = :val{i}")
        expr_attr_names[f"#{k}"] = k
        expr_attr_values[f":val{i}"] = _to_dynamodb_safe(v)

    response = table.update_item(
        Key=key,
        UpdateExpression="SET " + ", ".join(update_expr_parts),
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values,
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def delete_item(table_name: str, key: dict[str, Any]) -> None:
    """Delete an item by primary key."""
    table = get_table(table_name)
    table.delete_item(Key=key)


def scan_table(table_name: str, filter_expression=None, **kwargs) -> list[dict[str, Any]]:
    """Scan entire table with optional filter. Handles pagination automatically."""
    table = get_table(table_name)
    scan_kwargs = kwargs
    if filter_expression:
        scan_kwargs["FilterExpression"] = filter_expression

    items = []
    response = table.scan(**scan_kwargs)
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))

    return items


def query_by_gsi(table_name: str, index_name: str, key_condition, **kwargs) -> list[dict[str, Any]]:
    """Query a Global Secondary Index by key condition."""
    table = get_table(table_name)
    response = table.query(IndexName=index_name, KeyConditionExpression=key_condition, **kwargs)
    return response.get("Items", [])
