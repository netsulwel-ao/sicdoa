"""Fila persistente e processamento dos callbacks (webhooks) da AGT.

Fluxo:
    1. O endpoint público valida a assinatura (JWS RS256 ou HMAC-SHA256);
    2. Guarda o payload bruto em ``CallbackAGT`` (auditoria + idempotência);
    3. Responde imediatamente à AGT;
    4. O evento é processado de imediato (por omissão) ou pela fila
       ``processar_callbacks_agt`` / APScheduler, actualizando o estado da
       fatura e registando o histórico.

A chave ``chave_evento`` (SHA-256 do corpo HTTP) impede que um reenvio da AGT
produza uma segunda actualização de estado.
"""

import hashlib
import json
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import agt_service
from .models import CallbackAGT, ConfiguracaoAGT, FaturaEletronica, registrar_historico

logger = logging.getLogger(__name__)

MAX_TENTATIVAS = int(getattr(settings, 'AGT_CALLBACK_MAX_TENTATIVAS', 5))


# ── Identificação do evento ───────────────────────────────────────────

def extrair_identificadores(payload):
    """Devolve ``(request_id, document_no)`` a partir do payload da AGT."""
    if not isinstance(payload, dict):
        return '', ''
    request_id = str(
        payload.get('request_id') or payload.get('requestID')
        or payload.get('requestId') or payload.get('id') or ''
    ).strip()
    document_no = str(
        payload.get('documentNo') or payload.get('numero_fatura')
        or payload.get('numeroFatura') or payload.get('documento_numero') or ''
    ).strip()
    return request_id, document_no


def _resumo_cabecalhos(headers):
    """Guarda os cabeçalhos relevantes, mascarando credenciais."""
    sensiveis = {
        'authorization', 'cookie', 'proxy-authorization',
        'x-agt-signature', 'x-signature',
    }
    resumo = {}
    for chave, valor in (headers or {}).items():
        nome = str(chave).lower()[:100]
        resumo[nome] = '***' if nome in sensiveis else str(valor)[:500]
    return resumo


# ── Registo do evento (fila) ──────────────────────────────────────────

def registar_evento(raw, data, headers=None, ip=None, assinatura_valida=False):
    """Persiste o payload bruto na fila. Devolve ``(evento, criado)``.

    Reenvios exactos do mesmo corpo devolvem o evento existente (idempotência).
    """
    raw = raw or b''
    chave = hashlib.sha256(raw).hexdigest()
    payload = data if isinstance(data, dict) else {}
    request_id, document_no = extrair_identificadores(payload)
    valores = {
        'request_id': request_id,
        'document_no': document_no,
        'assinatura_valida': bool(assinatura_valida),
        'payload_bruto': raw.decode('utf-8', errors='replace')[:200000],
        'payload': payload or None,
        'cabecalhos': _resumo_cabecalhos(headers),
        'origem_ip': ip or None,
    }

    try:
        evento, criado = CallbackAGT.objects.get_or_create(
            chave_evento=chave, defaults=valores,
        )
    except IntegrityError:
        # Corrida entre dois reenvios simultâneos: recupera o registo vencedor.
        evento = CallbackAGT.objects.get(chave_evento=chave)
        criado = False

    # Um reenvio pode chegar já com assinatura validada (ex.: primeira tentativa
    # falhou antes da validação). Actualiza os metadados sem duplicar o evento.
    if not criado and assinatura_valida and not evento.assinatura_valida:
        evento.assinatura_valida = True
        evento.save(update_fields=['assinatura_valida'])

    return evento, criado


# ── Processamento ─────────────────────────────────────────────────────

def _localizar_fatura(request_id, document_no):
    fatura = None
    if request_id:
        fatura = FaturaEletronica.objects.filter(request_id=request_id).first()
    if fatura is None and document_no:
        fatura = (
            FaturaEletronica.objects.filter(document_no=document_no).order_by('-pk').first()
            or FaturaEletronica.objects.filter(numero_fatura=document_no).order_by('-pk').first()
        )
    return fatura


def _derivar_estado(payload):
    """Normaliza o estado devolvido pela AGT para o ciclo de vida local."""
    estado, resolvido = agt_service.extrair_estado(payload)
    if resolvido and estado:
        return estado
    # O callback confirma o pedido: sem estado explícito, a presença de erros
    # determina rejeição; caso contrário o documento foi aprovado.
    erros = payload.get('errorList') or payload.get('requestErrorList') or []
    if erros or payload.get('rejectedDocumentNo'):
        return 'Rejeitada AGT'
    return 'Aprovada AGT'


