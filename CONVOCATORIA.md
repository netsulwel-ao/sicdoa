# Convocatórias

## O que é?

A **Convocatória** é o mecanismo oficial de convocação dos membros (Administradores e Despachantes Oficiais) para uma Assembleia. Funciona como um edital de convocação digital.

## Fluxo Completo

### 1. Criação (Apenas Administrador)
- Acessa a Assembleia → botão **"Convocatórias"** → **"Nova Convocatória"**
- Preenche:
  - **Título** (obrigatório) — ex: "Convocatória para Assembleia Geral Ordinária"
  - **Descrição** (opcional) — detalhes adicionais
  - **Prazo de Confirmação** (opcional) — data limite para confirmar presença
  - **Documento** (opcional) — PDF/DOCX com o edital completo
- A Convocatória é criada em estado **"Rascunho"**

### 2. Publicação (Apenas Administrador)
- Na lista de Convocatórias, clica em **"Publicar"**
- O sistema:
  1. Muda o estado para **"Publicada"**
  2. Cria **notificações in-app** para:
     - **Administradores** — "Convocatória publicada"
     - **Despachantes Oficiais** — "Convocatória publicada. Confirme a sua presença."
  3. Disponibiliza o botão **"Confirmar Receção"** para todos os utilizadores

### 3. Confirmação de Presença (RSVP)
- O notificado clica na notificação e é levado à **página de detalhe da Assembleia**
- Lá encontra os botões **Sim / Não / Talvez** que registam a sua **RespostaPresenca**
- O quórum previsto (`quorum_previsto`) é atualizado automaticamente com base nas respostas "Sim"

## Relações

```
Convocatoria ──belongs_to──▶ Assembleia
                                 │
                                 ├── RespostaPresenca (RSVP dos utilizadores)
                                 ├── PautaVotacao (pautas a votar)
                                 └── DocumentoAssembleia (atas, decretos, relatórios)
```

## Modelo de Dados

| Campo | Tipo | Descrição |
|---|---|---|
| `assembleia` | FK → Assembleia | Assembleia alvo da convocação |
| `titulo` | CharField(300) | Título da convocatória |
| `descricao` | TextField | Descrição detalhada |
| `documento` | FileField | PDF/DOCX do edital |
| `data_envio` | DateTime (auto) | Data de criação |
| `prazo_confirmacao` | DateTime | Prazo limite para RSVP |
| `status` | Rascunho / Publicada | Estado atual |

## Estados

- **Rascunho** — visível apenas para Administradores, pode ser editada
- **Publicada** — notificações enviadas, RSVP disponível, todos veem

## URLs

| Rota | Função |
|---|---|
| `/governanca/assembleia/{id}/convocatorias/` | Lista de convocatórias da assembleia |
| `/governanca/assembleia/{id}/convocatoria/nova/` | Criar nova convocatória |
| `/governanca/api/convocatoria/{id}/publicar/` | Publicar convocatória |
| `/governanca/api/convocatoria/{id}/confirmar-rececao/` | Confirmar receção |
| `/governanca/api/assembleia/{id}/responder-presenca/` | RSVP (Sim/Não/Talvez) |

## Notificações

A publicação gera notificações in-app do tipo `convocatoria_publicada`:
- **Administradores**: "Foi publicada a convocatória \"{titulo}\" para {assembleia}."
- **Despachantes**: "Foi publicada a convocatória \"{titulo}\". Confirme a sua presença."

## Observações

- Não é enviado email aquando da publicação (apenas notificação in-app)
- O documento anexado é um upload manual (PDF/DOCX), não gerado pelo sistema
- A confirmação de receção é apenas front-end (não persiste na base de dados)
- O RSVP alimenta o cálculo de `quorum_previsto` da Assembleia
- Uma assembleia pode ter múltiplas convocatórias
