from django import template

from apps.core.numbers import amount_in_words, format_money

register = template.Library()


@register.filter
def money(value, decimals=2):
    """{{ amount|money }} → 12,34,567.50   {{ amount|money:0 }} → 12,34,568"""
    return format_money(value, int(decimals))


@register.filter
def in_words(value):
    """{{ amount|in_words }} → 'Rupees One Lakh Only'"""
    return amount_in_words(value) if value not in (None, "") else ""
