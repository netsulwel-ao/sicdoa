# 🔍 Debug - Auto-Preenchimento de Processo Aduaneiro

## Problema Identificado

**Ao selecionar um processo aduaneiro, os dados não estão sendo carregados nos campos.**

---

## ✅ Correções Implementadas

### 1. API de Dados do Processo (`api_dados_processo`)

#### ❌ ANTES (Problema):
```python
filtro['despachante_id'] = usuario_id  # Campo não existe!
```

#### ✅ DEPOIS (Corrigido):
```python
filtro['usuario_id'] = usuario_id  # Campo correto do modelo
```

### 2. Prioridade de Dados

O modelo `DeclaracaoUnica` tem dados em dois lugares:
- **`dados_json`** - JSON serializado (campo novo)
- **Campos diretos** - Campos do modelo (antigos)

#### ✅ Nova Lógica:
```python
# Prioridade: dados_json → campo direto
'numero_bl_awb': (
    dados_dict.get('numero_bl_awb') or 
    getattr(processo, 'numero_bl_awb', '') or 
    ''
)
```

### 3. Mapeamento de Campos

Alguns campos do formulário têm nomes diferentes no modelo:

| Campo Formulário | Campo Modelo | Alternativa |
|------------------|--------------|------------|
| `origem` | `pais_origem` | `origem` (em dados_json) |
| `destino` | `porto_desembarque` | `destino` (em dados_json) |
| `mercadoria_descricao` | `descricao_mercadoria` | `mercadoria_descricao` (em dados_json) |
| `quantidade_volumes` | `quantidade` | `quantidade_volumes` (em dados_json) |

### 4. Tratamento de Erros

Adicionado logging completo:

```python
# No Python (views.py)
import traceback
traceback.print_exc()
print(f'Processo: {processo.id}, Dados: {dados_dict}')

# No JavaScript (template)
console.log('✅ Dados do processo carregados:');
console.log(p);
```

---

## 🧪 Como Testar

### Passo 1: Abrir Console do Navegador
1. Pressionar `F12` ou `Ctrl+Shift+I`
2. Ir para aba "Console"
3. Manter console aberto enquanto testa

### Passo 2: Criar Requisição
1. Abrir `/financeiro/requisicoes/criar/`
2. **Verificar Console**: Deve ver `✅ Instituição carregada automaticamente`

### Passo 3: Selecionar Cliente
1. Clicar no dropdown de Cliente
2. Selecionar um cliente
3. **Verificar Console**: Deve ver `✅ Filtrando processos para: [nome cliente]`
4. **Verificar Console**: Deve ver `✅ Total encontrado: X processo(s)`

### Passo 4: Selecionar Processo
1. Clicar no dropdown de Processo
2. Selecionar um processo
3. **Verificar Console**: Deve aparecer objeto com dados:
   ```javascript
   {
     id: 123,
     numero_du: "DU-2026-000001",
     numero_bl_awb: "BL-123-ABC",
     meio_transporte: "Navio",
     origem: "Xangai, China",
     ...
   }
   ```

### Passo 5: Verificar Campos
- [ ] Campo "B/L / AWB" preenchido?
- [ ] Campo "Transporte" preenchido?
- [ ] Campo "Origem" preenchido?
- [ ] Campo "Destino" preenchido?
- [ ] Badge verde "Auto-preenchido" apareceu na Seção 3?
- [ ] Toast verde com mensagem apareceu?

---

## 🐛 Se Ainda Não Funcionar

### Verificar no Console:

#### 1. Erro de Permissão?
```
❌ Processo não encontrado ou sem permissão de acesso
```
**Solução**: Verificar se processo foi criado pelo utilizador logado

#### 2. Erro de API?
```javascript
// No console, fazer teste manual:
fetch('/financeiro/api/dados-processo/?processo_id=123')
  .then(r => r.json())
  .then(d => console.log(d))
```

#### 3. Verificar Banco de Dados:
```python
# No Django shell:
python manage.py shell

from aduaneiro.models import DeclaracaoUnica
from clientes.models import Cliente

# Verificar se processo existe
du = DeclaracaoUnica.objects.get(id=123)
print(du.exportador_nome)
print(du.dados_json)

# Verificar se cliente existe
cliente = Cliente.objects.get(id=456)
print(cliente.nome)
```

