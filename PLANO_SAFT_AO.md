# Plano de Implementação — Módulo SAF-T Angola
## Validação de Facturas para a AGT (SICDOA)

> Baseado na análise rigorosa dos documentos em `_ Documentos para validação/`

---

## 1. Base Legal e Fontes Analisadas

| Documento | O que define |
|---|---|
| **Decreto Presidencial 292/18** | Regime Jurídico das Obrigações Fiscais — institui o SAF-T como obrigação para todos os contribuintes com software de faturação certificado |
| **Decreto Executivo 74/19** | Regras e Requisitos de Validação do Sistema de Faturação — define o processo de certificação do software produtor junto à AGT |
| **Decreto 317/20** | Alteração dos Anexos do SAF-T AO — actualiza a estrutura XSD para a versão `AO_1.01_01` (actualmente em vigor) |
| **SAFT - 08.04.2022.xml** | Ficheiro real com estrutura completa, hash por fatura, tipos de documento e tabela de IVA |
| **Motivos de Isenção.pdf** | Tabela de códigos de isenção de IVA obrigatórios (M10, M18, M21...) com as alíneas legais do CIVA |
| **Testes de conformidade.pdf** | Critérios de validação técnica do ficheiro SAF-T antes da submissão à AGT |
| **Exemplos de facturas.pdf / Factura Térmica.pdf** | Modelos visuais de faturas e recibos válidos com campos obrigatórios |
| **Submissão Modelo 8.pdf** | Fluxo de submissão da declaração via portal do contribuinte AGT |

---

## 2. O que o SAF-T Angola exige — descobertas dos documentos

### 2.1 Estrutura do ficheiro XML

**Namespace:** `urn:OECD:StandardAuditFile-Tax:AO_1.01_01`

```
AuditFile
├── Header
│   ├── AuditFileVersion: "1.01_01"
│   ├── CompanyID, TaxRegistrationNumber (NIF)
│   ├── TaxAccountingBasis: "F" (Faturação) ou "C" (Contabilidade)
│   ├── CompanyName, CompanyAddress (City, Country: AO)
│   ├── FiscalYear, StartDate, EndDate
│   ├── CurrencyCode: "AOA"
│   ├── SoftwareValidationNumber: "000/AGT/AAAA"  ← obrigatório, emitido pela AGT
│   ├── ProductID: "SICDOA/CDOA"
│   └── ProductVersion: "1.0.0"
├── MasterFiles
│   ├── Customer[]
│   │   ├── CustomerID, CustomerTaxID (NIF)
│   │   ├── CompanyName, BillingAddress
│   │   └── SelfBillingIndicator: 0
│   ├── Product[]
│   │   ├── ProductType: "S" (Serviço) ou "P" (Produto)
│   │   ├── ProductCode, ProductGroup, ProductDescription
│   │   └── ProductNumberCode
│   └── TaxTable[]
│       ├── IVA / ISE / 0%     ← isento
│       ├── IVA / NOR / 14%    ← taxa normal
│       └── NS  / NS  / 0%     ← não sujeito
└── SourceDocuments
    └── SalesInvoices
        ├── NumberOfEntries
        ├── TotalDebit, TotalCredit
        └── Invoice[]
            ├── InvoiceNo: "FT 2022/1"
            ├── Hash: [RSA-SHA1 Base64 256 bytes]  ← encadeada
            ├── HashControl: 0 (primeira) ou 1
            ├── Period: 1-12 (mês fiscal)
            ├── InvoiceDate, InvoiceType: FT/FR/ND/NC
            ├── SpecialRegimes (SelfBilling, CashVAT, ThirdParties)
            ├── SourceID, SystemEntryDate
            ├── CustomerID
            ├── ShipTo / ShipFrom (Address)
            ├── Line[]
            │   ├── LineNumber, ProductCode, ProductDescription
            │   ├── Quantity, UnitOfMeasure, UnitPrice
            │   ├── CreditAmount ou DebitAmount
            │   ├── Tax (TaxType, TaxCountryRegion: AO, TaxCode, TaxPercentage)
            │   ├── TaxExemptionReason  ← obrigatório quando isento
            │   └── TaxExemptionCode: M10, M18, M21...
            └── DocumentTotals
                ├── TaxPayable, NetTotal, GrossTotal
                └── Payment (PaymentMechanism, PaymentAmount, PaymentDate)
```

