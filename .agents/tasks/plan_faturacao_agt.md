# Implementation Plan — Faturação Eletrónica AGT

## Codebase Findings (read before writing any code)

- **Auth pattern**: all financeiro views use `@requer_sessao_ativa` (from `users.auth_decorators`) for read
  views and additionally `@requer_escrita_financeira` for write views. Both are defined in / imported by
  `financeiro/views.py`. `views_agt.py` must import them from the same place:
  `from users.auth_decorators import requer_sessao_ativa` and
  `from .views import requer_escrita_financeira` (defined at line 215 in views.py).
- **Session shape**: `request.session.get('usuario', {})` returns a dict with keys `papel`, `nome`, etc.
  `request.session.get('usuario_id')` gives the numeric id. `request.session.get('banca_id')` gives the
  banca scope.
- **Latest migration**: `0044_alter_regime_requisicao.py` → new migration is `0045_fatura_agt.py`.
  Its `dependencies` line must be `[('financeiro', '0044_alter_regime_requisicao')]`.
- **models.py end**: the file is 1139 lines; the last entity ends at `registrar_historico` function.
  The comment `# Fim dos modelos existentes.` is on the last line. Append the new model after it.
- **Template conventions** (from `factura_lista.html` and `factura_detalhe.html`):
  - `{% extends 'base.html' %}` with `{% block content %}`.
  - Card style: `bg-white rounded-2xl shadow-sm border border-gray-200 p-4`.
  - Buttons: `bg-primary text-white rounded-xl px-4 py-2 text-sm font-semibold`.
  - Status badges: `inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold`.
  - Pagination: `{% include 'includes/pagination.html' %}`.
  - Dark mode classes used consistently alongside light ones.
- **Sidebar insertion point**: the Facturas `<li>` block ends just before
  `<li class="border-t border-gray-100 dark:border-gray-700/60 my-1 pt-1"></li>` that immediately
  precedes the Conta Corrente link. The new `<li>` (Faturação Eletrónica AGT) goes between the Facturas
  `</li>` and that border separator.
- **URL namespace**: `app_name = 'financeiro'` in `urls.py`; all `reverse()` calls use
  `financeiro:<name>`.
- **Callback URL**: `https://bejames.online/api/facturacaoelectronica/callback` — must match the path
  registered in `urls.py` **and** the `CALLBACK_URL` constant in `views_agt.py`.

---

## Execution Order

Dependencies: 1 → 2 → 3 → 4 → 5 → 6 → 7. Each step leaves the codebase in a buildable/importable state.

---

- [ ] 1. **Add `FaturaAGT` model to `financeiro/models.py`**

  Append the class after the `registrar_historico` function (after line 1139). The model must include
  every field, the `Meta` class, and the `__str__` method specified in the task. Do NOT touch anything
  above the insertion point.

  Fields to add:
  - `STATUS_AGT = [('Pendente','Pendente'),('Processando','Processando'),('Validada','Validada'),('Rejeitada','Rejeitada'),('Erro','Erro')]`
  - `banca = ForeignKey('rh.Banca', on_delete=SET_NULL, null=True, blank=True, related_name='faturas_agt')`
  - `factura_cliente = OneToOneField('FacturaCliente', on_delete=SET_NULL, null=True, blank=True, related_name='fatura_agt')`
  - `numero_fatura = CharField(max_length=50, blank=True, db_index=True)`
  - `serie = CharField(max_length=20, blank=True)`
  - `nif_emitente = CharField(max_length=20, blank=True)`
  - `nif_cliente = CharField(max_length=20, blank=True)`
  - `nome_cliente = CharField(max_length=200, blank=True)`
  - `descricao = TextField(blank=True)`
  - `valor_sem_iva = DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))`
  - `valor_iva = DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))`
  - `valor_total = DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))`
  - `taxa_iva = DecimalField(max_digits=5, decimal_places=2, default=Decimal('14.00'))`
  - `agt_id = CharField(max_length=100, blank=True)`
  - `agt_hash = CharField(max_length=200, blank=True)`
  - `agt_qr_code = TextField(blank=True)`
  - `agt_status = CharField(max_length=20, choices=STATUS_AGT, default='Pendente', db_index=True)`
  - `agt_motivo_rejeicao = TextField(blank=True)`
  - `agt_data_validacao = DateTimeField(null=True, blank=True)`
  - `agt_resposta_raw = TextField(blank=True)`
  - `data_emissao = DateTimeField(auto_now_add=True, db_index=True)`
  - `data_atualizacao = DateTimeField(auto_now=True)`
  - `criado_por_id = IntegerField(null=True, blank=True)`
  - `criado_por_nome = CharField(max_length=200, blank=True)`

  Meta:
  - `db_table = 'financeiro_fatura_agt'`
  - `ordering = ['-data_emissao']`
  - 3 indexes: `ix_fatagt_status_data (agt_status, -data_emissao)`, `ix_fatagt_banca_status (banca, agt_status)`, `ix_fatagt_nif_cliente (nif_cliente)`

  `__str__`: return `f"FaturaAGT {self.numero_fatura or self.pk} - {self.nome_cliente}"`

  **Files**: `c:\projetos\sicdoa\financeiro\models.py`

  **Verify**: `python -m py_compile c:\projetos\sicdoa\financeiro\models.py` — exits with code 0, no output.

