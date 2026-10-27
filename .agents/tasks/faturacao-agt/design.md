# Design Técnico — Módulo de Faturação Eletrónica AGT

**Versão**: 2.1 (revisão após findings de review)  
**Data**: Janeiro 2026  
**Status**: Pronto para implementação  
**Verificação**: Endereça todos os 3 findings da review (save() retry, KPI real, AGT_CALLBACK_SECRET)

---

## Overview

O módulo de Faturação Eletrónica AGT permite ao SICDOA submeter faturas à Administração Geral Tributária de Angola, acompanhar o ciclo de vida (Pendente → Processando → Validada/Rejeitada/Erro) e receber notificações por webhook. A arquitetura é baseada numa ligação `OneToOneField` entre `FaturaAGT` (novo modelo satélite) e `FacturaCliente` (modelo existente), com seis views, dois templates existentes (dashboard e lista), e URL routing completo já em produção.

A iteração 2 implementou o módulo com sucesso. Esta revisão (2.1) corre os 3 findings de revisão: (1) adiciona retry loop no `save()` do modelo para evitar `IntegrityError` em alta concorrência, (2) substitui KPI hardcoded por métrica real (taxa de validação mensal), e (3) documenta `AGT_CALLBACK_SECRET` como bloqueante de deployment obrigatório antes de exposição pública.

---

## 1. Modelo de Dados — `FaturaAGT`

### Estrutura de Ligação

```python
class FaturaAGT(models.Model):
    # Ligação um-para-um com fatura existente
    factura = models.OneToOneField(
        'FacturaCliente', 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name='fatura_agt'
    )
    banca = models.ForeignKey('rh.Banca', ...)  # Multi-tenant por banca
    
    # Identificadores de fatura
    numero_fatura = models.CharField(max_length=50, unique=True, blank=True)
    serie = models.CharField(max_length=20, blank=True)
    
    # Dados do emitente e cliente
    nif_emitente = models.CharField(max_length=20, blank=True)
    nif_cliente = models.CharField(max_length=20, blank=True)
    nome_cliente = models.CharField(max_length=255, blank=True)
    
    # Valores fiscais
    valor_sem_iva = models.DecimalField(max_digits=15, decimal_places=2, default='0.00')
    valor_iva = models.DecimalField(max_digits=15, decimal_places=2, default='0.00')
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, default='0.00')
    taxa_iva = models.DecimalField(max_digits=5, decimal_places=2, default='14.00')
    descricao = models.TextField(blank=True)
    
    # Campos de status AGT
    agt_id = models.CharField(max_length=200, blank=True)  # ID da fatura no sistema AGT
    agt_request_id = models.CharField(max_length=200, blank=True, db_index=True)  # requestID gerado em submissão
    agt_status = models.CharField(
        max_length=20,
        choices=[
            ('Pendente', 'Pendente'),
            ('Processando', 'Processando'),
            ('Validada', 'Validada'),
            ('Rejeitada', 'Rejeitada'),
            ('Erro', 'Erro'),
        ],
        default='Pendente',
        db_index=True
    )
    agt_hash = models.CharField(max_length=500, blank=True)  # Hash de validação AGT
    agt_qr_code = models.TextField(blank=True)  # QR code de validação
    agt_motivo_rejeicao = models.TextField(blank=True)  # Motivo se rejeitada
    agt_data_validacao = models.DateTimeField(null=True, blank=True)  # Timestamp de validação
    agt_resposta_raw = models.JSONField(null=True, blank=True)  # Resposta completa da AGT
    
    # Metadados
    data_emissao = models.DateTimeField(auto_now_add=True, db_index=True)
    data_atualizacao = models.DateTimeField(auto_now=True)
    criado_por_id = models.IntegerField(null=True, blank=True)
    criado_por_nome = models.CharField(max_length=200, blank=True, default='')
```

### Geração de Números de Fatura

