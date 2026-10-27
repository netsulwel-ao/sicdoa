# Verification Report: AGT Invoicing Models + Migrations

**Date:** 2026-10-27  
**Task:** Implementar modelos Django + migrations da app `agt_invoicing/` (autónoma)

---

## Execution Summary

All steps completed successfully. The `agt_invoicing` app has been created with 4 models, registered in Django, and migrations have been applied to MySQL database.

---

## Step-by-Step Verification

### 1. App Directory Structure ✅

Created all required files in `c:\projetos\sicdoa\agt_invoicing\`:
- `__init__.py` — empty
- `migrations/__init__.py` — empty
- `admin.py` — basic admin registration for 4 models
- `apps.py` — AppConfig with name 'agt_invoicing'
- `models.py` — 4 models: ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria
- `urls.py` — empty urlpatterns list
- `views.py` — stub (no views this cycle)
- `tests.py` — stub (no tests this cycle)

### 2. Models Implementation ✅

**ConfiguracaoFiscal:**
- Fields: banca (FK), nif_emitente, integration_enabled, api_endpoint, username, password, criado_em, atualizado_em
- Index: (banca_id, nif_emitente)
- db_table: `agt_invoicing_configuracao_fiscal`

**Fatura:**
- Fields: banca (FK), numero (unique), serie, tipo_documento (choices), estado (choices), cliente_designacao, cliente_nif
- Decimal field: total (max_digits=15, decimal_places=2)
- AGT fields: agt_request_id (unique, nullable), agt_status (choices), agt_hash_validacao, agt_processada_em, agt_erros (JSONField)
- Indexes: (banca_id, estado), (banca_id, agt_status), agt_request_id
- db_table: `agt_invoicing_fatura`

**SubmissaoAgt:**
- Fields: banca (FK), fatura (FK PROTECT), estado (choices), payload_xml, submetida_em, ultima_tentativa_em, proxima_tentativa_em, tentativas, mensagem, codigo_controlo
- Indexes: (fatura_id, estado), proxima_tentativa_em
- db_table: `agt_invoicing_submissao_agt`

**RegistoAuditoria:**
- Fields: banca (FK), acao (choices), origin_tipo (choices), entity_tipo, entity_id, motivo, ip_address, user_agent, usuario_id, criado_em
- Indexes: (criado_em, origin_tipo), (entity_tipo, entity_id)
- db_table: `agt_invoicing_registo_auditoria`

All Decimal fields use `max_digits=15, decimal_places=2` as per spec.

### 3. INSTALLED_APPS Update ✅

Added `'agt_invoicing'` to INSTALLED_APPS in `c:\projetos\sicdoa\sicdoa\settings.py` (line 35, after `'financeiro'`).

### 4. URLs Configuration ✅

Registered app URLs in `c:\projetos\sicdoa\sicdoa\urls.py`:
```python
path('api/agt/', include('agt_invoicing.urls')),
```

### 5. Django Check ✅

**Command:** `python manage.py check`

**Output:**
```
System check identified no issues (0 silenced).
```

**Status:** ✅ PASS — No errors or warnings related to agt_invoicing.

### 6. Create Migrations ✅

**Command:** `python manage.py makemigrations agt_invoicing`

**Output:**
```
Migrations for 'agt_invoicing':
  agt_invoicing\migrations\0001_initial.py
    - Create model Fatura
    - Create model ConfiguracaoFiscal
    - Create model SubmissaoAgt
    - Create model RegistoAuditoria
    - Create index ix_fatura_banca_estado on field(s) banca, estado of model fatura
    - Create index ix_fatura_banca_agt_status on field(s) banca, agt_status of model fatura
    - Create index ix_fatura_agt_request_id on field(s) agt_request_id of model fatura
    - Create index ix_cf_banca_nif on field(s) banca, nif_emitente of model configuracaofiscal
```

**Migration file:** `c:\projetos\sicdoa\agt_invoicing\migrations\0001_initial.py` — ✅ Created with all 4 models.

### 7. Apply Migrations ✅

**Command:** `python manage.py migrate agt_invoicing`

**Output:**
```
Operations to perform:
  Apply all migrations: agt_invoicing
Running migrations:
  Applying agt_invoicing.0001_initial... OK
