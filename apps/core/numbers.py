"""Money / number display that follows the company's grouping choice (1,234,567 or 12,34,567)."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .middleware import current_company


def group_digits(digits, style):
    if style == "indian" and len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        return ",".join(parts + [tail])
    parts = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return ",".join(parts)


def format_money(value, decimals=2, style=None):
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    if style is None:
        style = current_company().number_grouping
    quant = Decimal(1).scaleb(-decimals) if decimals else Decimal(1)
    number = number.quantize(quant, rounding=ROUND_HALF_UP)
    sign = "-" if number < 0 else ""
    whole, _sep, frac = f"{abs(number):f}".partition(".")
    text = group_digits(whole, style)
    return f"{sign}{text}.{frac}" if decimals else f"{sign}{text}"
