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


@register.filter
def check_perm(args, perm_dict):
    """Verifica se 'col_pk|perm_codigo' existe no dict. Uso: {{ col.pk|add:'_'|add:perm.codigo|check_perm:perm_checked }}"""
    return args in perm_dict


@register.filter
def union_set(set_a, set_b):
    """Retorna a união de dois sets."""
    if not set_a:
        return set_b or set()
    if not set_b:
        return set_a
    return set_a | set_b


@register.filter
def in_set(value, the_set):
    """Verifica se value está no the_set (set, list ou dict keys)."""
    if not the_set:
        return False
    return value in the_set


@register.filter
def multiply(value, arg):
    """Multiplica dois valores. Uso: {{ total|multiply:100 }}"""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0