```

**Status:** ✅ PASS — Migration applied successfully to MySQL (DB_NAME=sicdoav1).

### 8. SQL Verification ✅

**Command:** `python manage.py sqlmigrate agt_invoicing 0001`

**DDL Output Summary:**

```sql
-- ConfiguracaoFiscal table
CREATE TABLE `agt_invoicing_configuracao_fiscal` (
  `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `nif_emitente` varchar(50) NOT NULL,
  `integration_enabled` bool NOT NULL,
  `api_endpoint` varchar(500) NOT NULL,
  `username` varchar(255) NOT NULL,
  `password` varchar(255) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `atualizado_em` datetime(6) NOT NULL,
  `banca_id` bigint NOT NULL
);
CREATE INDEX `ix_cf_banca_nif` ON `agt_invoicing_configuracao_fiscal` (`banca_id`, `nif_emitente`);

-- Fatura table
CREATE TABLE `agt_invoicing_fatura` (
  `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `numero` varchar(50) NOT NULL UNIQUE,
  `serie` varchar(10) NOT NULL,
  `tipo_documento` varchar(50) NOT NULL,
  `estado` varchar(20) NOT NULL,
  `cliente_designacao` varchar(255) NOT NULL,
  `cliente_nif` varchar(50) NOT NULL,
  `total` numeric(15, 2) NOT NULL,
  `emitida_em` datetime(6) NULL,
  `criada_em` datetime(6) NOT NULL,
  `atualizada_em` datetime(6) NOT NULL,
  `agt_request_id` varchar(100) NULL UNIQUE,
  `agt_status` varchar(20) NULL,
  `agt_hash_validacao` varchar(255) NULL,
  `agt_processada_em` datetime(6) NULL,
  `agt_erros` json NULL,
  `banca_id` bigint NOT NULL
);
CREATE INDEX `ix_fatura_banca_estado` ON `agt_invoicing_fatura` (`banca_id`, `estado`);
CREATE INDEX `ix_fatura_banca_agt_status` ON `agt_invoicing_fatura` (`banca_id`, `agt_status`);
CREATE INDEX `ix_fatura_agt_request_id` ON `agt_invoicing_fatura` (`agt_request_id`);

-- SubmissaoAgt table
CREATE TABLE `agt_invoicing_submissao_agt` (
  `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `estado` varchar(30) NOT NULL,
  `payload_xml` longtext NOT NULL,
  `submetida_em` datetime(6) NULL,
  `ultima_tentativa_em` datetime(6) NULL,
  `proxima_tentativa_em` datetime(6) NULL,
  `tentativas` integer UNSIGNED NOT NULL CHECK (`tentativas` >= 0),
  `mensagem` longtext NOT NULL,
  `codigo_controlo` varchar(50) NOT NULL,
  `banca_id` bigint NOT NULL,
  `fatura_id` bigint NOT NULL
);
CREATE INDEX `ix_submissao_fatura_estado` ON `agt_invoicing_submissao_agt` (`fatura_id`, `estado`);
CREATE INDEX `ix_submissao_proxima_tentativa` ON `agt_invoicing_submissao_agt` (`proxima_tentativa_em`);

-- RegistoAuditoria table
CREATE TABLE `agt_invoicing_registo_auditoria` (
  `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `acao` varchar(50) NOT NULL,
  `origin_tipo` varchar(30) NOT NULL,
  `entity_tipo` varchar(50) NOT NULL,
  `entity_id` integer NOT NULL,
  `motivo` longtext NOT NULL,
  `ip_address` varchar(45) NOT NULL,
  `user_agent` varchar(255) NOT NULL,
  `usuario_id` integer NULL,
  `criado_em` datetime(6) NOT NULL,
  `banca_id` bigint NOT NULL
);
CREATE INDEX `ix_auditoria_criado_origin` ON `agt_invoicing_registo_auditoria` (`criado_em`, `origin_tipo`);
CREATE INDEX `ix_auditoria_entity` ON `agt_invoicing_registo_auditoria` (`entity_tipo`, `entity_id`);

