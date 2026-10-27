# Faturação Eletrónica AGT — Interface de Utilizador

Módulo de administração, visualização e controlo da faturação eletrónica integrada com a Administração Geral Tributária (AGT) de Angola.

---

## 1. Visão Geral

O módulo **Faturação Eletrónica AGT** oferece uma interface web completa para:

- **Dashboard**: Visão geral com KPIs (faturas emitidas, rejeitadas, pendentes)
- **Listagem**: Pesquisa, filtros e paginação de faturas
- **Detalhe**: Visualização completa de uma fatura com status AGT e erros
- **Sincronização**: Polling do status de processamento junto à AGT
- **Administração Django**: Gestão de configurações fiscais, faturas, submissões e auditoria

Todos os dados são **isolados por banca** (multi-tenant).

---

## 2. Instalação e Configuração

### 2.1 Variáveis de Ambiente

```env
AGT_USERNAME=usuario_produtor
AGT_PASSWORD=senha_forte
AGT_PRODUCT_ID=SICDOA
AGT_PRODUCT_VERSION=1.0.0
AGT_SOFTWARE_VALIDATION_NUMBER=000/AGT/2026
AGT_API_BASE=https://sifphml.minfin.gov.ao/sigt/fe/v1
AGT_NIF_EMITENTE=5001234567
AGT_COMPANY_NAME=CDOA
AGT_SOFTWARE_PRIVATE_KEY_FILE=keys/agt_software_private.pem
AGT_CONTRIBUTOR_PRIVATE_KEY_FILE=keys/agt_contributor_private.pem
AGT_CALLBACK_SECRET=segredo_webhook
AGT_CALLBACK_URL=https://seu-dominio.com/api/facturacaoelectronica/callback
```

### 2.2 Setup Inicial

```bash
python manage.py migrate agt_invoicing
python manage.py check
```

---

## 3. Interface Web

### 3.1 Dashboard (`/financeiro/faturacao-eletronica/`)

- **KPI Cards**: Faturas emitidas, rejeitadas, pendentes
- **Tabela**: 5 faturas mais recentes
- **Webhook Info**: URL para callbacks

### 3.2 Listagem (`/financeiro/faturacao-eletronica/lista/`)

**Filtros**: estado, agt_status, search (número)  
**Paginação**: 20 por página

### 3.3 Detalhe (`/financeiro/faturacao-eletronica/<fatura_id>/`)

- Documento: número, tipo, cliente, totais
- Status AGT: status, hash, data processamento
- Erros: JSON formatado se houver rejeição
- Botões: Sincronizar, voltar

### 3.4 Sincronizar

**POST** `/financeiro/faturacao-eletronica/<fatura_id>/sincronizar/`

Resposta JSON:
```json
{
    "ok": true,
    "status": "APROVADA",
    "message": "Sincronização concluída"
}
```

---

## 4. Modelos de Dados

### Fatura
- `banca` (FK)
- `numero` (CharField, único)
- `estado` (RASCUNHO, PENDENTE_AGT, EMITIDA, REJEITADA)
- `cliente_nif`, `cliente_designacao`
- `total` (Decimal)
- `agt_request_id`, `agt_status`, `agt_erros`, `agt_hash_validacao`

### SubmissaoAgt
Rastreia tentativas de submissão (estado, tentativas, próxima_tentativa_em)

### ConfiguracaoFiscal
Config por banca (nif_emitente, integration_enabled, credenciais)

### RegistoAuditoria
Auditoria completa (ação, entity_tipo, origin_tipo, usuário, timestamp)

---

## 5. Administração Django

**URLs**:
- `/admin/agt_invoicing/configuracaofiscal/`
- `/admin/agt_invoicing/fatura/`
- `/admin/agt_invoicing/submissaoagt/`
- `/admin/agt_invoicing/registoauditoria/`

---

## 6. Multi-Tenant Scoping

Todas as views filtram por `banca_id` da sessão do utilizador. Acesso não autorizado retorna 404.

---

## 7. Sidebar Navigation

**Item**: "Faturação Eletrónica" → `/financeiro/faturacao-eletronica/`  
**Visibilidade**: Papel Despachante Oficial, Administrador, Super Administrador  
**Ícone**: `fa-landmark`

---

## 8. Autenticação

Decorador `@requer_sessao_ativa` em todas as views.

---

## 9. Troubleshooting

- **404**: Verifique se fatura pertence à sua banca
- **Status antigo**: Endpoint é placeholder; aguarde próxima versão com polling real
- **Erros em JSON**: Use console F12 do navegador
- **Edição pós-submissão**: Não permitido; crie Nota de Crédito

---

## 10. Próximas Versões

- Polling real da AGT
- Callbacks em tempo real
- Geração SAF-T (XML)
- Validação XSD local
- Relatórios com gráficos

---

## 11. Suporte

Contacte: `suporte@cdoangola.co.ao`
