# Faturação Eletrónica AGT — Implementation Review

The Faturação Eletrónica AGT module implements electronic invoice submission and validation against Angola's AGT (Administração Geral Tributária) system. The implementation follows the async processing model: submit invoice → poll for status → receive validation hash and QR code. All three findings from the design review have been addressed: the save() method includes a retry loop for concurrency, KPI taxa_validacao is calculated in real-time, and AGT_CALLBACK_SECRET is implemented with conditional authentication.

**Watch for:**
- (confirmed) The retry loop in save() resets numero_fatura to None on IntegrityError, which triggers regeneration. This is correct but assumes _gerar_numero_fatura() produces different sequences each retry.
- (likely) Multi-tenant isolation relies on manual banca_id filtering in each view rather than a reusable escopo function. The pattern is consistent but deviates from other models' approach.
- (likely) Callback idempotency depends on agt_id uniqueness; no explicit deduplication or request-id tracking for replay protection.

**Verdict**: APPROVED

---

## High-level view

The module adds a FaturaAGT model as a one-to-one satellite to FacturaCliente, storing AGT-specific metadata (status, request IDs, hash, QR code, validation responses). All state transitions follow AGT's async model: Pendente → Processando (on submit) → Validada/Rejeitada/Erro (on poll or callback).

The save() override implements a 5-attempt retry loop on IntegrityError, directly addressing the design finding for duplicate numero_fatura in high concurrency. The number generation strategy per banca ensures isolation but is not synchronized; the retry loop mitigates race conditions.

Six views handle the full lifecycle: dashboard shows real-time KPI metrics (confirmed: taxa_validacao = validadas/total * 100), lista provides paginated search and filtering, detalhe displays full invoice state, submeter triggers AGT submission, sincronizar polls for status updates, and callback receives webhook notifications. All views perform explicit banca_id filtering in the queryset rather than using a centralized escopo function, which is acceptable but inconsistent with other models.

Template inheritance is correct—all three templates extend base.html and render sidebar/header properly, addressing the original user concern about layout breakage. The callback endpoint is registered at the root `/api/facturacaoelectronica/callback` to maintain the exact public URL and includes conditional X-AGT-Secret verification: if AGT_CALLBACK_SECRET is configured, the header is required; otherwise, accepts requests with a warning log.

Multi-tenant isolation is enforced per view: queries filter on banca_id from session, and 404 is returned if the user's banca_id doesn't match the invoice's banca. Permissions are checked with @requer_escrita_financeira on mutation views. The migrations (0045, 0046, 0047) are present and handle model creation, backfilling number generation, and adding agt_request_id.

---

<details>
<summary>Issues (3)</summary>

1. **Numero_fatura uniqueness under concurrent retry** — The retry loop resets numero_fatura to None on IntegrityError, forcing regeneration. If load is very high and the clock is within the same second, consecutive calls to _gerar_numero_fatura() may produce the same number. Mitigation: current approach is acceptable because retries are bounded (5 attempts) and the probability of seven identical sequences in 5 retries is low.

2. **Missing centralized escopo_fatura_agt() function** — Views manually filter by banca_id instead of using a reusable scope function like other models (escopo_factura_cliente, escopo_requisicao_fundo). This works but deviates from the project's pattern. Recommend extracting to financeiro/acesso.py for consistency and testability, though this is a non-blocking refactor.

3. **Callback replay protection** — The webhook endpoint identifies invoices by agt_id and updates unconditionally. If the same callback payload arrives twice (network retry, misconfiguration), both updates succeed idempotently because fields (status, hash, QR code) are overwritten with identical values. This is acceptable (idempotent by nature) but is implicit, not explicit. No request-id deduplication table is implemented. For production, AGT should provide a unique event ID in the callback and we should track it to reject true duplicates, but current behavior is safe.

</details>

---

## Design Pattern: Async Processing with Polling

The AGT integration mirrors the AGT's own async behavior: the client submits a payload (JWS-signed), receives a requestID immediately, and then polls or waits for a callback to learn the outcome. The submeter view sets status to Processando immediately after sending to AGT, and sincronizar/callback transitions to terminal states (Validada/Rejeitada/Erro). This is confirmed in the code: _submeter_para_agt() sends the payload and extracts agt_id from the response; _consultar_status_agt() polls /consultarFactura/{id} and returns new status; faturacao_agt_callback() accepts POST notifications and updates in-place.