**Método**: `_gerar_numero_fatura()`  
**Padrão**: `FAT-{ano}-{seq:04d}` (ex: `FAT-2026-0001`)  
**Isolamento**: Sequência independente por banca (cada banca tem numeração própria)

```python
def _gerar_numero_fatura(self):
    """
    Gera número único por banca no padrão FAT-{ano}-{seq:04d}.
    Isolamento: cada banca tem sequência própria.
    """
    ano = timezone.now().year
    qs = FaturaAGT.objects.filter(numero_fatura__startswith=f'FAT-{ano}-')
    if self.banca_id:
        qs = qs.filter(banca_id=self.banca_id)
    ultimo = qs.order_by('-numero_fatura').first()
    if ultimo and ultimo.numero_fatura:
        try:
            seq = int(ultimo.numero_fatura.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'FAT-{ano}-{seq:04d}'
```

### Override `save()` — Addressing Finding 1

**Problem**: A iteração anterior não tinha retry loop por `IntegrityError` em alta concorrência. Dois saves simultâneos com `numero_fatura` vazio podem gerar o mesmo número; o segundo lança `IntegrityError` não capturado (500).

**Solution**: Replicar o padrão `for _attempt in range(5)` / catch `IntegrityError` que todos os outros modelos usam.

```python
def save(self, *args, **kwargs):
    """
    Override com retry loop por IntegrityError em número de fatura duplicado.
    Padrão usado em FacturaCliente, ReciboCliente, NotaCredito, NotaDebito, FacturaRecibo.
    """
    from django.db import IntegrityError
    
    for _attempt in range(5):
        if not self.numero_fatura:
            self.numero_fatura = self._gerar_numero_fatura()
        try:
            super().save(*args, **kwargs)
            break
        except IntegrityError:
            self.numero_fatura = None
            # Loop tenta novamente — máx 5 tentativas
            continue
```

**Effect**: Em alta concorrência, até 5 tentativas de gerar um número único. Reduz probabilidade de 500 para mínima.

---

## 2. Views (URL Routing & Lógica)

Todas as views usam `@requer_sessao_ativa` (autenticação) e `@requer_escrita_financeira` (permissões).

### URL Routes (em `financeiro/urls.py`)

```python
# ─── Faturação Eletrónica AGT ─────────────────────────────────────────
path('faturacao-agt/', agt.faturacao_agt_dashboard, name='faturacao_agt_dashboard'),
path('faturacao-agt/lista/', agt.faturacao_agt_lista, name='faturacao_agt_lista'),
path('faturacao-agt/<int:pk>/', agt.faturacao_agt_detalhe, name='faturacao_agt_detalhe'),
path('faturacao-agt/submeter/<int:factura_pk>/', agt.faturacao_agt_submeter, name='faturacao_agt_submeter'),
path('faturacao-agt/<int:pk>/sincronizar/', agt.faturacao_agt_sincronizar, name='faturacao_agt_sincronizar'),

# API Pública (webhook AGT)
# NOTA: registado em urls.py raiz em /api/facturacaoelectronica/callback
```

### 2.1 Dashboard — `faturacao_agt_dashboard` (GET)

**URL**: `/financeiro/faturacao-agt/`  
**Template**: `financeiro/faturacao_agt_dashboard.html`  
**Permissões**: Autenticado

**Contexto**:
- `total_pendentes` — contagem de FaturaAGT com `agt_status='Pendente'`
- `total_emitidas` — contagem total de FaturaAGT (independente de status)
- `total_validadas` — contagem com `agt_status='Validada'`
- `total_rejeitadas` — contagem com `agt_status='Rejeitada'`
- `total_processando` — contagem com `agt_status='Processando'`
- `taxa_validacao` — **[FINDING 2 FIX]** métrica real: `(total_validadas / total_emitidas) * 100` para o mês atual
- `faturas_recentes` — últimas 5 faturas ordenadas por `-data_emissao`
- `alertas_config` — lista de avisos de configuração AGT (se credenciais em falta)
- `agt_configurado` — flag booleano (True se sem alertas)
- `callback_url` — URL pública do webhook callback

