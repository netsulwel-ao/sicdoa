# Implementation Plan: AGT Faturação Eletrónica UI & Admin

## Overview
Implement a complete UI module for AGT electronic invoicing (faturação eletrónica), integrating dashboard, listing, detail views, Django admin registration, sidebar navigation, and finalization for production readiness.

The work builds on existing models (`agt_invoicing.Fatura`, `agt_invoicing.SubmissaoAgt`, etc.), REST API (`agt_invoicing.views`), services, and the SICDOA Tailwind+dark-mode design pattern.

---

## Implementation Plan

### Phase 1: Admin & Permissions

- [ ] 1. **Enhance Django admin registration** for 4 AGT models with full filtering, search, and audit trail.
      
      **What:** Register in `agt_invoicing/admin.py`: `FaturaAdmin`, `SubmissaoAgtAdmin`, `ConfiguracaoFiscalAdmin`, `RegistoAuditoriaAdmin` with complete `list_display`, `list_filter`, `search_fields`, `readonly_fields`, and `fieldsets` per specification.
      
      **Files:**
      - `c:/projetos/sicdoa/agt_invoicing/admin.py` (update)
      
      **Verify:**
      ```bash
      cd c:\projetos\sicdoa
      python manage.py check
      # Launch Django admin UI and confirm all 4 models appear with correct columns and filters
      ```

---

### Phase 2: UI Templates & Views

- [ ] 2. **Create dashboard.html template** — overview with KPI cards and recent faturas.
      
      **What:** Create `templates/financeiro/faturacao_eletronica/dashboard.html` with breadcrumb (Financeiro > Faturação Eletrónica), header with description, info box (webhook URL + instructions), 3 KPI cards (Emitidas, Rejeitadas, Pendentes), and table of last 5 faturas. Use Tailwind + dark mode (SICDOA pattern from `templates/base.html`). Include Django messages rendering.
      
      **Files:**
      - `c:/projetos/sicdoa/templates/financeiro/faturacao_eletronica/dashboard.html` (create)
      
      **Verify:**
      Template file exists and is valid Django template syntax. Will be verified in conjunction with dashboard view (item 5).

- [ ] 3. **Create lista.html template** — filtering, search, paginated table.
      
      **What:** Create `templates/financeiro/faturacao_eletronica/lista.html` with filters (estado, agt_status dropdowns), search input (número fatura), paginated table (20/page) with columns: numero, cliente, total, estado, agt_status, data, action 'Ver'. Pagination at top and bottom. Follow `templates/financeiro/recibo_lista.html` pattern (grid + list view toggle).
      
      **Files:**
      - `c:/projetos/sicdoa/templates/financeiro/faturacao_eletronica/lista.html` (create)
      
      **Verify:**
      Template file exists and is valid Django template syntax. Will be verified in conjunction with lista view (item 6).

- [ ] 4. **Create detalhe.html template** — detail view with status, panels, and actions.
      
      **What:** Create `templates/financeiro/faturacao_eletronica/detalhe.html` with breadcrumb + numero fatura, status badges (estado + agt_status), Panel 1 'Documento' (numero, serie, cliente, total, data_emissao), Panel 2 'AGT' (agt_status, agt_request_id, agt_hash_validacao, agt_processada_em), Panel 3 'Erros' if agt_erros present (formatted JSON), 'Sincronizar' button (POST to endpoint), 'Voltar' button.
      
      **Files:**
      - `c:/projetos/sicdoa/templates/financeiro/faturacao_eletronica/detalhe.html` (create)
      
      **Verify:**
      Template file exists and is valid Django template syntax. Will be verified in conjunction with detalhe view (item 7).

- [ ] 5. **Create faturacao_eletronica_dashboard view** — fetch stats and recent faturas.
      
      **What:** Add view in `financeiro/views_agt.py` (or create new module) that fetches from `agt_invoicing.models` (Fatura model), computes KPI counts (Emitidas, Rejeitadas, Pendentes), fetches last 5 faturas ordered by criada_em desc, and renders `faturacao_eletronica_dashboard.html`. Use `@requer_sessao_ativa` decorator and multi-tenant filtering by user's banca. Return context: `{'kpis': {...}, 'recent_faturas': [...], 'webhook_url': ...}`.
      
      **Files:**
      - `c:/projetos/sicdoa/financeiro/views_agt.py` (update or create)
      
      **Verify:**
      View callable with GET request (no params) and returns 200 with rendered template. Multi-tenant filtering verified by checking rendered content only shows current banca's faturas.

