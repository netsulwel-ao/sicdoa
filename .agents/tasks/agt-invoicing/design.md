# AGT Electronic Invoicing Module — Technical Design
**Project:** SICDOA  
**Date:** 2026-01-01 (revision 1)  
**Status:** FIRST DRAFT (awaiting design review)

---

## Overview

This design specifies a production-ready, autonomous AGT (Administração Geral Tributária) Electronic Invoicing module for SICDOA. The module integrates with Angola's e-invoicing infrastructure via REST API + JWS RS256 digital signatures, processes submissions asynchronously (polling + callbacks), and exposes monitoring dashboards and REST APIs for authorized users.

The module **reuses existing SICDOA patterns** (multi-tenant via `banca_id`, role-based permissions, Celery async, session-based auth, Tailwind + base.html templates) and **reconciles with** the existing `financeiro/views_agt.py` callback implementation (see decision in Webhook Callback section).

**Key principle:** The module is independent of domain (clinic, shop, services) and exposes only REST APIs + ORM models; frontend consumption is the implementer's choice (Django templates here, future: SPA).

---

## 1. Data Models

### 1.1 ConfiguracaoFiscal

**Purpose:** Fiscal configuration per `banca` (multi-tenant). Stores AGT integration enablement, endpoint, NIF emitter, and credential metadata.

```python
class ConfiguracaoFiscal(models.Model):
    # Multi-tenant isolation
    banca = models.OneToOneField(
        'rh.Banca',
        on_delete=models.CASCADE,
        related_name='configuracao_fiscal_agt',
        help_text='Banca/empresa this config belongs to',
    )
    
    # Integration control
    agt_integration_enabled = models.BooleanField(
        default=False,
        help_text='Enable AGT submission for this banca',
    )
    
    # Fiscal identity
    nif_emitente = models.CharField(
        max_length=20,
        blank=True,
        help_text='Tax ID of the issuing entity (from banca or override)',
    )
    company_name = models.CharField(
        max_length=255,
        blank=True,
        help_text='Legal name of issuer',
    )
    
    # Series configuration
    serie_padrao = models.CharField(
        max_length=10,
        default='A',
        help_text='Default invoicing series (e.g. A, B, FT)',
    )
    
    # API endpoint (settable per banca if needed)
    agt_api_endpoint = models.URLField(
        blank=True,
        help_text='AGT API base URL (if blank, uses settings.AGT_API_BASE)',
    )
    
    # Metadata
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'agt_invoicing_configuracao_fiscal'
        verbose_name = 'Configuração Fiscal AGT'
        verbose_name_plural = 'Configurações Fiscais AGT'
    
    def __str__(self):
        return f"{self.banca.nome} — {'Ativo' if self.agt_integration_enabled else 'Inativo'}"
    
    def get_nif_emitente(self):
        """Return NIF, fallback to banca.nif, then to settings."""
        if self.nif_emitente:
            return self.nif_emitente
        if hasattr(self.banca, 'nif') and self.banca.nif:
            return self.banca.nif
        from django.conf import settings
        return getattr(settings, 'AGT_NIF_EMITENTE', '')
    
    def get_api_endpoint(self):
        """Return AGT API endpoint, fallback to settings."""
        if self.agt_api_endpoint:
            return self.agt_api_endpoint
        from django.conf import settings
        return getattr(settings, 'AGT_API_BASE', 'https://sifphml.minfin.gov.ao/sigt/fe/v1')
```

---

### 1.2 Fatura

**Purpose:** Invoice registry. Represents a fiscal document submitted to AGT with full lifecycle tracking.

```python
class EstadoFatura(models.TextChoices):
    RASCUNHO = 'RASCUNHO', 'Rascunho'
    PENDENTE_AGT = 'PENDENTE_AGT', 'Pendente AGT'
    EMITIDA = 'EMITIDA', 'Emitida'
    REJEITADA = 'REJEITADA', 'Rejeitada'

class EstadoAgt(models.TextChoices):
    APROVADA = 'APROVADA', 'Aprovada'
    REJEITADA = 'REJEITADA', 'Rejeitada'
    PENDENTE = 'PENDENTE', 'Pendente'

class TipoDocumento(models.TextChoices):
    FT = 'FT', 'Fatura'
    FR = 'FR', 'Fatura Recibo'
    NC = 'NC', 'Nota de Crédito'
    ND = 'ND', 'Nota de Débito'
    RC = 'RC', 'Recibo'

class Fatura(models.Model):
    # Multi-tenant
    banca = models.ForeignKey(
        'rh.Banca',
        on_delete=models.CASCADE,
        related_name='faturas_agt',
        db_index=True,
    )
    
    # Document identity
    numero = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text='Official number assigned by AGT',
    )
    serie = models.CharField(
        max_length=10,
        blank=True,
        help_text='Series (e.g., A, B)',
    )
    tipo_documento = models.CharField(
        max_length=10,
        choices=TipoDocumento,
        default=TipoDocumento.FT,
        db_index=True,
    )
    
    # Dates
    emitida_em = models.DateTimeField(
        help_text='Emission date/time',
    )
    criada_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizada_em = models.DateTimeField(auto_now=True)
    
    # Parties
    cliente_designacao = models.CharField(max_length=255)
    cliente_nif = models.CharField(max_length=20)
    
    # Amount (always Decimal)
    total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text='Total invoice amount in AOA',
    )
    
    # Local state
    estado = models.CharField(
        max_length=20,
        choices=EstadoFatura,
        default=EstadoFatura.RASCUNHO,
        db_index=True,
    )
    
    # AGT integration
    agt_request_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Request ID from AGT submission',
    )
    agt_status = models.CharField(
        max_length=20,
        choices=EstadoAgt,
        null=True,
        blank=True,
        db_index=True,
        help_text='AGT processing status',
    )
    agt_hash_validacao = models.CharField(
        max_length=256,
        blank=True,
        help_text='Validation hash from AGT',
    )
    agt_processada_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When AGT finished processing',
    )
    agt_erros = models.JSONField(
        null=True,
        blank=True,
        help_text='Error details from AGT (list of {code, message, field})',
    )
    
    # QR code and metadata (optional fields for future use)
    qr_code = models.TextField(blank=True, help_text='QR code data (may be base64 image)')
    
    class Meta:
        db_table = 'agt_invoicing_fatura'
        verbose_name = 'Fatura AGT'
        verbose_name_plural = 'Faturas AGT'
        indexes = [
            models.Index(fields=['banca', 'estado'], name='idx_fatura_banca_estado'),
            models.Index(fields=['banca', 'agt_status'], name='idx_fatura_banca_agt_status'),
            models.Index(fields=['agt_request_id'], name='idx_fatura_agt_request_id'),
            models.Index(fields=['banca', '-emitida_em'], name='idx_fatura_banca_data'),
        ]
        ordering = ['-emitida_em']
    
    def __str__(self):
        return f"{self.numero or self.agt_request_id or 'draft'} — {self.cliente_designacao}"
    
    def is_terminal(self):
        """Invoice is in a final state (not pending processing)."""
        return self.estado in (EstadoFatura.EMITIDA, EstadoFatura.REJEITADA)
```