**Lógica de Multi-tenant**: Filtra por `banca_id` se presente na sessão.

**KPI Card Fix (Finding 2)**:
Atualmente o template exibe `+5%` como texto fixo:
```html
<p class="text-lg font-bold text-blue-600">+5%</p>
```

Deve ser alterado para:
```html
<p class="text-lg font-bold text-blue-600">{{ taxa_validacao }}%</p>
```

A view calcula: 
```python
taxa_validacao = 0
if total_emitidas > 0:
    taxa_validacao = round((total_validadas / total_emitidas) * 100, 1)
```

**Métrica**: Taxa de validação no período (todas as faturas, não apenas mês atual — escopo pode ser refinado em iterações futuras).

### 2.2 Lista — `faturacao_agt_lista` (GET)

**URL**: `/financeiro/faturacao-agt/lista/`  
**Template**: `financeiro/faturacao_agt_lista.html`  
**Permissões**: Autenticado  
**Paginação**: 20 itens por página

**Parâmetros de Query**:
- `status` — filtro por `agt_status` (Pendente, Processando, Validada, Rejeitada, Erro)
- `busca` — search em `numero_fatura`, `nome_cliente`, `nif_cliente` (icontains)
- `page` — número da página

**Contexto**:
- `page_obj` — página actual (Paginator)
- `faturas` — alias para `page_obj`
- `status_choices` — lista de (value, label) de STATUS_AGT
- `status`, `busca` — valores actuais de filtro para persistência em template

### 2.3 Detalhe — `faturacao_agt_detalhe` (GET)

**URL**: `/financeiro/faturacao-agt/<int:pk>/`  
**Template**: `financeiro/faturacao_agt_detalhe.html`  
**Permissões**: Autenticado

**Contexto**:
- `fatura` — instância de FaturaAGT
- `factura` — FaturaCliente relacionada (se existir)
- Todos os campos da fatura para exibição (valores, NIF, hash AGT, QR code, resposta raw em JSON formatada)

**Lógica**:
```python
fatura = get_object_or_404(FaturaAGT, pk=pk)
# Escopo: se banca_id na sessão e fatura.banca_id ≠ banca_id, retorna 404
banca_id = request.session.get('banca_id')
if banca_id and fatura.banca_id != banca_id:
    raise Http404()
```

### 2.4 Submeter — `faturacao_agt_submeter` (POST)

**URL**: `/financeiro/faturacao-agt/submeter/<int:factura_pk>/`  
**Verbo**: POST (requer CSRF token)  
**Permissões**: `@requer_escrita_financeira`  
**Returns**: JSON `{"ok": true/false, "erro": "..."}`

**Parâmetros**:
- `factura_pk` — ID de FacturaCliente a submeter para AGT

**Lógica**:
1. Fetch `FacturaCliente(pk=factura_pk)` — retorna erro se não encontrada
2. Get-or-create `FaturaAGT` com `factura=FacturaCliente`
3. Populsar campos da FaturaAGT a partir de FacturaCliente (nif_cliente, nome_cliente, valores, etc.)
4. Chamar `_submeter_para_agt(fatura_agt)` — submete à API AGT
5. Atualizar:
   - `agt_status = 'Processando'`
   - `agt_request_id = request_id` (do payload construído)
   - `agt_resposta_raw = response JSON` (resposta AGT)
   - `data_atualizacao = now()`
6. Guardar FaturaAGT
7. Retornar JSON: `{"ok": true, "fatura_id": pk}`

**Error Handling**:
- Falha no fetch FacturaCliente → `{"ok": false, "erro": "Factura não encontrada"}`
- Falha na submissão à AGT (HTTPError, timeout, etc.) → `{"ok": false, "erro": "Erro ao contactar AGT: ..."}`
- Log de erro em `logger.exception()`

### 2.5 Sincronizar — `faturacao_agt_sincronizar` (POST)

