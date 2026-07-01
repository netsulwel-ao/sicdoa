from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse
from utils.format_kz import parse_kz, fmt_kz
from rh.templatetags.rh_extras import fmtkz
from rh.views import _dec as _dec_views, _remover_gestor_filial
from rh.tax_utils import _dec, _hash_password, _calcular_irt, DIAS_UTEIS_MES, INSS_TAXA_TRABALHADOR, INSS_TAXA_ENTIDADE
from rh.models import (
    Banca, Colaborador, Subsidio, PedidoFerias,
    ProcessamentoSalarial, ReciboSalarial, SubsidioRecibo,
    FilialBanca, GestorFilial,
)


def _setup_request(factory, url, banca_id=1):
    """Cria um request com sessão, mensagens e banca_id para views com _requer_sessao."""
    request = factory.get(url)
    request.user = type('obj', (object,), {'is_authenticated': True})()
    request.banca_id = banca_id
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session['usuario_id'] = 1
    request.session['usuario'] = {
        'email': 'adilsona87@gmail.com',
        'nome': 'Admin Teste',
        'papel': 'Administrador',
    }
    request.session.save()
    setattr(request, '_messages', FallbackStorage(request))
    return request


# ─── Tests: Utils ───────────────────────────────────────────────────

class FormatKZTests(TestCase):

    def test_parse_kz_angolan_format(self):
        """'1.234,56' → '1234.56'"""
        self.assertEqual(parse_kz('1.234,56'), '1234.56')

    def test_parse_kz_comma_only(self):
        """'1234,56' → '1234.56'"""
        self.assertEqual(parse_kz('1234,56'), '1234.56')

    def test_parse_kz_standard(self):
        """'1234.56' → '1234.56' (pass-through, standard decimal)"""
        self.assertEqual(parse_kz('1234.56'), '1234.56')

    def test_parse_kz_multiple_dots(self):
        """'1.234.567' (múltiplos dots, sem vírgula) → '1234567' (milhares)"""
        self.assertEqual(parse_kz('1.234.567'), '1234567')

    def test_parse_kz_integer(self):
        """'1500' → '1500'"""
        self.assertEqual(parse_kz('1500'), '1500')

    def test_parse_kz_empty(self):
        """'' → ''"""
        self.assertEqual(parse_kz(''), '')

    def test_parse_kz_none(self):
        """None → None"""
        self.assertIsNone(parse_kz(None))

    def test_parse_kz_large_number(self):
        """'1.234.567,89' → '1234567.89'"""
        self.assertEqual(parse_kz('1.234.567,89'), '1234567.89')

    def test_parse_kz_single_dot_no_comma(self):
        """'1.000' (1 dot, sem vírgula) → '1000' (milhar, pois 3 dígitos após ponto)"""
        self.assertEqual(parse_kz('1.000'), '1000')

    def test_fmt_kz_standard(self):
        """Decimal('1234.56') → '1 234,56'"""
        self.assertEqual(fmt_kz(Decimal('1234.56')), '1 234,56')

    def test_fmt_kz_integer(self):
        """Decimal('1500') → '1 500,00'"""
        self.assertEqual(fmt_kz(Decimal('1500')), '1 500,00')

    def test_fmt_kz_zero(self):
        """Decimal('0') → '0,00'"""
        self.assertEqual(fmt_kz(Decimal('0')), '0,00')

    def test_fmt_kz_small(self):
        """Decimal('5.5') → '5,50'"""
        self.assertEqual(fmt_kz(Decimal('5.5')), '5,50')

    def test_fmt_kz_none(self):
        """None → ''"""
        self.assertEqual(fmt_kz(None), '')

    def test_fmt_kz_negative(self):
        """Decimal('-1234.56') → '-1 234,56'"""
        self.assertEqual(fmt_kz(Decimal('-1234.56')), '-1 234,56')

    def test_fmt_kz_thousands(self):
        """Decimal('1000000.00') → '1 000 000,00'"""
        self.assertEqual(fmt_kz(Decimal('1000000.00')), '1 000 000,00')

    def test_template_filter_fmtkz(self):
        """Filtro |fmtkz com valor normal"""
        self.assertEqual(fmtkz(Decimal('1234.56')), '1 234,56')

    def test_template_filter_fmtkz_none(self):
        """Filtro |fmtkz com None → ''"""
        self.assertEqual(fmtkz(None), '')

    def test_template_filter_fmtkz_none_with_default(self):
        """Filtro |fmtkz com None e default → '0'"""
        self.assertEqual(fmtkz(None, default='0'), '0')