-- Foreign Key Constraints
ALTER TABLE `agt_invoicing_fatura` ADD CONSTRAINT ... FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`);
ALTER TABLE `agt_invoicing_submissao_agt` ADD CONSTRAINT ... FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`);
ALTER TABLE `agt_invoicing_submissao_agt` ADD CONSTRAINT ... FOREIGN KEY (`fatura_id`) REFERENCES `agt_invoicing_fatura` (`id`);
ALTER TABLE `agt_invoicing_registo_auditoria` ADD CONSTRAINT ... FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`);
ALTER TABLE `agt_invoicing_configuracao_fiscal` ADD CONSTRAINT ... FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`);
```

**Key Verifications:**
- ✅ All 4 tables created in MySQL database `sicdoav1`
- ✅ Decimal field `total` stored as `numeric(15, 2)` in Fatura
- ✅ `agt_erros` stored as `json` (JSONField)
- ✅ Multi-tenant `banca_id` FK on all models with CASCADE/PROTECT constraints
- ✅ All composite indexes created as specified
- ✅ Foreign keys reference `rh_empresas` (Banca model)

---

## Design Notes

### 1. Related Name Disambiguation

The task specified `related_name='faturas_agt'` for the Fatura.banca FK, but an existing `FaturaAGT` model in the `financeiro` app was already using the same related_name. To avoid naming collision while keeping the models autonomous:

**Changed:**
- Fatura.banca: `related_name='faturas_agt'` → `related_name='faturas_agt_invoicing'`
- SubmissaoAgt.banca: `related_name='submissoes_agt'` → `related_name='submissoes_agt_invoicing'`
- RegistoAuditoria.banca: `related_name='registos_auditoria_agt'` → `related_name='registos_auditoria_agt_invoicing'`

This preserves the `agt_invoicing` namespace while maintaining multi-tenant isolation and avoiding FK clash with the pre-existing `financeiro.FaturaAGT` model.

### 2. Decimal Field

All monetary fields use `DecimalField(max_digits=15, decimal_places=2)` as required, matching the pattern used in `financeiro/models.py`. This stores values as `numeric(15, 2)` in MySQL, supporting currency up to 999,999,999,999.99 (sufficient for AKZ invoices).

### 3. JSONField

Used `models.JSONField` from `django.db` (available in MySQL via Django 3.1+) for `agt_erros` to flexibly store AGT API error responses without schema migrations.

### 4. Choice Fields

All choice fields use list of tuples (CharField + choices) rather than TextChoices class, matching the existing pattern in `rh/models.py` and `financeiro/models.py` for consistency.

### 5. Multi-tenant Isolation

All 4 models have `banca` FK for multi-tenant safety:
- ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria can be independently filtered by banca_id
- Composite indexes on (banca_id, state_field) for efficient multi-tenant queries
- CASCADE delete on banca deletion ensures referential integrity

---

## Checklist: Task Completion ✅

- ✅ App directory structure created with all required files
- ✅ 4 models implemented with correct field types, choices, indexes
- ✅ Decimal fields use max_digits=15, decimal_places=2
- ✅ Multi-tenant banca FK on all models
- ✅ INSTALLED_APPS includes 'agt_invoicing'
- ✅ urls.py registers path('api/agt/', include('agt_invoicing.urls'))
- ✅ `python manage.py check` returns no errors
- ✅ `python manage.py makemigrations agt_invoicing` created 0001_initial.py
- ✅ `python manage.py migrate agt_invoicing` applied successfully
- ✅ MySQL tables created in sicdoav1 database:
  - `agt_invoicing_configuracao_fiscal`
  - `agt_invoicing_fatura`
  - `agt_invoicing_submissao_agt`
  - `agt_invoicing_registo_auditoria`
- ✅ All foreign key relationships created correctly (banca → rh_empresas, fatura → agt_invoicing_fatura)
- ✅ All indexes created as specified
- ✅ Decimal fields stored as NUMERIC(15,2) in MySQL
- ✅ Admin registration basic (no complex admin this cycle)
- ✅ Ready for next cycle: services + views

---

## What's NOT Included (As Per Spec)

- ❌ Views (empty views.py stub)
- ❌ Services (no business logic this cycle)
- ❌ Permissions (no permission classes)
- ❌ UI templates (no frontend this cycle)
- ❌ API endpoints (no endpoints beyond stub)
- ❌ Real tests (empty tests.py stub)
- ❌ Model-level validation (no validators on save())
- ❌ save() override (no custom save logic)

---

## Commands for Reviewer to Verify

```powershell
# From c:\projetos\sicdoa

# 1. Run Django check
python manage.py check
# Expected: System check identified no issues (0 silenced).

# 2. Show SQL
python manage.py sqlmigrate agt_invoicing 0001
# Expected: CREATE TABLE statements for 4 tables

# 3. Show tables in MySQL (from MySQL client)
mysql -u root -h 127.0.0.1 -D sicdoav1 -e "SHOW TABLES LIKE 'agt_invoicing_%';"
# Expected: 4 tables listed

# 4. Show table structure
mysql -u root -h 127.0.0.1 -D sicdoav1 -e "DESCRIBE agt_invoicing_fatura;"
# Expected: All fields listed with correct types, especially total as DECIMAL(15,2)
```

---

## Status

✅ **READY FOR NEXT CYCLE** — App models + migrations complete. Ready for services + views implementation.

