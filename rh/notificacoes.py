"""
Notificações do módulo RH: in-app (NotificacaoRH) + email.
"""
import logging
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


def _notificar_in_app(banca, destinatario, tipo, titulo, mensagem, link=''):
    from .models import NotificacaoRH
    NotificacaoRH.objects.create(
        banca=banca,
        destinatario=destinatario,
        tipo=tipo,
        titulo=titulo,
        mensagem=mensagem,
        link=link,
    )


def _notificar_email(destinatario_obj, assunto, texto_html):
    from utils.email_utils import _enviar
    if not destinatario_obj or not destinatario_obj.email:
        return
    _enviar(
        assunto=assunto,
        texto='',
        html=texto_html,
        destinatarios=[destinatario_obj.email],
    )


def _url_presencas(request=None):
    if not request:
        hoje = timezone.now().date()
        return f'{reverse("rh_presencas")}?mes={hoje.month}&ano={hoje.year}'
    base = request.build_absolute_uri(reverse('rh_presencas'))
    hoje = timezone.now().date()
    return f'{base}?mes={hoje.month}&ano={hoje.year}'


def notificar_presenca_pendente(registo, banca, responsavel, request=None):
    link = _url_presencas(request)
    _notificar_in_app(
        banca=banca, destinatario=responsavel,
        tipo='aprovacao_pendente',
        titulo='Presença pendente de aprovação',
        mensagem=f'{registo.colaborador.nome} tem um registo de presença ({registo.tipo}) '
                 f'de {registo.data} pendente.',
        link=link,
    )
    _notificar_email(
        responsavel,
        'SICDOA — Presença pendente de aprovação',
        f'<p>Olá {responsavel.nome},</p>'
        f'<p>{registo.colaborador.nome} tem um registo de presença ({registo.tipo}) '
        f'de {registo.data} pendente de aprovação.</p>'
        f'<p><a href="{link}">Ver presenças</a></p>',
    )


def notificar_ferias_pendente(pedido, banca, responsavel, request=None):
    link = _url_presencas(request)
    _notificar_in_app(
        banca=banca, destinatario=responsavel,
        tipo='aprovacao_pendente',
        titulo='Pedido de férias pendente',
        mensagem=f'{pedido.colaborador.nome} solicitou férias de {pedido.data_inicio} a {pedido.data_fim}.',
        link=link,
    )
    _notificar_email(
        responsavel,
        'SICDOA — Pedido de férias pendente',
        f'<p>Olá {responsavel.nome},</p>'
        f'<p>{pedido.colaborador.nome} solicitou férias de {pedido.data_inicio} a {pedido.data_fim}.</p>'
        f'<p><a href="{link}">Ver pedidos</a></p>',
    )


def notificar_aprovado(registo_ou_pedido, banca, colaborador, tipo_registo):
    if tipo_registo == 'presenca':
        titulo = 'Presença aprovada'
        mensagem = f'A sua presença de {registo_ou_pedido.data} foi aprovada.'
        assunto = 'SICDOA — Presença aprovada'
        corpo = f'<p>Olá {colaborador.nome},</p><p>A sua presença de {registo_ou_pedido.data} foi aprovada.</p>'
    else:
        titulo = 'Férias aprovadas'
        mensagem = f'O seu pedido de férias ({registo_ou_pedido.data_inicio} a {registo_ou_pedido.data_fim}) foi aprovado.'
        assunto = 'SICDOA — Férias aprovadas'
        corpo = f'<p>Olá {colaborador.nome},</p><p>O seu pedido de férias ({registo_ou_pedido.data_inicio} a {registo_ou_pedido.data_fim}) foi aprovado.</p>'
    _notificar_in_app(
        banca=banca, destinatario=colaborador,
        tipo='pedido_aprovado', titulo=titulo, mensagem=mensagem,
    )
    _notificar_email(colaborador, assunto, corpo)


def notificar_rejeitado(registo_ou_pedido, banca, colaborador, tipo_registo, motivo=''):
    if tipo_registo == 'presenca':
        titulo = 'Presença rejeitada'
        mensagem = f'A sua presença de {registo_ou_pedido.data} foi rejeitada.'
        assunto = 'SICDOA — Presença rejeitada'
        corpo = f'<p>Olá {colaborador.nome},</p><p>A sua presença de {registo_ou_pedido.data} foi rejeitada.</p>'
    else:
        titulo = 'Férias rejeitadas'
        mensagem = f'O seu pedido de férias ({registo_ou_pedido.data_inicio} a {registo_ou_pedido.data_fim}) foi rejeitado.'
        assunto = 'SICDOA — Férias rejeitadas'
        corpo = f'<p>Olá {colaborador.nome},</p><p>O seu pedido de férias ({registo_ou_pedido.data_inicio} a {registo_ou_pedido.data_fim}) foi rejeitado.</p>'
    if motivo:
        mensagem += f' Motivo: {motivo}'
        corpo += f'<p><strong>Motivo:</strong> {motivo}</p>'
    _notificar_in_app(
        banca=banca, destinatario=colaborador,
        tipo='pedido_rejeitado', titulo=titulo, mensagem=mensagem,
    )
    _notificar_email(colaborador, assunto, corpo)


def notificar_delegacao_recebida(delegacao):
    _notificar_in_app(
        banca=delegacao.banca, destinatario=delegacao.delegado,
        tipo='delegacao_recebida',
        titulo='Delegação de aprovação recebida',
        mensagem=f'{delegacao.delegante.nome} delegou-lhe a autoridade de aprovação '
                 f'de {delegacao.data_inicio} a {delegacao.data_fim}.',
        link=reverse('rh_presencas'),
    )