class DecFunctionTests(TestCase):

    def test_dec_angolan(self):
        """_dec('1.234,56') → Decimal('1234.56')"""
        self.assertEqual(_dec('1.234,56'), Decimal('1234.56'))

    def test_dec_comma(self):
        """_dec('1234,56') → Decimal('1234.56')"""
        self.assertEqual(_dec('1234,56'), Decimal('1234.56'))

    def test_dec_dot(self):
        """_dec('1234.56') → Decimal('1234.56')"""
        self.assertEqual(_dec('1234.56'), Decimal('1234.56'))

    def test_dec_empty(self):
        """_dec('') → Decimal('0')"""
        self.assertEqual(_dec(''), Decimal('0'))

    def test_dec_none(self):
        """_dec(None) → Decimal('0')"""
        self.assertEqual(_dec(None), Decimal('0'))



class IRTTests(TestCase):

    def test_irt_isento_ate_150k(self):
        """Salário ≤ 150.000 KZ → IRT = 0"""
        self.assertEqual(_calcular_irt(Decimal('150000')), Decimal('0'))
        self.assertEqual(_calcular_irt(Decimal('100000')), Decimal('0'))
        self.assertEqual(_calcular_irt(Decimal('0')), Decimal('0'))

    def test_irt_1o_escalao(self):
        """150.001–200.000 → 16% sobre excedente"""
        irt = _calcular_irt(Decimal('200000'))
        esperado = (Decimal('200000') - Decimal('150000')) * Decimal('0.16')
        self.assertEqual(irt, esperado)

    def test_irt_2o_escalao(self):
        """200.001–300.000 → 8.000 + 18% sobre excedente"""
        irt = _calcular_irt(Decimal('300000'))
        esperado = Decimal('8000') + (Decimal('300000') - Decimal('200000')) * Decimal('0.18')
        self.assertEqual(irt, esperado)

    def test_irt_3o_escalao(self):
        """300.001–500.000 → 26.000 + 19% sobre excedente"""
        irt = _calcular_irt(Decimal('500000'))
        esperado = Decimal('26000') + (Decimal('500000') - Decimal('300000')) * Decimal('0.19')
        self.assertEqual(irt, esperado)

    def test_irt_4o_escalao(self):
        """500.001–1.000.000 → 64.000 + 20% sobre excedente"""
        irt = _calcular_irt(Decimal('1000000'))
        esperado = Decimal('64000') + (Decimal('1000000') - Decimal('500000')) * Decimal('0.20')
        self.assertEqual(irt, esperado)

    def test_irt_5o_escalao(self):
        """1.000.001–1.500.000 → 164.000 + 21% sobre excedente"""
        irt = _calcular_irt(Decimal('1500000'))
        esperado = Decimal('164000') + (Decimal('1500000') - Decimal('1000000')) * Decimal('0.21')
        self.assertEqual(irt, esperado)

    def test_irt_6o_escalao(self):
        """1.500.001–2.000.000 → 269.000 + 22% sobre excedente"""
        irt = _calcular_irt(Decimal('2000000'))
        esperado = Decimal('269000') + (Decimal('2000000') - Decimal('1500000')) * Decimal('0.22')
        self.assertEqual(irt, esperado)

    def test_irt_7o_escalao(self):
        """2.000.001–5.000.000 → 379.000 + 23% sobre excedente"""
        irt = _calcular_irt(Decimal('5000000'))
        esperado = Decimal('379000') + (Decimal('5000000') - Decimal('2000000')) * Decimal('0.23')
        self.assertEqual(irt, esperado)

    def test_irt_8o_escalao(self):
        """5.000.001–10.000.000 → 1.069.000 + 24% sobre excedente"""
        irt = _calcular_irt(Decimal('10000000'))
        esperado = Decimal('1069000') + (Decimal('10000000') - Decimal('5000000')) * Decimal('0.24')
        self.assertEqual(irt, esperado)

    def test_irt_9o_escalao(self):
        """> 10.000.000 → 2.269.000 + 25% sobre excedente"""
        irt = _calcular_irt(Decimal('12000000'))
        esperado = Decimal('2269000') + (Decimal('12000000') - Decimal('10000000')) * Decimal('0.25')
        self.assertEqual(irt, esperado)

    def test_irt_valor_exato_no_limite(self):
        """Testa valor exatamente no limite do escalão"""
        irt = _calcular_irt(Decimal('150001'))
        esperado = (Decimal('150001') - Decimal('150000')) * Decimal('0.16')
        self.assertEqual(irt, esperado)


