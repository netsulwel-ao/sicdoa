"""
agt_crypto.py — Módulo de assinaturas JWS RS256 para integração AGT
Documentação: DOMENTACAO_AGT.md

Implementa as 3 assinaturas exigidas pela API da Administração Geral Tributária:
  - jwsSoftwareSignature  : assina dados do produtor de software (SICDOA)
  - jwsDocumentSignature  : assina os campos fiscais do documento
  - jwsSignature          : assina a requisição (taxRegistrationNumber + requestID)

Todas usam RSA-SHA256 (RS256) com JSON canónico (sem espaços, sem quebras de linha).
"""
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _canonical_json(obj: dict) -> str:
    """
    Serializa o objecto em JSON canónico:
    - Sem quebras de linha
    - Sem espaços (separators=(',', ':'))
    - Aspas duplas obrigatórias (default do json.dumps)
    - Números sem formatação adicional
    """
    return json.dumps(obj, sort_keys=False, separators=(',', ':'), ensure_ascii=False)


def _load_private_key_pem(pem_text: str):
    """
    Carrega uma chave privada RSA a partir de texto PEM.
    Suporta PKCS#8 (BEGIN PRIVATE KEY) e PKCS#1 (BEGIN RSA PRIVATE KEY).
    """
    pem_bytes = pem_text.strip().encode('utf-8')
    return serialization.load_pem_private_key(pem_bytes, password=None, backend=default_backend())


def _sign_rs256(payload: dict, private_key_pem: str) -> str:
    """
    Assina um dicionário com RS256.
    O payload é o objecto JSON completo (não concatenação de campos).
    Devolve o token JWS compact: header.payload.signature
    """
    private_key = _load_private_key_pem(private_key_pem)
    # PyJWT aceita o objecto directamente; internamente faz base64url sem padding
    token = jwt.encode(
        payload,
        private_key,
        algorithm='RS256',
        headers={'alg': 'RS256', 'typ': 'JWT'},
    )
    return token  # str no PyJWT >= 2.x


# ---------------------------------------------------------------------------
# Carregamento de chaves a partir das settings / ficheiros
# ---------------------------------------------------------------------------

def _get_software_private_key() -> str:
    """
    Chave privada do PRODUTOR DE SOFTWARE (SICDOA).
    Configurar em settings.py (ou .env):
        AGT_SOFTWARE_PRIVATE_KEY  — conteúdo PEM directo (variável de ambiente)
        AGT_SOFTWARE_PRIVATE_KEY_FILE — caminho para ficheiro .pem
    """
    pem = getattr(settings, 'AGT_SOFTWARE_PRIVATE_KEY', None)
    if pem:
        return pem

    key_file = getattr(settings, 'AGT_SOFTWARE_PRIVATE_KEY_FILE', None)
    if key_file and Path(key_file).exists():
        return Path(key_file).read_text(encoding='utf-8')

    # Fallback: gerar chave efémera de desenvolvimento (não usar em produção)
    logger.warning(
        'AGT_SOFTWARE_PRIVATE_KEY não configurada. '
        'A usar chave RSA gerada em tempo de execução (apenas para DESENVOLVIMENTO).'
    )
    return _generate_dev_key()


def _get_contributor_private_key() -> str:
    """
    Chave privada do CONTRIBUINTE (emitida pela AGT, disponível no portal do contribuinte).
    Configurar em settings.py (ou .env):
        AGT_CONTRIBUTOR_PRIVATE_KEY  — conteúdo PEM
        AGT_CONTRIBUTOR_PRIVATE_KEY_FILE — caminho para ficheiro .pem
    """
    pem = getattr(settings, 'AGT_CONTRIBUTOR_PRIVATE_KEY', None)
    if pem:
        return pem

    key_file = getattr(settings, 'AGT_CONTRIBUTOR_PRIVATE_KEY_FILE', None)
    if key_file and Path(key_file).exists():
        return Path(key_file).read_text(encoding='utf-8')

    logger.warning(
        'AGT_CONTRIBUTOR_PRIVATE_KEY não configurada. '
        'A usar chave RSA gerada em tempo de execução (apenas para DESENVOLVIMENTO).'
    )
    return _generate_dev_key()


def _generate_dev_key() -> str:
    """Gera chave RSA 2048-bit efémera para ambiente de desenvolvimento."""
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('utf-8')


# ---------------------------------------------------------------------------
# As 3 assinaturas AGT
# ---------------------------------------------------------------------------

def assinar_software() -> str:
    """
    jwsSoftwareSignature — assina dados de identificação do produtor de software.
    Payload: { productId, productVersion, softwareValidationNumber }

    Valores configuráveis:
        AGT_PRODUCT_ID                — nome do produto (default: 'SICDOA')
        AGT_PRODUCT_VERSION           — versão do produto (default: '1.0.0')
        AGT_SOFTWARE_VALIDATION_NUMBER — número de validação emitido pela AGT
    """
    payload = {
        'productId': getattr(settings, 'AGT_PRODUCT_ID', 'SICDOA'),
        'productVersion': getattr(settings, 'AGT_PRODUCT_VERSION', '1.0.0'),
        'softwareValidationNumber': getattr(settings, 'AGT_SOFTWARE_VALIDATION_NUMBER', '000000000'),
    }
    private_key = _get_software_private_key()
    return _sign_rs256(payload, private_key)


