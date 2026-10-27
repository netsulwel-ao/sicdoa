# Faturação Eletrónica AGT — módulo de gestão e submissão de faturas para a AGT

Este módulo adiciona ao SICDOA a capacidade de submeter faturas à Administração Geral Tributária angolana via e-Fatura, receber notificações de status por webhook, e acompanhar o ciclo de vida de cada fatura (Pendente → Processando → Validada/Rejeitada/Erro). A implementação cobre modelo de dados, seis views, URL routing, duas migrations, três templates e um novo item no sidebar. A iteração 2 resolveu o único bloqueante da iteração anterior (IntegrityError por `numero_fatura` em branco) com um `save()` override e uma migration de dados, e endereçou a ausência de autenticação no callback via verificação de token opcional. Watch for: o `save()` do modelo não tem o loop de retry por `IntegrityError` que todos os outros modelos do projeto usam — em alta concorrência pode lançar 500 (confirmado). O callback aceita qualquer POST sem autenticação enquanto `AGT_CALLBACK_SECRET` não estiver configurado em produção.

**Verdict**: APPROVED

---

## High-level view

O modelo `FaturaAGT` é um satélite de `FacturaCliente`, ligado por `OneToOneField`. O `save()` override gera `numero_fatura` no padrão `FAT-{ano}-{seq}` quando o campo está em branco, mas sem o loop de retry por `IntegrityError` que os outros modelos do projeto usam. Em produção com baixo volume este gap é improvável de disparar; em alta concorrência pode produzir um 500 silencioso. A migration 0046 trata registos legados com campo em branco antes de o constraint ser aplicado — a dependência na cadeia está correta.

As seis views seguem o padrão do projeto. `faturacao_agt_submeter` usa `get_or_create` seguido de save adicional, o que produz dois acessos à base de dados em vez de um para registos novos — é ineficiente mas não incorreto. `faturacao_agt_sincronizar` converte corretamente GET→POST; os templates usam `fetch` com CSRF token em vez de `<a href>`. O callback é `@csrf_exempt` com verificação condicional de `X-AGT-Secret`: quando a setting não está configurada, aceita qualquer POST — modo degradado documentado mas que constitui um deployment blocker se não for configurado antes de exposição pública.

O template de dashboard exibe um card "Status AGT" com valor hardcoded `+5%` — não vem do contexto, é texto fixo. Os outros três KPIs (`total_pendentes`, `total_emitidas`, `total_rejeitadas`) mapeiam corretamente para variáveis de contexto. O sidebar posiciona o item após Facturas e antes do separador de Conta Corrente, com guard de permissão e classe active correctas.

---

<details>
<summary>Issues (3)</summary>

1. **`save()` sem retry loop** — O `save()` de `FaturaAGT` não replica o padrão `for _attempt in range(5)` / catch `IntegrityError` que todos os outros modelos usam. Em alta concorrência, dois saves simultâneos com `numero_fatura` vazio podem gerar o mesmo número e o segundo lança `IntegrityError` não tratado (500). Adicionar o mesmo padrão de retry.

2. **KPI "Status AGT" hardcoded** — O segundo card do dashboard exibe `+5%` como texto fixo em vez de uma métrica real. Ou calcular um valor significativo (ex: taxa de validação do mês) e injetá-lo no contexto, ou remover o card para não exibir dados fictícios.

3. **`AGT_CALLBACK_SECRET` ausente em produção** — O callback aceita qualquer POST sem autenticação quando a setting não está configurada. Antes de expor `https://bejames.online/api/facturacaoelectronica/callback` publicamente, `AGT_CALLBACK_SECRET` deve ser definido em `settings.py` (ou via variável de ambiente). O código de verificação já existe — é um bloqueante de deployment.

</details>

---

<details>
<summary>Details</summary>

### `save()` sem retry no modelo FaturaAGT

Os modelos `FacturaCliente`, `ReciboCliente`, `NotaCredito`, `NotaDebito` e `FacturaRecibo` usam todos o mesmo padrão:

```python
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

O `save()` de `FaturaAGT` usa apenas:

```python
def save(self, *args, **kwargs):
    if not self.numero_fatura:
        self.numero_fatura = self._gerar_numero_fatura()
    super().save(*args, **kwargs)
```

Em dois saves concorrentes com campo em branco, `_gerar_numero_fatura()` pode retornar o mesmo número para ambos. O segundo `super().save()` lança `IntegrityError` não capturado, resultando em 500. Confirmado: o projeto inteiro usa o padrão retry; esta view é a única exceção. Severidade baixa em produção com volume típico mas é uma regressão face ao padrão do projeto.

### KPI "Status AGT" hardcoded no dashboard

O segundo card no template `faturacao_agt_dashboard.html` exibe literalmente `+5%` como texto fixo:

```html
<p class="text-lg font-bold text-blue-600">+5%</p>
```

Esta métrica não está no contexto da view (`faturacao_agt_dashboard` não passa nenhuma variável de taxa ou percentagem). O card exibe dados fictícios para qualquer utilizador, o que pode confundir operadores que esperem um valor real. Os outros três KPIs estão corretos.

### Callback: modo degradado sem autenticação

Quando `settings.AGT_CALLBACK_SECRET` não está definida, o callback regista um aviso mas aceita o POST:

```python
secret = getattr(settings, 'AGT_CALLBACK_SECRET', None)
if secret:
    received_token = request.headers.get('X-AGT-Secret', '')
    if received_token != secret:
        return JsonResponse({'status': 'error', 'detail': 'Unauthorized'}, status=401)
else:
    logger.warning("AGT_CALLBACK_SECRET não configurado — callback aceite sem autenticação.")
```

Qualquer actor que conheça a URL pública pode manipular o status de qualquer `FaturaAGT` com `agt_id` conhecido. O código de verificação está implementado e correto — o risco é puramente de deployment. Confirmado como deployment blocker na verificação anterior; endereçado na documentação mas não configurado no `settings.py` rastreado.


</details>

---

<details>
<summary>File map</summary>

| Ficheiro | O que mudou |
|---|---|
| `financeiro/models.py` | Novo modelo `FaturaAGT` com campos AGT, generator `_gerar_numero_fatura()`, `save()` override |
| `financeiro/views_agt.py` | Seis novas views: dashboard, lista, detalhe, submeter, sincronizar, callback |
| `financeiro/urls.py` | Import `views_agt as agt`; 6 novas rotas sob `faturacao-agt/` e `api/facturacaoelectronica/callback` |
| `financeiro/migrations/0045_fatura_agt.py` | Cria tabela `financeiro_fatura_agt` com todos os campos e índices |
| `financeiro/migrations/0046_faturaakt_gerar_numero.py` | `RunPython` que preenche `numero_fatura` em branco em registos legados |
| `financeiro/templates/financeiro/faturacao_agt_dashboard.html` | Dashboard com KPIs, tabela de últimas 5 faturas, info box de webhook |
| `financeiro/templates/financeiro/faturacao_agt_lista.html` | Lista paginada com filtros por status e busca |
| `financeiro/templates/financeiro/faturacao_agt_detalhe.html` | Detalhe da fatura com dados AGT, hash, QR code, resposta raw |
| `templates/includes/sidebar.html` | Novo item "Faturação Eletrónica AGT" após Facturas, antes do separador de Conta Corrente |

[Ver diff completo: `git diff main -- financeiro/models.py financeiro/views_agt.py financeiro/urls.py`]

</details>
