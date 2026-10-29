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


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_thousand(n):
    words = []
    if n >= 100:
        words += [_ONES[n // 100], "Hundred"]
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        words.append(_ONES[n])
    return " ".join(words)


def number_in_words(n, style="international"):
    n = int(n)
    if n == 0:
        return "Zero"
    if style == "indian":
        scales = [(10 ** 7, "Crore"), (10 ** 5, "Lakh"), (1000, "Thousand")]
    else:
        scales = [(10 ** 9, "Billion"), (10 ** 6, "Million"), (1000, "Thousand")]
    words = []
    for size, name in scales:
        if n >= size:
            words += [number_in_words(n // size, style), name]
            n %= size
    if n:
        words.append(_below_thousand(n))
    return " ".join(words)


def amount_in_words(value, company=None):
    """12,34,567.50 → 'Rupees Twelve Lakh Thirty-Four Thousand Five Hundred Sixty-Seven and Fifty Paise Only'."""
    company = company or current_company()
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole = int(abs(amount))
    fraction = int((abs(amount) - whole) * 100)
    text = f"{company.currency_name} {number_in_words(whole, company.number_grouping)}".strip()
    if fraction:
        text += f" and {number_in_words(fraction)} {company.currency_fraction_name}".rstrip()
    return text + " Only"
