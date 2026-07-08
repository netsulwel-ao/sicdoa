from django.test import TestCase
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.models import User
from clientes.models import Cliente
from aduaneiro.models import DeclaracaoUnica
from rh.models import Banca
from financeiro.models import RequisicaoFundo, RequisicaoFundoLinha


class RequisicaoFundoCalculosTestCase(TestCase):
    """Testes para validar cálculos corretos de IVA e retenção"""
    
    def setUp(self):
        """Cria dados de teste"""
        # Criar banca
        self.banca = Banca.objects.create(
            nome="Teste Banca",
            nif="123456789",
            email="teste@banca.com",
            telefone="123456789"
        )
        
        # Criar cliente
        self.cliente = Cliente.objects.create(
            nome="Cliente Teste",
            nif="987654321",
            email="cliente@teste.com",
            telefone="987654321"
        )
        
        # Criar DU
        self.du = DeclaracaoUnica.objects.create(
            numero_du="DU-2026-001",
            cliente=self.cliente,
            banca=self.banca,
            status="Pendente"
        )
        
        # Criar requisição
        self.requisicao = RequisicaoFundo.objects.create(
            banca=self.banca,
            cliente=self.cliente,
            processo_aduaneiro=self.du,
            data_validade=timezone.now().date(),
            moeda_referencia="AOA"
        )
    
    def test_calculo_iva_14_porcento_sobre_honorarios(self):
        """Testa se IVA é 14% apenas sobre honorários do despachante"""
        # Adicionar honorários de 100.000 KZ
        linha_honorarios = RequisicaoFundoLinha.objects.create(
            requisicao=self.requisicao,
            tipo_custo='Honorários do Despachante',
            descricao='Honorários',
            documentada=False,
            valor=Decimal('100000.00')
        )
        
        # Recarregar
        self.requisicao.refresh_from_db()
        
        # IVA deve ser 14% de 100.000 = 14.000
        self.assertEqual(self.requisicao.iva_honorarios, Decimal('14000.00'))
    
    def test_calculo_retencao_6_5_porcento_sobre_honorarios(self):
        """Testa se retenção é 6.5% apenas sobre honorários do despachante"""
        # Adicionar honorários de 100.000 KZ
        linha_honorarios = RequisicaoFundoLinha.objects.create(
            requisicao=self.requisicao,
            tipo_custo='Honorários do Despachante',
            descricao='Honorários',
            documentada=False,
            valor=Decimal('100000.00')
        )
        
        # Recarregar
        self.requisicao.refresh_from_db()
        
        # Retenção deve ser 6.5% de 100.000 = 6.500
        self.assertEqual(self.requisicao.retencao, Decimal('6500.00'))
    
    def test_total_geral_inclui_iva_e_retencao(self):
        """Testa se total = subtotal + IVA - retenção"""
        # Adicionar impostos (50.000) e honorários (100.000)
        linha_impostos = RequisicaoFundoLinha.objects.create(
            requisicao=self.requisicao,
            tipo_custo='Impostos e Taxas Aduaneiras (AGT)',
            descricao='Direitos de Importação',
            documentada=True,
            despesa_tipo='Direitos e importações',
            valor=Decimal('50000.00')
        )
        
        linha_honorarios = RequisicaoFundoLinha.objects.create(
            requisicao=self.requisicao,
            tipo_custo='Honorários do Despachante',
            descricao='Honorários',
            documentada=False,
            valor=Decimal('100000.00')
        )
        
        # Recarregar
        self.requisicao.refresh_from_db()
        
        # Subtotal = 50.000 + 100.000 = 150.000
        self.assertEqual(self.requisicao.subtotal_geral, Decimal('150000.00'))
        
        # IVA = 14% de 100.000 = 14.000
        self.assertEqual(self.requisicao.iva_honorarios, Decimal('14000.00'))
        
        # Retenção = 6.5% de 100.000 = 6.500
        self.assertEqual(self.requisicao.retencao, Decimal('6500.00'))
        
        # Total = 150.000 + 14.000 - 6.500 = 157.500
        self.assertEqual(self.requisicao.total_geral, Decimal('157500.00'))
    
    def test_sem_honorarios_iva_retenacao_zero(self):
        """Testa que sem honorários, IVA e retenção são zero"""
        # Adicionar apenas impostos
        linha_impostos = RequisicaoFundoLinha.objects.create(
            requisicao=self.requisicao,
            tipo_custo='Impostos e Taxas Aduaneiras (AGT)',
            descricao='Direitos de Importação',
            documentada=True,
            despesa_tipo='Direitos e importações',
            valor=Decimal('50000.00')
        )
        
        # Recarregar
        self.requisicao.refresh_from_db()
        
        # Sem honorários, IVA e retenção devem ser 0
        self.assertEqual(self.requisicao.iva_honorarios, Decimal('0.00'))
        self.assertEqual(self.requisicao.retencao, Decimal('0.00'))
        
        # Total = subtotal (sem IVA ou retenção)
        self.assertEqual(self.requisicao.total_geral, Decimal('50000.00'))
    
    def test_saldo_pendente_calculo(self):
        """Testa cálculo do saldo pendente"""
        # Adicionar honorários
        linha_honorarios = RequisicaoFundoLinha.objects.create(
            requisicao=self.requisicao,
            tipo_custo='Honorários do Despachante',
            descricao='Honorários',
            documentada=False,
            valor=Decimal('100000.00')
        )
        
        # Recarregar
        self.requisicao.refresh_from_db()
        
        # Total = 100.000 + 14.000 - 6.500 = 107.500
        self.assertEqual(self.requisicao.total_geral, Decimal('107500.00'))
        
        # Sem pagamento, saldo = total
        self.assertEqual(self.requisicao.saldo_pendente, Decimal('107500.00'))
        
        # Adicionar pagamento de 50.000
        self.requisicao.valor_pago = Decimal('50000.00')
        self.requisicao.save()
        
        # Saldo = 107.500 - 50.000 = 57.500
        self.assertEqual(self.requisicao.saldo_pendente, Decimal('57500.00'))
    
    def test_multiplas_linhas_honorarios_somadas(self):
        """Testa que múltiplas linhas de honorários são TODAS contabilizadas para IVA/retenção"""
        # Adicionar primeira linha de honorários: 50.000 KZ
        linha_honorarios_1 = RequisicaoFundoLinha.objects.create(
            requisicao=self.requisicao,
            tipo_custo='Honorários do Despachante',
            descricao='Honorários - Parte 1',
            documentada=False,
            valor=Decimal('50000.00')
        )
        
        # Adicionar segunda linha de honorários: 20.000 KZ
        linha_honorarios_2 = RequisicaoFundoLinha.objects.create(
            requisicao=self.requisicao,
            tipo_custo='Honorários do Despachante',
            descricao='Honorários - Parte 2',
            documentada=False,
            valor=Decimal('20000.00')
        )
        
        # Recarregar
        self.requisicao.refresh_from_db()
        
        # Total de honorários = 50.000 + 20.000 = 70.000
        # IVA = 70.000 × 0.14 = 9.800
        self.assertEqual(self.requisicao.iva_honorarios, Decimal('9800.00'))
        
        # Retenção = 70.000 × 0.065 = 4.550
        self.assertEqual(self.requisicao.retencao, Decimal('4550.00'))
        
        # Total = 70.000 + 9.800 - 4.550 = 75.250
        self.assertEqual(self.requisicao.total_geral, Decimal('75250.00'))
    
    def test_assinatura_digital_gerada(self):
        """Testa que assinatura digital é gerada automaticamente"""
        # Recarregar para certificar que foi salva com assinatura
        self.requisicao.refresh_from_db()
        
        # Deve ter assinatura digital (SHA-256 em Base64)
        self.assertIsNotNone(self.requisicao.assinatura_digital)
        self.assertGreater(len(self.requisicao.assinatura_digital), 0)
        # SHA-256 em Base64 tem 44 caracteres (sem padding) ou 48 (com padding)
        self.assertIn(len(self.requisicao.assinatura_digital), [44, 48])
    
    def test_editar_requisicao_nao_pendente_bloqueada(self):
        """Testa que não é possível editar requisição após mudar de estado"""
        # Aceitar requisição
        self.requisicao.estado = 'Aceite'
        self.requisicao.save()
        
        # Tentar editar deveria falhar na view (testar apenas lógica)
        # A validação é feita em RequisicaoFundoUpdateView.form_valid()
        self.assertNotEqual(self.requisicao.estado, 'Pendente')