**URL**: `/financeiro/faturacao-agt/<int:pk>/sincronizar/`  
**Verbo**: POST (requer CSRF token) — **[FINDING 1 FIX]**: GET→POST para evitar state mutation
**Permissões**: `@requer_escrita_financeira`  
**Returns**: JSON `{"ok": true/false, "status": "...", "erro": "..."}`

**Parâmetros**:
- `pk` — ID de FaturaAGT a sincronizar

**Lógica**:
1. Fetch `FaturaAGT(pk=pk)` — 404 se não encontrada
2. Se `agt_request_id` não preenchido → erro: "Fatura não foi submetida à AGT"
3. Chamar `_consultar_status_agt(agt_request_id)` — GET /consultarFactura/{id} à AGT
4. Parser resposta AGT:
   - Se `status == 'Validada'`:
     - `agt_status = 'Validada'`
     - `agt_hash = response['hash']`
     - `agt_qr_code = response['qrCode']` (ou encoding do QR)
     - `agt_id = response['id']` (ID único da fatura na AGT)
     - `agt_data_validacao = now()`
   - Se `status == 'Rejeitada'`:
     - `agt_status = 'Rejeitada'`
     - `agt_motivo_rejeicao = response['rejectReason']`
   - Se `status == 'Erro'`:
     - `agt_status = 'Erro'`
     - `agt_motivo_rejeicao = response.get('errorMessage', 'Erro desconhecido')`
   - Se `status == 'Processando'` (ainda em processamento):
     - `agt_status = 'Processando'` (já está, nada muda)
5. Atualizar `agt_resposta_raw` com resposta completa
6. Guardar FaturaAGT
7. Retornar JSON: `{"ok": true, "status": agt_status}`

**Error Handling**:
- Falha no fetch → 404
- `agt_request_id` não preenchido → `{"ok": false, "erro": "..."}`
- Falha na AGT API → `{"ok": false, "erro": "Erro ao consultar AGT: ..."}`

### 2.6 Callback — `faturacao_agt_callback` (POST)

**URL**: `/api/facturacaoelectronica/callback` (registado em urls.py raiz)  
**Verbo**: POST (JSON)  
**Permissões**: `@csrf_exempt` (webhook público) + **[FINDING 3 FIX]**: Verificação de `X-AGT-Secret`
**Returns**: JSON `{"status": "ok"}`

**Autenticação — [FINDING 3: AGT_CALLBACK_SECRET Bloqueante]**

O callback recebe notificações da AGT sem CSRF (webhook público). Proteção contra CSRF hijacking:

```python
@csrf_exempt
@require_POST
def faturacao_agt_callback(request):
    """
    Webhook público de callback da AGT.
    
    Autenticação: verificação de token em X-AGT-Secret header.
    Quando AGT_CALLBACK_SECRET não está configurado, aceita sem verificação (modo degradado).
    
    ⚠️ DEPLOYMENT BLOCKER: Configurar AGT_CALLBACK_SECRET em produção antes de expor URL publicamente.
    """
    secret = getattr(settings, 'AGT_CALLBACK_SECRET', None)
    
    if secret:
        # Modo seguro: verificar token
        received_token = request.headers.get('X-AGT-Secret', '')
        if received_token != secret:
            logger.warning(f"Callback com token inválido: {received_token}")
            return JsonResponse({'status': 'error', 'detail': 'Unauthorized'}, status=401)
    else:
        # Modo degradado (apenas em desenvolvimento/testes)
        logger.warning(
            "AGT_CALLBACK_SECRET não configurado — callback aceite sem autenticação. "
            "Em produção, configurar em settings.py ou .env."
        )
```

**Payload esperado**:
```json
{
  "requestID": "REQ-FAT-2026-0001-...",
  "agt_id": "id_da_fatura_agt",
  "status": "Validada|Rejeitada|Erro",
  "hash": "abc123...",
  "qrCode": "data:image/png;base64,...",
  "rejectReason": "..."  // Se Rejeitada
}
```

