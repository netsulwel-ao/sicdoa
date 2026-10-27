# Implementation Plan: AGT Invoicing Models + Migrations

## Project Context

**Workspace:** `c:/projetos/sicdoa`  
**App:** `agt_invoicing/` (to be created)  
**Database:** MySQL (DB_NAME=sicdoav1, via c:/projetos/sicdoa/.env)  
**Django Version:** 3.2+ with django.db.models  
**Pattern:** Multi-tenant with Banca FK isolation (reused from financeiro/ and rh/)

---

## Key Findings from Codebase Exploration

### 1. Banca Model and Multi-tenant Pattern

**Location:** `c:/projetos/sicdoa/rh/models.py` (lines ~47–150)

```python
class Banca(models.Model):
    usuario_id = models.IntegerField()
    nome = models.CharField(max_length=255, db_index=True)
    nif = models.CharField(max_length=50, unique=True)
    # ... other fields ...
    class Meta:
        db_table = 'rh_empresas'
        indexes = [
            models.Index(fields=['usuario_id']),
            models.Index(fields=['ativa']),
            models.Index(fields=['nif']),
        ]
```

**Multi-tenant FK pattern used in financeiro/models.py:**
- Field name: `banca`
- `on_delete=models.CASCADE` (destroy related records when banca is deleted)
- `related_name='<app>_<model>_plural'` (e.g., 'requisicoes_fundos', 'facturas_cliente')
- `null=True, blank=True` (optional in some models, required in others)
- Always indexed as part of `(banca_id, status_field)` or `(banca_id, date_field)` for multi-tenant safety

**Decision:** Use direct `banca` FK on SubmissaoAgt and RegistoAuditoria for consistent multi-tenant isolation at query layer. Fatura is the primary tenant root, so SubmissaoAgt and RegistoAuditoria will have their own banca FK for independent filtering if needed (standard pattern in existing app).

### 2. Django Settings & INSTALLED_APPS

**Location:** `c:/projetos/sicdoa/sicdoa/settings.py` (lines 22–35)

Current INSTALLED_APPS:
```python
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'utils',
    'users',
    'aduaneiro',
    'rh',
    'clientes',
    'governanca',
    'financeiro',
    'channels',
    'django_apscheduler',
]
```

**Decision:** Add `'agt_invoicing'` after `'financeiro'` in INSTALLED_APPS.

### 3. URLs Configuration

**Location:** `c:/projetos/sicdoa/sicdoa/urls.py` (lines 43–64)

Current app includes:
```python
path('du/', include('aduaneiro.urls')),
path('rh/', include('rh.urls')),
path('governanca/', include('governanca.urls')),
path('clientes/', include('clientes.urls')),
path('utils/', include('utils.error_urls')),
path('financeiro/', include('financeiro.urls')),
```

The AGT callback is already registered at the root level (line 63).

**Decision:** Register `agt_invoicing` with empty urlpatterns at line ~64 (after financeiro include):
```python
path('api/agt/', include('agt_invoicing.urls')),
```

### 4. Decimal Field Pattern

**Confirmed in financeiro/models.py:**
- All monetary fields use `DecimalField(max_digits=15, decimal_places=2)` (e.g., subtotal_geral, iva_honorarios, valor_total)
- Never use FloatField for currency

### 5. TextChoices Pattern

**Observed in rh/models.py (Colaborador model, lines ~300–310):**
```python
CARGOS = [
    ('Assistente', 'Assistente de Despacho'),
    ('Administrativo', 'Administrativo'),
    ('Financeiro', 'Financeiro'),
    ('Gestor', 'Gestor'),
    ('Outro', 'Outro'),
]
estado = models.CharField(max_length=10, choices=ESTADOS, default='Ativo')
```

**Decision:** Use Python list of tuples (CharField + choices) rather than TextChoices class for consistency with existing codebase.

### 6. Index Pattern