---

### 1.3 SubmissaoAgt

**Purpose:** Submission queue + retry history. Tracks each attempt to submit a Fatura to AGT, including retry logic, payload, and state machine.

```python
class EstadoSubmissao(models.TextChoices):
    PENDENTE = 'PENDENTE', 'Pendente'
    ACEITE = 'ACEITE', 'Aceite'
    REJEITADA = 'REJEITADA', 'Rejeitada'
    FALHA_TEMPORARIA = 'FALHA_TEMPORARIA', 'Falha Temporária'
    FALHA_PERMANENTE = 'FALHA_PERMANENTE', 'Falha Permanente'
    NAO_SUBMETIDA = 'NAO_SUBMETIDA', 'Não Submetida'  # Integration disabled

class SubmissaoAgt(models.Model):
    fatura = models.ForeignKey(
        Fatura,
        on_delete=models.PROTECT,
        related_name='submissoes',
        db_index=True,
    )
    
    # State machine
    estado = models.CharField(
        max_length=30,
        choices=EstadoSubmissao,
        default=EstadoSubmissao.PENDENTE,
        db_index=True,
    )
    
    # Payload snapshot
    payload_xml = models.TextField(
        blank=True,
        help_text='XML/JSON sent to AGT (for audit)',
    )
    
    # Timing
    submetida_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When first submitted',
    )
    ultima_tentativa_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last retry attempt',
    )
    proxima_tentativa_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Scheduled next retry (Celery countdown)',
    )
    
    # Retry tracking
    tentativas = models.PositiveIntegerField(
        default=0,
        help_text='Number of retry attempts',
    )
    
    # Feedback
    mensagem = models.TextField(
        blank=True,
        help_text='Error message or AGT response summary',
    )
    codigo_controlo = models.CharField(
        max_length=100,
        blank=True,
        help_text='AGT control code on success',
    )
    
    # Metadata
    criada_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizada_em = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'agt_invoicing_submissao'
        verbose_name = 'Submissão AGT'
        verbose_name_plural = 'Submissões AGT'
        indexes = [
            models.Index(fields=['fatura', 'estado'], name='idx_submissao_fatura_estado'),
            models.Index(fields=['estado', 'proxima_tentativa_em'], name='idx_submissao_retry'),
        ]
        ordering = ['-criada_em']
    
    def __str__(self):
        return f"Submissão {self.fatura.numero or self.fatura.agt_request_id} — {self.estado}"
    
    def deve_retentar(self):
        """Check if this submission should be retried (and hasn't exceeded max)."""
        return (
            self.estado == EstadoSubmissao.FALHA_TEMPORARIA
            and self.tentativas < 5
            and (self.proxima_tentativa_em is None or timezone.now() >= self.proxima_tentativa_em)
        )
```

---

### 1.4 RegistoAuditoria

**Purpose:** Audit trail for all AGT-related actions. Reuses or complements `users.LogAtividade` if needed.

```python
class RegistoAuditoria(models.Model):
    # Actor
    usuario_id = models.IntegerField(null=True, blank=True)
    usuario_nome = models.CharField(max_length=255, blank=True)
    
    # Origin (who/what triggered the action)
    origem = models.CharField(
        max_length=50,
        choices=[
            ('utilizador', 'Utilizador'),
            ('sistema', 'Sistema Automatizado'),
            ('webhook', 'Webhook AGT'),
            ('celery', 'Celery Task'),
        ],
        db_index=True,
    )
    
    # Entity touched
    tipo_entidade = models.CharField(max_length=50)  # 'Fatura', 'Submissao', etc.
    id_entidade = models.IntegerField()
    
    # Action
    acao = models.CharField(
        max_length=100,
        choices=[
            ('criar', 'Criar'),
            ('atualizar', 'Atualizar'),
            ('submeter', 'Submeter à AGT'),
            ('rejeitar', 'Rejeitar'),
            ('validar', 'Validar'),
            ('consultar_status', 'Consultar Status'),
            ('callback', 'Receber Callback'),
        ],
    )
    
    # Details
    motivo = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    detalhes = models.JSONField(null=True, blank=True)
    
    # Multi-tenant
    banca_id = models.IntegerField(db_index=True)
    
    # Timestamp
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'agt_invoicing_auditoria'
        verbose_name = 'Registo de Auditoria AGT'
        verbose_name_plural = 'Registos de Auditoria AGT'
        indexes = [
            models.Index(fields=['banca_id', '-criado_em'], name='idx_auditoria_banca'),
            models.Index(fields=['tipo_entidade', 'id_entidade'], name='idx_auditoria_entidade'),
        ]
        ordering = ['-criado_em']
    
    def __str__(self):
        return f"[{self.criado_em:%d/%m %H:%M}] {self.acao} — {self.tipo_entidade}#{self.id_entidade}"
```

---

## 2. Services & Crypto

### 2.1 AgtCryptoService

**Purpose:** Handle JWS RS256 signing for all three required signatures: software, document, request.

**File:** `agt_invoicing/services/crypto.py`