---

- [ ] 2. **Create migration `0045_fatura_agt.py`**

  Create the file `c:\projetos\sicdoa\financeiro\migrations\0045_fatura_agt.py` by hand (do not run
  `makemigrations` — the Django environment may not be fully set up). Write a standard
  `migrations.Migration` class.

  Critical details:
  - `dependencies = [('financeiro', '0044_alter_regime_requisicao')]`
  - `operations` = single `migrations.CreateModel(name='FaturaAGT', fields=[...], options={...})`
  - Include all fields from step 1 in the same order.
  - Include `indexes` in `options={'db_table': 'financeiro_fatura_agt', 'ordering': ['-data_emissao'], 'indexes': [...]}`.
  - For the `ForeignKey` to `'rh.Banca'` the migration must declare it as
    `models.ForeignKey(to='rh.banca', ...)` and add `('rh', '__first__')` to dependencies, or better
    use `('rh', '0001_initial')` if that migration exists — check with
    `Get-ChildItem c:\projetos\sicdoa\rh\migrations\ | Sort-Object Name | Select-Object -First 2`.
  - For `OneToOneField` to `FacturaCliente`, use `to='financeiro.facturacliente'` (same app, no extra
    dependency needed beyond `0044_...`).

  **Files**: `c:\projetos\sicdoa\financeiro\migrations\0045_fatura_agt.py`

  **Verify**: `python -m py_compile c:\projetos\sicdoa\financeiro\migrations\0045_fatura_agt.py` — exits 0.
  Also confirm the dependency chain is correct: the file header must not reference any migration that
  does not exist on disk.

---

