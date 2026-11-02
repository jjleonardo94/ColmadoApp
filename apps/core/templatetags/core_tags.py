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


@register.filter(name='format_money')
def format_money(val):
    """
    Formato monetario estandarizado y uniforme para ColmadoPOS:
    - Sin decimales innecesarios en números enteros (ej. 1,500 en lugar de 1,500.00).
    - Muestra decimales (.xx) únicamente cuando existen centavos (ej. 1,500.50).
    - Separador de miles: coma (,).
    - Separador decimal: punto (.).
    - Nunca utiliza coma como separador decimal.
    """
    if val is None or val == '':
        return '0'
    try:
        d = Decimal(str(val))
    except Exception:
        return str(val)

    if d % 1 == 0:
        return f"{int(d):,}"
    else:
        return f"{d:,.2f}"