def assinar_documento(
    document_no: str,
    tax_registration_number: str,
    document_type: str,
    document_date: str,
    customer_tax_id: str,
    customer_country: str,
    company_name: str,
    net_total: float,
    tax_payable: float,
    gross_total: float,
) -> str:
    """
    jwsDocumentSignature — assina os campos fiscais principais do documento.
    Payload estrutura documentada em DOMENTACAO_AGT.md.
    """
    payload = {
        'documentNo': document_no,
        'taxRegistrationNumber': tax_registration_number,
        'documentType': document_type,
        'documentDate': document_date,
        'customerTaxID': customer_tax_id,
        'customerCountry': customer_country,
        'companyName': company_name,
        'documentTotals': {
            'taxPayable': round(float(tax_payable), 2),
            'netTotal': round(float(net_total), 2),
            'grossTotal': round(float(gross_total), 2),
        },
    }
    private_key = _get_contributor_private_key()
    return _sign_rs256(payload, private_key)


def assinar_requisicao(tax_registration_number: str, request_id: str) -> str:
    """
    jwsSignature — assina a requisição com NIF do emitente + requestID.
    Garante autenticação forte por chamada.
    """
    payload = {
        'taxRegistrationNumber': tax_registration_number,
        'requestID': request_id,
    }
    private_key = _get_contributor_private_key()
    return _sign_rs256(payload, private_key)


# ---------------------------------------------------------------------------
# Geração de requestID único
# ---------------------------------------------------------------------------

def gerar_request_id(numero_fatura: str) -> str:
    """
    Gera um requestID único no formato REQ-{numero_fatura}-{timestamp_hex}.
    Ex: REQ-FAT-2026-0001-1a2b3c4d
    """
    import time
    ts = hex(int(time.time()))[2:].upper()
    base = numero_fatura.replace('/', '-').replace(' ', '-')
    return f'REQ-{base}-{ts}'


# ---------------------------------------------------------------------------
# Construção do payload completo para /sigt/fe/v1/registarFactura
# ---------------------------------------------------------------------------

def construir_payload_agt(fatura) -> dict:
    """
    Constrói o payload JSON completo para submissão à AGT,
    incluindo as 3 assinaturas JWS.

    Args:
        fatura: instância de FaturaAGT com os campos preenchidos.

    Returns:
        dict pronto para json.dumps e envio à API AGT.
    """
    request_id = gerar_request_id(fatura.numero_fatura)

    # Datas no formato ISO 8601 (YYYY-MM-DD)
    document_date = fatura.data_emissao.strftime('%Y-%m-%d') if fatura.data_emissao else ''

    # Calcular net_total (sem IVA) e tax_payable (IVA)
    gross_total = float(fatura.valor_total or 0)
    taxa = float(fatura.taxa_iva or 14) / 100
    # Se valor_iva já preenchido, usa; senão calcula
    tax_payable = float(fatura.valor_iva) if fatura.valor_iva else round(gross_total * taxa / (1 + taxa), 2)
    net_total = round(gross_total - tax_payable, 2)

    nif_emitente = fatura.nif_emitente or getattr(
        getattr(settings, 'AGT_NIF_EMITENTE', None), '__str__', lambda: '')() or ''

    company_name = getattr(settings, 'AGT_COMPANY_NAME', 'CDOA')

    # 3 assinaturas JWS
    jws_software = assinar_software()
    jws_document = assinar_documento(
        document_no=fatura.numero_fatura,
        tax_registration_number=nif_emitente,
        document_type='FT',  # Fatura
        document_date=document_date,
        customer_tax_id=fatura.nif_cliente or '000000000',
        customer_country='AO',
        company_name=company_name,
        net_total=net_total,
        tax_payable=tax_payable,
        gross_total=gross_total,
    )
    jws_request = assinar_requisicao(
        tax_registration_number=nif_emitente,
        request_id=request_id,
    )

    payload = {
        'requestID': request_id,
        'taxRegistrationNumber': nif_emitente,
        'documentNo': fatura.numero_fatura,
        'documentType': 'FT',
        'documentDate': document_date,
        'customerTaxID': fatura.nif_cliente or '000000000',
        'customerCountry': 'AO',
        'companyName': company_name,
        'serie': fatura.serie or getattr(settings, 'AGT_SERIE_PADRAO', 'A'),
        'documentTotals': {
            'taxPayable': tax_payable,
            'netTotal': net_total,
            'grossTotal': gross_total,
        },
        'lines': [
            {
                'lineNo': 1,
                'description': fatura.descricao or 'Serviços de Despacho Aduaneiro',
                'quantity': 1,
                'unitPrice': net_total,
                'taxBase': net_total,
                'taxAmount': tax_payable,
                'lineTotal': gross_total,
            }
        ],
        'jwsSoftwareSignature': jws_software,
        'jwsDocumentSignature': jws_document,
        'jwsSignature': jws_request,
    }

    # Armazenar requestID na fatura para uso no polling
    fatura._request_id_gerado = request_id

    return payload