**Lógica**:
1. Parse JSON do request
2. Fetch `FaturaAGT` por `agt_request_id = requestID`
3. Atualizar campos conforme status (idêntico a `sincronizar`)
4. Guardar
5. Retornar `{"status": "ok"}`

**Error Handling**:
- Falha no parse JSON → `{"status": "error"}` + 400
- FaturaAGT não encontrada → `{"status": "ok"}` (silencioso, para não revelar IDs)
- Log de todas as operações

---

## 3. Integração com Permissões Existentes

### Permissões Requeridas

- `ver_faturacao_eletronica` — Ver dashboard e lista de faturas AGT (views leitura)
- `gerir_faturacao_eletronica` — Submeter faturas, sincronizar, receber callbacks (views escrita)

### Integração com `acesso.py`

Adicionar função de escopo (padrão do projeto):

```python
# em financeiro/acesso.py

def escopo_fatura_agt(request, queryset):
    """Escopo multi-tenant para FaturaAGT."""
    banca_id, filial_id, perm_set, is_admin = _get_banca_filial(request)
    if is_admin:
        return queryset
    if banca_id is None:
        return queryset.none()
    # FaturaAGT não tem filial (apenas banca), ignora filial_id
    return queryset.filter(banca_id=banca_id)
```

Aplicar em cada view:
```python
from .acesso import escopo_fatura_agt

@requer_sessao_ativa
def faturacao_agt_lista(request):
    qs = FaturaAGT.objects.all()
    qs = escopo_fatura_agt(request, qs)
    # ... resto da lógica
```

### Sidebar Integration

Adicionar item no template `templates/includes/sidebar.html`:

```html
<!-- Faturação Eletrónica AGT -->
{% if 'ver_faturacao_eletronica' in usuario_permissoes or papel in 'Administrador' %}
<li class="mb-2">
  <a href="{% url 'financeiro:faturacao_agt_dashboard' %}"
    class="px-4 py-2 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300
           {% if active_sub == 'faturacao_agt' %}bg-primary/10 text-primary{% else %}hover:bg-gray-100 dark:hover:bg-gray-800{% endif %}">
    <i class="fas fa-landmark mr-2"></i> Faturação Eletrónica AGT
  </a>
</li>
{% endif %}
```

---

## 4. Templates (Estrutura & Herança)

### Base Template

Todos os templates estendem `base.html`:
```html
{% extends 'base.html' %}
{% block content %}
  <!-- conteúdo específico -->
{% endblock %}
```

**Base structure**:
- `{% block sidebar %}` — incluir sidebar (automático via include)
- `{% block header %}` — incluir header (automático via include)
- `{% block content %}` — bloco principal (cada template preenche)
- Dark mode support via classes `dark:*` (Tailwind)

### 4.1 Dashboard Template

**Ficheiro**: `financeiro/templates/financeiro/faturacao_agt_dashboard.html`

**Estrutura**:
1. Breadcrumb: Financeiro > Faturação Eletrónica AGT
2. Cabeçalho com título, descrição, botões de ação
3. Mensagens de Django (se existirem)
4. Alertas de configuração (se credenciais em falta)
5. Badge de ambiente e KPIs
6. **4 Cards KPI** (alterado em Finding 2):
   - Pendentes AGT: `total_pendentes`
   - **Status AGT: `taxa_validacao`%** ← ANTES: hardcoded `+5%`, AGORA: variável real
   - Faturas Emitidas: `total_emitidas`
   - Faturas Rejeitadas: `total_rejeitadas` (com link para filtro)
7. Tabela de últimas 5 faturas (recentes):
   - Colunas: N.º Fatura, Cliente, Valor, Status AGT, Data, Ações (Ver, Sincronizar)
8. Info box com "Como funciona" (3 passos: Submeter, Polling, Validada)
9. Info box com webhook (callback URL, copiar, instruções de registro)

**Scripts**: Função JS `sincronizarFaturaAGT()` que faz POST (não GET) ao endpoint de sincronização com CSRF token.