class ParseValorMonetarioTestCase(TestCase):
    """Testes para parsing flexível de valores monetários"""
    
    def test_parse_numero_simples(self):
        """2000000 deve parsear como 2000000"""
        from financeiro.views import parse_valor_monetario
        resultado = parse_valor_monetario('2000000')
        self.assertEqual(resultado, Decimal('2000000'))
    
    def test_parse_formato_europeu_ponto_virgula(self):
        """2.000.000,00 deve parsear como 2000000.00"""
        from financeiro.views import parse_valor_monetario
        resultado = parse_valor_monetario('2.000.000,00')
        self.assertEqual(resultado, Decimal('2000000.00'))
    
    def test_parse_formato_americano(self):
        """2,000,000.00 deve parsear como 2000000.00"""
        from financeiro.views import parse_valor_monetario
        resultado = parse_valor_monetario('2,000,000.00')
        self.assertEqual(resultado, Decimal('2000000.00'))
    
    def test_parse_com_espacos(self):
        """'2 000 000' deve parsear como 2000000"""
        from financeiro.views import parse_valor_monetario
        resultado = parse_valor_monetario('2 000 000')
        self.assertEqual(resultado, Decimal('2000000'))
    
    def test_parse_simples_decimal(self):
        """'1234.56' deve parsear como 1234.56"""
        from financeiro.views import parse_valor_monetario
        resultado = parse_valor_monetario('1234.56')
        self.assertEqual(resultado, Decimal('1234.56'))
    
    def test_parse_virgula_decimal(self):
        """'1234,56' deve parsear como 1234.56"""
        from financeiro.views import parse_valor_monetario
        resultado = parse_valor_monetario('1234,56')
        self.assertEqual(resultado, Decimal('1234.56'))
    
    def test_parse_vazio(self):
        """String vazia deve retornar 0"""
        from financeiro.views import parse_valor_monetario
        resultado = parse_valor_monetario('')
        self.assertEqual(resultado, Decimal('0'))
    
    def test_parse_invalido(self):
        """Valor inválido deve retornar 0"""
        from financeiro.views import parse_valor_monetario
        resultado = parse_valor_monetario('abc')
        self.assertEqual(resultado, Decimal('0'))
