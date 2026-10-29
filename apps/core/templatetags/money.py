from django import template

from apps.core.numbers import format_money

register = template.Library()


@register.filter
def money(value, decimals=2):
    """{{ amount|money }} → 12,34,567.50   {{ amount|money:0 }} → 12,34,568"""
    return format_money(value, int(decimals))
