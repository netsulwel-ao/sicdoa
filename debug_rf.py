import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')
django.setup()

from financeiro.models import RequisicaoFundo

rf = RequisicaoFundo.objects.filter(numero_requisicao='RF-2026/001').first()
if rf:
    print(f'=== RequisicaoFundo #{rf.id} ===')
    print(f'Número: {rf.numero_requisicao}')
    print(f'Cliente: {rf.cliente.nome if rf.cliente else "NULL"}')
    print(f'DU: {rf.processo_aduaneiro.numero_du if rf.processo_aduaneiro else "NULL"}')
    print(f'Data validade: {rf.data_validade}')
    print(f'Estado: {rf.estado}')
    print(f'Total: {rf.total_geral}')
    print(f'Valor pago: {rf.valor_pago}')
    print(f'Linhas: {rf.linhas.count()}')
    print(f'Criado por: {rf.criado_por_nome}')
    print(f'Banca: {rf.banca}')
    print(f'Origem: {rf.origem}')
    print(f'Destino: {rf.destino}')
    print(f'Banco: {rf.banco}')
    print(f'Conta: {rf.numero_conta}')
else:
    print('Nenhuma requisição encontrada')
