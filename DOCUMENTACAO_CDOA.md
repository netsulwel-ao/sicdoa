# Documentação Completa do Sistema CDOA

**SICDOA** — Sistema de Informação da Câmara dos Despachantes Oficiais de Angola

---

# Índice

1. [Visão Geral](#1-visão-geral)
2. [Módulo: DU (Declaração Única / Aduaneiro)](#2-módulo-du-declaração-única--aduaneiro)
3. [Módulo: Governança (Assembleias, Votações, Consultas Públicas)](#3-módulo-governança)
4. [Módulo: Quotas (Gestão Financeira)](#4-módulo-quotas-gestão-financeira)
5. [Módulo: RH (Recursos Humanos)](#5-módulo-rh-recursos-humanos)
6. [Módulo: Clientes](#6-módulo-clientes)
7. [Módulo: Perfil e Sessão](#7-módulo-perfil-e-sessão)
8. [Telas e URLs por Perfil](#8-telas-e-urls-por-perfil)
9. [Anexos Técnicos](#9-anexos-técnicos)

---

# 1. Visão Geral

O CDOA é um sistema multi-módulo que oferece:

- **Gestão de Declarações Aduaneiras (DU)** — para despachantes submeterem declarações
- **Governança Digital** — assembleias virtuais, votações online, consultas públicas, convocatórias, atas digitais
- **Gestão Financeira (Quotas)** — cobrança de quotas mensais, pagamentos online, certidões de regularidade
- **Recursos Humanos** — gestão de colaboradores, salários, subsídios, presenças, férias, avaliações, recrutamento
- **Gestão de Clientes** — registo de clientes associados a cada despachante

**Perfis de utilizador:**
| Perfil | Acesso |
|--------|--------|
| **Administrador** | Acesso total a todos os módulos |
| **Despachante Oficial** | DU, Governança (votar, consultas), Clientes, Quotas (pagar), RH (se gestor) |
| **Operador** | DU limitado, Clientes |
| **Visualizador** | Apenas consulta |

---

# 2. Módulo: DU (Declaração Única / Aduaneiro)

**App:** `aduaneiro`
**URL base:** `/du/`

## 2.1 O que é possível fazer

### Criar / Editar DU
- **URL:** `/du/` (nova) ou `/du/<uuid>/` (editar)
- Formulário completo com todos os campos de uma declaração aduaneira:
  - Informação do declarante (NIF, nome, endereço)
  - Regime aduaneiro
  - Código pautal com consulta à pauta
  - Descrição da mercadoria, quantidades, pesos
  - Valores (FOB, frete, seguro, CIF)
  - Impostos (direitos aduaneiros, IVA, imposto consumo, emolumentos)
  - Origem e transporte (país origem, portos, meio transporte)
  - Cliente associado (com criação rápida de novo cliente)
- **Campos calculados automaticamente:** valor CIF, totais de impostos, total geral
- **Ações:** Guardar como rascunho ou Submeter

### Listar DU
- **URL:** `/du/lista/`
- Tabela paginada com filtros por status e barra de pesquisa
- Status: Rascunho, Submetida, Em Análise, Aprovada, Rejeitada

### Ver Detalhe
- **URL:** `/du/<uuid>/ver/`
- Visualização completa da declaração

### Exportar PDF
- **URL:** `/du/<uuid>/pdf/`
- Gera PDF com todos os detalhes da declaração (ReportLab)

### Apagar DU
- **URL:** `/du/<uuid>/apagar/`
- Apenas Administrador

### Alterar Status
- **URL:** `/du/<uuid>/status/`
- Apenas Administrador — aprovar/rejeitar/submeter

### Consultar Pauta Aduaneira
- **URL:** `/du/pauta/`
- Consulta de códigos pautais

### Pesquisar DU por API
- **URL:** `/du/pesquisar/`
- Autocomplete/busca de declarações

## 2.2 Como usar

1. Aceda a `/du/`
2. Preencha o formulário (campos obrigatórios marcados)
3. Use "Buscar Cliente" para associar um cliente existente ou "Criar Cliente Rápido"
4. Clique "Guardar Rascunho" para salvar sem submeter
5. Clique "Submeter" para enviar a declaração
6. Acompanhe o status em `/du/lista/`
7. Administradores podem aprovar/rejeitar em `/du/<uuid>/status/`

---

# 3. Módulo: Governança

**App:** `governanca`
**URL base:** `/governanca/`

## 3.1 Dashboard de Governança
- **URL:** `/governanca/`
- Estatísticas: total de assembleias, quotas pendentes/pagas, notificações não lidas
- Links rápidos para todas as funcionalidades

## 3.2 Assembleias

### Listar Assembleias
- **URL:** `/governanca/assembleias/`
- Tabela paginada com filtro por estado (Agendada, Em Curso, Concluída, Cancelada)
- Botões: Criar (Admin), Ver detalhe, Gerir (Admin)

### Criar Assembleia
- **URL:** `/governanca/assembleia/nova/`
- **Quem:** Apenas Administrador
- Campos: título, descrição, data/hora, local, link streaming, quórum mínimo, max procurações
- Opção "Iniciar automaticamente após criar"

### Detalhe da Assembleia
- **URL:** `/governanca/assembleia/<pk>/`
- Informações: status, data, quórum, membros da mesa, pautas, documentos
- **Ações disponíveis (dependendo do status/perfil):**
  - ✅ **Sala da Assembleia** — entrar na sala virtual (vídeo, chat, votações)
  - ✅ **Gerir** — gestão completa (Admin)
  - ✅ **Convocatórias** — criar e gerir convocatórias (Admin)
  - ✅ **Confirmar Presença** — RSVP
  - ✅ **Ver Resultados** — após encerramento
  - ✅ **Exportar** — PDF, Excel, CSV dos resultados
  - ✅ **Logs** — auditoria (Admin)
  - ✅ **Ata Digital** — assinar e publicar

### Editar Assembleia
- **URL:** `/governanca/assembleia/<pk>/editar/`
- **Quem:** Apenas Administrador
- Editar dados, adicionar/remover pautas

### Gerir Assembleia (Painel Admin)
- **URL:** `/governanca/assembleia/<pk>/gerir/`
- **Quem:** Apenas Administrador
- **Ações disponíveis:**
  - **Iniciar Assembleia** — abre a sessão
  - **Concluir Assembleia** — encerra e gera manifesto de integridade
  - **Cancelar Assembleia**
  - **Pautas:**
    - Iniciar votação de uma pauta
    - Encerrar votação
    - Reabrir votação (apaga votos anteriores)
    - Ver resultados
  - **Mesa da Assembleia:**
    - Adicionar membro (Presidente, Vice-Presidente, Secretário, Vogal)
    - Remover membro
  - **Presenças:** ver lista de presentes
  - **Procurações:** ver lista de delegações de voto
  - **Documentos:**
    - Upload de documento (ata, relatório, outro)
    - Publicar documento (notifica despachantes)
    - Remover documento
  - **Ata Digital:**
    - Assinar ata (Presidente, Secretário)
    - Publicar ata

### Sala da Assembleia (Ao Vivo)
- **URL:** `/governanca/assembleia/<pk>/sala/`
- **Quem:** Todos os envolvidos na assembleia
- Layout com:
  - **Streaming/LiveKit:** transmissão de vídeo/áudio em tempo real
  - **Presentes:** lista de participantes com indicadores áudio/vídeo
  - **Chat:** mensagens de texto e reações (👍 mão, 👏 palmas, ❤️ coração)
  - **Pautas e Votação:** votar nas pautas abertas
  - **Procurações:** delegar voto a outro despachante (com código OTP)
  - **Controlo Admin:** iniciar/encerrar votações, gerir participantes (mute/câmara), gerir mesa
  - **Modo Popup:** `?popup=1` para janela flutuante (apenas vídeo + voto)

### Votação nas Assembleias

**Tipos de voto:** Favor, Contra, Abstenção
**Modalidades:** Aberta (visível) ou Secreta (encriptada)
**Fluxo:**
1. Admin abre votação numa pauta
2. Presentes votam (com opção de voto delegado via procuração)
3. Admin encerra votação
4. Resultados são apurados automaticamente
5. Cada voto gera um recibo hash para verificação
6. Sistema gera manifesto de integridade consolidado no encerramento

### Procuração (Delegação de Voto)
- **URL:** na sala da assembleia
- **Fluxo:**
  1. Outorgante (quem delega) solicita procuração para um outorgado
  2. Sistema gera código OTP
  3. Outorgado confirma com o código OTP
  4. Voto do outorgado conta também como voto do outorgante
- **Limite:** max_procuracao definido na assembleia (padrão: 3)

### Chat da Assembleia
- Mensagens em tempo real via WebSocket
- Suporta reações: levantar mão, palmas, coração
- Admin pode silenciar/remover áudio/vídeo dos participantes

### Convocatórias
- **URL:** `/governanca/assembleia/<pk>/convocatorias/`
- **Criar:** `/governanca/assembleia/<pk>/convocatoria/nova/`
- **Quem:** Apenas Administrador
- **Fluxo:**
  1. Criar convocatória (título, descrição, prazo confirmação, documento PDF)
  2. Fica como **Rascunho**
  3. Clicar **Publicar** — notifica todos os Despachantes
  4. Despachantes recebem notificação e podem clicar "Confirmar Receção"

### Documentos da Assembleia
- Upload de documentos (PDF) — atas, relatórios, anexos
- Publicar documento — notifica todos os despachantes
- Download do documento original
- Organizado por tipo: Ata, Relatório, Outro

### Atas Digitais
- Assinatura digital pelo Presidente e Secretário
- Fluxo de assinatura: Pendente → Aguardando Presidente → Aguardando Secretário → Assinada → Publicada
- Geração de PDF da ata
- Integridade garantida por hash de assinatura

### Logs/Auditoria
- **URL:** `/governanca/assembleia/<pk>/logs/`
- **Quem:** Apenas Administrador
- Registo cronológico de todas as ações na assembleia
- Inclui: quem fez, o que fez, quando, IP

### Exportar Resultados
- **Formatos:** PDF, Excel (XLSX), CSV
- Inclui: resultados de todas as pautas, lista de presenças, dados da assembleia

### Repositório de Atas
- **URL:** `/governanca/atas/`
- Atas publicadas de todas as assembleias
- Pesquisa e paginação

## 3.3 Consultas Públicas

### Listar Consultas
- **URL:** `/governanca/consultas/`
- Filtro por status: Rascunho, Publicada, Em Votação, Encerrada, Aprovada, Rejeitada

### Criar Consulta
- **URL:** `/governanca/consulta/nova/`
- **Quem:** Apenas Administrador
- Campos: título, descrição, documento (PDF), prazo
- Adicionar artigos com título e conteúdo

### Detalhe da Consulta
- **URL:** `/governanca/consulta/<pk>/`
- **Ações disponíveis:**
  - Comentar nos artigos
  - Responder a comentários
  - Votar (Favor/Contra/Abstenção)
  - **Admin:** Publicar, Abrir votação, Encerrar, Gerar relatório, Publicar versão final, Rejeitar

### Editar Consulta
- **URL:** `/governanca/consulta/<pk>/editar/`
- **Quem:** Apenas Administrador (apenas em estado Rascunho)

### Relatório
- **URL:** `/governanca/consulta/<pk>/relatorio/`
- Resultados da votação, histórico de comentários
- Download de PDF

## 3.4 Notificações
- **URL:** `/governanca/notificacoes/`
- Lista de notificações do sistema com paginação
- Marcar como lida (individual ou todas)
- **Tipos de notificação:** convocatoria_publicada, assembleia_iniciada, documento_publicado, votacao_aberta, etc.

---

# 4. Módulo: Quotas (Gestão Financeira)

**App:** `governanca.quotas`
**URL base:** `/governanca/quotas/`

## 4.1 Para Despachantes

### Dashboard Financeiro
- **URL:** `/governanca/quotas/`
- Visão geral: estado financeiro (Regular/Irregular/Suspenso), quotas pendentes e pagas
- Tabela de quotas mensais com status

### Faturas
- **URL:** `/governanca/quotas/faturas/`
- Lista de faturas emitidas
- Pagamento online (Multicaixa Express ou Transferência IBAN)
- Upload de comprovativo

### Detalhe da Fatura
- **URL:** `/governanca/quotas/fatura/<uuid>/`
- Detalhes completos da quota
- Opções de pagamento
- **Admin:** Marcar como paga manualmente

### Certidão de Regularidade
- **URL:** `/governanca/quotas/certidao/`
- Emitir certidão se estado financeiro for Regular
- Download de PDF
- Código único de verificação

### Carteira Profissional
- **URL:** `/governanca/quotas/carteira/`
- Visualizar carteira profissional
- Solicitar renovação

## 4.2 Para Administradores

### Dashboard Admin
- **URL:** `/governanca/quotas/admin/`
- Estatísticas: total de quotas, taxas de pagamento, valores recebidos
- Busca de membros e definição de estado financeiro
- Gráfico de pagamentos por mês

### Gestão de Pagamentos
- **URL:** `/governanca/quotas/admin/pagamentos/`
- Lista de pagamentos pendentes de aprovação
- Confirmar ou rejeitar pagamentos com comprovativo

### Configuração de Quotas
- **URL:** `/governanca/quotas/admin/config/`
- Definir valor da quota por mês/ano
- Data de vencimento

### Marcar Quota como Paga
- **URL:** via API (admin)
- Marcar manualmente uma quota como paga (para pagamentos offline)

### Definição de Estado Financeiro
- **URL:** via API (admin)
- Alterar estado: Regular, Irregular, Suspenso

### Geração Automática de Quotas
- **Comando:** `python manage.py gerar_quotas [--mes M] [--ano A] [--force]`
- Gera quotas mensais para todos os despachantes ativos
- Atualiza estado financeiro para Irregular
- Envia notificações e emails

---

# 5. Módulo: RH (Recursos Humanos)

**App:** `rh`
**URL base:** `/rh/`

## 5.1 Banca (Empresa do Despachante)

### Dashboard da Banca
- **URL:** `/rh/banca/`
- Visão geral da sua empresa

### Criar / Editar Banca
- **URL:** `/rh/banca/criar/` ou `/rh/banca/editar/`
- Dados: nome, NIF, tipo (Singular/Sociedade/SA), contacto, endereço, licença CDOA, logo
- Associada ao despachante logado

### Filiais
- **URL:** `/rh/filiais/nova/`, `/rh/filiais/<pk>/`, `/rh/filiais/<pk>/editar/`
- Gestão de filiais/escritórios
- Atribuir gestor de filial

## 5.2 Colaboradores

### Listar Colaboradores
- **URL:** `/rh/colaboradores/`
- Tabela com pesquisa e filtros

### Criar / Editar
- **URL:** `/rh/colaboradores/novo/` ou `/rh/colaboradores/<pk>/editar/`
- Dados: nome, BI, NIF, género, data nascimento, cargo, departamento, salário base
- Envio automático de credenciais por email

### Documentos
- Upload de documentos (CV, declarações, certificados)
- Download e remoção

## 5.3 Processamento Salarial

### Listar Processamentos
- **URL:** `/rh/salarios/`

### Criar Processamento
- **URL:** `/rh/salarios/novo/`
- Selecionar mês/ano
- Inclui subsídios configurados
- Gera recibos individuais

### Detalhe do Processamento
- **URL:** `/rh/salarios/<pk>/`
- Ver recibos de cada colaborador
- Download de PDF

### Subsídios
- **URL:** `/rh/subsidios/`
- Configurar: nome, tipo (Fixo/Percentual/Dias Trabalho/Dependentes), valor
- Ativar/desativar subsídios

## 5.4 Presenças

### Listar Presenças
- **URL:** `/rh/presencas/`
- Registo diário: entrada, saída, horas extras, faltas

### Registrar Presença
- **URL:** `/rh/presencas/registar/`
- Aprovar/rejeitar registos

## 5.5 Férias

### Pedir Férias
- **URL:** `/rh/ferias/pedir/`
- Data início, data fim, motivo
- Aprovação pelo gestor

## 5.6 Avaliações de Desempenho

### Ciclos de Avaliação
- **URL:** `/rh/avaliacoes/`
- Criar ciclo: nome, período, estado

### Avaliar Colaborador
- Critérios: pontualidade, produtividade, qualidade trabalho, trabalho em equipa, iniciativa
- Nota global e plano de desenvolvimento

## 5.7 Recrutamento

### Vagas
- **URL:** `/rh/recrutamento/`
- Criar vaga com descrição, requisitos, salário
- Link público para candidatura externa

### Candidaturas
- **URL:** `/rh/recrutamento/<vaga_pk>/candidaturas/`
- Gerir status: Recebida, Em Análise, Entrevista, Aprovado, Rejeitado

### Entrevistas
- Agendar entrevista (presencial, online, telefónica)
- Registar resultado e notas

### Integração (Onboarding)
- Criar plano de integração com tarefas
- Acompanhar progresso

## 5.8 Admin CDOA

### Gestão de Despachantes
- **URL:** `/rh/admin/despachantes/`
- Listar, criar, editar, ativar/desativar despachantes
- Enviar credenciais por email

### Gestão de Bancas
- **URL:** `/rh/admin/bancas/`
- Listar, ver detalhe, ativar/desativar bancas

---

# 6. Módulo: Clientes

**App:** `clientes`
**URL base:** `/clientes/`

## 6.1 O que é possível fazer

### Listar Clientes
- **URL:** `/clientes/`
- Tabela com pesquisa por nome/NIF
- Filtrados por utilizador (cada despachante vê apenas os seus)

### Criar Cliente
- **URL:** `/clientes/criar/`
- Campos: nome, NIF (único), localização, telefone, email, observações

### Ver Detalhe
- **URL:** `/clientes/<pk>/`
- Informações completas do cliente

### Editar Cliente
- **URL:** `/clientes/<pk>/editar/`

### Excluir Cliente
- **URL:** `/clientes/<pk>/excluir/`

---

# 7. Módulo: Perfil e Sessão

**App:** `users`
**URL base:** `/perfil/`

## 7.1 Meu Perfil
- **URL:** `/perfil/`
- Ver dados pessoais
- Editar nome, username, telefone
- Alterar password

## 7.2 Sessão
- A sessão expira após 2 horas de inatividade
- Extensão automática via AJAX (renovação silenciosa)
- Ao expirar: redireciona para login ou retorna erro 401 para chamadas AJAX

## 7.3 Login
- **URL:** `/login/`
- Autenticação com username/email + password (bcrypt)
- Suporte a SSO via portal externo em `/login-portal/`

---

# 8. Telas e URLs por Perfil

## Administrador
| Funcionalidade | URL |
|---|---|
| Dashboard | `/dashboard/` |
| Governança | `/governanca/` |
| Criar Assembleia | `/governanca/assembleia/nova/` |
| Gerir Assembleia | `/governanca/assembleia/<pk>/gerir/` |
| Sala Assembleia | `/governanca/assembleia/<pk>/sala/` |
| Convocatórias | `/governanca/assembleia/<pk>/convocatorias/` |
| Consultas | `/governanca/consultas/` |
| Criar Consulta | `/governanca/consulta/nova/` |
| Quotas Admin | `/governanca/quotas/admin/` |
| Pagamentos | `/governanca/quotas/admin/pagamentos/` |
| Config Quotas | `/governanca/quotas/admin/config/` |
| DU | `/du/` |
| DU Lista | `/du/lista/` |
| RH Admin | `/rh/admin/despachantes/` |
| Bancas | `/rh/admin/bancas/` |
| Clientes | `/clientes/` |
| Repositório Atas | `/governanca/atas/` |
| Notificações | `/governanca/notificacoes/` |
| Perfil | `/perfil/` |

## Despachante Oficial
| Funcionalidade | URL |
|---|---|
| Dashboard | `/dashboard/` |
| DU (Declarações) | `/du/` |
| Lista DU | `/du/lista/` |
| Assembleias | `/governanca/assembleias/` |
| Sala Assembleia | `/governanca/assembleia/<pk>/sala/` |
| Consultas | `/governanca/consultas/` |
| Quotas | `/governanca/quotas/` |
| Faturas | `/governanca/quotas/faturas/` |
| Certidão | `/governanca/quotas/certidao/` |
| Carteira | `/governanca/quotas/carteira/` |
| RH (se gestor) | `/rh/banca/` |
| Colaboradores | `/rh/colaboradores/` |
| Clientes | `/clientes/` |
| Notificações | `/governanca/notificacoes/` |
| Perfil | `/perfil/` |

## Operador / Visualizador
| Funcionalidade | URL |
|---|---|
| DU | `/du/` |
| Lista DU | `/du/lista/` |
| Clientes | `/clientes/` |
| Perfil | `/perfil/` |

---

# 9. Anexos Técnicos

## 9.1 Comandos Úteis (Terminal)

```bash
# Gerar quotas mensais
python manage.py gerar_quotas --mes 5 --ano 2026

# Forçar regeneração
python manage.py gerar_quotas --mes 5 --ano 2026 --force

# Limpar sessões expiradas
python limpar_sessoes.py

# Agendar quotas no Windows (PowerShell)
.\agendar_quotas.ps1
```

## 9.2 APIs Principais

### Assembleias
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/governanca/api/assembleia/<pk>/iniciar/` | Iniciar assembleia |
| POST | `/governanca/api/assembleia/<pk>/concluir/` | Concluir assembleia |
| POST | `/governanca/api/assembleia/<pk>/cancelar/` | Cancelar assembleia |
| POST | `/governanca/api/pauta/<pk>/iniciar-votacao/` | Abrir votação |
| POST | `/governanca/api/pauta/<pk>/encerrar-votacao/` | Encerrar votação |
| POST | `/governanca/api/pauta/<pk>/reabrir-votacao/` | Reabrir votação |
| POST | `/governanca/api/pauta/<pk>/votar/` | Votar |
| GET | `/governanca/api/pauta/<pk>/resultados/` | Resultados |
| GET | `/governanca/api/pauta/<pk>/verificar/` | Verificar voto |
| POST | `/governanca/api/assembleia/<pk>/registar-presenca/` | Registar presença |
| POST | `/governanca/api/assembleia/<pk>/responder-presenca/` | RSVP |
| POST | `/governanca/api/assembleia/<pk>/solicitar-procuracao/` | Solicitar procuração |
| POST | `/governanca/api/assembleia/<pk>/confirmar-procuracao/` | Confirmar procuração |
| POST | `/governanca/api/ata/<pk>/assinar/` | Assinar ata |
| POST | `/governanca/api/assembleia/<pk>/publicar-ata/` | Publicar ata |

### Documentos
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/governanca/api/assembleia/<pk>/documentos/upload/` | Upload documento |
| GET | `/governanca/api/assembleia/<pk>/documentos/listar/` | Listar documentos |
| POST | `.../documentos/<doc_pk>/publicar/` | Publicar documento |
| POST | `.../documentos/<doc_pk>/remover/` | Remover documento |

### Mesa
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/governanca/api/assembleia/<pk>/mesa/adicionar/` | Adicionar membro |
| POST | `/governanca/api/assembleia/<pk>/mesa/remover/<pk>/` | Remover membro |

### Convocatórias
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/governanca/api/convocatoria/<pk>/publicar/` | Publicar convocatória |
| POST | `/governanca/api/convocatoria/<pk>/confirmar-rececao/` | Confirmar receção |

### Consultas Públicas
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/governanca/api/consulta/<pk>/publicar/` | Publicar consulta |
| POST | `/governanca/api/consulta/<pk>/comentar/` | Comentar |
| POST | `/governanca/api/consulta/<pk>/abrir-votacao/` | Abrir votação |
| POST | `/governanca/api/consulta/<pk>/votar/` | Votar |
| POST | `/governanca/api/consulta/<pk>/encerrar/` | Encerrar |
| POST | `/governanca/api/consulta/<pk>/relatorio/` | Gerar relatório |

### Quotas
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/governanca/quotas/api/pagar/<fatura_uuid>/` | Pagar quota |
| POST | `/governanca/quotas/api/pagamento/<pk>/confirmar/` | Confirmar pagamento |
| POST | `/governanca/quotas/api/emitir-certidao/` | Emitir certidão |
| GET | `/governanca/quotas/api/estado/` | Estado financeiro |
| POST | `/governanca/quotas/api/definir-estado/<pk>/` | Definir estado (admin) |
| POST | `/governanca/quotas/api/marcar-paga/<fatura_uuid>/` | Marcar paga (admin) |
| GET | `/governanca/quotas/api/buscar-membros/` | Buscar membros |

### LiveKit (Vídeo)
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/governanca/api/livekit/token/` | Gerar token |
| POST | `/governanca/api/livekit/mute/` | Controlar áudio/vídeo |
| GET | `/governanca/api/livekit/participants/` | Listar participantes |

### Notificações
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/governanca/api/notificacoes/` | Listar |
| POST | `/governanca/api/notificacoes/marcar-lida/<pk>/` | Marcar lida |
| POST | `/governanca/api/notificacoes/marcar-todas/` | Marcar todas lidas |

### Exportação
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/governanca/assembleia/<pk>/exportar/pdf/` | Exportar PDF |
| GET | `/governanca/assembleia/<pk>/exportar/excel/` | Exportar Excel |
| GET | `/governanca/assembleia/<pk>/exportar/csv/` | Exportar CSV |

## 9.3 WebSocket

**Endpoint:** `ws://<host>/ws/assembleia/<assembleia_pk>/`

Eventos enviados pelo servidor:
| Tipo | Descrição |
|------|-----------|
| `quorum_update` | Atualização do quórum |
| `resultados_update` | Resultados de votação em tempo real |
| `votacao_aberta` | Votação foi aberta |
| `votacao_encerrada` | Votação foi encerrada |
| `votacao_reaberta` | Votação foi reaberta |
| `broadcast_chat` | Mensagem de chat |

Eventos recebidos do cliente:
| Tipo | Descrição |
|------|-----------|
| `votar` | Registrar voto |
| `ping` | Manter conexão ativa |
| `solicitar_quorum` | Solicitar atualização do quórum |
| `chat_message` | Enviar mensagem |
| `chat_reaction` | Enviar reação |

## 9.4 Notificações Automáticas

O sistema envia notificações nos seguintes eventos:
- Convocatória publicada
- Assembleia iniciada
- Votação aberta
- Votação encerrada
- Documento publicado
- Ata publicada
- Quota gerada
- Pagamento confirmado
- Certidão emitida
- Estado financeiro alterado
- Carteira profissional renovada

## 9.5 Estrutura de Ficheiros Relevante

```
└── governanca/
    ├── models.py              # Modelos de dados (20 modelos)
    ├── views.py               # Vistas HTML e API (2661 linhas)
    ├── urls.py                # Rotas (160+)
    ├── consumers.py           # WebSocket (chat, quórum, votações)
    ├── routing.py             # Rotas WebSocket
    ├── admin.py               # Registo admin
    └── templates/governanca/  # Templates do módulo
        ├── index.html
        ├── lista_assembleias.html
        ├── nova_assembleia.html
        ├── detalhe_assembleia.html
        ├── editar_assembleia.html
        ├── sala_assembleia.html
        ├── gerir_assembleia.html
        ├── repositorio_atas.html
        ├── notificacoes.html
        ├── assembleia_logs.html
        ├── consulta/
        ├── convocatorias/
        └── quotas/
```

---

> Documentação gerada em Maio 2026 — Sistema CDOA v1.0
