from decimal import Decimal, InvalidOperation
import bcrypt

from utils.format_kz import parse_kz


MESES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
         'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']

DIAS_UTEIS_MES = Decimal('22')

INSS_TAXA_TRABALHADOR = Decimal('0.03')
INSS_TAXA_ENTIDADE = Decimal('0.08')

# Tabela IRT Angola OGE 2026 — escalões mensais (KZ)
IRT_TABELA = [
    (Decimal('150000'),  Decimal('0'),      Decimal('0')),
    (Decimal('200000'),  Decimal('8000'),   Decimal('0.16')),
    (Decimal('300000'),  Decimal('26000'),  Decimal('0.18')),
    (Decimal('500000'),  Decimal('64000'),  Decimal('0.19')),
    (Decimal('1000000'), Decimal('164000'), Decimal('0.20')),
    (Decimal('1500000'), Decimal('269000'), Decimal('0.21')),
    (Decimal('2000000'), Decimal('379000'), Decimal('0.22')),
    (Decimal('5000000'), Decimal('1069000'),Decimal('0.23')),
    (Decimal('10000000'),Decimal('2269000'),Decimal('0.24')),
    (None,              Decimal('2269000'),Decimal('0.25')),
]

# Imposto sobre Serviço (taxa aplicada sobre o valor bruto)
TAXA_SERVICO = Decimal('0.05')


def _dec(val, default=Decimal('0')):
    try:
        parsed = parse_kz(val)
        return Decimal(str(parsed)) if parsed else default
    except (InvalidOperation, ValueError, TypeError):
        return default


def _hash_password(senha):
    if not senha:
        return None
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(senha.encode('utf-8'), salt)
    return hashed.decode('utf-8').replace('$2b$', '$2y$')


def _calcular_irt(salario: Decimal) -> Decimal:
    if salario <= Decimal('150000'):
        irt = Decimal('0')
    elif salario <= Decimal('200000'):
        irt = (salario - Decimal('150000')) * Decimal('0.16')
    elif salario <= Decimal('300000'):
        irt = Decimal('8000') + (salario - Decimal('200000')) * Decimal('0.18')
    elif salario <= Decimal('500000'):
        irt = Decimal('26000') + (salario - Decimal('300000')) * Decimal('0.19')
    elif salario <= Decimal('1000000'):
        irt = Decimal('64000') + (salario - Decimal('500000')) * Decimal('0.20')
    elif salario <= Decimal('1500000'):
        irt = Decimal('164000') + (salario - Decimal('1000000')) * Decimal('0.21')
    elif salario <= Decimal('2000000'):
        irt = Decimal('269000') + (salario - Decimal('1500000')) * Decimal('0.22')
    elif salario <= Decimal('5000000'):
        irt = Decimal('379000') + (salario - Decimal('2000000')) * Decimal('0.23')
    elif salario <= Decimal('10000000'):
        irt = Decimal('1069000') + (salario - Decimal('5000000')) * Decimal('0.24')
    else:
        irt = Decimal('2269000') + (salario - Decimal('10000000')) * Decimal('0.25')
    return Decimal(str(round(irt, 2)))