class INSSTests(TestCase):

    def test_inss_taxas_configuraveis(self):
        """INSS_TAXA_TRABALHADOR = 3%, INSS_TAXA_ENTIDADE = 8%"""
        self.assertEqual(INSS_TAXA_TRABALHADOR, Decimal('0.03'))
        self.assertEqual(INSS_TAXA_ENTIDADE, Decimal('0.08'))

    def test_inss_trabalhador_calculo(self):
        """INSS trabalhador = 3% do salário"""
        salario = Decimal('500000')
        inss = (salario * INSS_TAXA_TRABALHADOR).quantize(Decimal('0.01'))
        self.assertEqual(inss, Decimal('15000.00'))

    def test_inss_entidade_calculo(self):
        """INSS entidade = 8% do salário"""
        salario = Decimal('500000')
        inss = (salario * INSS_TAXA_ENTIDADE).quantize(Decimal('0.01'))
        self.assertEqual(inss, Decimal('40000.00'))


class HashPasswordTests(TestCase):

    def test_hash_password_returns_string(self):
        """_hash_password devolve uma string"""
        h = _hash_password('teste123')
        self.assertIsInstance(h, str)

    def test_hash_password_compativel_php(self):
        """Hash usa prefixo $2y$ (compatível PHP)"""
        h = _hash_password('teste123')
        self.assertTrue(h.startswith('$2y$'))

    def test_hash_password_diferente_salt(self):
        """Mesma senha gera hashes diferentes (salt aleatório)"""
        h1 = _hash_password('teste123')
        h2 = _hash_password('teste123')
        self.assertNotEqual(h1, h2)

    def test_hash_password_vazia(self):
        """Senha vazia → None"""
        self.assertIsNone(_hash_password(''))
        self.assertIsNone(_hash_password(None))


class DecTaxUtilsTests(TestCase):
    """Testes para _dec do tax_utils (partilhado)"""

    def test_dec_angolan(self):
        self.assertEqual(_dec('1.234,56'), Decimal('1234.56'))

    def test_dec_comma_only(self):
        self.assertEqual(_dec('1234,56'), Decimal('1234.56'))

    def test_dec_standard(self):
        self.assertEqual(_dec('1234.56'), Decimal('1234.56'))

    def test_dec_empty(self):
        self.assertEqual(_dec(''), Decimal('0'))

    def test_dec_none(self):
        self.assertEqual(_dec(None), Decimal('0'))


class DiasUteisConstTests(TestCase):
    """Testes para constantes de dias úteis e taxa de serviço"""

    def test_dias_uteis_mes(self):
        self.assertEqual(DIAS_UTEIS_MES, Decimal('22'))


# ─── Tests: Models ──────────────────────────────────────────────────

class PedidoFeriasModelTests(TestCase):

    def setUp(self):
        self.banca = Banca.objects.create(usuario_id=1, nome='Banca Teste', nif='123456789')
        self.col = Colaborador.objects.create(
            banca=self.banca, nome='João Teste',
            email='joao@teste.com', telefone='999999999',
        )
        self.today = date.today()

    def test_ferias_valido_futuro(self):
        """Pedido de férias futuro é válido"""
        pedido = PedidoFerias(
            colaborador=self.col,
            data_inicio=self.today + timedelta(days=10),
            data_fim=self.today + timedelta(days=15),
        )
        try:
            pedido.full_clean()
        except Exception:
            self.fail('Férias futuras não devia lançar exceção')

    def test_ferias_valido_hoje(self):
        """Pedido de férias começando hoje é válido (allow_today=True)"""
        pedido = PedidoFerias(
            colaborador=self.col,
            data_inicio=self.today,
            data_fim=self.today + timedelta(days=2),
        )
        try:
            pedido.full_clean()
        except Exception:
            self.fail('Férias começando hoje não devia lançar exceção')

    def test_ferias_invalido_passado(self):
        """Pedido de férias no passado é inválido"""
        pedido = PedidoFerias(
            colaborador=self.col,
            data_inicio=self.today - timedelta(days=5),
            data_fim=self.today + timedelta(days=2),
        )
        with self.assertRaises(Exception):
            pedido.full_clean()

    def test_ferias_invalido_fim_antes_inicio(self):
        """data_fim < data_inicio é inválido"""
        pedido = PedidoFerias(
            colaborador=self.col,
            data_inicio=self.today + timedelta(days=10),
            data_fim=self.today + timedelta(days=5),
        )
        with self.assertRaises(Exception):
            pedido.full_clean()

    def test_ferias_dias_calculo(self):
        """Calcula corretamente número de dias"""
        pedido = PedidoFerias(
            colaborador=self.col,
            data_inicio=date(2026, 6, 1),
            data_fim=date(2026, 6, 5),
        )
        self.assertEqual(pedido.dias, 5)

    def test_ferias_estado_pendente_default(self):
        """Estado inicial é Pendente"""
        pedido = PedidoFerias.objects.create(
            colaborador=self.col,
            data_inicio=self.today + timedelta(days=10),
            data_fim=self.today + timedelta(days=15),
        )
        self.assertEqual(pedido.estado, 'Pendente')


