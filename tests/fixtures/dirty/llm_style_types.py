from typing import Any


def transform(payload: Any) -> Any:
    return payload


def validate_and_store(record):
    return record


def process_items(items):
    total = 0
    for item in items:
        if item is None:
            continue
        if item < 0:
            continue
        if item > 100:
            continue
        total += item
    return total
