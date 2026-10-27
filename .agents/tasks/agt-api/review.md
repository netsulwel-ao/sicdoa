# AGT Invoicing Integration: Services, Permissions, Serializers, and REST API

This implementation brings AGT invoice submission, polling, and webhook callback handling to completion. The code introduces three service classes for cryptographic signing, HTTP communication with retry logic, and state machine management; a permissions decorator for role and tenant validation; serializers that ensure safe Decimal handling; and four REST endpoints that expose invoice stats, listing, detail, and callback ingestion.

The verification report shows comprehensive testing across all components. A few concerns require attention before shipping: the webhook always returns HTTP 200, which is correct for reliability but masks parsing failures; the audit log banca_id in the callback is hardcoded; and the XML generation is simplified.

**Watch for:**
- **confirmed**: Callback audit log banca_id hardcoded to 1 — should be derived from the fatura via SubmissaoAgt lookup to maintain multi-tenant audit trails.
- **confirmed**: XML generation is simplified placeholder — production requires full SAF-T XML per AGT spec.
- **likely**: State machine retry does not check proxima_tentativa_em — code does not guard against resubmission before the 15-minute window, potentially causing duplicate submissions.

**Verdict**: NEEDS_CHANGES

---

## High-level view

The HTTP client implements correct retry behavior: 3 attempts max with exponential backoff (1s, 2s, 4s), 5s timeout, and distinguishes between permanent (4xx) and temporary (5xx/timeout) failures. The state machine for submission follows the spec: PENDENTE → ACEITE on success, FALHA_TEMPORARIA or FALHA_PERMANENTE on error, max 5 tentativas per invoice, with 15-minute retry intervals. The crypto service reads the private key from either env var content or file path and signs JWS tokens with RS256.

The permissions decorator validates both role (whitelist: Administrador, Despachante Oficial) and multi-tenant context (banca_id), adding banca_id to kwargs for filtering. All protected endpoints (stats, pendentes, estado) filter by this banca_id; the callback is public.

Decimal serialization is handled consistently: all monetary values are converted to strings in JSON responses, avoiding float precision loss. Audit logging tracks all state transitions via RegistoAuditoria, including a WEBHOOK origin type for callback-driven changes.

The callback endpoint is correctly implemented to always return HTTP 200, even on errors, ensuring AGT never retries the notification. However, the audit log for callbacks is created with a hardcoded banca_id=1 instead of being sourced from the fatura lookup.

---

<details>
<summary>Issues (4)</summary>

1. **Callback audit log banca_id hardcoded** — The `agt_callback` view creates audit logs with `banca_id=1` instead of deriving it from the fatura via SubmissaoAgt. This breaks multi-tenant audit trails and could log webhooks against the wrong tenant.

2. **XML payload generation is placeholder** — The `_build_fatura_xml()` method returns a simplified XML structure suitable for testing but not production. Real SAF-T XML generation per AGT specification is required before live deployment.

3. **State machine retry guard missing** — The `submeter_fatura()` method does not check `proxima_tentativa_em` before attempting resubmission. If called again before the 15-minute window expires, it will bypass the throttle and attempt to submit again, potentially triggering AGT rate limits or double-submission errors.

4. **Private key loading does not fail fast** — If AgtCryptoService cannot load the private key, it logs and returns an empty string, which will cause jwt.encode() to fail later with an opaque error. Initialization should raise an exception on missing key to fail fast.

</details>

<details>
<summary>Details</summary>

### HTTP Client Retry and Timeout Strategy

The AgtHttpClient implements a robust retry policy: 3 attempts max, 5-second timeout per request, exponential backoff (1s, 2s, 4s between retries). The distinction between permanent and temporary failures is correct: 4xx responses (validation, auth, resource not found) are not retried and raise immediately; 5xx and Timeout are retried. This aligns with the spec.

The retry loop structure is sound. The Authorization header (Basic Auth, Base64-encoded username:password) is correctly built in `_build_auth_header()` and applied to each request. Exception types are not masked, so callers can distinguish Timeout from HTTPError.

### Cryptographic Signing: Private Key Loading

AgtCryptoService correctly prioritizes environment content over file: it checks `settings.AGT_SOFTWARE_PRIVATE_KEY` first (key material directly in env), then falls back to `settings.AGT_SOFTWARE_PRIVATE_KEY_FILE` (file path). This dual approach is appropriate for both development (env var) and production (file with restricted permissions).

The JWS signing methods use PyJWT with RS256 algorithm, which is the required specification. Three signing methods are exposed: `sign_jws_software()` (product metadata), `sign_jws_document()` (invoice fields), and `sign_jws_request()` (NIF + request ID). Each returns a compact JWS token (header.payload.signature format).

**possible** concern: No error is raised if the private key cannot be loaded — the service logs a warning/error but returns an empty string, which would cause jwt.encode() to fail silently or produce an invalid token.

### State Machine: Submission and Retry Logic

The `submeter_fatura()` method implements the required state machine with max 5 tentativas, 15-minute retry interval, and clear error handling. The flow is:

1. Fetch Fatura by ID, or return error if not found.
2. Get or create SubmissaoAgt.
3. If already ACEITE, return early (idempotent).
4. If tentativas >= 5, mark FALHA_PERMANENTE and return.
5. Build XML, submit to AGT.
6. On success: mark ACEITE, store request_id, increment tentativas.
7. On 4xx: mark FALHA_PERMANENTE, return error.
8. On 5xx or Timeout: mark FALHA_TEMPORARIA, set proxima_tentativa_em = now + 15 min, increment tentativas.

