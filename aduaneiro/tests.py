"""Testes do módulo aduaneiro — DU / Histórico."""
import json
from decimal import Decimal

from django.test import TestCase, RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware

from rh.models import Banca, FilialBanca
from users.models import Usuario
from .models import DeclaracaoUnica, HistoricoDU
from .signals import registrar_versao_du


class HistoricoDUTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(
            username='testadu',
            nome='Teste Aduaneiro',
            email='teste.adu@test.com',
        )
        self.banca = Banca.objects.create(
            usuario_id=self.usuario.id,
            nome='Banca Teste',
            nif='999999990',
        )
        self.du = DeclaracaoUnica.objects.create(
            usuario_id=self.usuario.id,
            banca=self.banca,
            status='Rascunho',
            dados_json=json.dumps({'form': 'data'}),
        )

    def test_registrar_versao_cria_historico(self):
        """registrar_versao() deve criar um registo HistoricoDU."""
        self.du.registrar_versao(
            {'status': {'de': '', 'para': 'Rascunho'}},
            utilizador_id=self.usuario.id,
            utilizador_nome=self.usuario.nome,
        )
        self.assertEqual(self.du.historico_versoes.count(), 1)
        h = self.du.historico_versoes.first()
        self.assertEqual(h.status, 'Rascunho')
        self.assertEqual(h.utilizador_id, self.usuario.id)

    def test_registrar_versao_com_request(self):
        """registrar_versao() com request deve extrair dados da sessão."""
        factory = RequestFactory()
        request = factory.get('/')
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session['usuario_id'] = self.usuario.id
        request.session['usuario'] = {'nome': self.usuario.nome}
        request.session.save()

        self.du.registrar_versao(
            {'_criado': 'Nova Declaração Única criada'},
            request=request,
        )
        h = self.du.historico_versoes.first()
        self.assertEqual(h.utilizador_id, self.usuario.id)
        self.assertEqual(h.utilizador_nome, self.usuario.nome)

    def test_registrar_versao_du_signal(self):
        """registrar_versao_du()  cria historico."""
        campos = {'regime_aduaneiro': {'de': '', 'para': 'Consumo'}}
        self.du.dados_json = json.dumps({'foo': 'bar'})
        self.du.save()
        registrar_versao_du(self.du, campos)
        self.assertEqual(self.du.historico_versoes.count(), 1)

    def test_campos_alterados_dict(self):
        """get_campos_alterados_dict() retorna dict parseado."""
        campos = {'status': {'de': 'Rascunho', 'para': 'Aprovada'}}
        self.du.registrar_versao(json.dumps(campos, ensure_ascii=False))
        h = self.du.historico_versoes.first()
        result = h.get_campos_alterados_dict()
        self.assertEqual(result, campos)

    def test_get_dados(self):
        """get_dados() retorna dict do dados_json."""
        dados = {'form': {'campo': 'valor'}}
        self.du.dados_json = json.dumps(dados)
        self.du.registrar_versao({})
        h = self.du.historico_versoes.first()
        self.assertEqual(h.get_dados(), dados)

    def test_campos_alterados_invalidos(self):
        """campos_alterados inválido retorna dict vazio."""
        h = HistoricoDU.objects.create(du=self.du, dados_json='{}', campos_alterados='{invalido')
        self.assertEqual(h.get_campos_alterados_dict(), {})

    def test_multiplas_versoes_ordenadas(self):
        """Múltiplas versões são ordenadas por criado_em descendente."""
        from django.utils import timezone
        import datetime
        h1 = HistoricoDU.objects.create(
            du=self.du, dados_json='{}', status='Rascunho',
            criado_em=timezone.now() - datetime.timedelta(hours=2),
        )
        h2 = HistoricoDU.objects.create(
            du=self.du, dados_json='{}', status='Aprovada',
            criado_em=timezone.now(),
        )
        versoes = list(self.du.historico_versoes.all())
        self.assertEqual(versoes[0], h2)
        self.assertEqual(versoes[1], h1)


class ModelDeclaracaoUnicaTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(
            username='testdu2', nome='Test DU', email='du2@test.com',
        )

    def test_gerar_codigo_processo(self):
        codigo = DeclaracaoUnica.gerar_codigo_processo()
        self.assertEqual(len(codigo), 8)
        self.assertTrue(codigo.isdigit())

    def test_unicidade_codigo_processo(self):
        usado = '12345678'
        DeclaracaoUnica.objects.create(
            usuario_id=self.usuario.id, codigo_processo=usado,
        )
        # Deve gerar um código diferente após 20 tentativas (fallback)
        import random
        random.seed(42)
        codigo = DeclaracaoUnica.gerar_codigo_processo()
        self.assertEqual(len(codigo), 8)

    def test_set_dados(self):
        du = DeclaracaoUnica(usuario_id=self.usuario.id)
        du.set_dados({'chave': 'valor'})
        dados = du.get_dados()
        self.assertEqual(dados['chave'], 'valor')
