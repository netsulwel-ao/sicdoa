"""
Unit tests for AGT Invoicing services, permissions, and REST API endpoints.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, RequestFactory
from django.utils import timezone
from django.contrib.sessions.middleware import SessionMiddleware
from rest_framework.test import APITestCase, APIClient

from rh.models import Banca
from .models import ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria
from .services import FaturaService, AgtHttpClient, AgtCryptoService
from .permissions import require_financial_permission


# ─── Test Data Fixtures ─────────────────────────────────────────────────

class AgtTestBase(TestCase):
    """Base test class with shared fixtures."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        """Create test data."""
        # Create test Banca
        self.banca = Banca.objects.create(
            nome="Banca Teste",
            nif="000000000",
            tipo="Banca",
            email="teste@banca.ao",
        )

        # Create test ConfiguracaoFiscal
        self.config = ConfiguracaoFiscal.objects.create(
            banca=self.banca,
            nif_emitente="000000000",
            integration_enabled=True,
            api_endpoint="https://test.example.com",
        )

        # Create test Fatura
        self.fatura = Fatura.objects.create(
            banca=self.banca,
            numero="FAT/001/2026",
            serie="A",
            tipo_documento="FACTURA",
            estado="RASCUNHO",
            cliente_designacao="Cliente Teste",
            cliente_nif="000000001",
            total=Decimal("1500.50"),
            emitida_em=timezone.now(),
        )

        # Create test SubmissaoAgt
        self.submissao = SubmissaoAgt.objects.create(
            banca=self.banca,
            fatura=self.fatura,
            estado="PENDENTE",
            tentativas=0,
        )


# ─── AgtCryptoService Tests ────────────────────────────────────────────

class AgtCryptoServiceTestCase(AgtTestBase):
    """Tests for AgtCryptoService."""

    def test_crypto_service_initialization(self):
        """Test crypto service initializes without error."""
        service = AgtCryptoService()
        self.assertIsNotNone(service)

    def test_sign_jws_software(self):
        """Test JWS software signature generation."""
        service = AgtCryptoService()
        # Should not raise even if key is empty (will return empty string)
        result = service.sign_jws_software()
        # If private key is empty, jwt.encode may fail, so we just check it doesn't crash
        # In a real test with actual keys, we'd verify the token format


# ─── AgtHttpClient Tests ───────────────────────────────────────────────

class AgtHttpClientTestCase(AgtTestBase):
    """Tests for AgtHttpClient with mocked HTTP."""

    @patch('agt_invoicing.services.requests.request')
    def test_post_registar_fatura_success(self, mock_request):
        """Test successful fatura submission."""
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {"requestId": "REQ123", "status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        client = AgtHttpClient()
        result = client.post_registar_fatura("<xml>test</xml>")

        self.assertEqual(result["request_id"], "REQ123")
        self.assertIn("resposta", result)

    @patch('agt_invoicing.services.requests.request')
    def test_post_registar_fatura_timeout(self, mock_request):
        """Test fatura submission timeout with retry."""
        import requests
        mock_request.side_effect = requests.Timeout("Request timeout")

        client = AgtHttpClient()
        with self.assertRaises(requests.Timeout):
            client.post_registar_fatura("<xml>test</xml>")

    @patch('agt_invoicing.services.requests.request')
    def test_get_consultar_fatura_success(self, mock_request):
        """Test successful status query."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "APROVADA",
            "hash": "HASH123",
            "erros": [],
        }
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        client = AgtHttpClient()
        result = client.get_consultar_fatura("REQ123")

        self.assertEqual(result["status"], "APROVADA")
        self.assertEqual(result["hash"], "HASH123")

    @patch('agt_invoicing.services.requests.request')
    def test_get_consultar_fatura_with_errors(self, mock_request):
        """Test status query with errors."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "REJEITADA",
            "hash": "",
            "erros": ["Invalid NIF", "Missing fields"],
        }
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        client = AgtHttpClient()
        result = client.get_consultar_fatura("REQ123")

        self.assertEqual(result["status"], "REJEITADA")
        self.assertEqual(len(result["erros"]), 2)


# ─── FaturaService Tests ───────────────────────────────────────────────

class FaturaServiceTestCase(AgtTestBase):
    """Tests for FaturaService state machine and business logic."""

    @patch('agt_invoicing.services.AgtHttpClient.post_registar_fatura')
    def test_submeter_fatura_success(self, mock_post):
        """Test successful fatura submission."""
        mock_post.return_value = {"request_id": "REQ001", "resposta": {"status": "ok"}}

        service = FaturaService()
        result = service.submeter_fatura(self.fatura.id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["request_id"], "REQ001")

        # Verify state changes
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.agt_request_id, "REQ001")
        self.assertEqual(self.fatura.agt_status, "PENDENTE")

        self.submissao.refresh_from_db()
        self.assertEqual(self.submissao.estado, "ACEITE")
        self.assertEqual(self.submissao.codigo_controlo, "REQ001")

    @patch('agt_invoicing.services.AgtHttpClient.post_registar_fatura')
    def test_submeter_fatura_idempotent(self, mock_post):
        """Test that submitting an already-accepted fatura is idempotent."""
        # First submission
        mock_post.return_value = {"request_id": "REQ002", "resposta": {"status": "ok"}}
        service = FaturaService()
        result1 = service.submeter_fatura(self.fatura.id)
        self.assertTrue(result1["ok"])

        # Second submission should return early
        result2 = service.submeter_fatura(self.fatura.id)
        self.assertTrue(result2["ok"])
        self.assertEqual(result2["request_id"], "REQ002")
        # mock_post should have been called only once
        self.assertEqual(mock_post.call_count, 1)

    @patch('agt_invoicing.services.AgtHttpClient.post_registar_fatura')
    def test_submeter_fatura_max_retries(self, mock_post):
        """Test max retries exceeded."""
        # Set tentativas to max
        self.submissao.tentativas = 5
        self.submissao.save()

        service = FaturaService()
        result = service.submeter_fatura(self.fatura.id)

        self.assertFalse(result["ok"])
        self.assertEqual(result["erro"], "Max retries exceeded")

        # Verify state is FALHA_PERMANENTE
        self.submissao.refresh_from_db()
        self.assertEqual(self.submissao.estado, "FALHA_PERMANENTE")

    @patch('agt_invoicing.services.AgtHttpClient.post_registar_fatura')
    def test_submeter_fatura_4xx_error(self, mock_post):
        """Test 4xx error (client error) → FALHA_PERMANENTE."""
        import requests
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_post.side_effect = requests.HTTPError(response=mock_response)

        service = FaturaService()
        result = service.submeter_fatura(self.fatura.id)

        self.assertFalse(result["ok"])

        self.submissao.refresh_from_db()
        self.assertEqual(self.submissao.estado, "FALHA_PERMANENTE")

    @patch('agt_invoicing.services.AgtHttpClient.post_registar_fatura')
    def test_submeter_fatura_5xx_error(self, mock_post):
        """Test 5xx error (server error) → FALHA_TEMPORARIA with retry scheduling."""
        import requests
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.side_effect = requests.HTTPError(response=mock_response)

        service = FaturaService()
        result = service.submeter_fatura(self.fatura.id)

        self.assertFalse(result["ok"])

        self.submissao.refresh_from_db()
        self.assertEqual(self.submissao.estado, "FALHA_TEMPORARIA")
        self.assertIsNotNone(self.submissao.proxima_tentativa_em)
        # proxima_tentativa_em should be ~15 minutes from now
        delta = self.submissao.proxima_tentativa_em - timezone.now()
        self.assertTrue(timedelta(minutes=14) < delta < timedelta(minutes=16))

    @patch('agt_invoicing.services.AgtHttpClient.post_registar_fatura')
    def test_submeter_fatura_timeout(self, mock_post):
        """Test timeout → FALHA_TEMPORARIA."""
        import requests
        mock_post.side_effect = requests.Timeout("Timeout")

        service = FaturaService()
        result = service.submeter_fatura(self.fatura.id)

        self.assertFalse(result["ok"])

        self.submissao.refresh_from_db()
        self.assertEqual(self.submissao.estado, "FALHA_TEMPORARIA")

    @patch('agt_invoicing.services.AgtHttpClient.get_consultar_fatura')
    def test_polling_status_success(self, mock_get):
        """Test successful status polling."""
        # Set up fatura with agt_request_id
        self.fatura.agt_request_id = "REQ001"
        self.fatura.save()

        mock_get.return_value = {
            "status": "APROVADA",
            "hash": "HASH123",
            "erros": [],
        }

        service = FaturaService()
        result = service.polling_status(self.fatura.id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "APROVADA")
        self.assertEqual(result["hash"], "HASH123")

        # Verify Fatura updated
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.agt_status, "APROVADA")
        self.assertEqual(self.fatura.agt_hash_validacao, "HASH123")

    @patch('agt_invoicing.services.AgtHttpClient.get_consultar_fatura')
    def test_polling_status_with_errors(self, mock_get):
        """Test status polling with AGT errors."""
        self.fatura.agt_request_id = "REQ001"
        self.fatura.save()

        mock_get.return_value = {
            "status": "REJEITADA",
            "hash": "",
            "erros": ["Invalid NIF", "Missing fields"],
        }

        service = FaturaService()
        result = service.polling_status(self.fatura.id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "REJEITADA")
        self.assertEqual(len(result["erros"]), 2)

        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.agt_status, "REJEITADA")
        self.assertEqual(self.fatura.agt_erros, ["Invalid NIF", "Missing fields"])

    def test_processar_callback_approved(self):
        """Test callback processing with APPROVED status."""
        # Set up submission with request_id
        self.submissao.codigo_controlo = "REQ001"
        self.submissao.save()

        service = FaturaService()
        payload = {
            "requestId": "REQ001",
            "status": "APPROVED",
            "hash": "HASH123",
            "erros": [],
        }

        result = service.processar_callback(payload)

        self.assertTrue(result["ok"])

        # Verify state updates
        self.submissao.refresh_from_db()
        self.assertEqual(self.submissao.estado, "ACEITE")

        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.agt_status, "APROVADA")
        self.assertEqual(self.fatura.agt_hash_validacao, "HASH123")

    def test_processar_callback_rejected(self):
        """Test callback processing with REJECTED status."""
        self.submissao.codigo_controlo = "REQ001"
        self.submissao.save()

        service = FaturaService()
        payload = {
            "requestId": "REQ001",
            "status": "REJECTED",
            "hash": "",
            "erros": ["Invalid NIF"],
        }

        result = service.processar_callback(payload)

        self.assertTrue(result["ok"])

        self.submissao.refresh_from_db()
        self.assertEqual(self.submissao.estado, "REJEITADA")

        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.agt_status, "REJEITADA")

    def test_processar_callback_missing_request_id(self):
        """Test callback with missing requestId."""
        service = FaturaService()
        payload = {"status": "APPROVED"}

        result = service.processar_callback(payload)

        self.assertFalse(result["ok"])
        self.assertIn("Missing requestId", result["reason"])

    def test_processar_callback_not_found(self):
        """Test callback for non-existent submission."""
        service = FaturaService()
        payload = {
            "requestId": "NONEXISTENT",
            "status": "APPROVED",
        }

        result = service.processar_callback(payload)

        self.assertFalse(result["ok"])
        self.assertIn("not found", result["reason"].lower())


# ─── Permission Decorator Tests ────────────────────────────────────────

class PermissionDecoratorTestCase(TestCase):
    """Tests for @require_financial_permission() decorator."""

    def setUp(self):
        self.factory = RequestFactory()
        self.banca = Banca.objects.create(
            nome="Banca Teste",
            nif="000000000",
            tipo="Banca",
            email="teste@banca.ao",
        )

    def _add_session(self, request, usuario_data, banca_id):
        """Add session to request."""
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session['usuario'] = usuario_data
        request.session['banca_id'] = banca_id
        request.session.save()

    def test_permission_denied_missing_papel(self):
        """Test 403 when papel not in whitelist."""
        from django.http import JsonResponse
        request = self.factory.get('/api/agt/stats/')
        self._add_session(request, {'id': 1, 'papel': 'Operador'}, self.banca.id)

        @require_financial_permission()
        def dummy_view(request, banca_id):
            return JsonResponse({"ok": True})

        response = dummy_view(request)

        self.assertEqual(response.status_code, 403)

    def test_permission_denied_missing_banca_id(self):
        """Test 403 when banca_id missing from session."""
        from django.http import JsonResponse
        request = self.factory.get('/api/agt/stats/')
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session['usuario'] = {'id': 1, 'papel': 'Administrador'}
        # banca_id not set
        request.session.save()

        @require_financial_permission()
        def dummy_view(request, banca_id):
            return JsonResponse({"ok": True})

        response = dummy_view(request)

        self.assertEqual(response.status_code, 403)

    def test_permission_granted_administrador(self):
        """Test success with Administrador role."""
        from django.http import JsonResponse
        request = self.factory.get('/api/agt/stats/')
        self._add_session(request, {'id': 1, 'papel': 'Administrador'}, self.banca.id)

        @require_financial_permission()
        def dummy_view(request, banca_id):
            return JsonResponse({"ok": True, "banca_id": banca_id})

        response = dummy_view(request)

        self.assertEqual(response.status_code, 200)

    def test_permission_granted_despachante_oficial(self):
        """Test success with Despachante Oficial role."""
        from django.http import JsonResponse
        request = self.factory.get('/api/agt/stats/')
        self._add_session(request, {'id': 1, 'papel': 'Despachante Oficial'}, self.banca.id)

        @require_financial_permission()
        def dummy_view(request, banca_id):
            return JsonResponse({"ok": True, "banca_id": banca_id})

        response = dummy_view(request)

        self.assertEqual(response.status_code, 200)


# ─── REST API Endpoint Tests ────────────────────────────────────────────

class AgtStatsEndpointTestCase(AgtTestBase):
    """Tests for GET /api/agt/stats/ endpoint."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.factory = RequestFactory()

    def _setup_session(self, user_data, banca_id):
        """Setup authenticated session."""
        session = self.client.session
        session['usuario'] = user_data
        session['banca_id'] = banca_id
        session.save()
        return session

    def test_stats_endpoint_unauthenticated(self):
        """Test 403 when not authenticated."""
        response = self.client.get('/api/agt/stats/')
        self.assertEqual(response.status_code, 403)

    def test_stats_endpoint_success(self):
        """Test successful stats response."""
        self._setup_session({'id': 1, 'papel': 'Administrador'}, self.banca.id)
        response = self.client.get('/api/agt/stats/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("emitidas", data)
        self.assertIn("rejeitadas", data)
        self.assertIn("pendentes", data)


class AgtPendentesEndpointTestCase(AgtTestBase):
    """Tests for GET /api/agt/pendentes/ endpoint."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        # Create several pending faturas
        for i in range(5):
            Fatura.objects.create(
                banca=self.banca,
                numero=f"FAT/00{i}/2026",
                tipo_documento="FACTURA",
                estado="EMITIDA",
                cliente_designacao=f"Cliente {i}",
                cliente_nif=f"00000000{i}",
                total=Decimal("1000.00"),
                agt_status="PENDENTE",
            )

    def _setup_session(self, user_data, banca_id):
        session = self.client.session
        session['usuario'] = user_data
        session['banca_id'] = banca_id
        session.save()

    def test_pendentes_pagination(self):
        """Test paginated list of pending invoices."""
        self._setup_session({'id': 1, 'papel': 'Administrador'}, self.banca.id)
        response = self.client.get('/api/agt/pendentes/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertGreater(len(data["results"]), 0)


class AgtEstadoEndpointTestCase(AgtTestBase):
    """Tests for GET /api/agt/estado/<id>/ endpoint."""

    def setUp(self):
        super().setUp()
        self.client = Client()

    def _setup_session(self, user_data, banca_id):
        session = self.client.session
        session['usuario'] = user_data
        session['banca_id'] = banca_id
        session.save()

    def test_estado_detail_success(self):
        """Test successful detail response."""
        self._setup_session({'id': 1, 'papel': 'Administrador'}, self.banca.id)
        response = self.client.get(f'/api/agt/estado/{self.fatura.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["numero"], self.fatura.numero)

    def test_estado_detail_not_found(self):
        """Test 404 for non-existent fatura."""
        self._setup_session({'id': 1, 'papel': 'Administrador'}, self.banca.id)
        response = self.client.get('/api/agt/estado/99999/')
        self.assertEqual(response.status_code, 404)

    def test_estado_detail_decimal_serialization(self):
        """Test that total is serialized as string, not float."""
        self._setup_session({'id': 1, 'papel': 'Administrador'}, self.banca.id)
        response = self.client.get(f'/api/agt/estado/{self.fatura.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # total should be a string, not float
        self.assertIsInstance(data["total"], str)
        self.assertEqual(data["total"], "1500.50")


class AgtCallbackEndpointTestCase(AgtTestBase):
    """Tests for POST /api/agt/callback/ webhook endpoint."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        # Setup submission with request_id
        self.submissao.codigo_controlo = "REQ001"
        self.submissao.save()

    def test_callback_always_returns_200(self):
        """Test that callback always returns HTTP 200, even on error."""
        response = self.client.post('/api/agt/callback/', {}, format='json')
        # Should return 200 even with empty/invalid payload
        self.assertEqual(response.status_code, 200)

    def test_callback_approved(self):
        """Test callback with APPROVED status."""
        payload = {
            "requestId": "REQ001",
            "status": "APPROVED",
            "hash": "HASH123",
            "erros": [],
        }
        response = self.client.post('/api/agt/callback/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("acknowledged", data)

        # Verify fatura was updated
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.agt_status, "APROVADA")

    def test_callback_rejected(self):
        """Test callback with REJECTED status."""
        payload = {
            "requestId": "REQ001",
            "status": "REJECTED",
            "hash": "",
            "erros": ["Invalid NIF"],
        }
        response = self.client.post('/api/agt/callback/', payload, format='json')
        self.assertEqual(response.status_code, 200)

        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.agt_status, "REJEITADA")

    def test_callback_missing_fatura_still_200(self):
        """Test that callback returns 200 even when fatura is missing."""
        payload = {
            "requestId": "NONEXISTENT",
            "status": "APPROVED",
        }
        response = self.client.post('/api/agt/callback/', payload, format='json')
        # CRITICAL: Must still return 200
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["acknowledged"])

    def test_callback_creates_audit_log(self):
        """Test that callback creates audit log entry."""
        payload = {
            "requestId": "REQ001",
            "status": "APPROVED",
            "hash": "HASH123",
            "erros": [],
        }
        response = self.client.post('/api/agt/callback/', payload, format='json')
        self.assertEqual(response.status_code, 200)

        # Should have created audit log
        audit = RegistoAuditoria.objects.filter(origin_tipo="WEBHOOK").first()
        self.assertIsNotNone(audit)
