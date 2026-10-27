# Plano de Implementação — Módulo de Faturação Eletrónica AGT

**Status:** Revisão e Consolidação de Iteração 2  
**Versão do Design:** 2.1 (Pronto para Implementação)  
**Data:** Janeiro 2026

---

## Resumo Executivo

O módulo de Faturação Eletrónica AGT foi implementado na iteração 2 e encontra-se em produção. Esta revisão (2.1) verifica a implementação contra os 3 findings identificados na review de design, valida o alinhamento com padrões existentes do projeto, e consolida a implementação com testes e verificações finais.

**Status de Implementação:**
- ✅ Modelo FaturaAGT com retry loop em save() — **IMPLEMENTADO**
- ✅ 6 Views (dashboard, lista, detalhe, submeter, sincronizar, callback) — **IMPLEMENTADO**
- ✅ 3 Templates com design Tailwind + dark mode — **IMPLEMENTADO**
- ✅ URL routing completo — **IMPLEMENTADO**
- ✅ Migrations (0045, 0046, 0047) — **IMPLEMENTADO**
- ✅ KPI taxa_validacao real (não hardcoded) — **IMPLEMENTADO E CORRETO**
- ✅ Autenticação do callback com AGT_CALLBACK_SECRET — **IMPLEMENTADO**
- ✅ Sidebar menu item — **IMPLEMENTADO**
- ⚠️ escopo_fatura_agt() em acesso.py — **NÃO CRÍTICO** (views filtram manualmente por banca_id)

---

## Plano de Verificação & Consolidação

A seguir, um plano ordenado de verificações e pequenos ajustes (se necessários) para garantir robustez de produção.

---

### 1. Validar Estrutura de Modelo e Migrations

**O que fazer:** Verificar que a migração está correcta e aplicada, modelo roda sem erros.

**Ficheiros:** 
- `financeiro/models.py` (classe FaturaAGT)
- `financeiro/migrations/0045_fatura_agt.py`
- `financeiro/migrations/0046_faturaakt_gerar_numero.py`
- `financeiro/migrations/0047_faturaakt_add_request_id.py`

**Verificação:**
```bash
cd c:/projetos/sicdoa
python manage.py makemigrations --no-input financeiro
python manage.py migrate financeiro
python manage.py check
```

**Esperado:** 
- Sem erros de migração ("No changes detected in app 'financeiro'")
- `check` sem findings críticos
- Modelo carrega sem erros

---

### 2. Validar KPI Taxa de Validação (Finding 2 — Review)

**O que fazer:** Confirmar que a métrica taxa_validacao é calculada corretamente em real-time (não hardcoded).

**Ficheiros:**
- `financeiro/views_agt.py` — função `faturacao_agt_dashboard`
- `financeiro/templates/financeiro/faturacao_agt_dashboard.html` — linha que exibe taxa_validacao

**Verificação:**
```bash
# Verificar que a view calcula corretamente
grep -n "taxa_validacao = round" c:/projetos/sicdoa/financeiro/views_agt.py
# Esperado: linha com cálculo real (total_validadas / total_emitidas) * 100

# Verificar que o template usa a variável (não hardcoded +5%)
grep -n "taxa_validacao" c:/projetos/sicdoa/financeiro/templates/financeiro/faturacao_agt_dashboard.html
# Esperado: "{{ taxa_validacao }}%" (não "+5%")
```

**Esperado:** 
- View calcula `taxa_validacao = round((total_validadas / total_emitidas) * 100, 1)` se total_emitidas > 0
- Template exibe `{{ taxa_validacao }}%` (não valor hardcoded)
- Dashboard carrega e exibe KPI corretamente

---

### 3. Validar Autenticação do Callback (Finding 3 — AGT_CALLBACK_SECRET)

**O que fazer:** Confirmar que o callback webhook verifica X-AGT-Secret header, com fallback seguro para desenvolvimento.

**Ficheiros:**
- `financeiro/views_agt.py` — função `faturacao_agt_callback`
- `financeiro/settings.py` ou `.env` — AGT_CALLBACK_SECRET

**Verificação:**
```bash
# Verificar que o callback verifica o header
grep -n "AGT_CALLBACK_SECRET\|X-AGT-Secret" c:/projetos/sicdoa/financeiro/views_agt.py
# Esperado: verificação condicional (se secret, verifica; senão, log de warning)

# Verificar que settings tem AGT_CALLBACK_SECRET
grep "AGT_CALLBACK_SECRET" c:/projetos/sicdoa/sicdoa/settings.py
# Esperado: definição com valor default vazio ou via .env
```

**Esperado:**
- Callback verifica `X-AGT-Secret` header se `AGT_CALLBACK_SECRET` definido
- Se secret não definido: aceita without authentication + log warning (modo degradado)
- Em produção: AGT_CALLBACK_SECRET **DEVE** estar configurado no `.env`