**Observed in financeiro/models.py (RequisicaoFundo.Meta, lines ~155–160):**
```python
indexes = [
    models.Index(fields=['estado', '-data_emissao'], name='ix_rf_estado_data'),
    models.Index(fields=['cliente', 'estado'], name='ix_rf_cliente_estado'),
    models.Index(fields=['banca', 'filial'], name='ix_rf_banca_filial'),
]
```

**Pattern:** Composite indexes named with `ix_<app>_<field1>_<field2>` convention, including banca in multi-tenant indexes for safety.

---

## Models Specification

### 1. ConfiguracaoFiscal

**Purpose:** AGT integration settings per banca/empresa.

**Fields:**
- `banca` FK → rh.Banca (CASCADE, related_name='configuracoes_fiscais')
- `nif_emitente` CharField(max_length=50) — NIF of the company issuing invoices
- `integration_enabled` BooleanField(default=False) — whether AGT integration is active
- `api_endpoint` URLField() — AGT API endpoint (e.g., AGT_API_BASE from settings)
- `username` CharField(max_length=255, blank=True) — Basic Auth username (production: via envvar)
- `password` CharField(max_length=255, blank=True) — Basic Auth password (production: via envvar)
- `criado_em` DateTimeField(auto_now_add=True, db_index=True)
- `atualizado_em` DateTimeField(auto_now=True)

**Meta indices:**
- `(banca_id, nif_emitente)` — lookup by banca + emitter NIF
- Composite index: `models.Index(fields=['banca', 'nif_emitente'], name='ix_cf_banca_nif')`

**Choice fields:** None for ConfiguracaoFiscal.

### 2. Fatura (Invoice — Primary Fiscal Document)

**Purpose:** Main invoice model tracking submission to AGT.

**Fields:**
- `banca` FK → rh.Banca (CASCADE, related_name='faturas_agt')
- `numero` CharField(max_length=50, unique=True, db_index=True) — invoice number (e.g., "FT-2026-0001")
- `serie` CharField(max_length=10, blank=True, default='A') — invoice series
- `tipo_documento` CharField(max_length=50, choices=[...]) — FACTURA, NOTA_CREDITO, NOTA_DEBITO, RECIBO, GUIA_REMESSA, etc.
- `estado` CharField(max_length=20, choices=[...]) — RASCUNHO, PENDENTE_AGT, EMITIDA, REJEITADA
- `cliente_designacao` CharField(max_length=255) — client name
- `cliente_nif` CharField(max_length=50) — client NIF
- `total` DecimalField(max_digits=15, decimal_places=2)
- `emitida_em` DateTimeField(null=True, blank=True) — when invoice was issued
- `criada_em` DateTimeField(auto_now_add=True, db_index=True)
- `atualizada_em` DateTimeField(auto_now=True)
- `agt_request_id` CharField(max_length=100, unique=True, null=True, db_index=True) — requestID from AGT API
- `agt_status` CharField(max_length=20, null=True, choices=[...]) — APROVADA, REJEITADA, PENDENTE
- `agt_hash_validacao` CharField(max_length=255, null=True, blank=True) — validation hash from AGT
- `agt_processada_em` DateTimeField(null=True, blank=True)
- `agt_erros` JSONField(null=True, blank=True) — error details from AGT (e.g., validation failures)

**Meta indices:**
- `(banca_id, estado)`
- `(banca_id, agt_status)`
- `agt_request_id` (already unique, for fast polling)

### 3. SubmissaoAgt (Submission Queue + History)

**Purpose:** Track submission attempts and retry logic for each invoice to AGT.

