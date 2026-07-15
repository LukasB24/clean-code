import logging

logger = logging.getLogger(__name__)

LARGE_ORDER_THRESHOLD = 500
LARGE_ORDER_DISCOUNT_RATE = 0.15
STANDARD_DISCOUNT_RATE = 0.05


def calc_order_discount(user, order):
    discount = 0.0
    if user.active:
        if order.total > LARGE_ORDER_THRESHOLD:
            discount = order.total * LARGE_ORDER_DISCOUNT_RATE
        else:
            discount = order.total * STANDARD_DISCOUNT_RATE
    try:
        charge(order, order.total - discount)
    except PaymentError:
        logger.exception("charge failed for order %s", order.id)
    return discount
