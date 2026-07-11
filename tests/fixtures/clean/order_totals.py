"""Aggregate raw order rows into per-customer spending totals."""

from collections import defaultdict


def spending_by_customer(order_rows):
    """Sums order amounts per customer, skipping refunded orders.

    Refunds arrive as negative amounts and are excluded here because the
    finance export already accounts for them separately.
    """
    totals = defaultdict(float)
    for order in order_rows:
        if order.amount < 0:
            continue
        totals[order.customer_id] += order.amount
    return dict(totals)


def top_customers(totals, count):
    ranked = sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
    return ranked[:count]