```python
import json
import base64
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
import jwt

class AgtCryptoService:
    """
    Manages JWS RS256 signing for AGT API calls.
    Loads private keys from env vars or filesystem (.pem files).
    """
    
    def __init__(self, settings):
        """
        Args:
            settings: Django settings object
        """
        self.settings = settings
        self._software_key = None
        self._contributor_key = None
    
    def _load_private_key_pem(self, pem_content):
        """Load private key from PEM string."""
        if isinstance(pem_content, str):
            pem_content = pem_content.encode('utf-8')
        return serialization.load_pem_private_key(
            pem_content,
            password=None,
            backend=default_backend(),
        )
    
    def _read_key_file(self, file_path):
        """Read private key from .pem file."""
        if not file_path:
            return None
        path = Path(file_path)
        if not path.exists():
            return None
        return path.read_bytes()
    
    def get_software_private_key(self):
        """Load software producer's private key."""
        if self._software_key:
            return self._software_key
        
        # Try env var first (direct PEM content)
        key_content = getattr(self.settings, 'AGT_SOFTWARE_PRIVATE_KEY', '')
        if key_content:
            self._software_key = self._load_private_key_pem(key_content)
            return self._software_key
        
        # Try file path
        file_path = getattr(self.settings, 'AGT_SOFTWARE_PRIVATE_KEY_FILE', '')
        if file_path:
            key_content = self._read_key_file(file_path)
            if key_content:
                self._software_key = self._load_private_key_pem(key_content)
                return self._software_key
        
        raise ValueError('AGT_SOFTWARE_PRIVATE_KEY not configured')
    
    def get_contributor_private_key(self):
        """Load contributor's private key (issued by AGT)."""
        if self._contributor_key:
            return self._contributor_key
        
        key_content = getattr(self.settings, 'AGT_CONTRIBUTOR_PRIVATE_KEY', '')
        if key_content:
            self._contributor_key = self._load_private_key_pem(key_content)
            return self._contributor_key
        
        file_path = getattr(self.settings, 'AGT_CONTRIBUTOR_PRIVATE_KEY_FILE', '')
        if file_path:
            key_content = self._read_key_file(file_path)
            if key_content:
                self._contributor_key = self._load_private_key_pem(key_content)
                return self._contributor_key
        
        raise ValueError('AGT_CONTRIBUTOR_PRIVATE_KEY not configured')
    
    def _to_canonical_json(self, obj):
        """Convert object to canonical JSON (no spaces, sorted keys)."""
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
        )
    
    def sign_jws_rs256(self, payload, private_key):
        """
        Create JWS compact format: header.payload.signature
        Args:
            payload: dict to sign
            private_key: cryptography PrivateKey object
        Returns:
            JWS token string
        """
        header = {'alg': 'RS256', 'typ': 'JWT'}
        payload_canonical = self._to_canonical_json(payload)
        
        # Use PyJWT for standard encoding
        token = jwt.encode(
            json.loads(payload_canonical),
            private_key,
            algorithm='RS256',
            headers=header,
        )
        return token
    
    def sign_software_signature(self):
        """
        jwsSoftwareSignature: Sign software producer info.
        """
        payload = {
            'productId': getattr(self.settings, 'AGT_PRODUCT_ID', 'SICDOA'),
            'productVersion': getattr(self.settings, 'AGT_PRODUCT_VERSION', '1.0.0'),
            'softwareValidationNumber': getattr(self.settings, 'AGT_SOFTWARE_VALIDATION_NUMBER', ''),
        }
        key = self.get_software_private_key()
        return self.sign_jws_rs256(payload, key)
    
    def sign_document_signature(self, fatura):
        """
        jwsDocumentSignature: Sign invoice document data.
        """
        payload = {
            'documentNo': fatura.numero or '',
            'taxRegistrationNumber': fatura.banca.nif if hasattr(fatura, 'banca') and fatura.banca else '',
            'documentType': fatura.tipo_documento,
            'documentDate': fatura.emitida_em.isoformat(),
            'customerTaxID': fatura.cliente_nif,
            'customerCountry': 'AO',  # Angola
            'companyName': fatura.banca.nome if hasattr(fatura, 'banca') and fatura.banca else '',
            'documentTotals': {
                'taxPayable': '0.00',  # If IVA included, compute
                'netTotal': str(fatura.total),
                'grossTotal': str(fatura.total),
            }
        }
        key = self.get_contributor_private_key()
        return self.sign_jws_rs256(payload, key)
    
    def sign_request_signature(self, request_payload):
        """
        jwsSignature: Sign the entire request payload.
        """
        key = self.get_contributor_private_key()
        return self.sign_jws_rs256(request_payload, key)
```

---

### 2.2 AgtHttpClient

**Purpose:** HTTP communication with AGT API, with Basic Auth, retry logic, and timeout.

**File:** `agt_invoicing/services/http_client.py`

```python
import logging
import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings
from decimal import Decimal

logger = logging.getLogger(__name__)

class AgtHttpClient:
    """HTTP client for AGT API with Basic Auth and retry."""
    
    TIMEOUT = 5  # seconds
    MAX_RETRIES = 3
    
    def __init__(self):
        self.username = getattr(settings, 'AGT_USERNAME', '')
        self.password = getattr(settings, 'AGT_PASSWORD', '')
        self.base_url = getattr(settings, 'AGT_API_BASE', 'https://sifphml.minfin.gov.ao/sigt/fe/v1')
    
    def _make_session(self):
        """Create requests session with Basic Auth."""
        session = requests.Session()
        session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })
        if self.username:
            session.auth = HTTPBasicAuth(self.username, self.password)
        return session
    
    def submit_invoice(self, payload_dict):
        """
        POST /registarFactura
        Args:
            payload_dict: dict with jws signatures and invoice data
        Returns:
            (success: bool, response_data: dict, error: str or None)
        Raises:
            May raise AgtHttpError (custom exception) on fatal errors
        """
        session = self._make_session()
        url = f'{self.base_url}/registarFactura'
        
        try:
            response = session.post(
                url,
                json=payload_dict,
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            return True, data, None
        
        except requests.exceptions.Timeout:
            error = 'AGT API timeout (5s)'
            logger.warning(error)
            return False, {}, error
        
        except requests.exceptions.ConnectionError as e:
            error = f'AGT API connection error: {e}'
            logger.warning(error)
            return False, {}, error
        
        except requests.exceptions.HTTPError as e:
            error = f'AGT API HTTP {e.response.status_code}: {e.response.text}'
            logger.error(error)
            return False, {}, error
        
        except Exception as e:
            logger.error(f'Unexpected AGT API error: {e}', exc_info=True)
            raise
    
    def check_invoice_status(self, request_id):
        """
        GET /consultarFactura/{requestId}
        Returns:
            (success: bool, response_data: dict, error: str or None)
        """
        session = self._make_session()
        url = f'{self.base_url}/consultarFactura/{request_id}'
        
        try:
            response = session.get(url, timeout=self.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            return True, data, None
        
        except requests.exceptions.Timeout:
            error = 'AGT polling timeout'
            logger.warning(error)
            return False, {}, error
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                error = f'Request {request_id} not found in AGT'
                return False, {}, error
            error = f'AGT polling error {e.response.status_code}'
            logger.error(error)
            return False, {}, error
        
        except Exception as e:
            logger.error(f'Unexpected polling error: {e}', exc_info=True)
            raise
```