**Fields:**
- `banca` FK → rh.Banca (CASCADE, related_name='submissoes_agt')
- `fatura` FK → Fatura (PROTECT, related_name='submissoes') — prevent deletion if submission exists
- `estado` CharField(max_length=30, choices=[...]) — PENDENTE, ACEITE, REJEITADA, FALHA_TEMPORARIA, FALHA_PERMANENTE, NAO_SUBMETIDA
- `payload_xml` TextField(blank=True) — XML payload sent to AGT (for audit trail)
- `submetida_em` DateTimeField(null=True, blank=True) — first submission timestamp
- `ultima_tentativa_em` DateTimeField(null=True, blank=True) — last attempt timestamp
- `proxima_tentativa_em` DateTimeField(null=True, db_index=True) — scheduled retry time (for batch retry jobs)
- `tentativas` PositiveIntegerField(default=0) — retry count
- `mensagem` TextField(blank=True) — error message or status message from AGT
- `codigo_controlo` CharField(max_length=50, blank=True) — control code from AGT (if applicable)

**Meta indices:**
- `(fatura_id, estado)`
- `proxima_tentativa_em` — for efficient batch retry queries

### 4. RegistoAuditoria (Audit Log)

**Purpose:** Full audit trail of all operations on invoices and submissions.

**Fields:**
- `banca` FK → rh.Banca (CASCADE, related_name='registos_auditoria_agt')
- `acao` CharField(max_length=50) — e.g., "CREATED", "SUBMITTED", "APPROVED", "REJECTED", "RETRIED"
- `origin_tipo` CharField(max_length=30, choices=[...]) — API, SISTEMA_AGT, ADMIN, WEBHOOK
- `entity_tipo` CharField(max_length=50) — e.g., "Fatura", "SubmissaoAgt", "ConfiguracaoFiscal"
- `entity_id` IntegerField() — PK of the entity being audited
- `motivo` TextField(blank=True) — reason for the action (e.g., why rejected, why retried)
- `ip_address` CharField(max_length=45, blank=True) — IPv4/IPv6 of API client (for admin actions)
- `user_agent` CharField(max_length=255, blank=True) — HTTP User-Agent (for admin actions)
- `usuario_id` IntegerField(null=True, blank=True) — FK to users.Usuario.id (if triggered by a user)
- `criado_em` DateTimeField(auto_now_add=True, db_index=True)

**Meta indices:**
- `(criado_em, origin_tipo)` — audit timeline filtered by source
- `(entity_tipo, entity_id)` — entity change history

---

## App Structure to Create

```
agt_invoicing/
├── migrations/
│   └── __init__.py
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── tests.py
├── urls.py
└── views.py (stub — empty file, no views for this cycle)
```

**Stub content for each file:**

- **migrations/__init__.py** — empty
- **__init__.py** — empty
- **admin.py** — empty or minimal (no AdminSite registration yet)
- **apps.py** — standard Django app config:
  ```python
  from django.apps import AppConfig
  class AgtInvoicingConfig(AppConfig):
      default_auto_field = 'django.db.models.BigAutoField'
      name = 'agt_invoicing'
      verbose_name = 'AGT Invoicing'
  ```
- **models.py** — implements ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria (full spec below)
- **tests.py** — empty (no tests in this cycle)
- **urls.py** — empty urlpatterns:
  ```python
  from django.urls import path
  urlpatterns = []
  ```
- **views.py** — empty (no views in this cycle)

---

## Implementation Steps

### Step 1: Create app directory structure
Create `c:/projetos/sicdoa/agt_invoicing/` directory with all files listed above (migrations/, __init__.py, admin.py, apps.py, models.py, tests.py, urls.py, views.py).

**Files to create:**
- `c:/projetos/sicdoa/agt_invoicing/__init__.py`
- `c:/projetos/sicdoa/agt_invoicing/migrations/__init__.py`
- `c:/projetos/sicdoa/agt_invoicing/admin.py`
- `c:/projetos/sicdoa/agt_invoicing/apps.py`
- `c:/projetos/sicdoa/agt_invoicing/models.py`
- `c:/projetos/sicdoa/agt_invoicing/tests.py`
- `c:/projetos/sicdoa/agt_invoicing/urls.py`
- `c:/projetos/sicdoa/agt_invoicing/views.py`