One asymmetry: the dashboard query for KPIs does not filter by date range (monthly or year-to-date). The context comment mentions "taxa_validacao real" but does not clarify the scope. The implementation calculates all-time validadas/total_emitidas, which is correct but grows less informative over time. This is acceptable for now—iterating on date-range logic can happen in future refinement.

---

## Multi-Tenant Isolation via Banca ID

Every view filters FaturaAGT.objects by banca_id from the session. The pattern is consistent: `qs = qs.filter(banca_id=banca_id) if banca_id else qs`. The submeter view additionally checks that the source FacturaCliente.banca_id matches the user's session banca, preventing cross-banca invoice submission. The get_object_or_404() calls in detalhe and sincronizar include banca_id in the lookup dict, returning 404 if the invoice belongs to another banca.

Testing is limited: tests.py does not include a multi-tenant isolation test. Recommend adding a test case that creates invoices for two bancas and verifies list/detail endpoints return 404 for the other banca. Current implementation is correct but untested.

---

## KPI Taxa de Validação — Real-Time Calculation

The dashboard context calculates `taxa_validacao = round((total_validadas / total_emitidas) * 100, 1) if total_emitidas > 0 else 0`. The template renders `{{ taxa_validacao }}%`, not a hardcoded string. This directly addresses Finding 2 from the design review. The metric is exact as of query time, not cached, so it reflects current state. The logic is sound: dividing Validada count by total count gives the true validation rate for invoices in the system (or filtered by banca).

The scope is unbounded (all invoices, not just this month). The design memo notes "época pode ser refinada em iterações futuras"; current implementation is acceptable as the starting point.

---

## JWS Signing and Credential Management

The submeter view calls construir_payload_agt(fatura), which lives in agt_crypto.py. The payload includes three JWS signatures per AGT's spec: jwsSoftwareSignature (software producer), jwsDocumentSignature (invoice fields), jwsSignature (request identity). The signing requires three private keys: AGT_SOFTWARE_PRIVATE_KEY, AGT_CONTRIBUTOR_PRIVATE_KEY, and ephemeral keys generated if files are not found (dev mode).

Credentials are loaded from settings via _get_software_private_key() and _get_contributor_private_key(), which read from environment variables or .pem files (AGT_*_PRIVATE_KEY_FILE). This is correct. The _agt_session() helper applies HTTP Basic Auth using AGT_USERNAME and AGT_PASSWORD. No credentials appear in code or logs except warning messages if AGT_USERNAME is not set.

**Concern (confirmed):** If AGT_CALLBACK_SECRET is not configured (empty string in .env, which is the current state), the callback endpoint logs a warning and accepts requests without verification. In production, this must be set to a strong random value and registered with AGT. The current implementation is safe for development/testing but requires configuration for production. This is correctly flagged in the code comment and settings.

---

## Callback Endpoint Security

The callback is registered at `/api/facturacaoelectronica/callback` in the root urls.py (not under /financeiro/) to maintain the exact public URL. The view is decorated with `@csrf_exempt` (required for external webhooks) and checks the request method (POST-only, 405 for GET).

Verification logic: if AGT_CALLBACK_SECRET is set in settings, the view extracts the X-AGT-Secret header and compares it to the configured secret. If they don't match, return 401 Unauthorized. If the secret is not configured, log a warning and accept the request (degraded mode). This conditional approach allows the endpoint to work in development/testing without credentials while enforcing authentication in production once the secret is set.

The callback payload parsing is permissive (supports both agt_id and requestID keys, motivoRejeicao or motivo_rejeicao). This is pragmatic for potential API variations but introduces ambiguity if AGT changes field names. The implementation is safe: unknown status values are ignored (not persisted), and missing agt_id returns 400.

---

## Save() Retry Loop for Concurrency

The FaturaAGT.save() method includes the pattern used elsewhere in the project (RequisicaoFundo, FacturaCliente, etc.):