---

### 2.3 FaturaService

**Purpose:** State machine for invoice submission. Encapsulates business logic: read config, build payload, submit, handle responses, manage retries.

**File:** `agt_invoicing/services/fatura_service.py`

```python
import logging
import uuid
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from decimal import Decimal

from agt_invoicing.models import (
    ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria,
    EstadoFatura, EstadoAgt, EstadoSubmissao, TipoDocumento,
)
from .crypto import AgtCryptoService
from .http_client import AgtHttpClient

logger = logging.getLogger(__name__)

class FaturaService:
    """
    Orchestrates invoice submission to AGT.
    Idempotent: submitting the same fatura twice is safe.
    """
    
    def __init__(self, banca=None, settings_obj=None):
        self.banca = banca
        self.settings = settings_obj or settings
        self.crypto = AgtCryptoService(self.settings)
        self.http = AgtHttpClient()
    
    def _get_configuracao(self):
        """Fetch or create ConfiguracaoFiscal for this banca."""
        if not self.banca:
            raise ValueError('banca required')
        config, _ = ConfiguracaoFiscal.objects.get_or_create(banca=self.banca)
        return config
    
    def _gerar_request_id(self):
        """Generate unique request ID."""
        return f"REQ-{int(timezone.now().timestamp())}-{uuid.uuid4().hex[:8]}".upper()
    
    def _construir_payload(self, fatura):
        """
        Build complete JSON payload with all 3 JWS signatures.
        Field names follow AGT spec (camelCase).
        """
        config = self._get_configuracao()
        
        # Generate signatures
        sw_sig = self.crypto.sign_software_signature()
        doc_sig = self.crypto.sign_document_signature(fatura)
        
        request_id = fatura.agt_request_id or self._gerar_request_id()
        
        # Base request payload (before signing)
        base_payload = {
            'taxRegistrationNumber': config.get_nif_emitente(),
            'requestID': request_id,
        }
        
        req_sig = self.crypto.sign_request_signature(base_payload)
        
        # Full payload sent to AGT
        payload = {
            'jwsSoftwareSignature': sw_sig,
            'jwsDocumentSignature': doc_sig,
            'jwsSignature': req_sig,
            'taxRegistrationNumber': config.get_nif_emitente(),
            'requestID': request_id,
            'documentNo': fatura.numero or '',
            'seriesCode': fatura.serie or config.serie_padrao,
            'documentType': fatura.tipo_documento,
            'documentDate': fatura.emitida_em.isoformat(),
            'customerTaxID': fatura.cliente_nif,
            'customerCountry': 'AO',
            'companyName': fatura.banca.nome if fatura.banca else '',
            'documentTotals': {
                'taxPayable': '0.00',
                'netTotal': str(fatura.total),
                'grossTotal': str(fatura.total),
            },
        }
        return payload, request_id
    
    def submeter(self, fatura, user_id=None, user_name=''):
        """
        Submit invoice to AGT (or skip if integration disabled).
        Idempotent via update_or_create on (fatura_id, estado=PENDENTE).
        
        Returns:
            (success: bool, submissao: SubmissaoAgt, message: str)
        """
        config = self._get_configuracao()
        
        # Check if integration is enabled
        if not config.agt_integration_enabled:
            submissao, created = SubmissaoAgt.objects.update_or_create(
                fatura=fatura,
                defaults={
                    'estado': EstadoSubmissao.NAO_SUBMETIDA,
                    'mensagem': 'Integração AGT desativada para esta banca',
                    'criada_em': timezone.now(),
                }
            )
            logger.info(f'Fatura {fatura.pk} — integração desativada')
            return True, submissao, 'Integração AGT desativada'
        
        # Idempotent: update_or_create
        with transaction.atomic():
            submissao, created = SubmissaoAgt.objects.update_or_create(
                fatura=fatura,
                defaults={
                    'estado': EstadoSubmissao.PENDENTE,
                    'tentativas': 0,
                    'criada_em': timezone.now(),
                }
            )
            
            # Build payload
            try:
                payload, request_id = self._construir_payload(fatura)
                fatura.agt_request_id = request_id
                fatura.estado = EstadoFatura.PENDENTE_AGT
                fatura.save(update_fields=['agt_request_id', 'estado', 'atualizada_em'])
            except Exception as e:
                submissao.estado = EstadoSubmissao.FALHA_PERMANENTE
                submissao.mensagem = f'Erro ao construir payload: {e}'
                submissao.save()
                logger.error(f'Fatura {fatura.pk} — payload build error: {e}')
                return False, submissao, str(e)
            
            # HTTP submit
            submissao.payload_xml = str(payload)  # Store as reference
            submissao.submetida_em = timezone.now()
            submissao.tentativas += 1
            
            success, response, error = self.http.submit_invoice(payload)
            
            if success:
                # 2xx response from AGT
                submissao.estado = EstadoSubmissao.ACEITE
                submissao.codigo_controlo = response.get('controlCode', '')
                submissao.mensagem = 'Aceite pela AGT'
                
                # Update fatura state
                fatura.agt_status = EstadoAgt.PENDENTE  # Start as pending
                fatura.estado = EstadoFatura.EMITIDA  # Mark locally as issued
                fatura.save(update_fields=['agt_status', 'estado', 'atualizada_em'])
                
                logger.info(f'Fatura {fatura.pk} aceite na AGT: {request_id}')
                msg = 'Aceite pela AGT — aguardando processamento'
            
            elif error and 'timeout' in error.lower() or 'connection' in error.lower():
                # Temporary failure — schedule retry
                submissao.estado = EstadoSubmissao.FALHA_TEMPORARIA
                submissao.proxima_tentativa_em = timezone.now() + timedelta(minutes=15)
                submissao.mensagem = error
                fatura.estado = EstadoFatura.RASCUNHO  # Revert to draft
                fatura.save(update_fields=['estado', 'atualizada_em'])
                logger.warning(f'Fatura {fatura.pk} — falha temporária, retry em 15min')
                msg = 'Falha temporária — novo intento agendado'
            
            else:
                # Permanent failure
                submissao.estado = EstadoSubmissao.FALHA_PERMANENTE
                submissao.mensagem = error or 'Erro desconhecido'
                fatura.estado = EstadoFatura.REJEITADA
                fatura.save(update_fields=['estado', 'atualizada_em'])
                logger.error(f'Fatura {fatura.pk} — falha permanente: {error}')
                msg = f'Falha permanente: {error}'
            
            submissao.atualizada_em = timezone.now()
            submissao.save()
        
        # Log audit
        self._registar_auditoria(
            fatura=fatura,
            acao='submeter',
            origem='celery' if not user_id else 'utilizador',
            usuario_id=user_id,
            motivo=msg,
        )
        
        return success, submissao, msg
    
    def processar_callback(self, request_id, status, numero=None, erros=None, hash_validacao=''):
        """
        Process webhook callback from AGT.
        Atomically updates fatura with callback data.
        
        Args:
            request_id: AGT requestID
            status: 'APPROVED', 'REJECTED', or 'PENDING'
            numero: official invoice number assigned by AGT
            erros: list of error dicts if REJECTED
            hash_validacao: validation hash
        
        Returns:
            (fatura or None, success: bool, message: str)
        """
        try:
            fatura = Fatura.objects.select_for_update().get(agt_request_id=request_id)
        except Fatura.DoesNotExist:
            logger.warning(f'Callback: fatura com agt_request_id={request_id} não encontrada')
            return None, False, 'not_found'
        
        with transaction.atomic():
            # Map AGT status to local state
            status_map = {
                'APPROVED': EstadoAgt.APROVADA,
                'REJECTED': EstadoAgt.REJEITADA,
                'PENDING': EstadoAgt.PENDENTE,
            }
            
            local_status = status_map.get(status, EstadoAgt.PENDENTE)
            
            # Determine fatura.estado
            if local_status == EstadoAgt.APROVADA:
                fatura.estado = EstadoFatura.EMITIDA
            elif local_status == EstadoAgt.REJEITADA:
                fatura.estado = EstadoFatura.REJEITADA
            else:
                fatura.estado = EstadoFatura.PENDENTE_AGT
            
            fatura.agt_status = local_status
            fatura.agt_hash_validacao = hash_validacao
            fatura.agt_processada_em = timezone.now()
            if numero:
                fatura.numero = numero
            if erros:
                fatura.agt_erros = erros
            fatura.save()
            
            # Update submission
            SubmissaoAgt.objects.filter(fatura=fatura).update(
                estado=EstadoSubmissao.ACEITE,
                atualizada_em=timezone.now(),
            )
        
        self._registar_auditoria(
            fatura=fatura,
            acao='callback',
            origem='webhook',
            motivo=f'Callback: status={status}',
        )
        
        return fatura, True, 'ok'
    
    def _registar_auditoria(self, fatura, acao, origem, usuario_id=None, motivo=''):
        """Log audit entry."""
        try:
            RegistoAuditoria.objects.create(
                usuario_id=usuario_id,
                origem=origem,
                tipo_entidade='Fatura',
                id_entidade=fatura.pk,
                acao=acao,
                motivo=motivo,
                banca_id=fatura.banca_id,
                criado_em=timezone.now(),
            )
        except Exception as e:
            logger.error(f'Erro ao registar auditoria: {e}')
```