---

### 4. Validar Save() com Retry Loop (Finding 1)

**O que fazer:** Confirmar que o modelo FaturaAGT trata IntegrityError em alta concorrência (numero_fatura duplicado).

**Ficheiros:**
- `financeiro/models.py` — método `save()` de FaturaAGT

**Verificação:**
```bash
# Verificar código do save()
grep -A 10 "def save" c:/projetos/sicdoa/financeiro/models.py | grep -A 10 "class FaturaAGT"
# Esperado: loop "for _attempt in range(5)" / catch IntegrityError / retry
```

**Teste:**
```bash
python manage.py shell
# Criar duas instâncias simultâneas com numero_fatura vazio
# (difícil de reproduzir em shell — validar via code review apenas)
```

**Esperado:**
- Modelo tem try/except IntegrityError com retry loop
- Máx 5 tentativas para gerar número único
- Reduz probabilidade de erro 500 em alta concorrência

---

### 5. Verificar Sidebar Item (Já Implementado)

**O que fazer:** Confirmar que Faturação Eletrónica AGT aparece no sidebar com permissões corretas.

**Ficheiros:**
- `templates/includes/sidebar.html`

**Verificação:**
```bash
grep -n "Faturação Eletrónica AGT" c:/projetos/sicdoa/templates/includes/sidebar.html
# Esperado: item presente com condicional de permissões
```

**Teste in-browser:**
```
1. Aceder a http://localhost:8000/financeiro/faturacao-agt/
2. Verificar que:
   - Header renderiza corretamente
   - Sidebar renderiza corretamente
   - Não há quebras de layout (confirmando que base.html é herdado)
   - Dashboard carrega com KPIs
```

---

### 6. Validar Templates (Herança & Dark Mode)

**O que fazer:** Confirmar que todos os templates herdam correctamente de base.html e renderizam em dark mode.

**Ficheiros:**
- `financeiro/templates/financeiro/faturacao_agt_dashboard.html`
- `financeiro/templates/financeiro/faturacao_agt_lista.html`
- `financeiro/templates/financeiro/faturacao_agt_detalhe.html`

**Verificação:**
```bash
# Verificar que herdam de base.html
grep "{% extends 'base.html' %}" c:/projetos/sicdoa/financeiro/templates/financeiro/faturacao_agt_*.html
# Esperado: todas as 3 templates com "{% extends 'base.html' %}"

# Verificar classes Tailwind dark:
grep "dark:" c:/projetos/sicdoa/financeiro/templates/financeiro/faturacao_agt_*.html | wc -l
# Esperado: múltiplos matches (dark mode suportado)
```

**Teste in-browser:**
1. Carregar dashboard em http://localhost:8000/financeiro/faturacao-agt/
2. Verificar rendering em light mode (padrão)
3. Activar dark mode no sistema/browser
4. Verificar que cores escuras aplicam-se correctamente
5. Testar navegar entre abas (dashboard → lista → detalhe)

---

### 7. Verificar Multi-tenancy (Isolamento por Banca)

**O que fazer:** Confirmar que todas as views filtram por banca_id corretamente, evitando vazamento de dados entre bancas.

**Ficheiros:**
- `financeiro/views_agt.py` — todas as 6 views

**Verificação:**
```bash
# Verificar que cada view filtra por banca_id
grep -n "banca_id = request.session.get" c:/projetos/sicdoa/financeiro/views_agt.py
# Esperado: múltiplos matches (uma por view)

grep -n "if banca_id" c:/projetos/sicdoa/financeiro/views_agt.py
# Esperado: lógica de filtro em cada view
```

**Teste:**
1. Criar duas bancas de teste (ou usar existentes)
2. Fazer login com usuário de banca A
3. Submeter fatura AGT para banca A
4. Fazer logout e login com usuário de banca B
5. Verificar que fatura de banca A **não aparece** em banca B

**Esperado:** Isolamento total por banca_id — sem vazamento de dados

---

### 8. Validar Configuração AGT (Settings & .env)

**O que fazer:** Listar todas as settings obrigatórias e opcionais para AGT, com valores de exemplo.

**Ficheiros:**
- `.env` (ou `sicdoa/settings.py`)

**Configurações Obrigatórias (Produção):**