### 2.2 Tipos de documento suportados

| Código | Descrição | Origem no SICDOA |
|---|---|---|
| `FT` | Factura | `FacturaCliente` |
| `FR` | Factura-Recibo | `FacturaRecibo` |
| `ND` | Nota de Débito | `NotaDebito` |
| `NC` | Nota de Crédito | `NotaCredito` |

### 2.3 Hash encadeada por fatura (RSA-SHA1)

Cada `<Hash>` assina os campos da fatura actual + o Hash da anterior:

```
campos = "data_fatura;data_sistema;numero_fatura;hash_anterior;gross_total"
chave_privada_contribuinte → RSA-SHA1 → Base64
```

- `HashControl = 0` → primeira fatura (sem hash anterior)
- `HashControl = 1` → encadeada com a fatura imediatamente anterior

### 2.4 Códigos de Isenção de IVA (documento Motivos de Isenção.pdf)

| Código | Base legal CIVA | Descrição |
|---|---|---|
| M10 | Art. 12.º n.º1 al. a) | Produtos alimentares básicos |
| M18 | Art. 12.º n.º1 al. i) | Equipamentos informáticos |
| M21 | Art. 12.º n.º1 al. l) | Outros equipamentos |
| M99 | Outros | Não sujeito / fora do âmbito IVA |

> Quando `TaxPercentage = 0`, os campos `TaxExemptionReason` e `TaxExemptionCode` são **obrigatórios**.

---

## 3. Arquitectura do Módulo no SICDOA

### Posição no sidebar (Gestão Financeira)

```
Gestão Financeira
├── Requisições de Fundos
├── Recibos
├── Notas
├── Facturas
├── Faturação Eletrónica AGT  (já implementado)
├── Validação SAF-T AGT        ← NOVO SUBITEM
├── Conta Corrente
└── Relatórios
```

### Ficheiros a criar

```
financeiro/
├── saft_generator.py              ← geração do XML + hash encadeada
├── saft_validator.py              ← validação XSD local
├── views_saft.py                  ← views Django
├── migrations/
│   └── 0048_submissao_saft.py
templates/financeiro/
├── saft_dashboard.html
├── saft_gerar.html
└── saft_historico.html
static/xsd/
└── SAFT-AO_1.01_01.xsd            ← descarregar do portal AGT
```

---

## 4. Modelo de Dados — `SubmissaoSAFT`

```python
class SubmissaoSAFT(models.Model):
    ESTADOS = [
        ('Rascunho',  'Rascunho'),
        ('Gerado',    'Gerado'),
        ('Validado',  'Validado'),
        ('Submetido', 'Submetido'),
        ('Aceite',    'Aceite'),
        ('Rejeitado', 'Rejeitado'),
    ]

    banca            = ForeignKey('rh.Banca')
    periodo_inicio   = DateField()        # ex: 2026-01-01
    periodo_fim      = DateField()        # ex: 2026-01-31
    ano_fiscal       = IntegerField()
    mes              = IntegerField(null=True)   # 1-12; None = anual
    tipo_base        = CharField(default='F')    # "F" faturação / "C" contabilidade

    # Ficheiro gerado
    ficheiro_xml     = FileField(upload_to='saft/%Y/%m/')
    numero_faturas   = IntegerField(default=0)
    total_debito     = DecimalField()
    total_credito    = DecimalField()

    # Estado e submissão
    estado           = CharField(choices=ESTADOS, default='Rascunho')
    erros_validacao  = JSONField(null=True)    # erros XSD detectados localmente
    submetido_em     = DateTimeField(null=True)
    resposta_agt     = JSONField(null=True)    # resposta do portal AGT

    # Auditoria
    criado_por_id    = IntegerField(null=True)
    criado_por_nome  = CharField(max_length=200, blank=True)
    criado_em        = DateTimeField(auto_now_add=True)
    atualizado_em    = DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('banca', 'periodo_inicio', 'periodo_fim')]
```

---

## 5. Módulo de Geração XML (`saft_generator.py`)

### 5.1 Algoritmo da Hash encadeada

