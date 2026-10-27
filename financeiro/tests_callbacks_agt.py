"""Testes da fila de callbacks (webhooks) da AGT."""

import hashlib
import hmac
import json

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from rh.models import Banca

from .models import CallbackAGT, ConfiguracaoAGT, FaturaEletronica


class CallbackAGTBaseTestCase(TestCase):
    def setUp(self):
        self.banca = Banca.objects.create(
            nome='Banca AGT', nif='123456789',
            email='agt@banca.com', telefone='923000000',
        )
        self.cliente = Cliente.objects.create(
            nome='Cliente AGT', nif='987654321',
            email='cliente@agt.com', telefone='923000001',
        )
        self.fatura = FaturaEletronica.objects.create(
            banca=self.banca,
            cliente=self.cliente,
            request_id='req-agt-001',
            estado='Enviada AGT',
            total_geral='150000.00',
        )


@override_settings(AGT_CALLBACK_SECRET='segredo-teste', AGT_CALLBACK_PROCESSAR_IMEDIATO=True)
class CallbackHMACTestCase(CallbackAGTBaseTestCase):
    def _post(self, payload, segredo='segredo-teste', url=None):
        raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        assinatura = hmac.new(
            segredo.encode('utf-8'), raw, hashlib.sha256
        ).hexdigest()
        return self.client.post(
            url or reverse('fatura_eletronica_callback_agt'),
            data=raw,
            content_type='application/json',
            HTTP_X_AGT_SIGNATURE=assinatura,
        )

    def test_callback_valido_actualiza_estado_e_guarda_payload_bruto(self):
        resposta = self._post({'requestID': 'req-agt-001', 'status': 'APROVADO'})
        self.assertEqual(resposta.status_code, 200)
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.estado, 'Aprovada AGT')
        self.assertIsNotNone(self.fatura.data_resposta_agt)

        evento = CallbackAGT.objects.get()
        self.assertEqual(evento.request_id, 'req-agt-001')
        self.assertEqual(evento.estado_processamento, 'Processado')
        self.assertTrue(evento.assinatura_valida)
        self.assertIn('req-agt-001', evento.payload_bruto)
        self.assertEqual(evento.payload['status'], 'APROVADO')

    def test_callback_duplicado_e_idempotente(self):
        primeira = self._post({'requestID': 'req-agt-001', 'status': 'APROVADO'})
        segunda = self._post({'requestID': 'req-agt-001', 'status': 'APROVADO'})
        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertTrue(segunda.json()['duplicado'])
        self.assertEqual(CallbackAGT.objects.count(), 1)
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.estado, 'Aprovada AGT')

    def test_callback_rejeitado_actualiza_motivo(self):
        resposta = self._post({
            'requestID': 'req-agt-001',
            'status': 'REJEITADO',
            'message': 'Contribuinte inválido.',
        })
        self.assertEqual(resposta.status_code, 200)
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.estado, 'Rejeitada AGT')
        self.assertEqual(self.fatura.observacoes, 'Contribuinte inválido.')

    def test_assinatura_invalida_nao_guarda_evento(self):
        raw = json.dumps({'requestID': 'req-agt-001'}).encode('utf-8')
        resposta = self.client.post(
            reverse('fatura_eletronica_callback_agt'),
            data=raw, content_type='application/json',
            HTTP_X_AGT_SIGNATURE='assinatura-errada',
        )
        self.assertEqual(resposta.status_code, 401)
        self.assertEqual(CallbackAGT.objects.count(), 0)
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.estado, 'Enviada AGT')

    def test_documento_desconhecido_devolve_404_mas_audita(self):
        resposta = self._post({'requestID': 'req-inexistente'})
        self.assertEqual(resposta.status_code, 404)
        evento = CallbackAGT.objects.get()
        self.assertEqual(evento.estado_processamento, 'Pendente')
        self.assertIn('não encontrado', evento.erro)

    def test_rota_sem_barra_final_aceita_post(self):
        resposta = self._post(
            {'requestID': 'req-agt-001', 'status': 'APROVADO'},
            url=reverse('fatura_eletronica_callback_agt_sem_barra'),
        )
        self.assertEqual(resposta.status_code, 200)
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.estado, 'Aprovada AGT')


@override_settings(AGT_CALLBACK_SECRET='', AGT_CALLBACK_PROCESSAR_IMEDIATO=True)
class CallbackJWSTestCase(CallbackAGTBaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.privada_pem = cls.chave_privada.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode('utf-8')
        cls.publica_pem = cls.chave_privada.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode('utf-8')

    def setUp(self):
        super().setUp()
        ConfiguracaoAGT.objects.create(
            banca=self.banca, ativo=True,
            tax_registration_number='5000123456',
            agt_public_key=self.publica_pem,
        )

    def test_callback_com_jws_rs256_valida_e_actualiza(self):
        payload = {'requestID': 'req-agt-001', 'estado': 'Aprovada'}
        token = jwt.encode(
            payload, self.privada_pem, algorithm='RS256',
            headers={'typ': 'JOSE', 'alg': 'RS256'},
        )
        raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        resposta = self.client.post(
            reverse('fatura_eletronica_callback_agt'),
            data=raw, content_type='application/json',
            HTTP_X_AGT_SIGNATURE=token,
        )
        self.assertEqual(resposta.status_code, 200)
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.estado, 'Aprovada AGT')
        self.assertEqual(CallbackAGT.objects.count(), 1)

    def test_jws_assinado_por_outra_chave_e_rejeitado(self):
        outra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        outra_pem = outra.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode('utf-8')
        token = jwt.encode({'requestID': 'req-agt-001'}, outra_pem, algorithm='RS256')
        resposta = self.client.post(
            reverse('fatura_eletronica_callback_agt'),
            data=json.dumps({'requestID': 'req-agt-001'}).encode('utf-8'),
            content_type='application/json',
            HTTP_X_AGT_SIGNATURE=token,
        )
        self.assertEqual(resposta.status_code, 401)
        self.assertEqual(CallbackAGT.objects.count(), 0)


@override_settings(AGT_CALLBACK_SECRET='segredo-teste', AGT_CALLBACK_PROCESSAR_IMEDIATO=False)
class CallbackFilaAssincronaTestCase(CallbackAGTBaseTestCase):
    def _post(self, payload):
        raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        assinatura = hmac.new(
            b'segredo-teste', raw, hashlib.sha256
        ).hexdigest()
        return self.client.post(
            reverse('fatura_eletronica_callback_agt'),
            data=raw, content_type='application/json',
            HTTP_X_AGT_SIGNATURE=assinatura,
        )

    def test_modo_assincrono_enfileira_e_comando_processa(self):
        resposta = self._post({'requestID': 'req-agt-001', 'status': 'APROVADO'})
        self.assertEqual(resposta.status_code, 202)
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.estado, 'Enviada AGT')
        evento = CallbackAGT.objects.get()
        self.assertEqual(evento.estado_processamento, 'Pendente')

        call_command('processar_callbacks_agt')
        evento.refresh_from_db()
        self.fatura.refresh_from_db()
        self.assertEqual(evento.estado_processamento, 'Processado')
        self.assertEqual(self.fatura.estado, 'Aprovada AGT')
