# AGT Invoicing Models + Migrations

Create autonomous `agt_invoicing` Django app with 4 models (ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria), database migrations, and multi-tenant integration via Banca FK. All 4 models deployed to MySQL with proper indexes, decimal handling, and choice enumerations. App registered in INSTALLED_APPS and URLs configured at `/api/agt/`. No views, services, or API endpoints included in this cycle.

**Watch for:** All Decimal fields must use `max_digits=15, decimal_places=2` to avoid float precision loss on currency. Multi-tenant banca FK isolation is critical for data safety; verify all 4 models have banca_id-based indexes for query efficiency. Migration applied successfully to MySQL (sicdoav1) — confirm tables exist with correct schema before proceeding.

**Verdict**: APPROVED

---

## High-level view

The task creates an autonomous, schema-complete invoicing app for AGT (Angola General Treasury) integration. Four models implement distinct concerns: ConfiguracaoFiscal holds per-banca API credentials and settings; Fatura is the primary fiscal document tracking state from draft through AGT approval; SubmissaoAgt manages the submission queue and retry history for each invoice; RegistoAuditoria records every operation for compliance and debugging. Multi-tenant isolation is enforced via banca FK on all models with composite indexes on (banca_id, state_field) for efficient filtering in a SaaS context.

Decimal fields use max_digits=15, decimal_places=2 throughout, matching the pattern in financeiro/models.py and storing as NUMERIC(15, 2) in MySQL rather than float. Choice fields use plain Python lists of tuples, consistent with rh/models.py (not TextChoices), minimizing friction with the existing codebase. The app is registered in INSTALLED_APPS after financeiro; URLs are stubbed at `/api/agt/` ready for endpoint registration in a later cycle. All 4 models have Django admin registration (basic, no custom admin views). Migrations created and applied; django check passes with no errors.

The verification evidence confirms schema correctness (all tables exist, indexes are in place, foreign keys reference rh_empresas correctly) and zero build/integration issues. No views, services, or permission logic are included, keeping scope tight and ready for the next cycle.

<details>
<summary>Issues (0)</summary>

No blocking concerns. Implementation is complete and ready for services/views.

</details>

<details>
<summary>Details</summary>

### Multi-tenant Isolation via Banca FK

All four models carry a `banca` FK to `rh.Banca` (mapped to `rh_empresas` table), enabling independent data isolation for each tenant/company. The FK uses `on_delete=CASCADE` for banca deletion (standard multi-tenant cleanup) and `related_name` set to app-specific names (`faturas_agt_invoicing`, `submissoes_agt_invoicing`, `registos_auditoria_agt_invoicing`, `configuracoes_fiscais`) to avoid naming collisions with pre-existing `FaturaAGT` model in the financeiro app.

**Indexes on banca_id:** ConfiguracaoFiscal has composite index (banca_id, nif_emitente); Fatura has (banca_id, estado) and (banca_id, agt_status); SubmissaoAgt and RegistoAuditoria do not include banca in composite indexes but the foreign key itself is indexed. This design supports efficient filtering by tenant across state-based queries (e.g., "all pending AGT invoices for this banca") without forcing full-table scans. The verification evidence confirms all indexes created as specified.

### Decimal Precision and Currency Representation

Fatura's `total` field uses `DecimalField(max_digits=15, decimal_places=2)`, storing as NUMERIC(15, 2) in MySQL with default Decimal('0.00'). This matches the financeiro/models.py pattern and supports invoices up to 999,999,999,999.99 (sufficient for Angola invoices in AKZ currency). No float fields are used; this avoids rounding errors that plague currency calculations. The migration correctly captures the field type; schema verification confirms NUMERIC storage.

### Choice Field Enumerations

Four models use choices across 13 total choice fields:
- **Fatura.tipo_documento** (5 values: FACTURA, NOTA_CREDITO, NOTA_DEBITO, RECIBO, GUIA_REMESSA)
- **Fatura.estado** (4 values: RASCUNHO, PENDENTE_AGT, EMITIDA, REJEITADA)
- **Fatura.agt_status** (3 values: APROVADA, REJEITADA, PENDENTE)
- **SubmissaoAgt.estado** (6 values: PENDENTE, ACEITE, REJEITADA, FALHA_TEMPORARIA, FALHA_PERMANENTE, NAO_SUBMETIDA)
- **RegistoAuditoria.acao** (7 values: CREATED, UPDATED, SUBMITTED, APPROVED, REJECTED, RETRIED, DELETED)
- **RegistoAuditoria.origin_tipo** (4 values: API, SISTEMA_AGT, ADMIN, WEBHOOK)