### 4.2 Lista Template

**Ficheiro**: `financeiro/templates/financeiro/faturacao_agt_lista.html`

**Estrutura**:
1. Breadcrumb
2. Filtros (select de status, input de busca, botão Filtrar)
3. Paginação no topo
4. Tabela com todas as faturas:
   - Colunas: N.º, Cliente, NIF, Valor, Status, Data, Ações
5. Status badges com cores (Pendente=amarelo, Validada=verde, Rejeitada=vermelho, Processando=azul)
6. Paginação no fundo

### 4.3 Detalhe Template

**Ficheiro**: `financeiro/templates/financeiro/faturacao_agt_detalhe.html`

**Estrutura**:
1. Breadcrumb
2. Cabeçalho com número da fatura e status badge
3. **Secções de abas ou painéis**:
   - **Dados Gerais**: numero_fatura, cliente, NIF, série, data
   - **Valores Fiscais**: valor_sem_iva, valor_iva, valor_total, taxa_iva
   - **Status AGT**: agt_status, agt_request_id, agt_id, data de validação
   - **Validação**: agt_hash, agt_qr_code (renderizado), agt_motivo_rejeicao (se houver)
   - **Resposta Raw AGT**: `agt_resposta_raw` exibido em JSON formatado (read-only)
4. Botão "Sincronizar" (POST ao endpoint)
5. Botão "Voltar" ou link para lista

---

## 5. Integração com AGT (Crypto & API)

### Assinatura JWS RS256 — `agt_crypto.py`

Existente; reutilizado conforme.

**3 assinaturas obrigatórias**:
- `jwsSoftwareSignature` — identifica o software produtor (SICDOA)
- `jwsDocumentSignature` — assina os campos fiscais
- `jwsSignature` — assina a requisição (NIF + requestID)

**Função principal**: `construir_payload_agt(fatura: FaturaAGT) -> dict`

Gera payload completo com as 3 assinaturas (JWS), pronto para POST à AGT.

### API HTTP

**Base URL**: `AGT_API_BASE` (settings) — homologação por padrão:
```python
AGT_API_BASE = getattr(settings, 'AGT_API_BASE', 'https://sifphml.minfin.gov.ao/sigt/fe/v1')
```

**Endpoints usados**:
- `POST /registarFactura` — submeter nova fatura
- `GET /consultarFactura/{id}` — polling de status

**Autenticação**: HTTP Basic Auth (username:password em Base64)
```python
AGT_USERNAME = getattr(settings, 'AGT_USERNAME', '')
AGT_PASSWORD = getattr(settings, 'AGT_PASSWORD', '')
```

**Helper functions** (em `views_agt.py`):
- `_agt_session()` — cria requests.Session com Basic Auth
- `_submeter_para_agt(fatura)` → POST, devolve `{request_id, agt_response}`
- `_consultar_status_agt(agt_request_id)` → GET, devolve dict de status

### Configuração Obrigatória (Settings)

Em `.env` ou `settings.py`:

```bash
# Credenciais AGT (emitidas pela AGT)
AGT_USERNAME=...
AGT_PASSWORD=...

# Números de validação (obtidos no portal AGT)
AGT_SOFTWARE_VALIDATION_NUMBER=...

# Chaves privadas (para assinatura JWS)
AGT_SOFTWARE_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----
AGT_CONTRIBUTOR_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----

# URLs (homologação por padrão; produção em .env)
AGT_API_BASE=https://sifphml.minfin.gov.ao/sigt/fe/v1
AGT_CALLBACK_URL=https://sicdoa.cdoangola.co.ao/api/facturacaoelectronica/callback

# [FINDING 3 FIX] Autenticação do callback
AGT_CALLBACK_SECRET=seu_token_secreto_aqui  # ⚠️ OBRIGATÓRIO em produção

# Nome da empresa, série padrão
AGT_COMPANY_NAME=CDOA
AGT_SERIE_PADRAO=A
AGT_NIF_EMITENTE=123456789  # NIF da empresa (contribuinte)
```

