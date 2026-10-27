"""Serviço de integração com a Faturação Eletrónica da AGT (Angola).

Implementa o Decreto Executivo n.º 683/25 (schema 2.0) e os serviços REST do
SIGT:
  * ``registarFactura``  — submissão de documentos (assinatura JWS RS256);
  * ``obterEstado``      — consulta do estado de validação;
  * ``solicitarSerie``   — comunicação/criação de séries de numeração.

Todas as assinaturas usam o algoritmo RS256 (RSA + SHA-256) em JWS compacto
com cabeçalho ``{"typ": "JOSE", "alg": "RS256"}``, tal como exigido pela AGT.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone as _tz
from decimal import Decimal, ROUND_HALF_UP

import jwt
import requests
from django.conf import settings


class AGTErro(Exception):
    """Erro de comunicação, assinatura ou validação com a AGT."""


# Mapeamento do tipo interno do SICDOA para o código oficial da AGT.
TIPO_DOCUMENTO_AGT = {
    'FATURA': 'FT',
    'NOTA_DEBITO': 'ND',
    'NOTA_CREDITO': 'NC',
}

IVA_PADRAO = Decimal('14')


# ── Utilitários ───────────────────────────────────────────────────────

def _agora_iso():
    """Timestamp ISO 8601 em UTC, ex.: 2025-11-04T14:30:00Z."""
    return datetime.now(_tz.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _f(valor):
    """Converte para float com 2 casas decimais (formato da AGT)."""
    return float(Decimal(valor or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# ── Assinaturas JWS (RS256) ───────────────────────────────────────────

def assinar_jws(payload, chave_privada_pem):
    """Assina um objecto JSON em JWS compacto (RS256, typ=JOSE)."""
    if not chave_privada_pem:
        raise AGTErro('Chave privada ausente para assinatura JWS.')
    try:
        return jwt.encode(
            payload, chave_privada_pem, algorithm='RS256',
            headers={'typ': 'JOSE', 'alg': 'RS256'},
        )
    except Exception as exc:  # noqa: BLE001 - normaliza qualquer falha de assinatura
        raise AGTErro(f'Falha ao assinar JWS: {exc}') from exc


def verificar_jws(token, chave_publica_pem):
    """Valida um JWS RS256 com a chave pública indicada e devolve o payload."""
    if not chave_publica_pem:
        raise AGTErro('Chave pública da AGT não configurada.')
    try:
        return jwt.decode(
            token, chave_publica_pem, algorithms=['RS256'],
            options={'verify_aud': False, 'verify_exp': False},
        )
    except Exception as exc:  # noqa: BLE001
        raise AGTErro(f'Assinatura JWS inválida: {exc}') from exc


def verificar_assinatura_callback(header_valor, corpo_json, config, segredo_hmac=''):
    """Valida a assinatura de um callback da AGT.

    Ordem de tentativa:
      1. JWS compacto no cabeçalho ``X-AGT-Signature``;
      2. JWS compacto no campo ``jwsSignature`` do corpo;
      3. HMAC-SHA256 (compatibilidade) usando ``segredo_hmac``.

    Devolve o payload validado (dict) ou lança ``AGTErro``.
    """
    if config is not None and getattr(config, 'agt_public_key', ''):
        token = (header_valor or '').strip()
        if not token and isinstance(corpo_json, dict):
            token = (corpo_json.get('jwsSignature') or '').strip()
        if token:
            return verificar_jws(token, config.agt_public_key)
        raise AGTErro('Callback sem assinatura JWS para validar.')

    if segredo_hmac:
        corpo = json.dumps(corpo_json, separators=(',', ':'), sort_keys=True).encode('utf-8')
        esperado = hmac.new(segredo_hmac.encode('utf-8'), corpo, hashlib.sha256).hexdigest()
        recebido = (header_valor or '').strip()
        if not hmac.compare_digest(esperado, recebido):
            raise AGTErro('Assinatura HMAC do callback inválida.')
        return corpo_json

    # Sem chave pública nem segredo: não há como validar a autenticidade.
    raise AGTErro('Sem chave pública da AGT nem segredo configurado para validar o callback.')


# ── Construção do documento (registarFactura) ─────────────────────────

def _totais_documento(fatura):
    """Deriva (netTotal, taxPayable, grossTotal, iva_percent) do documento de origem."""
    total = Decimal(fatura.total_geral or 0)
    fc = fatura.factura_cliente
    rf = fatura.requisicao_fundo
    iva = Decimal('0.00')
    net = Decimal('0.00')

    if fc is not None:
        iva = Decimal(fc.iva or 0)
        net = (Decimal(fc.honorarios_despachante or 0) + Decimal(fc.taxas_aduaneiras or 0)
               + Decimal(fc.emolumentos or 0) + Decimal(fc.despesas_operacionais or 0)
               + Decimal(fc.outros_encargos or 0))
        total = Decimal(fc.valor_total or total)
    elif rf is not None:
        iva = Decimal(rf.iva_honorarios or 0)
        net = Decimal(rf.subtotal_geral or 0)
        total = Decimal(rf.total_geral or total)

    if net <= 0:
        net = total - iva
        if net <= 0:
            net = total
            iva = Decimal('0.00')

    iva_percent = (iva / net * 100) if net > 0 else IVA_PADRAO
    return _f(net), _f(iva), _f(total), _f(iva_percent)


def construir_documento(fatura, config, document_no):
    """Constrói o objecto `document` do schema registarFactura."""
    net, iva, total, iva_pct = _totais_documento(fatura)
    cliente = fatura.cliente
    nif_cliente = (cliente.nif or '').strip() or '999999999'
    data = fatura.data_emissao or datetime.now(_tz.utc)

    linha = {
        'lineNumber': 1,
        'operationType': 'SG',
        'productCode': (fatura.numero_fatura or 'SERV')[:60],
        'productDescription': f'Serviços de despacho aduaneiro — {fatura.numero_fatura}'[:200],
        'quantity': 1,
        'unitOfMeasure': 'UN',
        'unitPriceBase': net,
        'unitPrice': net,
        'creditAmount': net,
        'settlementAmount': 0,
        'taxes': [{
            'taxType': 'IVA',
            'taxCountryRegion': 'AO',
            'taxCode': 'NOR',
            'taxPercentage': iva_pct,
            'taxContribution': iva,
        }],
    }

    # NC/ND exigem a referência ao documento base (campo referenceInfo da linha).
    if fatura.tipo_documento in ('NOTA_CREDITO', 'NOTA_DEBITO'):
        ref = fatura.documento_origem_ref
        if ref is not None and ref.document_no:
            linha['referenceInfo'] = {
                'reference': ref.document_no[:60],
                'reason': (fatura.motivo_ref or 'Regularização')[:60],
            }

    doc = {
        'documentNo': document_no,
        'documentStatus': 'N',
        'documentDate': data.date().isoformat(),
        'documentType': TIPO_DOCUMENTO_AGT.get(fatura.tipo_documento, 'FT'),
        'systemEntryDate': data.astimezone(_tz.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'customerTaxID': nif_cliente,
        'customerCountry': 'AO',
        'companyName': (cliente.nome or '')[:200],
        'lines': [linha],
        'documentTotals': {
            'taxPayable': iva,
            'netTotal': net,
            'grossTotal': total,
        },
    }
    if config.eac_code:
        doc['eacCode'] = config.eac_code[:5]
    return doc


def construir_software_info(config):
    """Objecto softwareInfo com a assinatura do próprio software (jwsSoftwareSignature)."""
    detalhe = {
        'productId': config.product_id,
        'productVersion': config.product_version,
        'softwareValidationNumber': config.software_validation_number,
        'signatureVersion': config.signature_version,
    }
    return {
        'softwareInfoDetail': detalhe,
        'jwsSoftwareSignature': assinar_jws(detalhe, config.software_private_key),
    }


def construir_payload_registo(fatura, config, sequencia):
    """Constrói o payload completo do serviço registarFactura.

    Devolve ``(payload, submission_uuid, document_no)``.
    """
    if fatura.serie is None:
        raise AGTErro('A fatura não tem uma série AGT associada. Crie/comunique uma série primeiro.')
    if not config.software_private_key or not config.emissor_private_key:
        raise AGTErro('Chaves de assinatura (software/emissor) não configuradas.')
    if fatura.tipo_documento in ('NOTA_CREDITO', 'NOTA_DEBITO'):
        ref = fatura.documento_origem_ref
        if ref is None or not ref.document_no:
            raise AGTErro(
                'As notas de crédito/débito exigem a referência ao documento '
                'original já registado na AGT.'
            )

    document_no = fatura.serie.montar_document_no(sequencia)
    doc = construir_documento(fatura, config, document_no)

    # Assinatura do documento: apenas os 8 campos exigidos pela AGT.
    payload_assinatura = {
        'documentNo': doc['documentNo'],
        'taxRegistrationNumber': config.tax_registration_number,
        'documentType': doc['documentType'],
        'documentDate': doc['documentDate'],
        'customerTaxID': doc['customerTaxID'],
        'customerCountry': doc['customerCountry'],
        'companyName': doc['companyName'],
        'documentTotals': doc['documentTotals'],
    }
    doc['jwsDocumentSignature'] = assinar_jws(payload_assinatura, config.emissor_private_key)

    submission_uuid = str(uuid.uuid4())
    payload = {
        'schemaVersion': '2.0',
        'submissionUUID': submission_uuid,
        'taxRegistrationNumber': config.tax_registration_number,
        'submissionTimeStamp': _agora_iso(),
        'softwareInfo': construir_software_info(config),
        'numberOfEntries': 1,
        'documents': [doc],
    }
    return payload, submission_uuid, document_no


def _post_json(url, payload, timeout=None):
    timeout = timeout or getattr(settings, 'AGT_TIMEOUT', 30)
    try:
        return requests.post(
            url, json=payload, timeout=timeout,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        )
    except requests.RequestException as exc:
        raise AGTErro(f'Falha de comunicação com a AGT: {exc}') from exc


def submeter_fatura_directo(payload, config):
    """Envia um payload de registarFactura já construído/assinado.

    Estrutura do retorno:
    ``{'ok', 'rejeitado', 'status_code', 'request_id', 'erros', 'resposta'}``.
    """
    resp = _post_json(config.get_submit_url(), payload)
    try:
        dados = resp.json()
    except ValueError:
        dados = {'raw': resp.text}
    if not isinstance(dados, dict):
        dados = {'raw': dados}

    erro_lista = dados.get('errorList') or []
    request_id = dados.get('requestID')
    ok = resp.ok and not erro_lista and bool(request_id)
    # A AGT recusa o pedido (sem retry) quando devolve 400/422 ou uma errorList.
    rejeitado = (not ok) and (resp.status_code in (400, 422) or bool(erro_lista))
    return {
        'ok': ok,
        'rejeitado': rejeitado,
        'status_code': resp.status_code,
        'request_id': request_id,
        'erros': erro_lista,
        'resposta': dados,
    }


# ── Envio de documentos (fila de submissão) ───────────────────────────

def resolver_serie(fatura):
    """Devolve a série AGT comunicada aplicável ao documento (ou ``None``)."""
    from django.db.models import Q
    from django.utils import timezone
    from .models import SerieFaturaEletronica

    serie = fatura.serie
    if serie is not None and serie.estado == 'Comunicada':
        return serie
    tipo = TIPO_DOCUMENTO_AGT.get(fatura.tipo_documento, 'FT')
    return (
        SerieFaturaEletronica.objects
        .filter(tipo_documento=tipo, estado='Comunicada', ano=timezone.now().year)
        .filter(Q(banca_id=fatura.banca_id) | Q(banca__isnull=True))
        .order_by('-data_comunicacao')
        .first()
    )


def enviar_fatura(fatura, config=None):
    """Reserva o número da série, assina e submete a fatura à AGT.

    Devolve ``{'ok', 'estado', 'motivo', 'request_id'}``. O número reservado é
    devolvido à série sempre que o documento não chega a ser registado na AGT,
    evitando lacunas na numeração autorizada.
    """
    from django.db import transaction
    from django.utils import timezone
    from .models import ConfiguracaoAGT, SerieFaturaEletronica

    config = config or ConfiguracaoAGT.obter(fatura.banca_id)
    if config is None or not config.configurada:
        return {'ok': False, 'estado': fatura.estado,
                'motivo': 'Integração AGT não configurada.'}

    serie = resolver_serie(fatura)
    if serie is None:
        return {'ok': False, 'estado': fatura.estado,
                'motivo': 'Não existe uma série AGT comunicada para este tipo de documento.'}

    # Reserva o próximo número sequencial da série de forma atómica.
    with transaction.atomic():
        serie = SerieFaturaEletronica.objects.select_for_update().get(pk=serie.pk)
        sequencia = serie.proximo_numero()
        try:
            payload, submission_uuid, document_no = construir_payload_registo(
                fatura, config, sequencia
            )
        except AGTErro as exc:
            return {'ok': False, 'estado': fatura.estado,
                    'motivo': f'Falha ao preparar assinatura JWS: {exc}'}
        serie.numero_atual = sequencia
        serie.save(update_fields=['numero_atual'])

    fatura.serie = serie
    fatura.document_no = document_no
    fatura.submission_uuid = submission_uuid
    fatura.save(update_fields=['serie', 'document_no', 'submission_uuid'])

    try:
        resultado = submeter_fatura_directo(payload, config)
    except AGTErro as exc:
        serie.devolver_numero(sequencia)
        return {'ok': False, 'estado': fatura.estado, 'motivo': str(exc)}

    fatura.resposta_agt = json.dumps(resultado['resposta'], ensure_ascii=False)[:20000]

    if resultado['ok']:
        fatura.estado = 'Enviada AGT'
        fatura.request_id = resultado['request_id']
        fatura.data_envio_agt = timezone.now()
        fatura.save(update_fields=['estado', 'request_id', 'data_envio_agt', 'resposta_agt'])
        return {'ok': True, 'estado': 'Enviada AGT', 'request_id': resultado['request_id'],
                'motivo': f'Documento submetido à AGT (Request ID: {resultado["request_id"]}).'}

    # O documento não foi registado na AGT: devolve o número reservado à série.
    serie.devolver_numero(sequencia)

    if resultado.get('rejeitado'):
        fatura.estado = 'Rejeitada AGT'
        fatura.save(update_fields=['estado', 'resposta_agt'])
        return {'ok': True, 'estado': 'Rejeitada AGT',
                'motivo': 'A AGT rejeitou o documento. Consulte os erros no detalhe.'}

    # Falha transitória (rede ou 5xx): mantém-se em fila para nova tentativa.
    fatura.resposta_agt = (
        f'HTTP {resultado["status_code"]}: '
        + json.dumps(resultado['resposta'], ensure_ascii=False)
    )[:20000]
    fatura.save(update_fields=['resposta_agt'])
    return {'ok': False, 'estado': 'Em Fila',
            'motivo': f'Falha de comunicação com a AGT (HTTP {resultado["status_code"]}).'}


# ── Consulta de estado (obterEstado) ──────────────────────────────────

def construir_payload_estado(request_id, config):
    payload_assinatura = {
        'taxRegistrationNumber': config.tax_registration_number,
        'requestID': request_id,
    }
    return {
        'schemaVersion': '2.0',
        'submissionUUID': str(uuid.uuid4()),
        'taxRegistrationNumber': config.tax_registration_number,
        'submissionTimeStamp': _agora_iso(),
        'softwareInfo': construir_software_info(config),
        'requestID': request_id,
        'jwsSignature': assinar_jws(payload_assinatura, config.emissor_private_key),
    }


def consultar_estado(request_id, config):
    """Consulta o estado de validação de um pedido na AGT."""
    payload = construir_payload_estado(request_id, config)
    resp = _post_json(config.get_query_url(), payload)
    try:
        dados = resp.json()
    except ValueError:
        dados = {'raw': resp.text}
    return {'ok': resp.ok, 'status_code': resp.status_code, 'resposta': dados}


# ── Séries (solicitarSerie) ───────────────────────────────────────────

def solicitar_serie(serie, config):
    """Comunica/cria a série na AGT. Devolve ``{'ok', 'codigo_fiscal', ...}``."""
    ano = str(serie.ano)
    estabelecimento = serie.estabelecimento or 'SEDE'
    contingencia = 'S' if serie.contingencia else 'N'
    payload_assinatura = {
        'taxRegistrationNumber': config.tax_registration_number,
        'seriesYear': ano,
        'documentType': serie.tipo_documento,
        'establishmentNumber': estabelecimento,
        'seriesContingencyIndicator': contingencia,
    }
    payload = {
        'schemaVersion': '2.0',
        'submissionUUID': str(uuid.uuid4()),
        'taxRegistrationNumber': config.tax_registration_number,
        'submissionTimeStamp': _agora_iso(),
        'softwareInfo': construir_software_info(config),
        'seriesYear': ano,
        'documentType': serie.tipo_documento,
        'establishmentNumber': estabelecimento,
        'seriesContingencyIndicator': contingencia,
        'jwsSignature': assinar_jws(payload_assinatura, config.emissor_private_key),
    }
    resp = _post_json(config.get_serie_url(), payload)
    try:
        dados = resp.json()
    except ValueError:
        dados = {'raw': resp.text}

    resultado = dados.get('seriesFEResult') or {}
    erro_lista = [e for e in (dados.get('errorList') or []) if e]
    ok = resp.ok and bool(resultado.get('seriesCode')) and not erro_lista
    return {
        'ok': ok,
        'status_code': resp.status_code,
        'codigo_fiscal': resultado.get('seriesCode', ''),
        'primeiro_numero': resultado.get('firstDocumentNo'),
        'ultimo_numero': resultado.get('lastDocumentNo'),
        'quantidade': resultado.get('authorizedQuantity'),
        'erros': erro_lista,
        'resposta': dados,
    }


# ── Reconciliação de estado ───────────────────────────────────────────

def mapear_estado(valor):
    """Normaliza os estados devolvidos pela AGT para o ciclo de vida local."""
    if not valor:
        return None
    valor = str(valor).strip().lower()
    mapa = {
        'aprovada': 'Aprovada AGT', 'aprovado': 'Aprovada AGT', 'approved': 'Aprovada AGT',
        'aceite': 'Aprovada AGT', 'success': 'Aprovada AGT', 'ok': 'Aprovada AGT',
        'rejeitada': 'Rejeitada AGT', 'rejeitado': 'Rejeitada AGT',
        'rejected': 'Rejeitada AGT', 'erro': 'Rejeitada AGT', 'error': 'Rejeitada AGT',
        'cancelada': 'Cancelada', 'cancelado': 'Cancelada',
        'cancelled': 'Cancelada', 'canceled': 'Cancelada',
        'enviada': 'Enviada AGT', 'enviado': 'Enviada AGT', 'submitted': 'Enviada AGT',
        'pendente': 'Enviada AGT', 'processing': 'Enviada AGT', 'em processamento': 'Enviada AGT',
    }
    return mapa.get(valor)


def _extrair_estado(dados):
    """Extrai o estado de validação de uma resposta de obterEstado/callback.

    Devolve ``(estado, resolvido)`` onde ``resolvido`` indica se há evidência
    suficiente para alterar o estado local (evita aprovar por omissão).
    """
    if not isinstance(dados, dict):
        return None, False
    estado = mapear_estado(
        dados.get('estado') or dados.get('status') or dados.get('state')
        or dados.get('validationStatus')
    )
    if estado:
        return estado, True

    erros = dados.get('errorList') or dados.get('requestErrorList') or []
    if erros or dados.get('rejectedDocumentNo'):
        return 'Rejeitada AGT', True
    # Sem estado explícito e sem erros: ainda em processamento na AGT.
    return None, False


def reconciliar_fatura(fatura, config=None):
    """Consulta a AGT (obterEstado) e sincroniza o estado de uma fatura.

    Devolve ``{'ok', 'alterado', 'estado', 'motivo'}``.
    """
    from .models import ConfiguracaoAGT, registrar_historico

    if fatura.estado != 'Enviada AGT':
        return {'ok': False, 'alterado': False, 'estado': fatura.estado,
                'motivo': f'Estado "{fatura.estado}" não requer consulta.'}
    if not fatura.request_id:
        return {'ok': False, 'alterado': False, 'estado': fatura.estado,
                'motivo': 'Documento sem Request ID da AGT.'}

    config = config or ConfiguracaoAGT.obter(fatura.banca_id)
    if config is None or not config.configurada:
        return {'ok': False, 'alterado': False, 'estado': fatura.estado,
                'motivo': 'Integração AGT não configurada.'}

    try:
        resultado = consultar_estado(fatura.request_id, config)
    except AGTErro as exc:
        return {'ok': False, 'alterado': False, 'estado': fatura.estado,
                'motivo': str(exc)}

    dados = resultado.get('resposta')
    if not isinstance(dados, dict):
        dados = {'raw': dados}

    estado_novo, resolvido = _extrair_estado(dados)
    if not resolvido:
        return {'ok': True, 'alterado': False, 'estado': fatura.estado,
                'motivo': 'Estado ainda não disponível na AGT.'}

    estado_anterior = fatura.estado
    fatura.resposta_agt = json.dumps(dados, ensure_ascii=False)[:20000]
    if estado_novo and estado_novo != estado_anterior:
        fatura.estado = estado_novo
        fatura.save(update_fields=['estado', 'resposta_agt'])
        registrar_historico(
            'FaturaEletronica', fatura.pk, fatura.numero_fatura, 'Consulta AGT (obterEstado)',
            estado_anterior=estado_anterior, estado_novo=estado_novo,
            valor=fatura.total_geral, cliente_nome=fatura.cliente.nome,
            banca_id=fatura.banca_id, filial_id=fatura.filial_id,
        )
        return {'ok': True, 'alterado': True, 'estado': estado_novo,
                'motivo': f'Estado atualizado para {estado_novo}.'}

    fatura.save(update_fields=['resposta_agt'])
    return {'ok': True, 'alterado': False, 'estado': fatura.estado,
            'motivo': 'Estado confirmado sem alterações.'}
