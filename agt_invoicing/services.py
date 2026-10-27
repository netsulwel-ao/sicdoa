"""
AGT Invoicing Services — HTTP client, crypto signing, and state machine.
"""
import base64
import logging
import time
import jwt
import requests
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.files.base import ContentFile
from .models import Fatura, SubmissaoAgt, RegistoAuditoria

logger = logging.getLogger(__name__)


# ─── AgtCryptoService ──────────────────────────────────────────────────────

class AgtCryptoService:
    """
    JWS RS256 signing for AGT integration.
    Loads private key from settings (AGT_SOFTWARE_PRIVATE_KEY_FILE or content).
    """

    def __init__(self):
        """Initialize with private key from settings."""
        self.private_key = self._load_private_key()

    def _load_private_key(self) -> str:
        """Load RSA private key from file or environment variable."""
        # Try direct environment content first
        if settings.AGT_SOFTWARE_PRIVATE_KEY:
            return settings.AGT_SOFTWARE_PRIVATE_KEY

        # Fall back to file
        key_file = settings.AGT_SOFTWARE_PRIVATE_KEY_FILE
        try:
            with open(key_file, 'r') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"AGT private key file not found: {key_file}")
            return ""
        except Exception as e:
            logger.error(f"Error loading AGT private key: {e}")
            return ""

    def sign_jws_software(self) -> str:
        """
        Sign software identification (productId + version + validationNumber).
        Returns JWS token.
        """
        payload = {
            "productId": settings.AGT_PRODUCT_ID,
            "version": settings.AGT_PRODUCT_VERSION,
            "validationNumber": settings.AGT_SOFTWARE_VALIDATION_NUMBER,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def sign_jws_document(self, fatura_data: dict) -> str:
        """
        Sign invoice document fields.
        Args:
            fatura_data: dict with invoice fields to sign
        Returns JWS token.
        """
        return jwt.encode(fatura_data, self.private_key, algorithm="RS256")

    def sign_jws_request(self, nif: str, request_id: str) -> str:
        """
        Sign submission request (NIF + request ID).
        Args:
            nif: NIF do contribuinte
            request_id: AGT request ID
        Returns JWS token.
        """
        payload = {
            "nif": nif,
            "requestId": request_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")


# ─── AgtHttpClient ────────────────────────────────────────────────────────

class AgtHttpClient:
    """
    HTTP client for AGT API with Basic Auth, retry logic, and exponential backoff.
    """

    MAX_RETRIES = 3
    TIMEOUT = 5  # seconds
    BACKOFF_DELAYS = [1, 2, 4]  # exponential backoff: 1s, 2s, 4s

    def __init__(self):
        """Initialize HTTP client with Basic Auth credentials."""
        self.username = settings.AGT_USERNAME
        self.password = settings.AGT_PASSWORD
        self.api_base = settings.AGT_API_BASE
        self.auth_header = self._build_auth_header()

    def _build_auth_header(self) -> str:
        """Build Basic Auth header (base64-encoded username:password)."""
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _make_request(self, method: str, endpoint: str, **kwargs):
        """
        Make HTTP request with retry logic and exponential backoff.
        Args:
            method: 'GET' or 'POST'
            endpoint: API endpoint path (e.g., '/registarFactura')
            **kwargs: additional request parameters (data, json, etc.)
        Returns:
            response.json() or raises HTTPError/Timeout
        """
        url = f"{self.api_base}{endpoint}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = self.auth_header
        headers["Content-Type"] = kwargs.pop("content_type", "application/json")

        last_exception = None
        for attempt in range(self.MAX_RETRIES):
            try:
                if attempt > 0:
                    delay = self.BACKOFF_DELAYS[attempt - 1]
                    logger.info(f"Retry {attempt}/{self.MAX_RETRIES} for {method} {endpoint} after {delay}s")
                    time.sleep(delay)

                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    timeout=self.TIMEOUT,
                    **kwargs
                )
                response.raise_for_status()
                return response.json()

            except requests.Timeout as e:
                last_exception = e
                logger.warning(f"Timeout on attempt {attempt + 1}/{self.MAX_RETRIES}: {method} {endpoint}")
                if attempt == self.MAX_RETRIES - 1:
                    raise

            except requests.HTTPError as e:
                last_exception = e
                status = e.response.status_code if hasattr(e, 'response') else None
                logger.error(f"HTTP Error {status} on attempt {attempt + 1}/{self.MAX_RETRIES}: {method} {endpoint}")
                
                # 4xx errors (client errors) are permanent failures — don't retry
                if status and 400 <= status < 500:
                    raise
                
                # 5xx errors — retry
                if attempt == self.MAX_RETRIES - 1:
                    raise

            except Exception as e:
                last_exception = e
                logger.error(f"Request error on attempt {attempt + 1}/{self.MAX_RETRIES}: {e}")
                if attempt == self.MAX_RETRIES - 1:
                    raise

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception

    def post_registar_fatura(self, xml_payload: str) -> dict:
        """
        Submit invoice XML to AGT.
        POST /registarFactura
        Args:
            xml_payload: XML document to submit
        Returns:
            {request_id: str, resposta: dict}
        """
        try:
            data = {"xml": xml_payload}
            response = self._make_request("POST", "/registarFactura", json=data)
            
            # Extract request_id from response (AGT API response format)
            request_id = response.get("requestId") or response.get("id")
            
            return {
                "request_id": request_id,
                "resposta": response,
            }
        except (requests.HTTPError, requests.Timeout, Exception) as e:
            logger.error(f"Failed to submit fatura: {e}")
            raise

    def get_consultar_fatura(self, request_id: str) -> dict:
        """
        Query invoice status from AGT.
        GET /consultarFactura/{request_id}
        Args:
            request_id: AGT request ID
        Returns:
            {status: str, hash: str, erros: []}
        """
        try:
            endpoint = f"/consultarFactura/{request_id}"
            response = self._make_request("GET", endpoint)
            
            return {
                "status": response.get("status", "PENDENTE"),
                "hash": response.get("hash", ""),
                "erros": response.get("erros", []),
            }
        except (requests.HTTPError, requests.Timeout, Exception) as e:
            logger.error(f"Failed to query fatura {request_id}: {e}")
            raise


# ─── FaturaService ────────────────────────────────────────────────────────

class FaturaService:
    """
    Business logic for invoice submission, polling, and callback handling.
    Implements state machine and AGT integration.
    """

    def __init__(self):
        """Initialize service with HTTP client and crypto service."""
        self.http_client = AgtHttpClient()
        self.crypto_service = AgtCryptoService()

    def submeter_fatura(self, fatura_id: int) -> dict:
        """
        Submit invoice to AGT.
        State machine: PENDENTE → ACEITE or FALHA_TEMPORARIA/PERMANENTE
        Retry: max 5 tentativas, proxima_tentativa_em = now + 15 min
        
        Args:
            fatura_id: Fatura ID
            
        Returns:
            {ok: bool, request_id: str, erro: str}
        """
        try:
            fatura = Fatura.objects.get(pk=fatura_id)
        except Fatura.DoesNotExist:
            logger.error(f"Fatura {fatura_id} not found")
            return {"ok": False, "request_id": None, "erro": "Fatura not found"}

        # Get or create SubmissaoAgt
        submissao, created = SubmissaoAgt.objects.update_or_create(
            fatura=fatura,
            defaults={
                "banca": fatura.banca,
                "estado": "PENDENTE" if created else submissao.estado if not created else "PENDENTE",
            }
        )

        # If already accepted, return early (idempotent)
        if submissao.estado == "ACEITE":
            logger.info(f"Fatura {fatura_id} already submitted (estado=ACEITE)")
            return {"ok": True, "request_id": submissao.codigo_controlo, "erro": None}

        # Check max retries
        if submissao.tentativas >= 5:
            submissao.estado = "FALHA_PERMANENTE"
            submissao.save()
            logger.error(f"Max retries exceeded for Fatura {fatura_id}")
            self._audit_log(fatura, "REJECTED", origin_tipo="API", motivo="Max retries exceeded")
            return {"ok": False, "request_id": None, "erro": "Max retries exceeded"}

        # Build XML payload (simplified for now)
        xml_payload = self._build_fatura_xml(fatura)
        submissao.payload_xml = xml_payload
        submissao.save()

        # Submit to AGT
        try:
            result = self.http_client.post_registar_fatura(xml_payload)
            request_id = result.get("request_id")

            if not request_id:
                raise ValueError("No request_id in AGT response")

            # Success: update state
            submissao.estado = "ACEITE"
            submissao.codigo_controlo = request_id
            submissao.submetida_em = timezone.now()
            submissao.tentativas += 1
            submissao.save()

            # Update Fatura
            fatura.agt_request_id = request_id
            fatura.agt_status = "PENDENTE"
            fatura.save()

            # Audit log
            self._audit_log(fatura, "SUBMITTED", origin_tipo="API")

            logger.info(f"Fatura {fatura_id} submitted successfully (request_id={request_id})")
            return {"ok": True, "request_id": request_id, "erro": None}

        except requests.HTTPError as e:
            status = e.response.status_code if hasattr(e, 'response') else None
            
            # 4xx errors (client errors) → permanent failure
            if status and 400 <= status < 500:
                submissao.estado = "FALHA_PERMANENTE"
                submissao.mensagem = f"Client error: {status} {str(e)}"
                submissao.save()
                logger.error(f"Permanent failure submitting Fatura {fatura_id}: {e}")
                self._audit_log(fatura, "REJECTED", origin_tipo="API", motivo=f"Client error {status}")
                return {"ok": False, "request_id": None, "erro": f"Client error: {status}"}
            
            # 5xx errors → temporary failure
            submissao.estado = "FALHA_TEMPORARIA"
            submissao.proxima_tentativa_em = timezone.now() + timedelta(minutes=15)
            submissao.tentativas += 1
            submissao.ultima_tentativa_em = timezone.now()
            submissao.mensagem = f"Server error: {status} {str(e)}"
            submissao.save()
            logger.warning(f"Temporary failure submitting Fatura {fatura_id}: {e}")
            return {"ok": False, "request_id": None, "erro": f"Server error: {status}"}

        except requests.Timeout as e:
            # Timeout → temporary failure
            submissao.estado = "FALHA_TEMPORARIA"
            submissao.proxima_tentativa_em = timezone.now() + timedelta(minutes=15)
            submissao.tentativas += 1
            submissao.ultima_tentativa_em = timezone.now()
            submissao.mensagem = f"Timeout: {str(e)}"
            submissao.save()
            logger.warning(f"Timeout submitting Fatura {fatura_id}: {e}")
            return {"ok": False, "request_id": None, "erro": "Timeout"}

        except Exception as e:
            logger.error(f"Unexpected error submitting Fatura {fatura_id}: {e}")
            submissao.estado = "FALHA_TEMPORARIA"
            submissao.proxima_tentativa_em = timezone.now() + timedelta(minutes=15)
            submissao.tentativas += 1
            submissao.mensagem = f"Error: {str(e)}"
            submissao.save()
            return {"ok": False, "request_id": None, "erro": str(e)}

    def polling_status(self, fatura_id: int) -> dict:
        """
        Query invoice status from AGT.
        Updates Fatura.agt_status, agt_hash_validacao, agt_erros.
        
        Args:
            fatura_id: Fatura ID
            
        Returns:
            {ok: bool, status: 'APROVADA'|'REJEITADA'|'PENDENTE', hash: str, erros: []}
        """
        try:
            fatura = Fatura.objects.get(pk=fatura_id)
        except Fatura.DoesNotExist:
            logger.error(f"Fatura {fatura_id} not found")
            return {"ok": False, "status": None, "hash": "", "erros": []}

        if not fatura.agt_request_id:
            logger.warning(f"Fatura {fatura_id} has no agt_request_id")
            return {"ok": False, "status": None, "hash": "", "erros": []}

        try:
            result = self.http_client.get_consultar_fatura(fatura.agt_request_id)
            
            status = result.get("status", "PENDENTE")
            hash_val = result.get("hash", "")
            erros = result.get("erros", [])

            # Update Fatura
            fatura.agt_status = status
            fatura.agt_hash_validacao = hash_val
            fatura.agt_erros = erros if erros else None
            fatura.agt_processada_em = timezone.now()
            fatura.save()

            # Audit log
            acao = "APPROVED" if status == "APROVADA" else "REJECTED" if status == "REJEITADA" else "UPDATED"
            self._audit_log(fatura, acao, origin_tipo="SISTEMA_AGT")

            logger.info(f"Fatura {fatura_id} status updated: {status}")
            return {"ok": True, "status": status, "hash": hash_val, "erros": erros}

        except Exception as e:
            logger.error(f"Error polling status for Fatura {fatura_id}: {e}")
            return {"ok": False, "status": None, "hash": "", "erros": [str(e)]}

    def processar_callback(self, payload: dict) -> dict:
        """
        Process AGT callback webhook.
        Webhook payload: {requestId, status: 'APPROVED'|'REJECTED'|'PENDING', hash, erros}
        
        Args:
            payload: dict with callback data
            
        Returns:
            {ok: bool, reason: str}
        """
        try:
            request_id = payload.get("requestId")
            status = payload.get("status", "PENDING")
            hash_val = payload.get("hash", "")
            erros = payload.get("erros", [])

            if not request_id:
                logger.warning("Callback missing requestId")
                return {"ok": False, "reason": "Missing requestId"}

            # Find SubmissaoAgt by codigo_controlo (which is the request_id)
            try:
                submissao = SubmissaoAgt.objects.get(codigo_controlo=request_id)
            except SubmissaoAgt.DoesNotExist:
                logger.warning(f"SubmissaoAgt not found for request_id={request_id}")
                return {"ok": False, "reason": f"SubmissaoAgt not found for {request_id}"}

            fatura = submissao.fatura
            banca = fatura.banca

            # Map AGT status to SubmissaoAgt estado
            estado_map = {
                "APPROVED": "ACEITE",
                "REJECTED": "REJEITADA",
                "PENDING": "PENDENTE",
            }
            novo_estado = estado_map.get(status, "PENDENTE")

            # Update SubmissaoAgt
            submissao.estado = novo_estado
            submissao.save()

            # Update Fatura
            status_map = {
                "APPROVED": "APROVADA",
                "REJECTED": "REJEITADA",
                "PENDING": "PENDENTE",
            }
            fatura.agt_status = status_map.get(status, "PENDENTE")
            fatura.agt_hash_validacao = hash_val
            fatura.agt_erros = erros if erros else None
            fatura.agt_processada_em = timezone.now()
            fatura.save()

            # Audit log
            acao = "APPROVED" if status == "APPROVED" else "REJECTED" if status == "REJECTED" else "UPDATED"
            self._audit_log(fatura, acao, origin_tipo="WEBHOOK")

            logger.info(f"Callback processed: request_id={request_id}, status={status}, fatura={fatura.numero}")
            return {"ok": True, "reason": f"Processed {status}"}

        except Exception as e:
            logger.error(f"Error processing callback: {e}", exc_info=True)
            return {"ok": False, "reason": str(e)}

    def _build_fatura_xml(self, fatura: Fatura) -> str:
        """
        Build XML payload for AGT submission.
        This is a simplified placeholder — in production, generate proper SAF-T XML.
        
        Args:
            fatura: Fatura object
            
        Returns:
            XML string
        """
        nif_emitente = settings.AGT_NIF_EMITENTE or "000000000"
        empresa = settings.AGT_COMPANY_NAME or "CDOA"
        
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Fatura>
  <NumeroFatura>{fatura.numero}</NumeroFatura>
  <Serie>{fatura.serie}</Serie>
  <TipoDocumento>{fatura.tipo_documento}</TipoDocumento>
  <NifEmitente>{nif_emitente}</NifEmitente>
  <Empresa>{empresa}</Empresa>
  <ClienteNif>{fatura.cliente_nif}</ClienteNif>
  <ClienteDesignacao>{fatura.cliente_designacao}</ClienteDesignacao>
  <Total>{fatura.total}</Total>
  <EmitidaEm>{fatura.emitida_em.isoformat() if fatura.emitida_em else timezone.now().isoformat()}</EmitidaEm>
</Fatura>"""
        
        return xml

    def _audit_log(self, fatura: Fatura, acao: str, origin_tipo: str = "API", motivo: str = ""):
        """
        Create audit log entry.
        
        Args:
            fatura: Fatura object
            acao: action code
            origin_tipo: origin type (API, SISTEMA_AGT, WEBHOOK)
            motivo: reason/message
        """
        try:
            RegistoAuditoria.objects.create(
                banca=fatura.banca,
                acao=acao,
                origin_tipo=origin_tipo,
                entity_tipo="Fatura",
                entity_id=fatura.id,
                motivo=motivo,
            )
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