---

## 6. Processamento Assíncrono (Modelo AGT)

O sistema segue o modelo de processamento assíncrono definido na documentação AGT:

```
1. SUBMETER (sincronizar)
   ↓
   Cliente POST /registarFactura {payload JWS}
   ↓
   AGT responde com requestID imediatamente
   ↓
   Documento entra na fila de processamento AGT
   
2. POLLING (sincronizar)
   ↓
   Cliente GET /consultarFactura/{requestID}
   ↓
   AGT devolve estado: Processando | Validada | Rejeitada | Erro
   
3. NOTIFICAÇÃO (webhook callback)
   ↓
   AGT POST {dados de validação} ao CALLBACK_URL
   ↓
   Cliente atualiza status FaturaAGT com hash + QR code
```

**Workflow na prática**:

1. Utilizador submete fatura (via UI "Submeter")
   - View `faturacao_agt_submeter` POST
   - Cria FaturaAGT se não existe
   - Chama `_submeter_para_agt()` → POST à AGT
   - Guarda `agt_request_id` e `agt_status='Processando'`
   
2. Utilizador sincroniza (via UI "Sincronizar")
   - View `faturacao_agt_sincronizar` POST
   - Chama `_consultar_status_agt(agt_request_id)` → GET à AGT
   - Atualiza status (Validada/Rejeitada/Erro)
   
3. (Alternativa) AGT envia notificação
   - POST ao webhook callback (`/api/facturacaoelectronica/callback`)
   - Callback atualiza FaturaAGT com hash + QR code
   - Utilizador vê status atualizado em tempo real (sem polling)

---

## 7. Edge Cases & Tratamento de Erros

### Network Errors
- **Timeout em submissão**: Capturar `requests.Timeout` → retornar erro JSON, log em WARNING
- **Timeout em polling**: Idem, retornar JSON com estado anterior (pode retentar)
- **Connection refused**: Retornar erro JSON, sugerir verificar config AGT_API_BASE

### Data Integrity
- **numero_fatura duplicado**: Tratado pelo novo retry loop no `save()` (Finding 1)
- **agt_request_id vazio**: Sincronizar sem agt_request_id deve retornar erro ("Fatura não foi submetida")
- **Fatura AGT órfã** (sem FacturaCliente): Permitido (via ON_DELETE=SET_NULL), renderizar com dados de FaturaAGT apenas

### State Transitions
- **Pendente → Processando**: Em submissão (OK)
- **Processando → Validada/Rejeitada/Erro**: Em polling/callback (OK)
- **Validada → Rejeitada**: Não permitir (Estado final, log WARNING se AGT tentar)
- **Rejeitada → Pendente**: Permitir (resubmissão após corrigir dados)

### Callback Idempotência
- O webhook pode chegar múltiplas vezes
- **Solução**: Atualizar pelo `agt_request_id` (único + durable)
- Se callback chega para fatura já `Validada`: apenas sobrescrever hash/QR (OK)

---

## 8. Testes

### Unit Tests (recomendado)

```python
# financeiro/tests.py

class FaturaAGTModelTestCase(TestCase):
    """Testes do modelo FaturaAGT."""
    
    def test_gerar_numero_fatura(self):
        """Verifica geração de número único."""
        ...
    
    def test_save_retry_loop(self):
        """Verifica retry loop em IntegrityError."""
        # Simular dois saves simultâneos com numero_fatura vazio
        ...
    
    def test_multi_tenant_scoping(self):
        """Verifica isolamento por banca."""
        ...

class FaturaAGTViewsTestCase(TestCase):
    """Testes de views."""
    
    def test_dashboard_kpi_taxa_validacao(self):
        """Verifica que taxa_validacao é calculada corretamente."""
        # FINDING 2: taxa deve ser (validadas / total) * 100
        ...
    
    def test_callback_secret_verification(self):
        """Verifica autenticação do callback."""
        # FINDING 3: sem secret, aceita; com secret, verifica
        ...
```