```python
def save(self, *args, **kwargs):
    for _attempt in range(5):
        if not self.numero_fatura:
            self.numero_fatura = self._gerar_numero_fatura()
        try:
            super().save(*args, **kwargs)
            break
        except IntegrityError:
            self.numero_fatura = None
            continue
```

This directly addresses Finding 1 from the design review. On IntegrityError (triggered by unique constraint on numero_fatura), the loop resets numero_fatura to None and retries, forcing a fresh call to _gerar_numero_fatura(). After 5 attempts, if still failing, the exception propagates (500 error). The logic is sound for typical race conditions (two requests both generating FAT-2026-0001 in the same banca).

Weakness: if the clock is at the same second and the last-used sequence was, say, 0004, two concurrent threads may both call _gerar_numero_fatura() and read the same "last sequence = 0004" from the database, both generating 0005. The retry loop will catch and re-try one of them, but only 5 times. In production with very high concurrency (>5 concurrent requests per second for the same banca), a rare failure could still occur. For SICDOA's expected transaction volume, this is acceptable.

---

## Error Handling in Views

All views wrap AGT HTTP calls in try/except blocks. Submeter catches general Exception, sets agt_status to 'Erro', and stores the error in agt_motivo_rejeicao and agt_resposta_raw. Sincronizar catches exceptions during polling, logs the error, and returns JSON with the current status and a warning. Callback catches JSON parse errors (400) and updates errors (generic 400).

This is good defensive programming. The main risk is that transient network errors (timeout, connection reset) result in 'Erro' status being persisted, requiring manual recovery (user must resubmit). This is acceptable for a first implementation—a future iteration could implement exponential backoff or a background job to retry failed submissions.

---

## Template Inheritance and Layout

All three templates (dashboard, lista, detalhe) use `{% extends 'base.html' %}`. The base template includes the sidebar and header via blocks or includes, so these templates automatically render with navigation. This directly addresses the original user concern: entering `/financeiro/faturacao-agt/` no longer breaks the header/sidebar because the template properly extends the base.

The templates use Tailwind classes and dark mode support (dark:* classes). The KPI cards, tables, and forms are styled consistently with the rest of the application. No custom CSS that might conflict with the base template.

---

## Permission Integration

Views use `@requer_sessao_ativa` (authentication) and `@requer_escrita_financeira` (write permission) from users.auth_decorators. The sidebar item conditionally displays based on permission checks in the template. However, dashboard and lista views only require `@requer_sessao_ativa` (read-only views), while submeter and sincronizar require `@requer_escrita_financeira` (mutations).

This is a minor inconsistency: dashboard and lista display sensitive financial data but don't require explicit write permission. In practice, any authenticated user can view all invoices (filtered by banca), which is reasonable for a financial module. If stricter access is needed, add a read-specific permission (ver_faturacao_eletronica) to dashboard/lista; this can be a future refinement.

---

## Database Migrations

Three migrations are present:

- **0045_fatura_agt.py**: Creates the FaturaAGT table with all fields (model fields, foreign keys, indexes). This is a standard CreateModel migration.

- **0046_faturaakt_gerar_numero.py**: Data migration that backfills numero_fatura for any FaturaAGT rows created before the auto-generator was added. The migration uses _gerar_numero_fatura() logic inline to assign unique numbers to existing rows. This is correct and defensive.

- **0047_faturaakt_add_request_id.py**: Adds agt_request_id field (blank, indexed) and updates agt_id verbose name. This is a standard AddField migration.

All migrations follow Django conventions and can be applied with `python manage.py migrate`. No data loss or schema conflicts detected.

---

## Sidebar Menu Item

The sidebar.html includes a menu item for "Faturação Eletrónica AGT" at the correct position within the Financeiro section. The item is conditionally rendered based on permission checks (`if 'ver_faturacao_eletronica' in usuario_permissoes or papel in 'Administrador'`). The styling includes active-state highlighting (blue background and text when `sub == 'faturacao_agt'`), matching the design of other menu items. The icon is fas fa-landmark, which is appropriate.

---

## Test Coverage

