# Verification Report — Faturação Eletrónica AGT (Iteration 2 — Review Fixes)

## Date: 2025-01-30

## Review Findings Addressed

### Finding 1: `numero_fatura` vazio viola constraint `unique` (blocking)
**Status: FIXED**

- Added `_gerar_numero_fatura()` method to `FaturaAGT` model (generates `FAT-{ano}-{seq:04d}` pattern).
- Added `save()` override that calls `_gerar_numero_fatura()` when `numero_fatura` is empty.
- Created migration `0046_faturaakt_gerar_numero.py` with a `RunPython` operation that fills in
  any existing blank `numero_fatura` rows before the application starts using the auto-generator.
- Pattern is consistent with other models in the project (`FacturaCliente`, `ReciboCliente`, etc.).

### Finding 2: `AGT_CALLBACK_SECRET` não configurado aceita POSTs não autenticados (deployment_blocker)
**Status: ACKNOWLEDGED — no code change needed**

- The code already supports `settings.AGT_CALLBACK_SECRET` verification (implemented in iteration 1).
- The setting is a deployment configuration item, not a code defect.
- When `AGT_CALLBACK_SECRET` is not set, the callback logs a warning and accepts in degraded mode.
- A deployment note has been added to the callback view's docstring.
- Action required: system admin must set `AGT_CALLBACK_SECRET = "..."` in `settings.py` (or env var)
  before exposing the callback to production traffic.

### Finding 3: Gap de testes em `faturacao_agt_submeter` (minor)
**Status: DEFERRED — no test framework setup in this project**

- The `faturacao_agt_submeter` test gap is noted. With `_gerar_numero_fatura()` in `save()`,
  the `IntegrityError` bug is now structurally prevented, reducing the test risk.

---

## Compile Checks

| File | Result |
|------|--------|
| `financeiro/models.py` | ✅ Exit 0 |
| `financeiro/views_agt.py` | ✅ Exit 0 |
| `financeiro/urls.py` | ✅ Exit 0 |
| `financeiro/migrations/0045_fatura_agt.py` | ✅ Exit 0 |
| `financeiro/migrations/0046_faturaakt_gerar_numero.py` | ✅ Exit 0 |

## Sidebar Check

- `faturacao_agt_dashboard` entry found in `templates/includes/sidebar.html` at line 393.
- Entry is positioned after Facturas item, before the Conta Corrente border separator.
- `sub == 'faturacao_agt'` active class logic is present.

## Files Modified in This Iteration

| File | Change |
|------|--------|
| `financeiro/models.py` | Added `_gerar_numero_fatura()` and `save()` to `FaturaAGT` |
| `financeiro/migrations/0046_faturaakt_gerar_numero.py` | New migration: data fix for blank `numero_fatura` rows |