The logic is generally correct, but the `update_or_create()` call has a concern. The ternary for the defaults estado is convoluted: `"PENDENTE" if created else submissao.estado if not created else "PENDENTE"` simplifies to `"PENDENTE" if created else submissao.estado`. More importantly: if submissao exists with estado='FALHA_TEMPORARIA' and the method is called again before proxima_tentativa_em elapses, the code does not check this guard and will attempt resubmission anyway. The caller is expected to throttle retries by checking proxima_tentativa_em externally; the service should verify this internally to prevent race conditions.

### Polling: Status Query and Update

The `polling_status()` method queries AGT for invoice status, updates Fatura fields (agt_status, agt_hash_validacao, agt_erros, agt_processada_em), and creates an audit log. The method returns a summary dict for the caller.

### Callback Processing: Webhook Receiver

The `processar_callback()` method parses the webhook payload, finds the matching SubmissaoAgt by codigo_controlo, and updates both SubmissaoAgt and Fatura states. The mapping from AGT status ('APPROVED', 'REJECTED', 'PENDING') to internal states is correct. The method returns early with an error dict if requestId is missing or SubmissaoAgt not found, which is safe since the caller (agt_callback view) always returns HTTP 200.

**Audit log banca_id issue** (confirmed): The agt_callback view creates the audit log with hardcoded `banca_id=1`:

```python
RegistoAuditoria.objects.create(
    banca_id=1,  # FIXME: This should be determined from fatura or config
    acao="UPDATED",
    origin_tipo="WEBHOOK",
    entity_tipo="Callback",
    entity_id=0,
    motivo=f"requestId={request_id}, status={payload.get('status')}",
)
```

This breaks multi-tenant audit trails. The banca should be fetched from the fatura via SubmissaoAgt lookup (available in processar_callback result or passed back to the view). The `_audit_log()` helper in FaturaService correctly uses `fatura.banca`, but the view is not calling that helper.

### Callback Always Returns HTTP 200

The `agt_callback` view correctly implements the critical requirement: it ALWAYS returns HTTP 200, even on parsing errors, missing fatura, or unexpected exceptions. The wrapping try/except logs the error but returns a 200 response with acknowledged=False and the error reason. This ensures AGT does not retry the webhook notification if we've already received it.

### Permissions: Role and Multi-tenant Validation

The `@require_financial_permission()` decorator validates role (whitelist: Administrador, Despachante Oficial) and multi-tenant context (banca_id), adding banca_id to kwargs. All protected views filter Fatura by `banca_id=banca_id` (from kwargs). The callback endpoint is public (not decorated).

### Decimal Serialization: Monetary Values as Strings

Both FaturaListSerializer and FaturaDetailSerializer override the `total` field to convert Decimal to string, avoiding float precision issues. All endpoints return monetary values as strings in JSON.

### XML Payload Generation: Simplified Placeholder

The `_build_fatura_xml()` method returns a basic XML structure with invoice fields (NumeroFatura, Serie, TipoDocumento, NifEmitente, Empresa, ClienteNif, ClienteDesignacao, Total, EmitidaEm). It does not include line items, taxes, or other AGT-required fields. A production implementation must follow AGT's SAF-T XSD schema.

### Audit Trail: RegistoAuditoria Integration

All state-changing operations create audit log entries: submission (acao='SUBMITTED', origin_tipo='API'), polling (acao='APPROVED'|'REJECTED'|'UPDATED', origin_tipo='SISTEMA_AGT'), callback (acao='APPROVED'|'REJECTED'|'UPDATED', origin_tipo='WEBHOOK'). The `_audit_log()` helper correctly captures fatura.banca, but the callback audit log (created in views.agt_callback) is hardcoded to banca_id=1.

### Endpoint Implementations

**GET /api/agt/stats/**: Filters Fatura by banca_id, counts by estado and agt_status, returns aggregate dict. Multi-tenant isolation is enforced. **GET /api/agt/pendentes/**: Filters by agt_status='PENDENTE' and banca_id, paginates at 50 items per page. **GET /api/agt/estado/<id>/**: Filters by id and banca_id, returns full detail or 404. **POST /api/agt/callback/**: Public endpoint, always returns HTTP 200 (with hardcoded banca_id issue noted above). All protected endpoints are decorated with `@require_financial_permission()`.

The spec requires idempotent submission via SubmissaoAgt update_or_create(fatura=fatura). Submitting the same fatura twice returns early if estado=ACEITE, using the stored request_id.

The implementation uses real model objects (Fatura, SubmissaoAgt, RegistoAuditoria) throughout service logic; only HTTP calls are mocked in tests.

</details>

<details>
<summary>File map</summary>

- `agt_invoicing/services.py` (504 lines) — AgtCryptoService (JWS RS256), AgtHttpClient (Basic Auth + retry + exponential backoff), FaturaService (state machine, polling, callback processing, audit logging).
- `agt_invoicing/permissions.py` (59 lines) — @require_financial_permission() decorator for role and multi-tenant validation.
- `agt_invoicing/serializers.py` (68 lines) — FaturaListSerializer, FaturaDetailSerializer (Decimal as strings), serialize_stats helper.
- `agt_invoicing/views.py` (240 lines) — 4 REST endpoints: GET stats, GET pendentes (paginated), GET estado/<id>, POST callback (always 200).
- `agt_invoicing/urls.py` (8 lines) — URL registration for 4 endpoints.

**Full diff**: `git diff HEAD~1 HEAD` (verification.md confirms all changes are contained in these 5 files).

</details>