- [ ] 6. **Create faturacao_eletronica_lista view** — list with filters, search, pagination.
      
      **What:** Add view in `financeiro/views_agt.py` that fetches Fatura queryset filtered by user's banca, applies estado/agt_status/search filters from GET params, paginates (20/page), and renders `lista.html`. Support GET params: `estado`, `agt_status`, `search` (numero), `page`. Use `@requer_sessao_ativa` decorator.
      
      **Files:**
      - `c:/projetos/sicdoa/financeiro/views_agt.py` (update)
      
      **Verify:**
      View callable with GET and optional filter params; returns 200 with paginated list. Verify filters work: calling with `?estado=RASCUNHO` returns only RASCUNHO faturas; calling with `?search=001` filters by numero; calling with `?page=2` returns page 2.

- [ ] 7. **Create faturacao_eletronica_detalhe view** — detail with AGT status and errors.
      
      **What:** Add view in `financeiro/views_agt.py` that fetches a single Fatura by ID (multi-tenant check: verify banca matches user's banca), and renders `detalhe.html`. Include agt_erros JSON in context (formatted for display). Handle 404 if fatura not found or unauthorized.
      
      **Files:**
      - `c:/projetos/sicdoa/financeiro/views_agt.py` (update)
      
      **Verify:**
      View callable with valid fatura_id (GET); returns 200 with detail page. Verify 404 with invalid ID. Verify multi-tenant: access a fatura from different banca returns 403.

---

### Phase 3: URL Routing & Integration

- [ ] 8. **Add URLs to financeiro/urls.py** — register 3 routes.
      
      **What:** Add to `financeiro/urls.py` under financeiro app namespace:
      ```
      path('faturacao-eletronica/', ..., name='faturacao_eletronica_dashboard')
      path('faturacao-eletronica/lista/', ..., name='faturacao_eletronica_lista')
      path('faturacao-eletronica/<int:fatura_id>/', ..., name='faturacao_eletronica_detalhe')
      ```
      Point each to the corresponding view from `views_agt.py`.
      
      **Files:**
      - `c:/projetos/sicdoa/financeiro/urls.py` (update)
      
      **Verify:**
      Run `python manage.py check` and verify no URL errors. Test URLs resolve:
      ```bash
      python manage.py shell
      >>> from django.urls import reverse
      >>> reverse('financeiro:faturacao_eletronica_dashboard')
      '/financeiro/faturacao-eletronica/'
      >>> reverse('financeiro:faturacao_eletronica_lista')
      '/financeiro/faturacao-eletronica/lista/'
      >>> reverse('financeiro:faturacao_eletronica_detalhe', kwargs={'fatura_id': 1})
      '/financeiro/faturacao-eletronica/1/'
      ```

---

### Phase 4: Sidebar Navigation

- [ ] 9. **Verify sidebar.html already includes faturação link** — confirm gating and access control.
      
      **What:** Verify `templates/includes/sidebar.html` already has the link at financeiro section:
      ```html
      <a href="{% url 'financeiro:faturacao_agt_dashboard' %}" ...>
        <i class="fas fa-landmark"></i>Faturação Eletrónica AGT
      </a>
      ```
      Confirm it is gated by papel access control: visible for Despachante Oficial, Administrador, Super Administrador, or users with 'gerir_financeiro' permission. URL name matches our new route name (correct to `faturacao_eletronica_dashboard`).
      
      **Files:**
      - `c:/projetos/sicdoa/templates/includes/sidebar.html` (verify, update if needed)
      
      **Verify:**
      Load dashboard in browser as different roles; sidebar link appears only for authorized roles. Click link navigates to dashboard.

---

### Phase 5: Django Admin Tests & Finalization

- [ ] 10. **Run tests** — verify agt_invoicing and financeiro modules.
      
      **What:** Run full test suite for both modules:
      ```bash
      python manage.py test agt_invoicing financeiro
      ```
      Verify all tests pass. If tests fail, fix them before proceeding.
      
      **Files:**
      - `c:/projetos/sicdoa/agt_invoicing/tests.py` (no changes, verify pass)
      - `c:/projetos/sicdoa/financeiro/tests.py` (no changes, verify pass)
      
      **Verify:**
      ```bash
      python manage.py test agt_invoicing financeiro --verbosity=2
      # Expected: all tests pass, exit code 0
      ```

- [ ] 11. **Verify header/sidebar render and URLs resolve** — integration check.
      
      **What:** Start development server and manually test:
      1. Load `/financeiro/faturacao-eletronica/` — dashboard should render with KPI cards
      2. Load `/financeiro/faturacao-eletronica/lista/` — listing with filters should render
      3. Load `/financeiro/faturacao-eletronica/1/` — detail page should render (use valid fatura_id)
      4. Verify sidebar link renders and navigates correctly
      5. Verify header (dark mode, Tailwind, breadcrumbs) matches SICDOA pattern
      6. Verify messages (success/error/info) render correctly
      
      **Verify:**
      All 3 URLs return 200 OK. Template rendering has no errors. No console errors (check browser dev tools). Dark mode toggles correctly.

- [ ] 12. **Django check & migrations** — system validation.
      
      **What:** Run Django system checks and ensure no pending migrations:
      ```bash
      python manage.py check
      python manage.py migrate --plan  # verify no pending migrations
      ```
      
      **Files:**
      - No files modified
      
      **Verify:**
      `python manage.py check` returns no errors or warnings. `python manage.py migrate --plan` shows no pending migrations.

- [ ] 13. **Documentation** — README and setup instructions.
      
      **What:** Create or update `docs/SETUP_AGT_UI.md` with:
      - Overview of the 3 views (dashboard, lista, detalhe)
      - How to access admin: `/admin/` with superuser
      - URLs and route names
      - Multi-tenant filtering behavior
      - Sidebar access control rules (papel-based)
      - Example API responses from agt_invoicing REST API
      - Webhook callback documentation (reference to existing `/api/facturacaoelectronica/callback`)
      
      **Files:**
      - `c:/projetos/sicdoa/docs/SETUP_AGT_UI.md` (create)
      
      **Verify:**
      File exists, is readable, contains all sections listed above.

- [ ] 14. **Finalize: commit and verify production readiness** — final checklist.
      
      **What:**
      1. Run full test suite one more time: `python manage.py test agt_invoicing financeiro`
      2. Run Django checks: `python manage.py check`
      3. Verify all 3 views render at `/financeiro/faturacao-eletronica/*` without errors
      4. Verify sidebar link renders and is gated correctly
      5. Verify Django admin: all 4 models appear with correct filters and search
      6. Create final commit with semantic message: `feat(agt-ui): implement dashboard, listing, detail views and admin registration for AGT faturação eletrónica`
      7. Create `final-report.md` with completion checklist
      
      **Files:**
      - `.agents/tasks/agt-ui/final-report.md` (create)
      - `.agents/tasks/agt-ui/.commit-message` (create for reference)
      
      **Verify:**
      - All tests pass: `echo $?` returns 0
      - Django check: no errors
      - Manual smoke test: all 3 URLs render without console errors
      - Git: new commit created on feature branch (not main/master)
      - `final-report.md` exists with completion checklist

---

## Summary of Artifacts

**New Templates:**
- `templates/financeiro/faturacao_eletronica/dashboard.html`
- `templates/financeiro/faturacao_eletronica/lista.html`
- `templates/financeiro/faturacao_eletronica/detalhe.html`

**New/Updated Views:**
- `financeiro/views_agt.py` (3 views: dashboard, lista, detalhe)

**Updated Files:**
- `financeiro/urls.py` (3 new URL patterns)
- `templates/includes/sidebar.html` (verify/correct link URL name if needed)
- `agt_invoicing/admin.py` (enhanced admin registration — already partially done, complete if needed)

**Documentation:**
- `docs/SETUP_AGT_UI.md`
- `.agents/tasks/agt-ui/final-report.md`

---

## Acceptance Criteria

1. ✓ Dashboard renders at `/financeiro/faturacao-eletronica/` with KPI cards and recent faturas
2. ✓ Listing renders at `/financeiro/faturacao-eletronica/lista/` with working filters (estado, agt_status, search) and pagination (20/page)
3. ✓ Detail renders at `/financeiro/faturacao-eletronica/<id>/` with all panels (Documento, AGT, Erros) and status badges
4. ✓ All 3 views enforce multi-tenant filtering (each banca sees only its faturas)
5. ✓ Django admin: all 4 models registered with full filtering, search, and audit fields
6. ✓ Sidebar link renders and navigates to dashboard; gated by papel access control
7. ✓ Templates follow SICDOA Tailwind+dark-mode pattern (consistent with existing financeiro templates)
8. ✓ All tests pass: `python manage.py test agt_invoicing financeiro`
9. ✓ Django check: `python manage.py check` returns no errors
10. ✓ URLs resolve correctly via reverse() and Django URL router
11. ✓ Documentation complete: setup instructions, API reference, webhook info
12. ✓ Final commit created with semantic message; feature branch clean for merge

---

## Dependencies & Context

- **Models:** `agt_invoicing.Fatura`, `agt_invoicing.SubmissaoAgt`, `agt_invoicing.ConfiguracaoFiscal`, `agt_invoicing.RegistoAuditoria` (already exist)
- **Services:** `agt_invoicing.services` (already exist; not modified)
- **REST API:** `agt_invoicing.views` (already exist; not modified in this task)
- **Existing Views Pattern:** Follow `financeiro/views.py` class-based views + decorator pattern
- **Template Pattern:** Reuse `templates/financeiro/recibo_lista.html` (grid/list view toggle, pagination, filters)
- **Design Pattern:** Tailwind CSS + dark mode from `templates/base.html`, color scheme = primary/green
- **Multi-Tenant:** All views filter by `user.banca` from session context
- **Access Control:** Papel-based gating (Despachante Oficial, Administrador, or 'gerir_financeiro' permission)

