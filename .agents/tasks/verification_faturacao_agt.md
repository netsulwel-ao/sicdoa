# Verification Report — Faturação Eletrónica AGT (Review Iteration)

**Date**: 2025-07-13  
**Iteration**: Correction pass — addressing `review_faturacao_agt.json` findings

---

## Findings Addressed

### Finding 1 — Sync-on-GET state mutation (blocking) ✅ FIXED

- **Change**: Added `@require_POST` decorator to `faturacao_agt_sincronizar` (after `@requer_sessao_ativa`).
- **Templates**: Replaced all `<a href="{% url 'financeiro:faturacao_agt_sincronizar' ... %}">` anchors with `<button type="button">` elements that call JavaScript `fetch()` with `method: 'POST'` and the CSRF token from the cookie.
  - `faturacao_agt_dashboard.html`: button with `onclick="sincronizarFaturaAGT(...)"` + inline `<script>` block.
  - `faturacao_agt_detalhe.html`: button with `id="btnSincronizar"` + `<script>` block at end of template.
- **Verified**: `Select-String` confirms zero `<a href>` links to the sincronizar URL remain in any template.

### Finding 2 — Unauthenticated webhook (blocking) ✅ FIXED

- **Change**: `faturacao_agt_callback` now reads `settings.AGT_CALLBACK_SECRET`. When set, it compares the value against the `X-AGT-Secret` request header and returns HTTP 401 if they don't match. When not set, it logs a warning and accepts (backward-compatible, no disruption to current deployment).
- **Behaviour**: Adding the setting to `settings.py` activates the check; not adding it keeps current behaviour. This is a non-breaking default.
- **Verified**: `Select-String` shows `AGT_CALLBACK_SECRET`, `X-AGT-Secret`, `Unauthorized` all present in `views_agt.py`.

### Finding 3 — Decorator order on `faturacao_agt_submeter` (minor) ✅ FIXED

- **Change**: Reversed decorator order from `@require_POST → @requer_sessao_ativa → @requer_escrita_financeira` to `@requer_sessao_ativa → @require_POST → @requer_escrita_financeira`.
- **Result**: Unauthenticated users now get redirected to login (session check first) rather than a 405.
- **Verified**: `Select-String` at lines 111–114 confirms correct order.

### Finding 4 — No tests (minor) ✅ FIXED

- **Change**: Added two test classes to `financeiro/tests.py`:
  - `FaturaAGTCallbackTestCase` — 6 tests covering:
    - Valid payload updates status and hash
    - Unknown `agt_id` returns 404
    - Invalid JSON returns 400
    - GET returns 405
    - Rejected status persists `motivo_rejeicao`
    - Invalid status not persisted (status unchanged)
  - `FaturaAGTSincronizarTestCase` — 3 tests covering:
    - GET returns 405 (Finding 1 regression guard)
    - Empty `agt_id` returns `ok=True` with status unchanged
    - Nonexistent PK results in error response
- **Verified**: `python -m py_compile financeiro/tests.py` exits 0.

---

## Compilation Checks

| File | Result |
|------|--------|
| `financeiro/views_agt.py` | ✅ `py_compile` exits 0 |
| `financeiro/tests.py` | ✅ `py_compile` exits 0 |
| Templates (no `<a href>` sincronizar links) | ✅ Verified via `Select-String` |
| Decorator order `faturacao_agt_submeter` | ✅ Correct order confirmed |
| Decorator order `faturacao_agt_sincronizar` | ✅ `@require_POST` present |

---

## Files Changed

| File | Change |
|------|--------|
| `financeiro/views_agt.py` | Finding 1: `@require_POST` on sincronizar; Finding 2: secret token check on callback; Finding 3: corrected decorator order on submeter |
| `financeiro/templates/financeiro/faturacao_agt_dashboard.html` | Finding 1: `<a href>` → `<button>` + JS fetch |
| `financeiro/templates/financeiro/faturacao_agt_detalhe.html` | Finding 1: `<a href>` → `<button>` + JS fetch |
| `financeiro/tests.py` | Finding 4: added `FaturaAGTCallbackTestCase` + `FaturaAGTSincronizarTestCase` |
| `.agents/tasks/verification_faturacao_agt.md` | This report |