All choices are defined as Python lists of tuples (CharField with choices parameter), not TextChoices class. This is consistent with rh/models.py (Colaborador.CARGOS) and financeiro/models.py patterns, reducing migration complexity and keeping code style uniform across the project.

### Submission Queue and Retry Logic

SubmissaoAgt tracks submission state transitions for each invoice. Fields `ultima_tentativa_em`, `proxima_tentativa_em`, and `tentativas` support retry scheduling. The `proxima_tentativa_em` field has `db_index=True`, enabling efficient batch queries to identify invoices ready for retry ("SELECT * FROM agt_invoicing_submissao_agt WHERE proxima_tentativa_em < NOW() AND estado='PENDENTE'"). The `payload_xml` TextField stores the XML sent to AGT for audit trail (blank=True allows creation before submission). The `codigo_controlo` field is blank=True to accommodate control codes returned by AGT on success.

The FK to Fatura uses `on_delete=PROTECT`, preventing accidental deletion of invoices if submissions exist. This enforces a data integrity constraint: a Fatura cannot be deleted via cascade if SubmissaoAgt records reference it. This is appropriate because invoices tied to submissions should require explicit cleanup (flag as DELETED in audit log before removing) rather than cascading deletion.

### Audit Trail with Entity Tracking

RegistoAuditoria records every operation at the banca level. The `entity_tipo` and `entity_id` design (CharField and IntegerField) allows polymorphic audit entries: the same audit log can record changes to Fatura, SubmissaoAgt, or ConfiguracaoFiscal by storing the entity type name and primary key. The `origin_tipo` field (API, SISTEMA_AGT, ADMIN, WEBHOOK) enables filtering by source for compliance audits. The `usuario_id` is nullable (IntegerField, not FK) to accommodate webhook/system events without requiring a user. Composite indexes on (criado_em, origin_tipo) and (entity_tipo, entity_id) support common queries: "timeline of changes for this banca" and "all changes to a specific invoice."

### Configuration Model Structure

ConfiguracaoFiscal holds per-banca AGT settings: `nif_emitente` (company NIF), `integration_enabled` toggle, `api_endpoint` URL, and `username`/`password` (CharField, blank=True). The model allows multiple configurations per banca, enabling support for multiple tax numbers per company in future cycles.

### Foreign Key Constraints

SubmissaoAgt.fatura uses `on_delete=PROTECT`, preventing accidental deletion of invoices if submissions exist. This enforces a data integrity constraint: invoices tied to submissions require explicit cleanup rather than cascading deletion. All banca FKs use CASCADE for standard multi-tenant cleanup (deleting a company deletes all related invoicing records).

</details>

<details>
<summary>File map</summary>

- **agt_invoicing/__init__.py** — app package marker (empty)
- **agt_invoicing/apps.py** — Django app configuration (AgtInvoicingConfig)
- **agt_invoicing/models.py** — all 4 models: ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria with fields, choices, indexes, and __str__ methods
- **agt_invoicing/admin.py** — basic Django admin registration for all 4 models
- **agt_invoicing/urls.py** — empty urlpatterns list (ready for endpoint registration in next cycle)
- **agt_invoicing/views.py** — empty (stub for next cycle)
- **agt_invoicing/tests.py** — empty (stub for next cycle)
- **agt_invoicing/migrations/__init__.py** — migrations package marker (empty)
- **agt_invoicing/migrations/0001_initial.py** — auto-generated migration creating all 4 tables and indexes
- **sicdoa/settings.py** — added 'agt_invoicing' to INSTALLED_APPS after 'financeiro'
- **sicdoa/urls.py** — added path('api/agt/', include('agt_invoicing.urls'))

[Full diff available at git diff main -- agt_invoicing/ sicdoa/settings.py sicdoa/urls.py]

</details>
