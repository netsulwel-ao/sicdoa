import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')
django.setup()

from financeiro.models import RequisicaoFundo
from decimal import Decimal

# Test the numero_para_extenso function
def numero_para_extenso(num):
    if num == 0:
        return 'zero'
    
    unidades = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove']
    dezenas = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
    teens = ['dez', 'onze', 'doze', 'treze', 'catorze', 'quinze', 'dezasseis', 'dezassete', 'dezoito', 'dezanove']
    centenas = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']
    
    def ate_999(n):
        if n == 0:
            return ''
        elif n < 10:
            return unidades[n]
        elif n < 20:
            return teens[n - 10]
        elif n < 100:
            d, u = divmod(n, 10)
            if u == 0:
                return dezenas[d]
            return f"{dezenas[d]} e {unidades[u]}"
        else:
            c, resto = divmod(n, 100)
            if c == 1 and resto == 0:
                return 'cem'
            elif resto == 0:
                return centenas[c]
            return f"{centenas[c]} e {ate_999(resto)}"
    
    # Grupos: unidades, milhares, milhões
    if num < 1000:
        return ate_999(num)
    elif num < 1000000:
        milhares, resto = divmod(num, 1000)
        m_txt = 'mil' if milhares == 1 else f"{ate_999(milhares)} mil"
        if resto == 0:
            return m_txt
        return f"{m_txt} e {ate_999(resto)}"
    else:
        milhoes, resto = divmod(num, 1000000)
        m_txt = 'um milhão' if milhoes == 1 else f"{ate_999(milhoes)} milhões"
        if resto == 0:
            return m_txt
        elif resto < 1000:
            return f"{m_txt} e {ate_999(resto)}"
        else:
            return f"{m_txt}, {numero_para_extenso(resto)}"

# Test with some sample values
test_values = [45000, 100000, 250000, 1500000, 2345678]

print("=== TESTE DE CONVERSÃO PARA EXTENSO ===\n")

for val in test_values:
    extenso = numero_para_extenso(val)
    print(f"{val:>12,} -> {extenso.capitalize()} kwanzas")

print("\n=== TESTE COM REQUISIÇÕES REAIS ===\n")

requisicoes = RequisicaoFundo.objects.all()[:5]
if requisicoes:
    for req in requisicoes:
        print(f"Req: {req.numero_requisicao}")
        print(f"  Total: {req.total_geral}")
        print(f"  Extenso: {req.valor_total_extenso}")
        print()
else:
    print("Nenhuma requisição encontrada")
