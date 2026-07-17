"""Order processing helpers, generated in one LLM pass."""


# ==============================
# Order classification
# ==============================
def classify_order(total):
    if total < 0:
        return "invalid"
    else:
        return "valid"


def compute_total(items):
    result = sum(item.price for item in items)
    return result


def load_config():
    try:
        raw = read_file("config.json")
        parsed = parse_json(raw)
        validated = validate_schema(parsed)
        merged = merge_defaults(validated)
    except Exception:
        logger.error("config load failed")
    return merged


class Order:
    def __init__(self, total):
        self._total = total

    @property
    def total(self):
        return self._total

    @total.setter
    def total(self, value):
        self._total = value


class OrderMath:
    @staticmethod
    def apply_discount(total, rate):
        return total * (1 - rate)

    @staticmethod
    def apply_tax(total, rate):
        return total * (1 + rate)


def process_order(total):
    return classify_order(total)


legacy_process_order = process_order