```python
def calcular_hash(invoice, hash_anterior: str) -> str:
    """
    Fórmula SAF-T AO (Decreto 317/20):
      campos = "data_fatura;data_sistema;numero_fatura;hash_anterior;gross_total"
      assinar com RSA-SHA1 usando chave privada do contribuinte → Base64
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    campos = (
        f"{invoice.data_emissao.date()};"
        f"{invoice.data_emissao.strftime('%Y-%m-%dT%H:%M:%S')};"
        f"{invoice.numero_factura};"
        f"{hash_anterior};"
        f"{invoice.valor_total}"
    )
    chave = _carregar_chave_privada_contribuinte()
    assinatura = chave.sign(
        campos.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA1()
    )
    return base64.b64encode(assinatura).decode('utf-8')
```

### 5.2 Mapeamento SICDOA → SAF-T AO

| Campo SAF-T | Origem no SICDOA |
|---|---|
| `TaxRegistrationNumber` | `Banca.nif` |
| `SoftwareValidationNumber` | `settings.AGT_SOFTWARE_VALIDATION_NUMBER` |
| `CompanyName` | `Banca.nome` |
| `ProductID` | `settings.AGT_PRODUCT_ID` (= "SICDOA") |
| `ProductVersion` | `settings.AGT_PRODUCT_VERSION` |
| `CustomerID` / `CustomerTaxID` | `Cliente.id` / `Cliente.nif` |
| `InvoiceNo` | `FacturaCliente.numero_factura` |
| `InvoiceType` | `"FT"` ou `"FR"` conforme modelo |
| `NetTotal` | `valor_total - iva` |
| `TaxPayable` | `iva` |
| `GrossTotal` | `valor_total` |
| `TaxCode` | `"NOR"` (14%) / `"ISE"` (0%) / `"NS"` (n.s.) |
| `ProductDescription` | `"Serviços de Despacho Aduaneiro"` |

---

## 6. Validação Local XSD (`saft_validator.py`)

```python
from lxml import etree

def validar_saft_xml(xml_content: str, xsd_path: str) -> list[str]:
    """
    Valida o XML gerado contra o XSD oficial SAF-T AO 1.01_01.
    Devolve lista de erros. Lista vazia = ficheiro válido.
    """
    with open(xsd_path, 'rb') as f:
        schema = etree.XMLSchema(etree.parse(f))

    doc = etree.fromstring(xml_content.encode('utf-8'))
    schema.validate(doc)
    return [str(e) for e in schema.error_log]
```

**Instalar dependência:**
```bash
pip install lxml==5.2.2
```

---

## 7. Views Django (`views_saft.py`)

| View | URL | Descrição |
|---|---|---|
| `saft_dashboard` | `GET /financeiro/saft/` | Dashboard com KPIs e histórico |
| `saft_gerar` | `GET/POST /financeiro/saft/gerar/` | Formulário: escolher período → gerar XML |
| `saft_preview` | `GET /financeiro/saft/<pk>/preview/` | Pré-visualização do XML |
| `saft_validar` | `POST /financeiro/saft/<pk>/validar/` | Executar validação XSD local |
| `saft_download` | `GET /financeiro/saft/<pk>/download/` | Descarregar ficheiro .xml |
| `saft_historico` | `GET /financeiro/saft/historico/` | Lista completa de submissões |

---

## 8. Dashboard — Layout previsto

```
┌───────────────────────────────────────────────────────────────┐
│  Validação SAF-T AGT                          [Gerar SAF-T]   │
│  Geração e gestão de ficheiros SAF-T para submissão à AGT     │
├──────────┬─────────────┬──────────────┬────────────────────── ┤
│ Ficheiros│ Validados   │ Submetidos   │ Rejeitados            │
│   12     │    10       │     8        │     1                 │
├──────────┴─────────────┴──────────────┴──────────────────────-┤
│ Período     │ Faturas │ Total (Kz)    │ Estado    │ Acções    │
│ Jan 2026    │   45    │ 12.450.000    │ Aceite ✅  │ Download  │
│ Fev 2026    │   38    │  9.876.000    │ Aceite ✅  │ Download  │
│ Mar 2026    │   52    │ 15.230.000    │ Rascunho   │ Gerar/Val │
└───────────────────────────────────────────────────────────────┘
```

---

## 9. Fases de Implementação