- [ ] 3. **Create `financeiro/views_agt.py`**

  Create the file from scratch following the exact patterns from `views.py`:
  - Import `requer_sessao_ativa` from `users.auth_decorators`.
  - Import `requer_escrita_financeira` from `.views` (defined at line 215 of views.py).
  - Import `FaturaAGT` from `.models`.
  - Define module-level constants:
    ```python
    CALLBACK_URL = "https://bejames.online/api/facturacaoelectronica/callback"
    AGT_API_BASE = "https://efatura.hml.minfin.gov.ao/api/v1"
    ```

  Views to implement:

  **`faturacao_agt_dashboard(request)`**
  - Decorator: `@requer_sessao_ativa`
  - Computes `total_pendentes`, `total_emitidas` (Validada), `total_rejeitadas`, `total_validadas` via
    `FaturaAGT.objects.filter(agt_status=...).count()`.
  - `faturas_recentes = FaturaAGT.objects.select_related('factura_cliente').order_by('-data_emissao')[:5]`
  - Context also includes `active_menu='Financeiro'`, `active_sub='faturacao_agt'`,
    `callback_url=CALLBACK_URL`, `usuario=request.session.get('usuario', {})`.
  - Renders `'financeiro/faturacao_agt_dashboard.html'`.

  **`faturacao_agt_lista(request)`**
  - Decorator: `@requer_sessao_ativa`
  - Filters: `status = request.GET.get('status', '')`, `busca = request.GET.get('busca', '')`.
  - Applies `Q(numero_fatura__icontains=busca) | Q(nome_cliente__icontains=busca)` when busca set.
  - Paginates with `Paginator(qs, 20)`.
  - Context: `faturas`, `page_obj`, `status`, `busca`, `active_menu='Financeiro'`,
    `active_sub='faturacao_agt'`, `usuario=...`.
  - Renders `'financeiro/faturacao_agt_lista.html'`.

  **`faturacao_agt_detalhe(request, pk)`**
  - Decorator: `@requer_sessao_ativa`
  - `fatura = get_object_or_404(FaturaAGT, pk=pk)`
  - Context: `fatura`, `active_menu`, `active_sub`, `usuario`.
  - Renders `'financeiro/faturacao_agt_detalhe.html'`.

  **`faturacao_agt_submeter(request, factura_pk)`**
  - Decorators: `@require_POST`, `@requer_sessao_ativa`, `@requer_escrita_financeira`
  - Get-or-create `FaturaAGT` for the given `FacturaCliente` pk.
  - Populate fields from the FacturaCliente (nif_cliente, nome_cliente, valor_total, etc.).
  - Set `agt_status = 'Processando'`, save.
  - Wrap AGT API call in `try/except requests.RequestException`; on error set `agt_status = 'Erro'`.
  - Use `import requests` locally inside the function to avoid top-level import failures.
  - Redirect to `reverse('financeiro:faturacao_agt_detalhe', args=[fatura.pk])`.

  **`faturacao_agt_sincronizar(request, pk)`**
  - Decorator: `@requer_sessao_ativa`
  - GET request; polls AGT API for status update.
  - Returns `JsonResponse({'status': fatura.agt_status, 'ok': True})`.
  - On exception returns `JsonResponse({'ok': False, 'erro': str(e)}, status=500)`.

  **`faturacao_agt_callback(request)`**
  - Decorator: `@csrf_exempt` (from `django.views.decorators.csrf`).
  - Only handles POST; returns `JsonResponse({'status': 'ok'}, status=405)` for other methods.
  - Parses `json.loads(request.body)`.
  - Looks up `FaturaAGT` by `agt_id` from payload; updates `agt_status`, `agt_motivo_rejeicao`,
    `agt_data_validacao`, `agt_resposta_raw`.
  - Wraps everything in `try/except`; on error returns `JsonResponse({'status': 'error', 'detail': str(e)}, status=400)`.
  - Returns `JsonResponse({'status': 'ok'})`.

  **Files**: `c:\projetos\sicdoa\financeiro\views_agt.py`

  **Verify**: `python -m py_compile c:\projetos\sicdoa\financeiro\views_agt.py` — exits 0.

---

- [ ] 4. **Register URLs in `financeiro/urls.py`**

  Append to the bottom of `urlpatterns` in `urls.py`. Add the import line near the top (after the
  existing `from . import views_relatorio_pdf as rel_pdf` line):
  ```python
  from . import views_agt as agt
  ```

  Then add inside `urlpatterns`:
  ```python
  # ─── Faturação Eletrónica AGT ───────────────────────────────────────────
  path('faturacao-agt/', agt.faturacao_agt_dashboard, name='faturacao_agt_dashboard'),
  path('faturacao-agt/lista/', agt.faturacao_agt_lista, name='faturacao_agt_lista'),
  path('faturacao-agt/<int:pk>/', agt.faturacao_agt_detalhe, name='faturacao_agt_detalhe'),
  path('faturacao-agt/submeter/<int:factura_pk>/', agt.faturacao_agt_submeter, name='faturacao_agt_submeter'),
  path('faturacao-agt/<int:pk>/sincronizar/', agt.faturacao_agt_sincronizar, name='faturacao_agt_sincronizar'),
  path('api/facturacaoelectronica/callback', agt.faturacao_agt_callback, name='faturacao_agt_callback'),
  ```

  ⚠️ Attention: `path('faturacao-agt/<int:pk>/', ...)` must come AFTER `path('faturacao-agt/lista/', ...)`
  in the list to avoid the `lista` path being swallowed by the `<int:pk>` pattern — which would fail
  anyway since "lista" is not an int. Django matches in order, and `lista` is safe because `<int:pk>`
  only matches integers. Still, keep list before detail for clarity.

  **Files**: `c:\projetos\sicdoa\financeiro\urls.py`

  **Verify**: `python -m py_compile c:\projetos\sicdoa\financeiro\urls.py` — exits 0.