---

## 3. Celery Task

**File:** `agt_invoicing/tasks.py`

```python
from celery import shared_task
from django.utils import timezone
from agt_invoicing.models import Fatura, SubmissaoAgt, EstadoSubmissao
from .services.fatura_service import FaturaService
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=5)
def submit_fatura_task(self, fatura_id):
    """
    Async task: submit fatura to AGT.
    On temporary failure, reschedule with 15min countdown.
    """
    try:
        fatura = Fatura.objects.get(pk=fatura_id)
        service = FaturaService(banca=fatura.banca)
        success, submissao, msg = service.submeter(fatura, user_id=None, user_name='Celery')
        
        if not success and submissao.estado == EstadoSubmissao.FALHA_TEMPORARIA:
            # Reschedule
            logger.info(f'Fatura {fatura_id} — retrying in 15 minutes')
            raise self.retry(countdown=900)  # 15 minutes
        
        return {'fatura_id': fatura_id, 'success': success, 'message': msg}
    
    except Fatura.DoesNotExist:
        logger.error(f'Fatura {fatura_id} not found')
        return {'fatura_id': fatura_id, 'success': False, 'message': 'not_found'}
    
    except Exception as exc:
        logger.error(f'Task error for fatura {fatura_id}: {exc}', exc_info=True)
        raise

@shared_task
def consultar_status_fatura_task(fatura_id):
    """
    Polling task: check invoice status from AGT.
    Scheduled periodically for all PENDENTE_AGT faturas.
    """
    try:
        fatura = Fatura.objects.get(pk=fatura_id)
        if not fatura.agt_request_id:
            return {'fatura_id': fatura_id, 'status': 'no_request_id'}
        
        service = FaturaService(banca=fatura.banca)
        success, response, error = service.http.check_invoice_status(fatura.agt_request_id)
        
        if success:
            status = response.get('status', 'PENDING')
            numero = response.get('invoiceNumber')
            erros = response.get('errors', [])
            hash_val = response.get('validationHash', '')
            
            fatura, ok, msg = service.processar_callback(
                request_id=fatura.agt_request_id,
                status=status,
                numero=numero,
                erros=erros,
                hash_validacao=hash_val,
            )
            return {'fatura_id': fatura_id, 'status': status, 'success': ok}
        
        else:
            logger.warning(f'Polling error for fatura {fatura_id}: {error}')
            return {'fatura_id': fatura_id, 'error': error}
    
    except Fatura.DoesNotExist:
        logger.error(f'Fatura {fatura_id} not found')
        return {'fatura_id': fatura_id, 'error': 'not_found'}
```