**Verify:** All files exist in the directory.

### Step 2: Implement models.py with all 4 models

Create `c:/projetos/sicdoa/agt_invoicing/models.py` with:

1. **Import statements:**
   - `from django.db import models`
   - `from decimal import Decimal`
   - `from django.utils import timezone`

2. **ConfiguracaoFiscal model:**
   - Fields: banca (FK), nif_emitente, integration_enabled, api_endpoint, username, password, criado_em, atualizado_em
   - Meta: db_table, verbose_name, indexes with (banca_id, nif_emitente)
   - __str__: return f"{self.banca.nome} — {self.nif_emitente}"

3. **Fatura model:**
   - Fields: banca (FK), numero, serie, tipo_documento (choices), estado (choices), cliente_designacao, cliente_nif, total, emitida_em, criada_em, atualizada_em, agt_request_id, agt_status (choices), agt_hash_validacao, agt_processada_em, agt_erros (JSONField)
   - Meta: db_table, verbose_name, indexes for (banca_id, estado), (banca_id, agt_status), agt_request_id
   - __str__: return f"{self.numero} — {self.cliente_nif} — {self.estado}"

4. **SubmissaoAgt model:**
   - Fields: banca (FK), fatura (FK PROTECT), estado (choices), payload_xml, submetida_em, ultima_tentativa_em, proxima_tentativa_em, tentativas, mensagem, codigo_controlo
   - Meta: db_table, verbose_name, indexes for (fatura_id, estado), proxima_tentativa_em
   - __str__: return f"Submissão {self.pk} — Fatura {self.fatura.numero} — {self.estado}"

5. **RegistoAuditoria model:**
   - Fields: banca (FK), acao, origin_tipo (choices), entity_tipo, entity_id, motivo, ip_address, user_agent, usuario_id, criado_em
   - Meta: db_table, verbose_name, indexes for (criado_em, origin_tipo), (entity_tipo, entity_id)
   - __str__: return f"{self.acao} — {self.entity_tipo}({self.entity_id}) — {self.criado_em.strftime('%Y-%m-%d %H:%M:%S')}"

**Verify:** `python manage.py check agt_invoicing` passes (no errors).

### Step 3: Update INSTALLED_APPS

Edit `c:/projetos/sicdoa/sicdoa/settings.py` (line ~33):
- Find the INSTALLED_APPS list
- Add `'agt_invoicing'` after `'financeiro'` and before `'channels'`

**Verify:** settings.py has correct Python syntax: `python manage.py check` (full check, not app-specific).

### Step 4: Update URLs configuration

Edit `c:/projetos/sicdoa/sicdoa/urls.py` (after line ~63, after the financeiro include):
- Add: `path('api/agt/', include('agt_invoicing.urls'))`

**Verify:** File is valid Python syntax: `python manage.py check`.

### Step 5: Create migrations

Run (in PowerShell, from workspace root):
```powershell
python manage.py makemigrations agt_invoicing
```

**Expected:** Migration file created at `c:/projetos/sicdoa/agt_invoicing/migrations/0001_initial.py` containing CreateModel operations for all 4 models.

**Verify:** Migration file exists and contains all 4 models.

### Step 6: Apply migrations to database

Run (in PowerShell, from workspace root):
```powershell
python manage.py migrate agt_invoicing
```

**Expected:** Migration applied successfully; MySQL tables created (configuracaofiscal, fatura, submissaoagt, registoauditoria in sicdoav1 database).

**Verify:** 
- No SQL errors in output
- Tables appear in MySQL: Query `SHOW TABLES;` in sicdoav1 database should list the 4 new tables

### Step 7: Verify app integration

Run (in PowerShell):
```powershell
python manage.py check
```

**Expected:** No errors or warnings related to agt_invoicing.

**Verify:** Output includes "System check identified no issues (0 silenced)."

### Step 8: Verify database schema