#### 4. Comparar Nomes:
```python
# No Django shell:
du = DeclaracaoUnica.objects.get(id=123)
cliente = Cliente.objects.get(id=456)

print(f"DU exportador: '{du.exportador_nome}'")
print(f"Cliente nome:  '{cliente.nome}'")
print(f"Match exato: {du.exportador_nome == cliente.nome}")
print(f"Match case-insensitive: {du.exportador_nome.lower() == cliente.nome.lower()}")
```

---

## 📊 Resposta Esperada da API

```json
{
  "success": true,
  "processo": {
    "id": 123,
    "numero_du": "DU-2026-000001",
    "ref_despachante": "REF-2024-ABC",
    "exportador_nome": "Cliente XYZ",
    "destinatario_nome": "Destinatário ABC",
    "status": "Submetida",
    "numero_bl_awb": "BL-2026-ABC-123",
    "meio_transporte": "Navio",
    "origem": "Xangai, China",
    "destino": "Porto de Luanda",
    "mercadoria_descricao": "Peças de reposição",
    "peso_bruto_kg": "5000",
    "peso_liquido_kg": "4800",
    "cbm_metros_cubicos": "25.5",
    "quantidade_volumes": "100",
    "valor_cif": "250000",
    "nome_banco": "BPC",
    "termo_pagamento": "LC"
  }
}
```

---

## 🔧 Campos da API Retornados

| Campo | Origem | Tipo |
|-------|--------|------|
| `id` | Direct | int |
| `numero_du` | Direct | str |
| `ref_despachante` | Direct | str |
| `exportador_nome` | Direct | str |
| `destinatario_nome` | Direct | str |
| `status` | Direct | str |
| `numero_bl_awb` | JSON \| Direct | str |
| `meio_transporte` | JSON \| Direct | str |
| `origem` | JSON \| `pais_origem` | str |
| `destino` | JSON \| `porto_desembarque` | str |
| `mercadoria_descricao` | JSON \| `descricao_mercadoria` | str |
| `peso_bruto_kg` | JSON \| `peso_bruto` | str |
| `peso_liquido_kg` | JSON \| `peso_liquido` | str |
| `cbm_metros_cubicos` | JSON only | str |
| `quantidade_volumes` | JSON \| `quantidade` | str |
| `valor_cif` | Direct | str |
| `nome_banco` | JSON \| Direct | str |
| `termo_pagamento` | JSON \| Direct | str |

---

## 📋 Checklist de Debugging

- [ ] Console F12 aberto?
- [ ] Mensagens aparecem no console?
- [ ] Dados retornam da API (check Network tab)?
- [ ] Campos do formulário têm os IDs corretos?
  - [ ] `id_numero_bl_awb`
  - [ ] `id_meio_transporte`
  - [ ] `id_origem`
  - [ ] `id_destino`
  - [ ] `id_mercadoria_descricao`
  - [ ] `id_peso_bruto_kg`
  - [ ] `id_peso_liquido_kg`
  - [ ] `id_cbm_metros_cubicos`
  - [ ] `id_quantidade_volumes`
  - [ ] `id_valor_cif`
  - [ ] `id_banco`
  - [ ] `id_termo_pagamento`
- [ ] Permissões do utilizador OK?
- [ ] Cliente e Processo pertencem ao mesmo utilizador?

---

## 📞 Próximos Passos

1. **Testar com Console Aberto** - Seguir os passos acima
2. **Capturar Logs** - Enviar prints do console
3. **Testar API Direto** - GET `/financeiro/api/dados-processo/?processo_id=X`
4. **Verificar BD** - Confirmar dados no banco de dados

---

## 📝 Arquivos Modificados

✅ `/financeiro/views.py` - API corrigida  
✅ `/financeiro/templates/financeiro/requisicao_fundo_form.html` - JavaScript melhorado

---

**Data**: Julho 2026  
**Status**: 🟢 Implementado e Debugável