# ─── Tests: Views ───────────────────────────────────────────────────

class ColaboradorViewsTests(TestCase):

    def setUp(self):
        self.banca = Banca.objects.create(usuario_id=1, nome='Banca Teste', nif='123456788')
        self.col = Colaborador.objects.create(
            banca=self.banca, nome='Maria Teste',
            email='maria@teste.com', telefone='999999999',
        )
        self.filial = FilialBanca.objects.create(
            banca=self.banca, provincia='Luanda',
        )
        self.factory = RequestFactory()

    def test_remover_gestor_filial(self):
        """_remover_gestor_filial marca gestor como inativo e limpa cargo"""
        GestorFilial.objects.create(colaborador=self.col, filial=self.filial)
        self.col.cargo_personalizado = 'Responsável de Filial'
        self.col.cargo = 'Gestor'
        self.col.save()

        _remover_gestor_filial(self.col)

        gf = GestorFilial.objects.get(colaborador=self.col)
        self.assertFalse(gf.ativo)
        self.col.refresh_from_db()
        self.assertEqual(self.col.cargo_personalizado, '')
        self.assertEqual(self.col.cargo, 'Assistente')

    def test_colaborador_editar_view_get(self):
        """GET na página de editar colaborador retorna 200"""
        url = reverse('rh_colaborador_editar', args=[self.col.pk])
        request = _setup_request(self.factory, url, self.banca.pk)
        from rh.views import colaborador_editar_view
        response = colaborador_editar_view(request, self.col.pk)
        if response.status_code == 302:
            from urllib.parse import urlparse
            self.fail(f'Redirected to {response.url}')
        self.assertEqual(response.status_code, 200)


class FeriasViewsTests(TestCase):

    def setUp(self):
        self.banca = Banca.objects.create(usuario_id=1, nome='Banca Teste', nif='123456787')
        self.col = Colaborador.objects.create(
            banca=self.banca, nome='Ana Teste',
            email='ana@teste.com', telefone='999999999',
        )
        self.factory = RequestFactory()

    def test_ferias_lista_view_redirects_to_presencas(self):
        """ferias_lista_view redireciona para rh_presencas?tab=ferias"""
        url = reverse('rh_ferias')
        request = _setup_request(self.factory, url, self.banca.pk)
        from rh.views import ferias_lista_view
        response = ferias_lista_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('tab=ferias', response.url)


class SubsidioReciboTests(TestCase):

    def setUp(self):
        self.banca = Banca.objects.create(usuario_id=1, nome='Banca Teste', nif='123456786')
        self.col = Colaborador.objects.create(
            banca=self.banca, nome='Carlos Teste',
            email='carlos@teste.com', telefone='999999999',
        )
        self.proc = ProcessamentoSalarial.objects.create(
            banca=self.banca, mes=6, ano=2026,
        )
        self.recibo = ReciboSalarial.objects.create(
            processamento=self.proc, colaborador=self.col,
            salario_base=Decimal('100000.00'),
        )

    def test_subsidio_obrigatorio_criado_no_get(self):
        """SubsidioRecibo de subsídio obrigatório é criado se não existir"""
        subsidio = Subsidio.objects.create(
            banca=self.banca, nome='Subsidio Teste',
            tipo_calculo='valor', valor_padrao=Decimal('5000.00'),
            obrigatorio=True,
        )
        from django.urls import reverse
        factory = RequestFactory()
        url = reverse('rh_salario_detalhe', args=[self.proc.pk])
        request = _setup_request(factory, url, self.banca.pk)
        from rh.views import salario_detalhe_view
        response = salario_detalhe_view(request, self.proc.pk)
        if response.status_code == 302:
            from urllib.parse import urlparse
            self.fail(f'Redirected to {response.url}')
        self.assertEqual(response.status_code, 200)
        existe = SubsidioRecibo.objects.filter(
            recibo=self.recibo, subsidio=subsidio
        ).exists()
        self.assertTrue(existe, 'SubsidioRecibo obrigatório devia ser criado no GET')