```bash
# Credenciais emitidas pela AGT
AGT_USERNAME=seu_username_agt
AGT_PASSWORD=sua_password_agt

# Números de validação (obtidos no portal AGT)
AGT_SOFTWARE_VALIDATION_NUMBER=123456789

# Chaves privadas para JWS RS256 (min 2048 bits RSA)
AGT_SOFTWARE_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkq...\n-----END PRIVATE KEY-----
AGT_CONTRIBUTOR_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkq...\n-----END PRIVATE KEY-----

# URL da API AGT
AGT_API_BASE=https://sifp.minfin.gov.ao/sigt/fe/v1  # Produção
# AGT_API_BASE=https://sifphml.minfin.gov.ao/sigt/fe/v1  # Homologação

# URL pública do nosso webhook callback
AGT_CALLBACK_URL=https://sicdoa.cdoangola.co.ao/api/facturacaoelectronica/callback

# ⚠️ BLOQUEANTE PARA PRODUÇÃO: Token secreto para o callback
AGT_CALLBACK_SECRET=seu_token_secreto_aleatorio_aqui

# Dados da empresa (para JWS)
AGT_COMPANY_NAME=CDOA
AGT_SERIE_PADRAO=A
AGT_NIF_EMITENTE=123456789
```

**Verificação:**
```bash
# Verificar que pelo menos USERNAME e PASSWORD estão definidos
python manage.py shell
>>> from django.conf import settings
>>> print(getattr(settings, 'AGT_USERNAME', 'UNDEFINED'))
>>> print(getattr(settings, 'AGT_CALLBACK_SECRET', 'UNDEFINED'))
# Esperado: valores, não 'UNDEFINED'
```

---

### 9. Testar Fluxo Completo (Integração Ponta-a-Ponta)

**O que fazer:** Submeter uma fatura de teste e acompanhar ciclo completo (Pendente → Processando → Validada/Rejeitada).

**Passos:**
1. Criar/seleccionar uma FacturaCliente existente
2. Aceder a http://localhost:8000/financeiro/facturas/
3. Clicar em "Submeter para AGT" (se botão existe no detalhe da factura) ou ir direto:
   - http://localhost:8000/financeiro/faturacao-agt/lista/
   - Submeter uma factura via forma ou API
4. Esperar que a submissão completa (modal de carregamento + sucesso)
5. Verificar que FaturaAGT foi criada e agt_status = 'Processando'
6. Clicar "Sincronizar" para fazer polling
7. Verificar que status actualiza (Validada ou Rejeitada conforme resposta AGT)

**Esperado:**
- Dashboard carrega sem erros
- Fatura submete e recebe requestID
- Polling funciona e actualiza status
- KPIs actualizam em real-time
- Sem quebras de header/sidebar

---

### 10. Adicionar Função escopo_fatura_agt() em acesso.py (Recomendado mas Não Crítico)

**O que fazer:** Adicionar função de escopo reutilizável (padrão do projecto).

**Ficheiros:**
- `financeiro/acesso.py`

**Código a Adicionar:**

```python
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

**Integração em Views** (refactoring cosmético — não muda comportamento):

```python
# Em cada view de faturacao_agt_*, adicionar:
from .acesso import escopo_fatura_agt

@requer_sessao_ativa
def faturacao_agt_lista(request):
    qs = FaturaAGT.objects.all()
    qs = escopo_fatura_agt(request, qs)
    # ... resto da lógica
```

**Verificação:**
```bash
python manage.py check
python manage.py test financeiro.tests
# Esperado: sem erros, todos os testes passam
```

**Nota:** Esta é uma refactoring cosmética e não-bloqueante. Se os testes passam com o manual filter (como actualmente), mantém-se assim.

---

### 11. Criar Testes Unitários (Recomendado)

**O que fazer:** Adicionar testes para garantir robustez futura.

**Ficheiro:** `financeiro/tests.py`

**Testes Recomendados:**

```python
class FaturaAGTModelTestCase(TestCase):
    """Testes do modelo FaturaAGT."""
    
    def test_gerar_numero_fatura_unico(self):
        """Verifica que numero_fatura é gerado único."""
        fatura1 = FaturaAGT.objects.create(banca_id=1)
        fatura2 = FaturaAGT.objects.create(banca_id=1)
        self.assertNotEqual(fatura1.numero_fatura, fatura2.numero_fatura)
    
    def test_save_retry_loop_on_integrity_error(self):
        """Verifica retry loop em IntegrityError."""
        # Simular duplicação e verificar que retry funciona
        fatura = FaturaAGT(banca_id=1)
        fatura.numero_fatura = 'FAT-2026-0001'
        fatura.save()
        
        fatura2 = FaturaAGT(banca_id=1)
        fatura2.numero_fatura = 'FAT-2026-0001'
        # Deve falhar ou reatribuir número automaticamente
        # (dependendo da implementação)
    
    def test_multi_tenant_isolation(self):
        """Verifica isolamento por banca."""
        banca1 = Banca.objects.create(...)
        banca2 = Banca.objects.create(...)
        
        fatura1 = FaturaAGT.objects.create(banca=banca1)
        fatura2 = FaturaAGT.objects.create(banca=banca2)
        
        qs = FaturaAGT.objects.filter(banca=banca1)
        self.assertIn(fatura1, qs)
        self.assertNotIn(fatura2, qs)