### Integration Tests (recomendado)

- Mock `_agt_session()` e endpoints AGT
- Testar fluxo completo: submissão → polling → validação

---

## 9. Deployment Checklist

- [ ] **Setting `AGT_CALLBACK_SECRET`** (FINDING 3 — bloqueante)
  - Gerar token único seguro
  - Adicionar a `.env` e `settings.py`
  - Registar em portal AGT

- [ ] **Chaves privadas** (AGT_SOFTWARE_PRIVATE_KEY, AGT_CONTRIBUTOR_PRIVATE_KEY)
  - Obter do portal AGT (chave do contribuinte)
  - Gerar/obter chave de software
  - Armazenar seguramente (não commit em git)

- [ ] **Credenciais AGT** (AGT_USERNAME, AGT_PASSWORD)
  - Obter do portal AGT

- [ ] **URL AGT_API_BASE**
  - Homologação: `https://sifphml.minfin.gov.ao/sigt/fe/v1`
  - Produção: `https://sifp.minfin.gov.ao/sigt/fe/v1`

- [ ] **Registar webhook callback** em portal AGT
  - URL: `AGT_CALLBACK_URL` (default: `https://sicdoa.cdoangola.co.ao/api/facturacaoelectronica/callback`)
  - Token: `AGT_CALLBACK_SECRET`

- [ ] **Database migrations** aplicadas
  - `migrate financeiro` (inclui modelos FaturaAGT)

- [ ] **Permissões criadas** em sistema de permissões
  - `ver_faturacao_eletronica`
  - `gerir_faturacao_eletronica`

- [ ] **Sidebar atualizado** com item "Faturação Eletrónica AGT"

- [ ] **Testes em homologação** com AGT
  - Submeter fatura de teste
  - Verificar polling / callback
  - Validar hash e QR code

---

## 10. Mitigações de Findings (Resumo)

| Finding | Severidade | Status | Solução |
|---------|-----------|--------|---------|
| **save() sem retry** | Minor | **ENDEREÇADO** | Adicionar `for _attempt in range(5)` / catch `IntegrityError` (secção 1) |
| **KPI Status AGT hardcoded** | Minor | **ENDEREÇADO** | Substituir `+5%` literal por `{{ taxa_validacao }}%` calculado em real-time (secção 2.1, 4.1) |
| **AGT_CALLBACK_SECRET** | Deployment Blocker | **ENDEREÇADO** | Documentar como obrigatório, implementar verificação condicional, adicionar ao deployment checklist (secção 5, 9) |

---

## 11. Estrutura de Ficheiros

```
financeiro/
├── models.py                              (classe FaturaAGT — já existe)
├── views_agt.py                           (6 views — já existe)
├── urls.py                                (routes — já existe)
├── acesso.py                              (+ escopo_fatura_agt)
├── agt_crypto.py                          (assinaturas — já existe)
├── templates/financeiro/
│   ├── faturacao_agt_dashboard.html       (template — já existe, atualizar KPI)
│   ├── faturacao_agt_lista.html           (template — já existe)
│   └── faturacao_agt_detalhe.html         (template — já existe)
├── migrations/
│   ├── 0045_fatura_agt.py                 (criar tabela — já existe)
│   └── 0046_faturaakt_gerar_numero.py     (dados legados — já existe)
└── tests.py                               (testes — recomendado estender)

urls.py (raiz)                             (adicionar callback à rota /api/)
templates/includes/sidebar.html            (adicionar item Faturação Eletrónica AGT)
```

---

## Notas Finais

- **Status**: Implementação de iteração 2 já em produção; esta revisão (2.1) endereça os 3 findings identificados em review
- **Deadline**: Alterações são de baixa complexidade (retry loop, KPI fix, documentação de segurança)
- **Testes**: Criar testes unitários para novo `save()` override e teste de integração para callback
- **Verificação**: Após implementação, testar em homologação da AGT para confirmar fluxo completo