def _marcar_erro(evento, mensagem):
    evento.tentativas = (evento.tentativas or 0) + 1
    evento.erro = str(mensagem)[:5000]
    if evento.tentativas >= MAX_TENTATIVAS:
        evento.estado_processamento = 'Erro'
    else:
        evento.estado_processamento = 'Pendente'
    evento.processado_em = None
    evento.save(update_fields=[
        'tentativas', 'erro', 'estado_processamento', 'processado_em',
    ])


def processar_evento(evento, config=None):
    """Processa um evento da fila e sincroniza o estado da fatura.

    Devolve ``{'ok', 'duplicado', 'estado', 'numero_fatura', 'motivo'}``.
    Nunca levanta excepções de negócio: falhas ficam registadas no evento para
    nova tentativa.
    """
    with transaction.atomic():
        evento = (
            CallbackAGT.objects.select_for_update()
            .select_related('fatura')
            .get(pk=evento.pk)
        )
        if evento.estado_processamento == 'Processado':
            return {
                'ok': True, 'duplicado': True,
                'estado': evento.fatura.estado if evento.fatura_id else '',
                'numero_fatura': evento.fatura.numero_fatura if evento.fatura_id else '',
                'motivo': 'Evento já processado (idempotência).',
            }

        payload = evento.payload or {}
        request_id, document_no = extrair_identificadores(payload)
        request_id = request_id or evento.request_id
        document_no = document_no or evento.document_no

        fatura = _localizar_fatura(request_id, document_no)
        if fatura is None:
            _marcar_erro(evento, 'Documento não encontrado no sistema.')
            return {
                'ok': False, 'duplicado': False, 'estado': '',
                'numero_fatura': '',
                'motivo': 'Documento não encontrado no sistema.',
            }

        evento.fatura = fatura
        if fatura.estado == 'Cancelada':
            evento.estado_processamento = 'Ignorado'
            evento.erro = ''
            evento.processado_em = timezone.now()
            evento.save(update_fields=[
                'fatura', 'estado_processamento', 'erro', 'processado_em',
            ])
            return {
                'ok': True, 'duplicado': False, 'estado': fatura.estado,
                'numero_fatura': fatura.numero_fatura,
                'motivo': 'Documento cancelado: evento ignorado.',
            }

        estado_novo = _derivar_estado(payload)
        estado_anterior = fatura.estado
        observacoes = (
            payload.get('observacoes') or payload.get('mensagem')
            or payload.get('message') or ''
        )

        fatura.estado = estado_novo
        fatura.resposta_agt = json.dumps(payload, ensure_ascii=False)[:20000]
        fatura.data_resposta_agt = timezone.now()
        campos = ['estado', 'resposta_agt', 'data_resposta_agt']
        if observacoes:
            fatura.observacoes = str(observacoes)[:5000]
            campos.append('observacoes')
        # Confirma o request_id quando o documento foi identificado pelo número.
        if request_id and not fatura.request_id:
            fatura.request_id = request_id
            campos.append('request_id')
        fatura.save(update_fields=campos)

        registrar_historico(
            'FaturaEletronica', fatura.pk, fatura.numero_fatura, 'Callback AGT',
            estado_anterior=estado_anterior, estado_novo=estado_novo,
            valor=fatura.total_geral, cliente_nome=fatura.cliente.nome,
            banca_id=fatura.banca_id, filial_id=fatura.filial_id,
        )

        evento.request_id = fatura.request_id or ''
        evento.document_no = fatura.document_no or document_no
        evento.estado_processamento = 'Processado'
        evento.erro = ''
        evento.processado_em = timezone.now()
        evento.save(update_fields=[
            'fatura', 'request_id', 'document_no', 'estado_processamento',
            'erro', 'processado_em',
        ])

        return {
            'ok': True, 'duplicado': False, 'estado': estado_novo,
            'numero_fatura': fatura.numero_fatura,
            'motivo': f'Estado actualizado para {estado_novo}.',
        }


def processar_pendentes(limite=50):
    """Processa os eventos pendentes da fila. Devolve contadores."""
    ids = list(
        CallbackAGT.objects
        .filter(estado_processamento='Pendente')
        .order_by('recebido_em', 'pk')
        .values_list('pk', flat=True)[:limite]
    )
    resultado = {'total': len(ids), 'processados': 0, 'ignorados': 0, 'erros': 0}
    for evento_id in ids:
        evento = CallbackAGT.objects.filter(pk=evento_id).first()
        if evento is None:
            continue
        try:
            saida = processar_evento(evento)
        except Exception as exc:  # noqa: BLE001 - a fila não pode parar
            logger.exception('Falha ao processar callback AGT #%s', evento_id)
            _marcar_erro(evento, f'Erro inesperado: {exc}')
            resultado['erros'] += 1
            continue
        if not saida.get('ok'):
            resultado['erros'] += 1
        elif saida.get('estado') == 'Cancelada':
            resultado['ignorados'] += 1
        else:
            resultado['processados'] += 1
    return resultado