class FaturaAGTViewsTestCase(TestCase):
    """Testes de views."""
    
    def test_dashboard_kpi_taxa_validacao(self):
        """Verifica que taxa_validacao é calculada corretamente."""
        # Criar faturas com status diferentes
        FaturaAGT.objects.create(banca_id=1, agt_status='Validada')
        FaturaAGT.objects.create(banca_id=1, agt_status='Validada')
        FaturaAGT.objects.create(banca_id=1, agt_status='Pendente')
        
        response = self.client.get('/financeiro/faturacao-agt/')
        # taxa_validacao deve ser 66.7 (2/3 * 100)
        self.assertContains(response, '66')
    
    def test_callback_auth_with_secret(self):
        """Verifica autenticação do callback."""
        payload = {'agt_id': '123', 'status': 'Validada'}
        response = self.client.post(
            '/api/facturacaoelectronica/callback',
            json.dumps(payload),
            content_type='application/json',
            HTTP_X_AGT_SECRET='wrong_secret'
        )
        # Deve retornar 401 se secret errado
        # (se AGT_CALLBACK_SECRET definido)
```

**Verificação:**
```bash
python manage.py test financeiro.tests.FaturaAGTModelTestCase
python manage.py test financeiro.tests.FaturaAGTViewsTestCase
# Esperado: todos os testes passam (OK)
```

---

### 12. Verificação Final em Ambiente de Produção-like

**O que fazer:** Teste final em ambiente similar a produção (SSL, domínio real, etc.).

**Passos:**
1. Deploiar em servidor de staging
2. Registar webhook callback URL em portal AGT (homologação ou produção)
3. Configurar AGT_CALLBACK_SECRET com token forte
4. Testar submissão → polling → notificação de callback
5. Validar SSL/HTTPS (callback é HTTPS)
6. Testar handling de erros de rede (timeout, 500, etc.)

**Esperado:**
- Fluxo completo funciona sem erros
- Callback recebe notificações e actualiza status
- Sem avisos de segurança no browser
- Logs são informativos

---

## Checklist de Deployment

Antes de deploiar para produção:

- [ ] AGT_CALLBACK_SECRET configurado com token forte (não default vazio)
- [ ] AGT_USERNAME e AGT_PASSWORD definidos (credenciais da AGT)
- [ ] Chaves privadas (AGT_SOFTWARE_PRIVATE_KEY, AGT_CONTRIBUTOR_PRIVATE_KEY) carregadas
- [ ] AGT_API_BASE apontando para produção (não homologação)
- [ ] AGT_CALLBACK_URL apontando para URL pública correcta
- [ ] Migrations aplicadas (`migrate financeiro`)
- [ ] Testes unitários passam (`test financeiro`)
- [ ] Dashboard carrega e exibe KPIs correctamente
- [ ] Multi-tenancy testado (sem vazamento de dados entre bancas)
- [ ] Callback pode receber notificações AGT (webhook acessível)
- [ ] HTTPS/SSL configurado para callback URL
- [ ] Logs monitorizados para erros de integração AGT

---

## Notas Finais

- **Iteração 2 Status**: Implementação completa e funcionando em produção
- **Review 2.1 Findings**: Todos os 3 findings foram endereçados na iteração 2
- **Próximos Passos**: Validar em produção, otimizar com base em usage real, expandir para outras entidades fiscais
- **Tech Debt**: Refactoring cosmético (escopo_fatura_agt) recomendado mas não bloqueante

---

## Ficheiros Envolvidos (Para Referência)

### Modelos
- `financeiro/models.py` — classe FaturaAGT

### Views
- `financeiro/views_agt.py` — 6 views + helpers

### Templates
- `financeiro/templates/financeiro/faturacao_agt_dashboard.html`
- `financeiro/templates/financeiro/faturacao_agt_lista.html`
- `financeiro/templates/financeiro/faturacao_agt_detalhe.html`

### Routing
- `financeiro/urls.py` — routes financeiro
- `sicdoa/urls.py` — rota do callback

### Migrations
- `financeiro/migrations/0045_fatura_agt.py`
- `financeiro/migrations/0046_faturaakt_gerar_numero.py`
- `financeiro/migrations/0047_faturaakt_add_request_id.py`

### Suporte
- `financeiro/agt_crypto.py` — assinaturas JWS
- `financeiro/acesso.py` — (recomendado adicionar escopo_fatura_agt)
- `templates/includes/sidebar.html` — menu item (já presente)
- `.env` — configurações obrigatórias

---

**Fim do Plano**