---

- [ ] 5. **Create dashboard template `faturacao_agt_dashboard.html`**

  Read `factura_lista.html` as the exact style reference before writing. The template must:

  - `{% extends 'base.html' %}` / `{% block content %}`
  - Breadcrumb: `Financeiro > Faturação Eletrónica AGT`
  - Page title `Faturação Eletrónica AGT` + subtitle `Gestão e acompanhamento de faturas validadas pela AGT`
  - Callback badge (gray info box) showing `{{ callback_url }}`
  - Two action buttons: `🔄 Actualizar` (JS `location.reload()`) and `Ver todas as faturas`
    (link to `{% url 'financeiro:faturacao_agt_lista' %}`)
  - 4 KPI cards (`grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5`):
    1. **Pendentes AGT** — `{{ total_pendentes }}` — icon `fa-clock`, color yellow
    2. **Status AGT** — `+5%` — icon `fa-chart-line`, color blue
    3. **Faturas Emitidas** — `{{ total_emitidas }}` — icon `fa-file-invoice`, color blue
    4. **Faturas Rejeitadas** — `{{ total_rejeitadas }}` — icon `fa-times-circle`, color red
  - Section `Visão Geral` — table of `{{ faturas_recentes }}` with columns:
    N.º Fatura | Cliente | Valor Total | Status AGT | Data Emissão | Ações
  - Status badge colors: Pendente=yellow, Validada=green, Rejeitada=red, Processando=blue, Erro=red
  - Action buttons per row: `Ver` (→ `faturacao_agt_detalhe`) and `Sincronizar`
    (→ `faturacao_agt_sincronizar`)
  - Info box explaining AGT integration context
  - Code block showing example callback JSON payload:
    ```json
    {"agt_id": "...", "status": "Validada", "hash": "...", "qr_code": "..."}
    ```
  - Empty state when `faturas_recentes` is empty.

  **Files**: `c:\projetos\sicdoa\financeiro\templates\financeiro\faturacao_agt_dashboard.html`

  **Verify**: File exists and `{% extends 'base.html' %}` is on line 1. No Django template syntax
  errors visible on inspection (template tag balance check).

---

- [ ] 6. **Create list template `faturacao_agt_lista.html`**

  Read `factura_lista.html` as the direct style reference. The template must:

  - `{% extends 'base.html' %}` / `{% block content %}`
  - Breadcrumb: `Financeiro > Faturação Eletrónica AGT > Lista`
  - Filter bar with `<form method="get">` — `<select name="status">` (blank + all STATUS_AGT choices)
    and text `<input name="busca">` search field and submit button and clear-search link when filters
    active.
  - Table view (no grid toggle needed for this one) with columns:
    N.º Fatura | NIF Cliente | Cliente | Valor Total | Status AGT | Data Emissão | Ações
  - Status badge colors identical to dashboard template.
  - Pagination via `{% include 'includes/pagination.html' %}` — only shown when `page_obj.has_other_pages`.
  - Empty state block when `faturas` is empty.
  - Back button linking to `{% url 'financeiro:faturacao_agt_dashboard' %}`.

  **Files**: `c:\projetos\sicdoa\financeiro\templates\financeiro\faturacao_agt_lista.html`

  **Verify**: File exists and parses as valid Django template (check opening/closing tag balance).

---