---

## 4. REST API Endpoints

**File:** `agt_invoicing/views.py` (or `api.py` for clarity)

All endpoints require authentication + `require_financial_permission` decorator (see Permissions section).

### 4.1 GET /api/agt/stats/

**Purpose:** KPI dashboard — summary statistics.

**Response:**
```json
{
  "emitidas": 150,
  "rejeitadas": 12,
  "pendentes": 8,
  "por_estado": {
    "RASCUNHO": 2,
    "PENDENTE_AGT": 8,
    "EMITIDA": 150,
    "REJEITADA": 12
  },
  "por_agt_status": {
    "APROVADA": 150,
    "REJEITADA": 12,
    "PENDENTE": 8
  }
}
```

**Implementation:** Filter by `banca_id`, aggregate `estado` and `agt_status`.

---

### 4.2 GET /api/agt/pendentes/

**Purpose:** List pending invoices (awaiting AGT response).

**Query params:**
- `page`: pagination (default 1)
- `limit`: per-page (default 50, max 100)
- `search`: filter by numero/cliente_designacao/cliente_nif

**Response:**
```json
{
  "count": 123,
  "next": "http://...",
  "previous": null,
  "results": [
    {
      "id": 5,
      "numero": "FT-2026-001",
      "serie": "A",
      "cliente_designacao": "ACME Ltd",
      "cliente_nif": "1234567890",
      "total": "10000.00",
      "emitida_em": "2026-01-15T10:30:00Z",
      "agt_request_id": "REQ-...",
      "agt_status": "PENDENTE",
      "estado": "PENDENTE_AGT"
    }
  ]
}
```

**Implementation:** Filter by `banca_id` + `agt_status='PENDENTE'`, paginate, return serialized data.

---

### 4.3 GET /api/agt/estado/<id>/

**Purpose:** Detailed invoice information (including errors).

**Response:**
```json
{
  "id": 5,
  "numero": "FT-2026-001",
  "serie": "A",
  "tipo_documento": "FT",
  "cliente_designacao": "ACME Ltd",
  "cliente_nif": "1234567890",
  "total": "10000.00",
  "emitida_em": "2026-01-15T10:30:00Z",
  "criada_em": "2026-01-15T08:00:00Z",
  "atualizada_em": "2026-01-15T12:00:00Z",
  "estado": "REJEITADA",
  "agt_request_id": "REQ-1735618200-abc12345",
  "agt_status": "REJEITADA",
  "agt_hash_validacao": "hash123...",
  "agt_processada_em": "2026-01-15T11:00:00Z",
  "agt_erros": [
    {
      "code": "INVALID_NIF",
      "message": "NIF de cliente inválido",
      "field": "customerTaxID"
    }
  ],
  "qr_code": "..."
}
```

**Implementation:** Retrieve by `id` + verify `banca_id` match. Return as-is (agt_erros is JSONField, already a dict/list).

---

### 4.4 GET /api/agt/request/<request_id>/

**Purpose:** Locate invoice by AGT request ID.

**Response:** Same as /api/agt/estado/<id>/

**Implementation:** Filter by `banca_id` + `agt_request_id`, get first, or 404.

---

### 4.5 POST /api/agt/callback/

**Purpose:** Public webhook — AGT sends invoice status updates.

**Security:**
- `@csrf_exempt`
- `permission_classes([AllowAny])`
- Verify `X-AGT-Secret` header matches `settings.AGT_CALLBACK_SECRET`

**Request payload:**
```json
{
  "requestId": "REQ-...",
  "status": "APPROVED",
  "invoiceNumber": "FT-2026-001",
  "invoiceSeriesCode": "A",
  "documentType": "FT",
  "errors": [],
  "validationHash": "hash123...",
  "processedAt": "2026-01-15T11:00:00Z"
}
```

**Response:**
- **Always HTTP 200** (even on error), to prevent AGT re-sending.
- Body: `{"acknowledged": true}` or `{"acknowledged": false, "reason": "..."}`

**Implementation:**
1. Check `requestId` is present; if not → 200 `{acknowledged: false}`
2. Find fatura by `agt_request_id`; if not found → 200 `{acknowledged: false, reason: "not_found"}`
3. Call `FaturaService.processar_callback(...)`
4. Atomically update fatura inside transaction + select_for_update
5. Return 200 `{acknowledged: true}`
6. Log all outcomes to RegistoAuditoria with origem='webhook'

---

### 4.6 GET /api/agt/callback/ (info endpoint)

**Purpose:** Informative endpoint for testing webhook URL in browser.

**Response:**
```json
{
  "status": "healthy",
  "webhook_url": "https://sicdoa.cdoangola.co.ao/api/agt/callback/",
  "message": "Send POST requests to this URL for AGT callbacks"
}
```

---

## 5. Permissions Decorator

**File:** `agt_invoicing/permissions.py`

```python
from functools import wraps
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def require_financial_permission(view_func):
    """
    Decorator: require user to have financial access (Despachante Oficial or Administrador).
    Also enforces multi-tenant isolation via banca_id.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check session
        usuario = request.session.get('usuario', {})
        papel = usuario.get('papel', '')
        banca_id = request.session.get('banca_id')
        
        # Allowed roles
        allowed_papeis = ['Despachante Oficial', 'Administrador', 'Super Administrador']
        if papel not in allowed_papeis:
            logger.warning(f'AGT access denied for user {usuario.get("nome")} (papel={papel})')
            if request.content_type and 'json' in request.content_type:
                return JsonResponse(
                    {'error': 'Acesso negado — permissão insuficiente'},
                    status=403,
                )
            return JsonResponse(
                {'detail': 'You do not have permission to perform this action.'},
                status=403,
            )
        
        # Verify banca_id for isolation
        if not banca_id:
            logger.error(f'Missing banca_id in session for user {usuario.get("nome")}')
            return JsonResponse({'error': 'banca_id não encontrado na sessão'}, status=403)
        
        return view_func(request, *args, **kwargs)
    
    return wrapper
```

---

## 6. Webhook Callback Decision: Consolidation Strategy

