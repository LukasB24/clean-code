"""Fixture: docstrings/comments near CM307's boundary that must never flag.

The false-positive net for the semantic tier: composite what+why texts,
rationale-only texts, noun-led value contracts, and wrapped comment blocks
whose rationale sits on the second line.
"""


def blocked_multiply(matrix_a, matrix_b):
    """Computes matrix multiplication using block-striping to maximize L1 cache hits."""
    product_rows = []
    for row in matrix_a:
        product_rows.append(row_product(row, matrix_b))
    return product_rows


def row_product(row, matrix):
    """Kept separate from the blocked walk so the stripe logic stays testable alone."""
    return [dot(row, column) for column in transposed(matrix)]


def transposed(matrix):
    """Columns of ``matrix`` as rows, materialized once per multiply."""
    return list(zip(*matrix))


def dot(left_vector, right_vector):
    """Assumes equal lengths; the caller validated both shapes at the boundary."""
    return sum(left * right for left, right in zip(left_vector, right_vector))


def monthly_totals(ledger_rows):
    """Amounts are in cents to avoid floating-point money bugs."""
    totals = {}
    # Recomputed on every call rather than cached, because a stale
    # figure here is worse than the extra pass over the ledger.
    for ledger_row in ledger_rows:
        month_key = ledger_row.month
        running_cents = totals.get(month_key, 0)
        totals[month_key] = running_cents + ledger_row.cents
    return totals