### Fase 1 — Modelo e Geração XML (1–2 dias)
- [ ] Criar modelo `SubmissaoSAFT` + migration `0048`
- [ ] Implementar `saft_generator.py` com estrutura XML completa
- [ ] Hash encadeada RSA-SHA1 (conforme Decreto 317/20)
- [ ] Mapear `FacturaCliente`, `FacturaRecibo`, `NotaCredito`, `NotaDebito`
- [ ] Suporte a motivos de isenção de IVA (M10, M18, M21, M99)
- [ ] Testes unitários da geração e da hash

### Fase 2 — Validação Local XSD (0.5 dia)
- [ ] Descarregar XSD oficial `SAFT-AO_1.01_01.xsd` do portal AGT
- [ ] Implementar `saft_validator.py` com `lxml`
- [ ] Instalar `lxml==5.2.2`
- [ ] Exibir erros de validação de forma clara no frontend

### Fase 3 — Views e Templates (1–2 dias)
- [ ] `views_saft.py` com as 6 views
- [ ] Registar URLs em `financeiro/urls.py`
- [ ] Templates com padrão visual do projecto (Tailwind + Font Awesome)
- [ ] Subitem "Validação SAF-T AGT" no sidebar (`templates/includes/sidebar.html`)

### Fase 4 — Submissão ao Portal AGT (0.5 dia)
- [ ] Botão "Abrir Portal AGT" com link directo ao portal do contribuinte
- [ ] Registo manual do estado após submissão (`estado` + `submetido_em`)
- [ ] Nota: o portal AGT não tem API pública de upload — submissão é via browser

### Fase 5 — Polimento e Isolamento (0.5 dia)
- [ ] Isolamento multi-tenant por banca em todas as views
- [ ] Impedir dois ficheiros para o mesmo período da mesma banca
- [ ] Numeração sequencial do SAF-T por banca + período

---

## 10. Dependências Técnicas

| Biblioteca | Uso | Estado |
|---|---|---|
| `lxml` | Validação XSD do SAF-T | **A instalar** |
| `cryptography` | Hash RSA-SHA1 | Já instalada |
| `xml.etree.ElementTree` | Geração do XML | stdlib Python |
| `PyJWT` | Já usada na Faturação Eletrónica | Já instalada |

---

## 11. Variáveis `.env` a Configurar

```env
# SAF-T AO
AGT_SOFTWARE_VALIDATION_NUMBER=000/AGT/XXXX   # obter no portal do parceiro
AGT_NIF_EMITENTE=                              # NIF da banca emitente
AGT_COMPANY_NAME=CDOA
SAFT_XSD_PATH=static/xsd/SAFT-AO_1.01_01.xsd  # caminho para o XSD oficial
```

---

## 12. Diferenças entre os dois módulos AGT

| | Faturação Eletrónica (existente) | SAF-T (a implementar) |
|---|---|---|
| **Norma** | API REST em tempo real | Ficheiro XML periódico |
| **Quando** | Por cada fatura emitida | Mensalmente ou anualmente |
| **Formato** | JSON + JWS RS256 | XML (XSD AO_1.01_01) |
| **Hash** | JWS RS256 na requisição HTTP | RSA-SHA1 encadeada por documento |
| **Endpoint AGT** | `POST /sigt/fe/v1/registarFactura` | Upload manual no portal do contribuinte |
| **Submissão** | Automática via API | Manual via browser |
| **Decreto base** | D.E. 74/19 + DOMENTACAO_AGT.md | D.P. 292/18 + D.E. 74/19 + D. 317/20 |

---

## 13. Notas Críticas

1. **`SoftwareValidationNumber`** é obrigatório no Header. Sem ele o ficheiro é imediatamente rejeitado. Formato: `NNN/AGT/AAAA`. Obtido no portal do parceiro após certificação.

2. **Hash encadeada** — cada fatura assina os dados da fatura anterior. Se uma fatura for alterada retroactivamente, todas as hashes seguintes ficam inválidas. As faturas no SAF-T devem ser **imutáveis** após geração.

3. **Isenções de IVA** — quando `TaxPercentage = 0`, os campos `TaxExemptionReason` e `TaxExemptionCode` são **obrigatórios** segundo o Decreto 317/20.

4. **Todos os tipos de documento** entram no SAF-T: `FacturaCliente` (FT), `FacturaRecibo` (FR), `NotaCredito` (NC), `NotaDebito` (ND).

5. **Período fiscal** — cada ficheiro SAF-T cobre exactamente um período (mês/ano). A AGT valida rigorosamente o `FiscalYear` e o `Period`.
