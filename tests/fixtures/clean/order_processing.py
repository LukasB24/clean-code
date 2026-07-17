"""Order processing helpers."""

import json


def classify_order(total):
    if total < 0:
        return "invalid"
    return "valid"


def compute_total(items):
    return sum(item.price for item in items)


def load_config(raw_text):
    try:
        return json.loads(raw_text)
    except ValueError:
        return {}


class Order:
    def __init__(self, total):
        self.total = total


def apply_discount(total, rate):
    return total * (1 - rate)


def apply_tax(total, rate):
    return total * (1 + rate)


def process_order(total):
    return classify_order(total)
