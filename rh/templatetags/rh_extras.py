from django import template
from utils.format_kz import fmt_kz

register = template.Library()


@register.filter
def abs_value(value):
    """Retorna o valor absoluto."""
    if value is None:
        return 0
    return abs(value)


@register.filter
def fmtkz(value, default=''):
    """Formata um Decimal para o formato angolano: 1.234,56

    Uso:  {{ valor|fmtkz }}         → '9.999,81'  (ou '' se None)
          {{ valor|fmtkz:'0' }}     → '0,00'      (fallback se None/vazio)
    """
    if value is None or value == '':
        return default
    result = fmt_kz(value)
    return result if result else default
