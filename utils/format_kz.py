from decimal import Decimal, InvalidOperation


def parse_kz(val):
    """Converte string em formato pt_AO para Decimal string standard.

    '1.234,56' -> '1234.56'
    '1234,56'  -> '1234.56'
    '1234.56'  -> '1234.56'  (standard, pass-through)
    '1500'     -> '1500'
    ''         -> ''         (pass-through)
    None       -> None       (pass-through)
    """
    if not val:
        return val
    s = str(val).strip()
    if not s:
        return s
    if ',' in s:
        # Formato angolano: '1.234,56' → '1234.56'
        s = s.replace('.', '')
        s = s.replace(',', '.')
    elif '.' in s and s.count('.') > 1:
        # Múltiplos pontos sem vírgula: '1.234.567' → '1234567'
        # Único ponto: '1234.56' (standard decimal) ou '1.000' (milhar) — ambíguo, preservar
        s = s.replace('.', '')
    return s


def fmt_kz(value):
    """Formata um valor numérico para pt_AO: 1.234,56

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
        # Inserir ponto separador de milhares
        groups = []
        remaining = integer_part
        while remaining:
            groups.append(remaining[-3:])
            remaining = remaining[:-3]
            if not remaining:
                break
        integer_part = '.'.join(reversed(groups)) if groups else '0'
        return f'{prefix}{integer_part},{decimal_part}'
    except (ValueError, TypeError, InvalidOperation):
        return ''
