from decimal import Decimal, InvalidOperation


def parse_kz(val):
    """Converte string em formato pt_AO para Decimal string standard.

    '1 234,56' -> '1234.56'
    '1.234,56' -> '1234.56'  (compatibilidade retroativa)
    '1234,56'  -> '1234.56'
    '1234.56'  -> '1234.56'  (standard, pass-through)
    '558.000'  -> '558000'   (dot = milhar, 3+ dígitos após ponto)
    '1500'     -> '1500'
    ''         -> ''         (pass-through)
    None       -> None       (pass-through)
    """
    if not val:
        return val
    s = str(val).strip()
    if not s:
        return s
    s = s.replace(' ', '')
    if ',' in s:
        s = s.replace('.', '')
        s = s.replace(',', '.')
    elif '.' in s:
        if s.count('.') > 1:
            s = s.replace('.', '')
        else:
            parts = s.split('.')
            if len(parts) == 2 and len(parts[1]) >= 3:
                s = s.replace('.', '')
    return s


def fmt_kz(value):
    """Formata um valor numérico para pt_AO: 1 234,56

    Usado em Python (views, relatórios, etc.).
    Para uso em templates, usar o filtro |fmtkz.
    """
    if value is None:
        return ''
    try:
        d = Decimal(str(value)).quantize(Decimal('0.01'))
        if d < 0:
            prefix = '-'
            d = -d
        else:
            prefix = ''
        s = str(d)
        if '.' in s:
            integer_part, decimal_part = s.split('.')
        else:
            integer_part, decimal_part = s, '00'
        if len(decimal_part) == 1:
            decimal_part += '0'
        groups = []
        remaining = integer_part
        while remaining:
            groups.append(remaining[-3:])
            remaining = remaining[:-3]
            if not remaining:
                break
        integer_part = ' '.join(reversed(groups)) if groups else '0'
        return f'{prefix}{integer_part},{decimal_part}'
    except (ValueError, TypeError, InvalidOperation):
        return ''
