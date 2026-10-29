from django import template
from decimal import Decimal

register = template.Library()

@register.filter(name='abs')
def abs_filter(val):
    """
    Retorna el valor absoluto de un número (Decimal, float o int).
    """
    if val is None:
        return Decimal('0.00')
    try:
        return abs(val)
    except Exception:
        return val
