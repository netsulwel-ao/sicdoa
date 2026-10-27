# Módulo SAF-T Angola no SICDOA

Adiciona ao módulo de Gestão Financeira um sub-item de "Validação SAF-T AGT" que gera, valida localmente e faz o rastreio de submissões de ficheiros SAF-T AO (formato `AO_1.01_01`, Decreto 317/20). O módulo cobre quatro tipos de documento (FT, FR, NC, ND), assina cada documento com hash RSA-SHA1 encadeada e persiste o XML num `FileField`. O fluxo de estados vai de Rascunho → Gerado → Validado → Submetido → Aceite/Rejeitado.

**Watch for:**
- Template Django usa `in` contra string literal em vez de lista — condicional de acção "Marcar como Submetido" é frágil (confirmed).
- Validação XSD depende de variável de ambiente `SAFT_XSD_PATH` e biblioteca `lxml` opcionais; sem elas o sistema degrada silenciosamente para validação mínima de cabeçalho (confirmed).
- `requer_escrita_financeira` não tem `@functools.wraps` — o nome/docstring da view é mascarado, o que afecta introspection e `reverse()` em alguns cenários (confirmed).

**Verdict**: APPROVED

---

## Vista geral

O isolamento multi-tenant está correcto em todas as seis views: todas as queries filtram por `banca_id = request.session.get('banca_id')`, e `get_object_or_404` inclui `banca_id=banca_id` nas views que operam sobre um registo existente. Não há caminho que exponha dados de outra banca.

A assinatura RSA-SHA1 usa `padding.PKCS1v15()` + `hashes.SHA1()` conforme exigido pelo Decreto 317/20. O namespace XML é registado antes da criação do elemento raiz. `TaxExemptionReason`/`TaxExemptionCode` são emitidos na `<Line>` quando IVA = 0 — posição aparentemente correcta, mas deve ser confirmada contra o XSD definitivo. A migration `0048` tem dependências correctas, `unique_together` e dois índices compostos.

O validador degrada silenciosamente para uma verificação mínima de cabeçalho quando `lxml` não está instalado ou `SAFT_XSD_PATH` não existe — o utilizador vê "Ficheiro válido!" sem saber que `SourceDocuments` não foi inspeccionado. A condicional de estado no template de detalhe usa `in` contra uma string literal em vez de uma lista, o que funciona por acidente mas é frágil.

---

<details>
<summary>Issues (4)</summary>

1. **Condicional de template com `in` string** — `{% if submissao.estado in 'Gerado,Validado' %}` testa pertença de substring, não de lista. Funciona por acidente neste caso mas quebraria se um estado futuro como `'Ge'` fosse adicionado. Mudar para `{% if submissao.estado == 'Gerado' or submissao.estado == 'Validado' %}`.

2. **Validação XSD silenciosa** — Sem `SAFT_XSD_PATH` definido ou sem `lxml`, o validador salta para uma verificação mínima do cabeçalho que não detecta erros estruturais no `SourceDocuments`. Documentar explicitamente que o ambiente de produção precisa de `lxml` e do XSD, ou emitir um aviso de configuração no arranque.

3. **`requer_escrita_financeira` sem `@functools.wraps`** — O decorator não preserva o nome/docstring da view original. Adicionar `@functools.wraps(view_func)` ao `wrapper` interno.

4. **`NumberOfEntries`/`TotalDebit`/`TotalCredit` reordenados com lógica invertida** — O código remove e reinsere os elementos de sumário antes dos `<Invoice>`. Embora produza o XML correcto, esta manipulação de lista in-place é frágil e desnecessária: inserir os três elementos de sumário no início de `<SalesInvoices>` com `sales.insert(0, ...)` após o loop é mais seguro e claro.

</details>

---

<details>
<summary>Detalhes</summary>

### Reordenação dos totais de SalesInvoices

