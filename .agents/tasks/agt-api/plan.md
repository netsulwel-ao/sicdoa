# Implementation Plan: AGT Services + REST API Endpoints

## Context

- **Workspace**: `c:/projetos/sicdoa`
- **App**: `agt_invoicing` (already in INSTALLED_APPS)
- **Database**: MySQL (sicdoav1)
- **Models**: ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria (already created)
- **Auth Pattern**: Session-based (`request.session['usuario']['papel']`, `request.session.get('banca_id')`)
- **Multi-tenant**: All queries filter by `banca_id` from session
- **Decimal serialization**: As strings in JSON (e.g., `"1500.50"`)
- **Settings Keys**: AGT_USERNAME, AGT_PASSWORD, AGT_API_BASE, AGT_PRODUCT_ID, AGT_PRODUCT_VERSION, AGT_SOFTWARE_VALIDATION_NUMBER, AGT_SOFTWARE_PRIVATE_KEY_FILE, AGT_SOFTWARE_PRIVATE_KEY, AGT_CONTRIBUTOR_PRIVATE_KEY_FILE, AGT_CONTRIBUTOR_PRIVATE_KEY

---

## Plan Items

- [ ] 1. Create `agt_invoicing/services.py` with AgtCryptoService, AgtHttpClient, and FaturaService.
      
      **What**: Implement three service classes:
      - **AgtCryptoService**: JWS RS256 signing for software, document, and request. Loads private key from `AGT_SOFTWARE_PRIVATE_KEY_FILE` or `AGT_SOFTWARE_PRIVATE_KEY` env var. Methods: `sign_jws_software()`, `sign_jws_document(fatura_data)`, `sign_jws_request(nif, request_id)`.
      - **AgtHttpClient**: HTTP client with Basic Auth (username:password Base64-encoded). Methods: `post_registar_fatura(xml_payload)` → POST `/registarFactura` returning `{request_id, resposta}`; `get_consultar_fatura(request_id)` → GET `/consultarFactura/{id}` returning `{status, hash, erros}`. Retry logic: 3 attempts max, 5s timeout, exponential backoff (1s, 2s, 4s), raises on HTTPError/Timeout.
      - **FaturaService**: State machine and AGT integration. Methods: `submeter_fatura(fatura_id)` state machine PENDENTE→ACEITE/FALHA_TEMPORARIA/PERMANENTE with max 5 tentativas, proxima_tentativa_em = now+15min; `polling_status(fatura_id)` updates Fatura.agt_status/agt_hash_validacao/agt_erros; `processar_callback(payload)` webhook handler parsing requestId/status/hash/erros, updating SubmissaoAgt and Fatura, creating RegistoAuditoria with origin_tipo='WEBHOOK'.
      
      **Files**: `agt_invoicing/services.py`
      
      **Verify**: `python manage.py check` passes with no errors related to imports.

- [ ] 2. Create `agt_invoicing/permissions.py` with @require_financial_permission() decorator.
      
      **What**: Decorator validates `request.session['usuario']['papel']` against whitelist `['Administrador', 'Despachante Oficial']`. Extracts `banca_id` from `request.session.get('banca_id')` and adds to view kwargs for multi-tenant filtering. Returns 403 Forbidden if papel not in whitelist or banca_id missing.
      
      **Files**: `agt_invoicing/permissions.py`
      
      **Verify**: `python manage.py check` passes.

- [ ] 3. Create serializers in `agt_invoicing/serializers.py` for JSON responses.
      
      **What**: DRF serializers (or plain dicts) for: Fatura list (id, numero, cliente_designacao, total, agt_status, criada_em with Decimal as strings); Fatura detail (numero, serie, estado, total, agt_status, agt_request_id, agt_hash_validacao, agt_erros, agt_processada_em with Decimal as strings); stats dict with counts and groupings by estado and agt_status.
      
      **Files**: `agt_invoicing/serializers.py`
      
      **Verify**: `python manage.py check` passes.