### Context
- **Existing:** `financeiro/views_agt.py:faturacao_agt_callback()` is currently registered at `/api/facturacaoelectronica/callback` in root `urls.py`.
- **New design:** Proposes `/api/agt/callback/` under a new `agt_invoicing` app.

### Decision: **CONSOLIDATE INTO NEW APP**

**Rationale:**
1. The new AGT invoicing module is autonomous and self-contained. It should own all its API endpoints, including the webhook.
2. The existing callback in `financeiro/views_agt.py` is simpler and doesn't follow the full design (no crypto signatures, simpler state machine).
3. **Path change:** Migrate from `/api/facturacaoelectronica/callback` → `/api/agt/callback/` and update AGT portal webhook URL accordingly. Update `.env` `AGT_CALLBACK_URL`.
4. **Backward compatibility:** A temporary redirect at the old path can warn users to update AGT portal settings.

**Action:**
- Delete `financeiro/views_agt.py` (or move to deprecated/)
- Remove its route from root `urls.py`
- Implement the new callback in `agt_invoicing/views.py` (as designed above)
- Register new URL at `/api/agt/callback/` in `agt_invoicing/urls.py`
- Include `agt_invoicing.urls` in root as `path('api/agt/', include('agt_invoicing.urls'))`

This keeps the new module cohesive and avoids duplication.

---

## 7. UI Templates

**Location:** `agt_invoicing/templates/agt_invoicing/`

All templates inherit from `base.html`, use Tailwind + dark mode, and reuse SICDOA's sidebar/header.

### 7.1 Dashboard (`dashboard.html`)

**URL:** `/financeiro/faturacao-eletronica/` (registered in financeiro app)

**Sections:**
- Header: "Faturação Eletrónica AGT" + description + webhook info box (callback URL + instructions)
- KPI Cards: Emitidas | Rejeitadas | Pendentes (fetch from GET /api/agt/stats/)
- Tabs:
  1. **Visão Geral:** Bar chart (estados), table (recent invoices)
  2. **Pendentes:** Table with search, pagination, "Ver" action
  3. **Status AGT:** Breakdown by agt_status
- Loading/empty/error states for all sections
- All data populated from API (no mock)

### 7.2 Invoice Detail (`detalhe.html`)

**Modal/page view of single invoice:**
- Numero, serie, cliente, total, emitida_em
- Estado (local), agt_status, agt_request_id
- agt_processada_em, agt_hash_validacao
- agt_erros (if any, as formatted list)
- Actions: "Sincronizar" (polling), "Reenviar" (if appropriate)

### 7.3 Admin (`admin.py`)

Register models with:
- **Fatura:** list_filter (estado, agt_status, banca, emitida_em), search_fields (numero, agt_request_id, cliente_nif)
- **SubmissaoAgt:** list_filter (estado, fatura), search_fields (fatura__numero)
- **ConfiguracaoFiscal:** list_filter (banca, agt_integration_enabled)
- **RegistoAuditoria:** list_filter (origem, acao, banca_id, criado_em), search_fields (usuario_nome, tipo_entidade)

---

## 8. Multi-Tenancy (banca_id Isolation)

**Rule:** All queries must filter by `banca_id` from `request.session.get('banca_id')`.

**Implementation:**
- Models: `banca = ForeignKey('rh.Banca', on_delete=CASCADE, db_index=True)`
- Views: `qs = qs.filter(banca_id=banca_id)` before returning
- Permissions decorator: verify `banca_id` in session exists
- Admin: auto-filter in querysets

---

## 9. Error Handling

### Invoice Submission (FaturaService.submeter)

| Scenario | Recoverable | Response | Logging |
|----------|------------|----------|---------|
| Integration disabled | No | SubmissaoAgt.NAO_SUBMETIDA | Info (expected) |
| Payload build error | No | SubmissaoAgt.FALHA_PERMANENTE | Error + log message |
| HTTP timeout/ConnErr | Yes | SubmissaoAgt.FALHA_TEMPORARIA, schedule retry +15min | Warning |
| HTTP 4xx/5xx | No | SubmissaoAgt.FALHA_PERMANENTE | Error |
| Signature gen error | No | SubmissaoAgt.FALHA_PERMANENTE | Error + stack trace |

All exceptions are caught in try/except; service never raises (returns bool + message instead).

### Webhook Callback

| Scenario | Response | Logged |
|----------|----------|--------|
| requestId missing | 200 `{acknowledged: false}` | Debug |
| Fatura not found | 200 `{acknowledged: false, reason: "not_found"}` | Warning |
| Invalid X-AGT-Secret | 200 `{acknowledged: false}` | Warning (suspected attack) |
| Transaction error (DB) | 200 `{acknowledged: false}` (from catch block) | Error + stack trace |
| Success | 200 `{acknowledged: true}` | Info |

**Key:** Always respond HTTP 200, never 4xx/5xx, to prevent AGT retransmit storms.

---

## 10. Input Validation

### Fatura creation (API or admin)
- `numero`: max 50 chars, alphanumeric + hyphens
- `serie`: max 10 chars, uppercase letters preferred
- `tipo_documento`: one of TipoDocumento choices
- `cliente_nif`: max 20 chars, matches regex `^\d+$`
- `cliente_designacao`: max 255 chars, non-empty
- `total`: Decimal with 2 places, >= 0
- `emitida_em`: DateTimeField, not in future

### Webhook callback payload
- `requestId`: required, max 100 chars
- `status`: required, one of APPROVED|REJECTED|PENDING
- `invoiceNumber`: optional, max 50 chars
- `customerTaxID`: optional, max 20 chars
- `errors`: optional, list of {code, message, field} dicts

**Validation layer:** Serializers (DRF) for API; model `clean()` methods for ORM.

---

## 11. Testability

### Unit tests (agt_invoicing/tests/test_*.py)
- **test_models.py:** Model creation, field validation, TextChoices
- **test_crypto.py:** JWS signing (mock private keys), signature format validation
- **test_http_client.py:** HTTP mock responses (success, timeout, 4xx, 5xx), error handling
- **test_fatura_service.py:** State machine (disabled integration, success, retryable error, permanent error), idempotency, callback processing

### Integration tests
- Callback POST with valid/invalid payload, signature verification
- Full submission flow (create fatura → submit → callback → verify state)
- Multi-tenant isolation (banca_id filtering)
- Permission checks (unauthorized access denied)