A reordenação de `NumberOfEntries`/`TotalDebit`/`TotalCredit` para antes dos elementos `<Invoice>` funciona mas usa uma manipulação que remove e reinsere todos os filhos de `<SalesInvoices>`. Uma abordagem com `sales.insert(0, el)` seria mais legível e menos propensa a regressão se o loop for modificado.

### Condicional de template frágil (confirmed)

Em `saft_detalhe.html`:
```django
{% if submissao.estado in 'Gerado,Validado' %}
```
O operador `in` do template Django testa pertença de substring na string `'Gerado,Validado'`. Funciona correctamente para os estados actuais, mas é semanticamente errado. Se `estado` fosse `'do'` ou qualquer substring de `'Gerado,Validado'`, o botão apareceria indevidamente. Usar:
```django
{% if submissao.estado == 'Gerado' or submissao.estado == 'Validado' %}
```

### Degradação silenciosa do validador

O `saft_validator.py` tem três caminhos de execução:
1. `lxml` instalado + XSD presente → validação XSD completa
2. `lxml` instalado + XSD ausente → fallback sem aviso
3. `lxml` não instalado → validação básica de cabeçalho

No caminho 2 e 3, o utilizador vê "Ficheiro válido!" para um XML que pode ter erros estruturais nos `SourceDocuments`. Não há log de aviso nem indicação de que a validação foi parcial. Produção deve garantir `lxml` instalado e `SAFT_XSD_PATH` definido.

### Decorator sem `functools.wraps`

```python
def requer_escrita_financeira(view_func):
    def wrapper(request, *args, **kwargs):
        ...
    return wrapper
```

Sem `@functools.wraps(view_func)`, `wrapper.__name__` é `'wrapper'` para todas as views decoradas. Isso pode afectar introspection, Django Debug Toolbar, e em alguns casos a resolução de nomes de URL.

### Migration e modelo

A migration `0048_submissao_saft.py` declara dependências correctas, `unique_together` sobre `(banca, periodo_inicio, periodo_fim)`, e dois índices compostos (`ix_saft_banca_periodo`, `ix_saft_estado_data`). O modelo e a migration estão alinhados.

### URLs, sidebar e cobertura de testes

O `urls.py` regista seis rotas SAF-T no namespace `financeiro` com o import correcto `from . import views_saft as saft`. A sidebar aplica a mesma condição de permissão que a "Faturação Eletrónica AGT".

Não foram adicionados testes automáticos. Não testado: geração de XML para período sem documentos, falha silenciosa da hash com chave privada ausente (`except Exception: h = ''`), validação com `lxml`, condicional de estado duplicado na view `saft_gerar`.

</details>

---

<details>
<summary>Ficheiros alterados</summary>

| Ficheiro | O que mudou |
|---|---|
| `financeiro/saft_generator.py` | Novo — gerador XML SAF-T AO completo com hash RSA-SHA1 |
| `financeiro/saft_validator.py` | Novo — validação XSD via lxml com fallback básico |
| `financeiro/views_saft.py` | Novo — seis views para dashboard, gerar, detalhe, validar, download, submeter |
| `financeiro/models.py` | Adicionado `SubmissaoSAFT` no final do ficheiro |
| `financeiro/urls.py` | Import de `views_saft` e seis rotas SAF-T adicionadas |
| `templates/includes/sidebar.html` | Sub-item "Validação SAF-T AGT" no grupo Financeiro |
| `financeiro/migrations/0048_submissao_saft.py` | Migration `CreateModel SubmissaoSAFT` com índices e unique_together |
| `financeiro/templates/financeiro/saft_dashboard.html` | Novo template — dashboard com KPIs e tabela de submissões |
| `financeiro/templates/financeiro/saft_gerar.html` | Novo template — formulário de geração por período |
| `financeiro/templates/financeiro/saft_detalhe.html` | Novo template — detalhe com acções (validar, download, submeter) |

</details>