- [ ] 4. Create four REST endpoints in `agt_invoicing/views.py`.
      
      **What**: Implement:
      1. **GET /api/agt/stats/** — Returns `{emitidas: int, rejeitadas: int, pendentes: int, por_estado: {...}, por_agt_status: {...}}`. Filter by banca_id from session. Permission: @require_financial_permission().
      2. **GET /api/agt/pendentes/** (paginated) — Paginated list of Fatura with agt_status='PENDENTE'. Limit 50 per page. Fields: id, numero, cliente_designacao, total (as string), agt_status, criada_em. Permission: @require_financial_permission().
      3. **GET /api/agt/estado/<id>/** — Full Fatura detail: numero, serie, estado, total, agt_status, agt_request_id, agt_hash_validacao, agt_erros (as JSON object), agt_processada_em. Permission: @require_financial_permission().
      4. **POST /api/agt/callback/** — Webhook endpoint (public, no login required). @csrf_exempt, @api_view(['POST']). Payload: {requestId, status: 'APPROVED'|'REJECTED'|'PENDING', hash, erros: []}. Calls FaturaService.processar_callback(). **CRITICAL**: Always return HTTP 200 with `{acknowledged: true/false, reason: "..."}` even on error. Creates RegistoAuditoria with origin_tipo='WEBHOOK'. Log all exceptions.
      
      **Files**: `agt_invoicing/views.py`
      
      **Verify**: Run `python manage.py test agt_invoicing` and confirm all endpoint tests pass. Manual test with curl/Postman.

- [ ] 5. Update `agt_invoicing/urls.py` with four paths.
      
      **What**: Register endpoints:
      ```python
      urlpatterns = [
          path('stats/', views.agt_stats, name='agt_stats'),
          path('pendentes/', views.agt_pendentes, name='agt_pendentes'),
          path('estado/<int:id>/', views.agt_estado, name='agt_estado'),
          path('callback/', views.agt_callback, name='agt_callback'),
      ]
      ```
      Confirm in `sicdoa/urls.py`: `path('api/agt/', include('agt_invoicing.urls'))` already registered (verified during exploration).
      
      **Files**: `agt_invoicing/urls.py`
      
      **Verify**: `python manage.py check` and visit endpoints in browser/curl with valid session.

- [ ] 6. Create comprehensive unit tests in `agt_invoicing/tests.py`.
      
      **What**: Tests cover:
      - FaturaService state machine: PENDENTE → ACEITE, FALHA_TEMPORARIA, FALHA_PERMANENTE; retry logic with max 5 tentativas; proxima_tentativa_em calculation.
      - AgtHttpClient: retry/timeout behavior (mock HTTP layer with unittest.mock.patch), exponential backoff, HTTPError/Timeout handling.
      - Callback webhook: APPROVED/REJECTED/PENDING status processing; SubmissaoAgt and Fatura state updates; RegistoAuditoria creation.
      - Permissions: @require_financial_permission() returns 403 for missing papel, returns 200 for valid role, banca_id filtering.
      - Callback always returns HTTP 200 even when Fatura missing.
      - Decimal serialization in JSON (verify strings, not floats).
      - Multi-tenant filtering: stats/pendentes/estado filtered by banca_id from session.
      Use real model objects (create Banca, ConfiguracaoFiscal, Fatura, SubmissaoAgt); mock only HTTP layer. No mock-only tests.
      
      **Files**: `agt_invoicing/tests.py`
      
      **Verify**: `python manage.py test agt_invoicing -v 2` — all tests pass.

- [ ] 7. Run final checks and migrations.
      
      **What**: 
      - Run `python manage.py makemigrations agt_invoicing` (should be no-op if models unchanged from prior workflow).
      - Run `python manage.py migrate agt_invoicing` to confirm migrations apply.
      - Run `python manage.py check` — confirm no errors.
      - Run `python manage.py test agt_invoicing` — all tests pass.
      
      **Files**: None (verification only)
      
      **Verify**: All four commands above succeed with exit code 0.

---

## Key Implementation Notes

### AgtCryptoService
- Reads private key from `settings.AGT_SOFTWARE_PRIVATE_KEY` (env content) OR `settings.AGT_SOFTWARE_PRIVATE_KEY_FILE` (file path).
- Uses `PyJWT` library: `jwt.encode(payload, private_key, algorithm='RS256')` to sign JWS RS256.
- Methods return JWS token string (compact format: `header.payload.signature`).

### AgtHttpClient
- Basic Auth header: `base64.b64encode(f'{username}:{password}'.encode()).decode()`.
- POST to `/registarFactura` with XML payload; GET to `/consultarFactura/{request_id}` with query params.
- Retry decorator: attempt 1 immediate, attempt 2 after 1s, attempt 3 after 2s (exponential backoff).
- Timeout: 5 seconds per request.
- On max retries exceeded or timeout, raise custom exception (or let requests.Timeout propagate).

### FaturaService State Machine
- `submeter_fatura(fatura_id)`:
  - Fetch Fatura by ID.
  - Fetch or create SubmissaoAgt (update_or_create pattern).
  - If SubmissaoAgt.estado == 'ACEITE', return early (idempotent).
  - If SubmissaoAgt.tentativas >= 5, set estado='FALHA_PERMANENTE', return.
  - Otherwise, post XML to AGT via AgtHttpClient.post_registar_fatura().
  - On success: SubmissaoAgt.estado='ACEITE', SubmissaoAgt.codigo_controlo=request_id, Fatura.agt_request_id=request_id.
  - On HTTPError 4xx (validation): SubmissaoAgt.estado='FALHA_PERMANENTE'.
  - On HTTPError 5xx or Timeout: SubmissaoAgt.estado='FALHA_TEMPORARIA', proxima_tentativa_em=now+15min, tentativas+=1.
  - Create RegistoAuditoria(acao='SUBMITTED', origin_tipo='API').
  - Return `{ok: bool, request_id: str, erro: str}`.
- `polling_status(fatura_id)`:
  - Fetch Fatura by ID.
  - Call AgtHttpClient.get_consultar_fatura(Fatura.agt_request_id).
  - Update Fatura.agt_status, Fatura.agt_hash_validacao, Fatura.agt_erros.
  - Create RegistoAuditoria(acao='UPDATED', origin_tipo='SISTEMA_AGT').
  - Return `{ok: bool, status: 'APROVADA'|'REJEITADA'|'PENDENTE', hash: str, erros: []}`.
- `processar_callback(payload)`:
  - Extract requestId, status, hash, erros from payload.
  - Fetch SubmissaoAgt by codigo_controlo (or fatura.agt_request_id).
  - Update SubmissaoAgt.estado based on status ('APPROVED'→'ACEITE', etc.).
  - Update related Fatura.agt_status, agt_hash_validacao, agt_erros, agt_processada_em=now.
  - Create RegistoAuditoria(acao='APPROVED'|'REJECTED', origin_tipo='WEBHOOK').
  - Return `{ok: bool, reason: str}`. **This is called from views.agt_callback which ALWAYS returns HTTP 200.**

### Views
- All protected endpoints (@require_financial_permission) must check `request.session.get('banca_id')` in query filters.
- Decimal values serialized as strings: `str(fatura.total)` or custom JSON encoder.
- Pagination: Use Django Paginator(queryset, 50); return page data + count.
- Callback endpoint: Wrap entire logic in try/except; always return HTTP 200 JsonResponse even if SubmissaoAgt not found or callback fails. Log errors with full traceback.

### Tests
- Use `TestCase` or `TransactionTestCase` from Django.
- Create real Banca, Fatura, SubmissaoAgt objects.
- Mock HTTP calls: `@patch('agt_invoicing.services.AgtHttpClient')`.
- Test state transitions with assertions on model states after service calls.
- Test webhook callback with missing Fatura — should return HTTP 200, not 500.

---

## Migration & Verification

After all items complete:

1. **Local test**: `python manage.py test agt_invoicing -v 2` ✓
2. **Check for issues**: `python manage.py check` ✓
3. **Migrations applied**: `python manage.py migrate agt_invoicing` ✓
4. **Manual API test** (with curl or Postman):
   - GET `/api/agt/stats/` (authenticated) → 200 with stats object
   - GET `/api/agt/pendentes/` (authenticated) → 200 with paginated list
   - GET `/api/agt/estado/1/` (authenticated) → 200 with detail or 404
   - POST `/api/agt/callback/` (no auth) with sample payload → 200 with acknowledged response