- [ ] 7. **Create detail template `faturacao_agt_detalhe.html`**

  Read `factura_detalhe.html` as the style reference. The template must:

  - `{% extends 'base.html' %}` / `{% block content %}`
  - Breadcrumb: `Faturação Eletrónica AGT > {{ fatura.numero_fatura|default:fatura.pk }}`
  - Header: fatura number + status badge.
  - Two-column layout with left column (main details) and right column (AGT metadata):
    - Left: N.º Fatura, Série, NIF Emitente, NIF Cliente, Nome Cliente, Descrição, Valor sem IVA,
      IVA, Valor Total, Taxa IVA, Data Emissão.
    - Right: AGT ID, AGT Hash, Status AGT (badge), Motivo Rejeição (when applicable), Data Validação,
      QR Code (if agt_qr_code set, render as text/pre block — not as img, since it may be a data URL
      or base64 string), Raw Response (collapsible `<details>` block).
  - Action buttons: `Voltar` (back to lista), `Sincronizar` (GET to `faturacao_agt_sincronizar`).
  - If `fatura.factura_cliente` is set: link to `{% url 'financeiro:factura_detalhe' fatura.factura_cliente.pk %}`.

  **Files**: `c:\projetos\sicdoa\financeiro\templates\financeiro\faturacao_agt_detalhe.html`

  **Verify**: File exists and extends `base.html`.

---

- [ ] 8. **Insert sidebar entry in `templates/includes/sidebar.html`**

  Insert the new `<li>` block **after** the closing `</li>` of the Facturas item and **before** the
  `<li class="border-t border-gray-100 dark:border-gray-700/60 my-1 pt-1"></li>` separator that
  precedes the Conta Corrente section.

  The exact text to find (anchor for insertion — must match exactly):
  ```
        {% endif %}
        <li class="border-t border-gray-100 dark:border-gray-700/60 my-1 pt-1"></li>
        {% if papel == 'Administrador' or papel == 'Super Administrador' or papel == 'Despachante Oficial' or 'gerir_financeiro' in user_permissoes or 'ver_conta_corrente' in user_permissoes %}
  ```

  Insert before that block:
  ```html
        {% if papel == 'Despachante Oficial' or papel == 'Administrador' or papel == 'Super Administrador' or 'gerir_financeiro' in user_permissoes %}
        <li>
          <a href="{% url 'financeiro:faturacao_agt_dashboard' %}"
             class="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors text-sm
                    {% if sub == 'faturacao_agt' %}bg-primary/10 text-primary font-semibold{% else %}text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800{% endif %}">
            <i class="fas fa-landmark text-base"></i>Faturação Eletrónica AGT
          </a>
        </li>
        {% endif %}
  ```

  **Files**: `c:\projetos\sicdoa\templates\includes\sidebar.html`

  **Verify**: The file contains `faturacao_agt_dashboard` after the edit; the `<li class="border-t...">` separator
  that precedes Conta Corrente is still present and in the right position.

---

## Points of Attention

1. **Import cycle risk**: `views_agt.py` imports `requer_escrita_financeira` from `.views`. Since
   `views.py` does not import from `views_agt.py`, there is no circular import. This is safe.

2. **`requests` library**: The AGT API call uses `import requests`. If the library is not installed,
   the import inside the function body prevents a startup crash — only the actual API call fails at
   runtime. Do not put `import requests` at the top of the file.

3. **Migration `rh` dependency**: Before writing the migration file, check whether
   `c:\projetos\sicdoa\rh\migrations\0001_initial.py` exists. If it does, add
   `('rh', '0001_initial')` to the migration dependencies. If the rh app has no migrations folder,
   use `('rh', '__first__')`. Either way, the `ForeignKey` to `rh.Banca` requires this.

4. **`FacturaCliente` reference**: The `OneToOneField` points to `'FacturaCliente'` — same app,
   no additional migration dependency needed beyond the financeiro chain.

5. **Decimal import**: `models.py` already imports `from decimal import Decimal`. Do not duplicate it.

6. **Callback URL trailing slash**: The `path(...)` entry for the callback in `urls.py` has no trailing
   slash (`path('api/facturacaoelectronica/callback', ...)`). This must match exactly what bejames.online
   expects. Do not add a slash.

7. **`csrf_exempt` on callback**: The callback endpoint is called by the AGT server — it has no browser
   session. Apply `@csrf_exempt` before `@require_POST` or use a plain method guard inside the view
   (check `request.method == 'POST'`). Both work; `@csrf_exempt` + internal method check is cleaner.

8. **Template context variable `usuario`**: The base template and sidebar both rely on
   `request.session.get('usuario')` being passed in context as `usuario`. Every view in `views_agt.py`
   must include `'usuario': request.session.get('usuario', {})` in its render context, consistent with
   how `BaseContextMixin` works in `views.py`.