### Fixtures
- Mock settings (AGT_USERNAME, AGT_PASSWORD, keys)
- Mock RSA key pairs (4096-bit for testing)
- Sample faturas per banca

**Strategy:** Use `responses` library to mock HTTP, `freezegun` for time mocking, pytest + Django test client.

---

## 12. Existing Patterns Reused

| Pattern | Source | Usage |
|---------|--------|-------|
| Multi-tenant banca_id | rh.models.Banca | All models filter by banca_id |
| Session auth + papel | users.models.Usuario | require_financial_permission decorator |
| Celery async tasks | sicdoa.settings | submit_fatura_task, polling task |
| Decimal for money | financeiro.models | total, valores always Decimal(max_digits=15, decimal_places=2) |
| Auto timestamp fields | All Django models | criada_em (auto_now_add), atualizada_em (auto_now) |
| JSON fields | users.LogAtividade | agt_erros, detalhes JSONField |
| Admin registration + filters | All apps | Standard Django admin pattern |
| Audit logging | users.LogAtividade | RegistoAuditoria (similar structure) |
| Django templates + Tailwind | templates/base.html | All UI templates |

---

## 13. Configuration & Secrets

### Settings (`settings.py`)
- `AGT_USERNAME`, `AGT_PASSWORD`: Basic Auth credentials (from .env)
- `AGT_API_BASE`: API endpoint URL (default homologação)
- `AGT_PRODUCT_ID`, `AGT_PRODUCT_VERSION`, `AGT_SOFTWARE_VALIDATION_NUMBER`: software identity
- `AGT_NIF_EMITENTE`, `AGT_COMPANY_NAME`, `AGT_SERIE_PADRAO`: issuer defaults
- `AGT_SOFTWARE_PRIVATE_KEY` / `AGT_SOFTWARE_PRIVATE_KEY_FILE`: producer private key (never in git)
- `AGT_CONTRIBUTOR_PRIVATE_KEY` / `AGT_CONTRIBUTOR_PRIVATE_KEY_FILE`: contributor private key (never in git)
- `AGT_CALLBACK_SECRET`: webhook signature verification

### .env
All AGT_* keys defined in `.env`; production values set in Render dashboard.

### File structure
```
agt_invoicing/
├── migrations/
├── templates/
│   └── agt_invoicing/
│       ├── dashboard.html
│       └── detalhe.html
├── tests/
│   ├── test_models.py
│   ├── test_crypto.py
│   ├── test_http_client.py
│   ├── test_fatura_service.py
│   └── test_api.py
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── permissions.py
├── urls.py
├── views.py (or api.py)
├── tasks.py
└── services/
    ├── __init__.py
    ├── crypto.py
    ├── fatura_service.py
    └── http_client.py
```

---

## 14. Deployment & Migrations

- Add `'agt_invoicing'` to `INSTALLED_APPS` in `settings.py`
- Create `agt_invoicing/apps.py` with ready() hook (register Celery tasks)
- `python manage.py makemigrations agt_invoicing`
- `python manage.py migrate agt_invoicing`
- Create ConfiguracaoFiscal entries per banca (via admin or fixture)
- Ensure Redis/Celery running for async tasks
- Deploy to Render; update `AGT_CALLBACK_URL` in AGT portal to new endpoint

---

## 15. Open Questions & Assumptions

1. **QR code generation:** Design stores `qr_code` as TextField (base64 or data URL). Implementation may use `qrcode` library or generate on-demand. **Assumption:** Not critical for MVP; can be added later.

2. **Invoice linking:** Design assumes Fatura is independent, not linked to existing `FacturaCliente` or `RequisicaoFundo` models. **Assumption:** Correct; AGT module is autonomous. If future feature requires linking, add FK with nullable + on_delete=SET_NULL.

3. **Tax calculations:** Design stores only total + zero taxPayable (placeholder). **Assumption:** AGT spec may require itemized tax breakdown. Revisit in detailed implementation.

4. **Polling vs. callback:** Design includes both polling (manual "Sincronizar" button) and Celery task-based polling. **Assumption:** AGT callbacks "available in future versions"; polling is primary mechanism for now.

5. **Key rotation:** Design doesn't include key rotation logic (revoke old, generate new). **Assumption:** Manual process via portal; code supports multiple keys if needed later.

6. **Invoice numbering:** Design stores `numero` as CharField (manual or auto-generated). **Assumption:** AGT assigns official numero; local serie + seq could be schema-dependent.

7. **Backward compatibility:** New callback URL breaks existing AGT portal setup. **Assumption:** Acceptable; migration period allows operators to update portal settings.

---

## 16. Summary of Concrete Decisions

| Decision | Rationale |
|----------|-----------|
| **Autonomous app** | Reusable across domain types; doesn't assume Fatura/RequisicaoFundo structure |
| **Decimal always** | Comply with financial best practices; never float |
| **Webhook → always 200** | Prevent AGT retry storms; decouple errors from HTTP codes |
| **Atomicity + select_for_update** | Avoid race conditions on callback + retry |
| **Max 5 retries, 15min** | Reasonable limit; prevents infinite loops; allows manual intervention |
| **Multi-tenant filter** | All queries by banca_id; enforce at permission layer + service layer |
| **Crypto in service** | Encapsulates complexity; testable in isolation |
| **Async via Celery** | Non-blocking; allows future scaling; retry built-in |
| **Callback consolidation** | New module owns all endpoints; simpler than split management |
| **UI in Django templates** | Consistent with SICDOA; can later be consumed by SPA via API |

---

## 17. Next Steps (Implementation)

1. **Phase 1:** Models + migrations
2. **Phase 2:** Services (crypto, http, fatura_service)
3. **Phase 3:** API views + URLs
4. **Phase 4:** Celery tasks
5. **Phase 5:** UI templates + dashboard
6. **Phase 6:** Admin registration
7. **Phase 7:** Tests (unit + integration)
8. **Phase 8:** Documentation + deployment

---

## Document Metadata

- **Author:** AI Design Agent
- **Date:** 2026-01-01
- **Version:** 1.0 (First Draft)
- **Status:** Awaiting Design Review
- **Next Step:** Review findings → Revise → Resubmit