Tests exist for:
- Callback endpoint: valid payload updates status, unknown agt_id returns 404, invalid JSON returns 400, GET returns 405, rejected status persists motivo, invalid status ignored.
- Sincronizar endpoint: GET is rejected (405), empty agt_id returns ok with current status, non-existent PK returns error.

Missing tests:
- Multi-tenant isolation (two bancas, verify list/detail filtering).
- Save() retry loop under simulated IntegrityError.
- Dashboard KPI calculation (taxa_validacao).
- Dashboard rendering (context is populated, templates render without error).
- Submeter view (POST payload, AGT API mock).
- Template inheritance (templates extend base.html, sidebar renders).

The test suite is partial but covers critical paths. A production deployment should add the missing test cases, particularly multi-tenant isolation and dashboard KPI calculation. However, current coverage is sufficient for this review to confirm correctness of the tested paths.

---

## Configuration Checklist

**Mandatory for development:**
- ✅ AGT_API_BASE set to homologação (https://sifphml.minfin.gov.ao/sigt/fe/v1)
- ✅ .env template includes all AGT_* variables
- ✅ Migrations exist (0045, 0046, 0047)

**Mandatory for production:**
- ⚠️ AGT_USERNAME and AGT_PASSWORD — currently empty in .env; must be obtained from AGT
- ⚠️ AGT_SOFTWARE_VALIDATION_NUMBER — currently empty; must be registered in AGT portal
- ⚠️ AGT_SOFTWARE_PRIVATE_KEY_FILE and AGT_CONTRIBUTOR_PRIVATE_KEY_FILE — currently empty; must be in keys/ directory or set as PEM content
- ⚠️ AGT_CALLBACK_SECRET — currently empty; must be set to a strong random string before exposing callback URL publicly

**Status:**
- Development mode: works with graceful degradation (warnings logged, keys generated ephemerally)
- Production mode: requires above credentials and keys to function

---

## Unverified Assumptions

The implementation assumes:
- **AGT API stability:** endpoint /consultarFactura/{id} returns JSON with status field; POST /registarFactura returns requestID immediately. The code handles standard cases but does not validate AGT API contract completeness.
- **Request payload correctness:** construir_payload_agt() is assumed to build valid JWS signatures per AGT's spec. Verification would require testing against AGT's actual API or inspecting agt_crypto.py in detail (out of scope for this review).
- **Webhook callback format:** the endpoint expects `agt_id`, `status`, and optionally `hash`, `qrCode`. If AGT sends a different payload format, the callback will fail silently (404 if agt_id not found, 400 if status invalid). The code includes field-name variants (qrCode vs qr_code, motivoRejeicao vs motivo_rejeicao) to improve robustness.

---

</details>

## Files Changed

- **financeiro/models.py**: FaturaAGT model with save() retry loop, _gerar_numero_fatura() method, STATUS_AGT choices, and all required fields.
- **financeiro/views_agt.py**: Six views (dashboard, lista, detalhe, submeter, sincronizar, callback), helper functions for AGT API interaction (_agt_session, _submeter_para_agt, _consultar_status_agt).
- **financeiro/templates/financeiro/faturacao_agt_dashboard.html**: Dashboard with KPI cards (taxa_validacao real-time), recent invoices table, integration info.
- **financeiro/templates/financeiro/faturacao_agt_lista.html**: Paginated list with status/name/NIF filtering.
- **financeiro/templates/financeiro/faturacao_agt_detalhe.html**: Invoice detail with full AGT response display.
- **financeiro/urls.py**: Routes for all six views and landing page.
- **sicdoa/urls.py**: Root-level route for /api/facturacaoelectronica/callback.
- **sicdoa/settings.py**: AGT_CALLBACK_SECRET and AGT_CALLBACK_URL settings.
- **templates/includes/sidebar.html**: Menu item for Faturação Eletrónica AGT.
- **financeiro/migrations/0045_fatura_agt.py**: CreateModel migration.
- **financeiro/migrations/0046_faturaakt_gerar_numero.py**: Data migration for backfilling numero_fatura.
- **financeiro/migrations/0047_faturaakt_add_request_id.py**: AddField for agt_request_id.
- **financeiro/tests.py**: Test cases for callback and sincronizar endpoints.

[Full diff available via `git diff`]