Run (in PowerShell):
```powershell
python manage.py sqlmigrate agt_invoicing 0001
```

**Expected:** SQL DDL statements for CREATE TABLE commands matching the models.

**Verify:** Output contains:
- CREATE TABLE with correct field names and types
- DECIMAL(15,2) for total field in Fatura
- Foreign key constraints with CASCADE/PROTECT as specified
- Indexes created as defined in Meta

### Step 9: Commit locally

Run (in PowerShell, from workspace root):
```powershell
git add c:\projetos\sicdoa\agt_invoicing\
git add c:\projetos\sicdoa\sicdoa\settings.py
git add c:\projetos\sicdoa\sicdoa\urls.py
git commit -m "feat(agt_invoicing): Create app with 4 models (ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria) + migrations

- Add agt_invoicing app to INSTALLED_APPS in settings
- Register app URLs at /api/agt/ in urls.py
- Implement multi-tenant Banca FK pattern for all models
- Create initial migration with 4 tables (MySQL charset utf8mb4)
- All Decimal fields use max_digits=15, decimal_places=2
- Composite indexes for efficient multi-tenant filtering
- No views, services, or admin registrations (for next cycle)"
```

**Verify:** Commit succeeds locally (no push yet).

---

## Verification Checklist

- [ ] App directory structure created with all required files
- [ ] models.py implements all 4 models with correct field types, choices, and indexes
- [ ] INSTALLED_APPS includes 'agt_invoicing'
- [ ] urls.py registers the app at path('api/agt/', include('agt_invoicing.urls'))
- [ ] `python manage.py check` returns no errors
- [ ] `python manage.py makemigrations agt_invoicing` creates 0001_initial.py
- [ ] `python manage.py migrate agt_invoicing` applies successfully to MySQL
- [ ] MySQL tables exist in sicdoav1 database:
  - `agt_invoicing_configuracaofiscal`
  - `agt_invoicing_fatura`
  - `agt_invoicing_submissaoagt`
  - `agt_invoicing_registoauditoria`
- [ ] All foreign key relationships created correctly (banca → rh_empresas, fatura → agt_invoicing_fatura)
- [ ] All indexes created as specified
- [ ] Decimal fields stored as DECIMAL(15,2) in MySQL
- [ ] Commit created locally with clear message (not pushed)

---

## Design Decisions Recorded

1. **Multi-tenant isolation:** Direct `banca` FK on SubmissaoAgt and RegistoAuditoria ensures independent query filtering; Fatura is the primary tenant root. Rationale: Consistent with existing financeiro/ and rh/ patterns, and allows audit records to be filtered by banca even if fatura is soft-deleted or archived in future.

2. **Decimal(max_digits=15, decimal_places=2):** Chosen to match existing financeiro/ pattern for all monetary fields; supports up to 999,999,999,999.99 (sufficient for invoices in Angola Kwanzas).

3. **CharField + choices (not TextChoices):** Matches rh/ and financeiro/ existing patterns; simpler migration compatibility.

4. **On_delete=PROTECT for Fatura → SubmissaoAgt:** Prevents accidental invoice deletion if submissions exist; PROTECT enforces referential integrity and forces explicit cleanup.

5. **On_delete=CASCADE for banca → all models:** Standard multi-tenant cleanup; if banca is deleted, all related invoicing records are deleted (auditable via RegistoAuditoria before deletion if needed in future).

6. **JSONField for agt_erros:** Allows flexible storage of AGT API error responses without schema migration; null=True allows clean invoices without errors.

7. **CharField(unique=True) for numero:** Ensures invoice numbers are globally unique (per Banca, could be constrained in future); db_index=True for fast lookups.

8. **agt_request_id (unique, nullable):** AGT polling requires fast lookup by requestID; nullable until submitted to AGT; unique prevents duplicate submissions.

---

## No Code Implementation Yet

This plan is complete and ready for the coding phase. No models.py, migrations, or configuration changes have been made to the repository.
