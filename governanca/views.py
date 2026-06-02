import json
import random
import hashlib
import hmac
import time
import urllib.parse

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.cache import cache
from utils.cache_utils import cache_get_or_set, safe_cache_key, cache_invalidate_prefix

from users.models import Usuario
from users.auth_decorators import sessao_expirada, limpar_sessao
from utils.email_utils import _enviar
from .models import (
    QuotaConfig, QuotaGerada, PagamentoQuota, EstadoFinanceiro,
    CertidaoRegularidade, CarteiraProfissional,
    CategoriaMembro, TipoQuota,
    Assembleia, PautaVotacao, PresencaAssembleia,
    Procuracao, Voto, ReciboVoto, ManifestoIntegridade, AtaDigital, Notificacao,
    DocumentoAssembleia, MembroMesa, MensagemChat,
    ConsultaPublica, ArtigoDocumento, Comentario,
    VotacaoConsulta, VotoConsulta, RelatorioConsulta,
    Convocatoria, RespostaPresenca, LogAssembleia,
)


# â”€â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _get_usuario(request):
    if not request.session.get('usuario_id'):
        return None
    if sessao_expirada(request):
        limpar_sessao(request)
        return None
    return request.session.get('usuario')


def _requer_login(view_func):
    def wrapper(request, *args, **kwargs):
        usuario = _get_usuario(request)
        if not usuario:
            return redirect('login')
        request.usuario_obj = Usuario.objects.get(id=request.session['usuario_id'])
        return view_func(request, *args, **kwargs)
    return wrapper


def _criar_notificacao(usuario_id, tipo, titulo, mensagem='', link=''):
    Notificacao.objects.create(
        usuario_id=usuario_id,
        tipo=tipo,
        titulo=titulo,
        mensagem=mensagem,
        link=link,
    )
    cache_invalidate_prefix(f'dash_governanca_{usuario_id}')


def _notificar_para_papel(papel, tipo, titulo, mensagem='', link=''):
    usuarios = list(Usuario.objects.filter(papel=papel, status='Ativo').values_list('id', flat=True))
    if not usuarios:
        return
    if getattr(settings, 'REDIS_ENABLED', False):
        from governanca.tasks import notificar_utilizadores_task
        notificar_utilizadores_task.delay(usuarios, tipo, titulo, mensagem, link)
    else:
        for u_id in usuarios:
            _criar_notificacao(u_id, tipo, titulo, mensagem, link)


def _gerar_otp():
    return f'{random.randint(100000, 999999)}'


def _b64url(data):
    return __import__('base64').urlsafe_b64encode(data).rstrip(b'=').decode()

def _livekit_token(room_name, identity):
    api_key = settings.LIVEKIT_API_KEY
    api_secret = settings.LIVEKIT_API_SECRET
    header = {'alg': 'HS256', 'typ': 'JWT'}
    now = int(time.time())
    payload = {
        'iss': api_key,
        'sub': identity,
        'nbf': now - 10,
        'exp': now + 3600,
        'identity': identity,
        'video': {
            'room': room_name,
            'roomJoin': True,
            'canPublish': True,
            'canSubscribe': True,
            'canPublishSources': ['camera', 'microphone', 'screen_share'],
        },
    }
    header_b64 = _b64url(json.dumps(header, separators=(',', ':')).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(',', ':')).encode())
    sig = hmac.new(api_secret.encode(), f'{header_b64}.{payload_b64}'.encode(), hashlib.sha256).digest()
    sig_b64 = _b64url(sig)
    return f'{header_b64}.{payload_b64}.{sig_b64}'


def _broadcast_ws(assembleia_id, event_type, data):
    """Envia evento WebSocket para todos os conectados na sala da assembleia."""
    try:
        layer = get_channel_layer()
        if layer is None:
            print(f'[BROADCAST WS] ERRO: channel_layer is None')
            return
        async_to_sync(layer.group_send)(
            f'assembleia_{assembleia_id}',
            {'type': event_type, 'data': data},
        )
    except Exception as e:
        print(f'[BROADCAST WS] ERRO: {e}')


def _get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _log_assembleia(assembleia_id, usuario_id, acao, detalhes=None, ip=''):
    LogAssembleia.objects.create(
        assembleia_id=assembleia_id,
        usuario_id=usuario_id,
        acao=acao,
        detalhes=detalhes or {},
        ip=ip or '',
    )


def _verificar_elegibilidade(usuario_id):
    ef = EstadoFinanceiro.objects.filter(despachante_id=usuario_id).first()
    if ef and ef.estado == 'Irregular':
        return False, 'Status financeiro irregular — direito de voto suspenso. Acesso ao streaming autorizado.'
    return True, ''


# â”€â”€â”€ Páginas Principais â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_requer_login
def index(request):
    usuario_obj = request.usuario_obj
    hoje = timezone.now()

    if usuario_obj.papel == 'Administrador':
        qs_quotas = QuotaGerada.objects.all()
        quotas_pendentes = qs_quotas.filter(status='Pendente').count()
        quotas_pagas = qs_quotas.filter(status='Paga').count()
    else:
        qs_quotas = QuotaGerada.objects.filter(despachante=usuario_obj)
        quotas_pendentes = qs_quotas.filter(status='Pendente').count()
        quotas_pagas = qs_quotas.filter(status='Paga').count()
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'assembleias': Assembleia.objects.all()[:5],
        'proximas': Assembleia.objects.filter(status='Agendada', data_hora__gte=hoje).order_by('data_hora')[:5],
        'assembleias_em_curso': Assembleia.objects.filter(status='Em Curso')[:5],
        'total_assembleias': Assembleia.objects.count(),
        'documentos_recentes': DocumentoAssembleia.objects.filter(publicado=True).select_related('assembleia', 'created_by').order_by('-created_at')[:5],
        'total_docs_publicados': DocumentoAssembleia.objects.filter(publicado=True).count(),
        'notificacoes_nao_lidas': Notificacao.objects.filter(usuario=usuario_obj, lida=False).count(),
        'quotas_pendentes': quotas_pendentes,
        'quotas_pagas': quotas_pagas,
        'assembleias_concluidas': Assembleia.objects.filter(status='Concluida').order_by('-data_hora'),
    }
    return render(request, 'governanca/index.html', context)


@_requer_login
def lista_assembleias(request):
    status_filtro = request.GET.get('status', '')
    qs = Assembleia.objects.all()
    agora = timezone.now()
    qs.filter(status='Agendada', data_hora__lte=agora).update(status='Em Curso')
    if status_filtro:
        qs = qs.filter(status=status_filtro)
    from itertools import chain
    STATUS_CHOICES = [
        ('', 'Todas'),
        ('Agendada', 'Agendadas'),
        ('Em Curso', 'Em Curso'),
        ('Concluida', 'Concluidas'),
        ('Cancelada', 'Canceladas'),
    ]
    paginator = Paginator(qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'active_sub': 'assembleias',
        'assembleias': page_obj,
        'page_obj': page_obj,
        'status_atual': status_filtro,
        'status_choices': STATUS_CHOICES,
    }
    return render(request, 'governanca/lista_assembleias.html', context)


@_requer_login
def nova_assembleia(request):
    papel = request.session['usuario']['papel']
    if papel != 'Administrador':
        messages.error(request, 'Sem permissão para criar assembleias.')
        return redirect('governanca_assembleias')

    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        descricao = request.POST.get('descricao', '').strip()
        data_hora_str = request.POST.get('data_hora', '').strip()
        livekit_room = request.POST.get('livekit_room', '').strip()
        iniciar_agora = request.POST.get('iniciar_agora') == 'on'
        quorum_minimo = request.POST.get('quorum_minimo', '').strip()

        if not titulo:
            messages.error(request, 'Preencha todos os campos obrigatórios.')
            return render(request, 'governanca/nova_assembleia.html', {**locals()})

        if iniciar_agora:
            data_hora = timezone.now()
        else:
            if not data_hora_str:
                messages.error(request, 'Preencha a data e hora.')
                return render(request, 'governanca/nova_assembleia.html', {**locals()})
            from django.utils.dateparse import parse_datetime
            from django.utils.timezone import make_aware
            data_hora = parse_datetime(data_hora_str)
            if not data_hora:
                messages.error(request, 'Data/hora inválida.')
                return render(request, 'governanca/nova_assembleia.html', {**locals()})
            if timezone.is_naive(data_hora):
                data_hora = make_aware(data_hora)
            if data_hora <= timezone.now():
                messages.error(request, 'A data e hora deve ser posterior ao momento atual.')
                return render(request, 'governanca/nova_assembleia.html', {**locals()})

        if not livekit_room:
            livekit_room = f'assembleia-{int(time.time())}'

        if iniciar_agora:
            status = 'Em Curso'
        else:
            status = 'Agendada'

        total_ativos = Usuario.objects.filter(status='Ativo').count()
        try:
            quorum_minimo_val = int(quorum_minimo) if quorum_minimo else total_ativos
        except (ValueError, TypeError):
            quorum_minimo_val = total_ativos

        assembleia = Assembleia.objects.create(
            titulo=titulo,
            descricao=descricao,
            data_hora=data_hora,
            status=status,
            local='Sala Virtual CDOA',
            livekit_room=livekit_room,
            quorum_minimo=quorum_minimo_val,
            total_eleitores=total_ativos,
            max_procuracao=1,
            created_by=request.usuario_obj,
        )

        if iniciar_agora:
            _notificar_para_papel(
                'Administrador', 'assembleia_iniciada',
                f'Assembleia em curso: {titulo}',
                f'Assembleia iniciada instantaneamente. Entre na sala virtual!',
                f'/governanca/assembleia/{assembleia.pk}/sala/'
            )
            _notificar_para_papel(
                'Despachante Oficial', 'assembleia_iniciada',
                f'Assembleia em curso: {titulo}',
                f'Assembleia iniciada instantaneamente. Entre na sala virtual!',
                f'/governanca/assembleia/{assembleia.pk}/sala/'
            )
        else:
            _notificar_para_papel(
                'Administrador', 'assembleia_agendada',
                f'Nova Assembleia: {titulo}',
                f'Foi agendada uma nova assembleia para {data_hora:%d/%m/%Y às %H:%M}.',
                f'/governanca/assembleia/{assembleia.pk}/'
            )
            _notificar_para_papel(
                'Despachante Oficial', 'assembleia_agendada',
                f'Assembleia Agendada: {titulo}',
                f'Foi agendada uma assembleia para {data_hora:%d/%m/%Y às %H:%M}. Participe!',
                f'/governanca/assembleia/{assembleia.pk}/'
            )

        for u in Usuario.objects.filter(status='Ativo', papel__in=['Administrador', 'Despachante Oficial']).exclude(email=''):
            if iniciar_agora:
                assunto = f'Assembleia em curso: {titulo}'
                corpo = f'Prezado(a) {u.nome},\n\nA assembleia "{titulo}" foi iniciada e já está em curso.\n\nEntre na sala virtual: {getattr(settings, "SITE_URL", "http://127.0.0.1:8000")}/governanca/assembleia/{assembleia.pk}/sala/\n\nAtenciosamente,\nCDOA'
            else:
                assunto = f'Assembleia Agendada: {titulo}'
                corpo = f'Prezado(a) {u.nome},\n\nFoi agendada uma nova assembleia:\n\n  Título: {titulo}\n  Data: {data_hora:%d/%m/%Y às %H:%M}\n  Descrição: {descricao}\n\nParticipe em: {getattr(settings, "SITE_URL", "http://127.0.0.1:8000")}/governanca/assembleia/{assembleia.pk}/\n\nAtenciosamente,\nCDOA'
            _enviar(assunto, corpo, None, [u.email])

        pautas_titulos = request.POST.getlist('pauta_titulo[]')
        pautas_descricoes = request.POST.getlist('pauta_descricao[]')
        pautas_tipos = request.POST.getlist('pauta_tipo[]')
        for i, titulo in enumerate(pautas_titulos):
            if titulo.strip():
                PautaVotacao.objects.create(
                    assembleia=assembleia,
                    titulo=titulo.strip(),
                    descricao=(pautas_descricoes[i] if i < len(pautas_descricoes) else ''),
                    tipo_votacao=(pautas_tipos[i] if i < len(pautas_tipos) else 'Aberta'),
                    ordem=i + 1,
                )

        messages.success(request, 'Assembleia criada com sucesso!')
        return redirect('governanca_detalhe', pk=assembleia.pk)

    total_ativos = Usuario.objects.filter(status='Ativo').count()
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'active_sub': 'assembleias',
        'total_ativos': total_ativos,
    }
    return render(request, 'governanca/nova_assembleia.html', context)


@_requer_login
def detalhe_assembleia(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    if assembleia.status == 'Agendada' and assembleia.data_hora <= timezone.now():
        assembleia.status = 'Em Curso'
        assembleia.save(update_fields=['status'])
    usuario_id = request.session['usuario_id']
    minhas_procuracao = Procuracao.objects.filter(outorgante_id=usuario_id, assembleia=assembleia)
    procuracao_recebidas = Procuracao.objects.filter(outorgado_id=usuario_id, assembleia=assembleia)
    tenho_presenca = PresencaAssembleia.objects.filter(assembleia=assembleia, usuario_id=usuario_id, presente_em__isnull=False).exists()
    ja_votei_pautas = set(
        Voto.objects.filter(pauta__assembleia=assembleia, usuario_id=usuario_id, em_delegacao=False)
        .values_list('pauta_id', flat=True)
    )
    documentos = assembleia.documentos.filter(publicado=True)

    minha_resposta_obj = RespostaPresenca.objects.filter(assembleia=assembleia, usuario_id=usuario_id).first()

    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'assembleia': assembleia,
        'minhas_procuracao': minhas_procuracao,
        'procuracao_recebidas': procuracao_recebidas,
        'tenho_presenca': tenho_presenca,
        'ja_votei_pautas': ja_votei_pautas,
        'despachantes': Usuario.objects.filter(papel__in=['Administrador', 'Despachante Oficial'], status='Ativo').exclude(id=usuario_id),
        'documentos': documentos,
        'minha_resposta': minha_resposta_obj.resposta if minha_resposta_obj else None,
    }
    return render(request, 'governanca/detalhe_assembleia.html', context)


@_requer_login
def editar_assembleia(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    papel = request.session['usuario']['papel']
    if papel != 'Administrador':
        messages.error(request, 'Sem permissão.')
        return redirect('governanca_detalhe', pk=pk)

    if request.method == 'POST':
        assembleia.titulo = request.POST.get('titulo', assembleia.titulo)
        assembleia.descricao = request.POST.get('descricao', assembleia.descricao)
        data_hora_str = request.POST.get('data_hora', '').strip()
        if data_hora_str:
            from django.utils.dateparse import parse_datetime
            assembleia.data_hora = parse_datetime(data_hora_str) or assembleia.data_hora
        assembleia.link_streaming = request.POST.get('link_streaming', assembleia.link_streaming)
        assembleia.local = request.POST.get('local', '').strip() or 'Sala Virtual CDOA'
        assembleia.livekit_room = request.POST.get('livekit_room', assembleia.livekit_room)
        quorum_str = request.POST.get('quorum_minimo', '').strip()
        if quorum_str:
            try:
                assembleia.quorum_minimo = int(quorum_str)
            except (ValueError, TypeError):
                pass
        assembleia.save()

        pautas_titulos = request.POST.getlist('pauta_titulo[]')
        pautas_descricoes = request.POST.getlist('pauta_descricao[]')
        pautas_tipos = request.POST.getlist('pauta_tipo[]')
        for i, titulo in enumerate(pautas_titulos):
            if titulo.strip():
                PautaVotacao.objects.create(
                    assembleia=assembleia,
                    titulo=titulo.strip(),
                    descricao=(pautas_descricoes[i] if i < len(pautas_descricoes) else ''),
                    tipo_votacao=(pautas_tipos[i] if i < len(pautas_tipos) else 'Aberta'),
                    ordem=i + 1,
                )

        messages.success(request, 'Assembleia atualizada!')
        return redirect('governanca_detalhe', pk=pk)

    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'assembleia': assembleia,
    }
    return render(request, 'governanca/editar_assembleia.html', context)


# â”€â”€â”€ Sala da Assembleia (Fase 2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_requer_login
def sala_assembleia(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    usuario_id = request.session['usuario_id']

    if assembleia.status == 'Agendada':
        if assembleia.data_hora <= timezone.now():
            assembleia.status = 'Em Curso'
            assembleia.save()
        else:
            messages.warning(request, 'A assembleia ainda não começou.')
            return redirect('governanca_detalhe', pk=pk)

    presencia, created = PresencaAssembleia.objects.get_or_create(
        assembleia=assembleia,
        usuario_id=usuario_id,
        defaults={'presente_em': timezone.now()},
    )
    if not presencia.presente_em:
        presencia.presente_em = timezone.now()
        presencia.save()

    pauta_ativa = assembleia.pautas.filter(status='Em Votacao').first()

    if not MembroMesa.objects.filter(assembleia=assembleia).exists() and assembleia.created_by:
        MembroMesa.objects.get_or_create(
            assembleia=assembleia, usuario=assembleia.created_by,
            defaults={'funcao': 'Presidente', 'ordem': 0},
        )

    minhas_procuracao = Procuracao.objects.filter(
        outorgado_id=usuario_id, assembleia=assembleia, status='Confirmada'
    ).select_related('outorgante')
    # minhas_procuracao: procurações onde sou outorgado (recebi o poder de voto)

    pautas_ja_votadas = set(
        Voto.objects.filter(usuario_id=usuario_id, em_delegacao=False)
        .values_list('pauta_id', flat=True)
    )
    pautas_voto_delegado = set(
        Voto.objects.filter(
            usuario_id=usuario_id, em_delegacao=True, delegado_de__isnull=False
        ).values_list('pauta_id', 'delegado_de_id')
    )

    livekit_token = ''
    if assembleia.livekit_room:
        livekit_token = _livekit_token(
            assembleia.livekit_room,
            request.session['usuario']['nome'],
        )

    elegivel, _ = _verificar_elegibilidade(usuario_id)

    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'assembleia': assembleia,
        'pautas': assembleia.pautas.with_vote_counts(),
        'pauta_ativa': pauta_ativa,
        'minhas_procuracao': minhas_procuracao,
        'pautas_ja_votadas': pautas_ja_votadas,
        'pautas_voto_delegado': pautas_voto_delegado,
        'livekit_token': livekit_token,
        'livekit_url': settings.LIVEKIT_URL,
        'ws_url': f'{"ws" if not request.is_secure() else "wss"}://{request.get_host()}/ws/assembleia/{pk}/',
        'presentes': assembleia.presencas.filter(presente_em__isnull=False).select_related('usuario'),
        'mesa': MembroMesa.objects.filter(assembleia=assembleia).select_related('usuario'),
        'despachantes': Usuario.objects.filter(
            papel__in=['Administrador', 'Despachante Oficial'], status='Ativo'
        ).exclude(id=usuario_id) if request.session['usuario']['papel'] == 'Administrador' else [],
        'elegivel': elegivel,
    }
    return render(request, 'governanca/sala_assembleia.html', context)


# â”€â”€â”€ Gestão / Mesa (Admin) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_requer_login
def gerir_assembleia(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    papel = request.session['usuario']['papel']
    if papel != 'Administrador':
        messages.error(request, 'Sem permissão.')
        return redirect('governanca_detalhe', pk=pk)

    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': papel,
        'active_menu': 'Governanca',
        'assembleia': assembleia,
        'pautas': assembleia.pautas.with_vote_counts(),
        'presentes': assembleia.presencas.filter(presente_em__isnull=False).select_related('usuario'),
        'procuracao': Procuracao.objects.filter(assembleia=assembleia).select_related('outorgante', 'outorgado'),
        'documentos': assembleia.documentos.all(),
        'mesa': MembroMesa.objects.filter(assembleia=assembleia).select_related('usuario'),
        'despachantes': Usuario.objects.filter(
            papel__in=['Administrador', 'Despachante Oficial'], status='Ativo'
        ).exclude(id=request.session['usuario_id']),
        'tem_convocatoria_publicada': assembleia.convocatorias.filter(status='Publicada').exists(),
    }
    return render(request, 'governanca/gerir_assembleia.html', context)


# â”€â”€â”€ Repositório de Atas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@_requer_login
def repositorio_atas(request):
    page_number = request.GET.get('page', '1')
    cache_key = safe_cache_key('repositorio_atas', page_number)

    def _compute():
        atas = AtaDigital.objects.filter(publicado_em__isnull=False).select_related('assembleia', 'assinado_por')
        documentos = DocumentoAssembleia.objects.filter(publicado=True).select_related('assembleia', 'created_by')
        paginator = Paginator(atas, 8)
        page_obj = paginator.get_page(page_number)
        return {
            'atas': page_obj,
            'page_obj': page_obj,
            'documentos': list(documentos),
        }

    cached = cache_get_or_set(cache_key, _compute, timeout=300)
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'active_sub': 'atas',
        **cached,
    }
    return render(request, 'governanca/repositorio_atas.html', context)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# API - Presença
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_registar_presenca(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    usuario_id = request.session['usuario_id']
    obj, created = PresencaAssembleia.objects.get_or_create(
        assembleia=assembleia, usuario_id=usuario_id,
        defaults={'presente_em': timezone.now()},
    )
    if not obj.presente_em:
        obj.presente_em = timezone.now()
        obj.save()

    _broadcast_ws(pk, 'quorum_update', {
        'presentes': assembleia.presentes_count,
        'quorum_minimo': assembleia.quorum_minimo,
        'atingido': assembleia.quorum_atingido,
        'total_eleitores': assembleia.total_eleitores,
    })

    _log_assembleia(assembleia.id, usuario_id, 'entrada', {}, ip=_get_client_ip(request))

    return JsonResponse({
        'status': 'ok', 'presente': True,
        'presentes_count': assembleia.presentes_count,
        'quorum': assembleia.quorum_minimo,
        'quorum_atingido': assembleia.quorum_atingido,
    })


@_requer_login
def api_listar_presencas(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    presencas = assembleia.presencas.filter(presente_em__isnull=False).select_related('usuario')
    data = [{
        'id': p.usuario.id,
        'nome': p.usuario.nome,
        'email': p.usuario.email,
        'presente_em': p.presente_em.isoformat() if p.presente_em else None,
    } for p in presencas]
    return JsonResponse({
        'presentes': data,
        'total': len(data),
        'quorum_minimo': assembleia.quorum_minimo,
        'quorum_atingido': assembleia.quorum_atingido,
    })


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# API - Procuração
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_solicitar_procuracao(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    outorgante_id = request.session['usuario_id']

    existing = Procuracao.objects.filter(assembleia=assembleia, outorgante_id=outorgante_id).first()
    if existing and existing.status != 'Cancelada':
        return JsonResponse({'status': 'error', 'message': 'Já possui uma procuração ativa para esta assembleia.'}, status=400)
    if existing and existing.status == 'Cancelada':
        existing.delete()

    data = json.loads(request.body)
    outorgado_id = data.get('outorgado_id')
    if not outorgado_id:
        return JsonResponse({'status': 'error', 'message': 'Destinatário não informado.'}, status=400)

    # Validar limite de procurações por outorgado
    procuracao_ativas = Procuracao.objects.filter(
        assembleia=assembleia, outorgado_id=outorgado_id, status='Confirmada'
    ).count()
    max_proc = assembleia.max_procuracao
    if procuracao_ativas >= max_proc:
        return JsonResponse({
            'status': 'error',
            'message': f'Limite máximo de {max_proc} procuração(ões) atingido para este membro.'
        }, status=400)

    otp = _gerar_otp()
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    procuracao = Procuracao.objects.create(
        assembleia=assembleia,
        outorgante_id=outorgante_id,
        outorgado_id=outorgado_id,
        codigo_otp=otp_hash,
    )
    _criar_notificacao(
        outorgado_id, 'procuracao_solicitada',
        'Procuração Solicitada',
        f'{request.session["usuario"]["nome"]} solicitou-lhe procuração para {assembleia.titulo}.',
        f'/governanca/assembleia/{assembleia.pk}/'
    )
    request.session['otp_plaintext'] = otp
    request.session['otp_procuracao_id'] = procuracao.id

    outorgante = Usuario.objects.get(id=outorgante_id)
    if outorgante.email:
        _enviar(
            'Código OTP â€” Procuração â€” CDOA',
            f'Prezado(a) {outorgante.nome},\n\n'
            f'O seu código OTP para confirmar a procuração na assembleia "{assembleia.titulo}" é:\n\n'
            f'  {otp}\n\n'
            f'O código expira após a primeira utilização.\n\n'
            f'Atenciosamente,\nSICDOA',
            None,
            [outorgante.email],
        )
    else:
        logger = __import__('logging').getLogger(__name__)
        logger.warning('Outorgante %s não tem email cadastrado â€” OTP não enviado por email', outorgante.nome)
    _log_assembleia(assembleia.id, outorgante_id, 'procuracao_solicitada', {
        'outorgado_id': outorgado_id,
        'procuracao_id': procuracao.id,
    }, ip=_get_client_ip(request))

    return JsonResponse({
        'status': 'ok',
        'procuracao_id': procuracao.id,
        'message': 'Código OTP enviado para o seu email. Verifique a sua caixa de entrada.',
    })


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_confirmar_procuracao(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    data = json.loads(request.body)
    codigo = data.get('codigo_otp', '')
    procuracao_id = data.get('procuracao_id')
    procuracao = get_object_or_404(Procuracao, pk=procuracao_id, assembleia=assembleia, outorgante_id=request.session['usuario_id'])

    if procuracao.status != 'Pendente':
        return JsonResponse({'status': 'error', 'message': 'Procuração já foi processada.'}, status=400)

    otp_hash_input = hashlib.sha256(codigo.encode()).hexdigest()
    otp_session = request.session.get('otp_plaintext', '')
    if procuracao.codigo_otp != otp_hash_input and otp_session != codigo:
        return JsonResponse({'status': 'error', 'message': 'Código OTP inválido.'}, status=400)

    procuracao.status = 'Confirmada'
    procuracao.confirmado_em = timezone.now()
    procuracao.save()

    _criar_notificacao(
        procuracao.outorgado_id, 'procuracao_confirmada',
        'Procuração Confirmada',
        f'{request.session["usuario"]["nome"]} confirmou a procuração para {assembleia.titulo}. Agora tem um voto delegado.',
        f'/governanca/assembleia/{assembleia.pk}/'
    )
    _log_assembleia(assembleia.id, request.session['usuario_id'], 'procuracao_confirmada', {
        'outorgado_id': procuracao.outorgado_id,
        'procuracao_id': procuracao.id,
    }, ip=_get_client_ip(request))
    return JsonResponse({'status': 'ok', 'message': 'Procuração confirmada com sucesso!'})


@_requer_login
def api_minhas_procuracao(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    usuario_id = request.session['usuario_id']
    como_outorgante = Procuracao.objects.filter(assembleia=assembleia, outorgante_id=usuario_id).select_related('outorgado')
    como_outorgado = Procuracao.objects.filter(assembleia=assembleia, outorgado_id=usuario_id).select_related('outorgante')
    data = {
        'como_outorgante': [{
            'id': p.id, 'nome': p.outorgado.nome,
            'status': p.status, 'confirmado_em': p.confirmado_em.isoformat() if p.confirmado_em else None,
        } for p in como_outorgante],
        'como_outorgado': [{
            'id': p.id, 'nome': p.outorgante.nome,
            'outorgante_id': p.outorgante_id,
            'status': p.status, 'confirmado_em': p.confirmado_em.isoformat() if p.confirmado_em else None,
        } for p in como_outorgado],
    }
    return JsonResponse(data)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# API - Votação
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_iniciar_votacao(request, pk):
    pauta = get_object_or_404(PautaVotacao, pk=pk)
    papel = request.session['usuario']['papel']
    if papel != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores podem abrir votaçÃµes.'}, status=403)
    if pauta.assembleia.status != 'Em Curso':
        return JsonResponse({'status': 'error', 'message': 'Assembleia não está em curso.'}, status=400)
    if pauta.status == 'Concluida':
        return JsonResponse({'status': 'error', 'message': 'Votação já foi concluída.'}, status=400)

    pauta.status = 'Em Votacao'
    pauta.iniciado_em = timezone.now()
    pauta.save()

    _broadcast_ws(pauta.assembleia_id, 'votacao_aberta', {
        'pauta_id': pauta.id,
        'titulo': pauta.titulo,
        'tipo_votacao': pauta.tipo_votacao,
    })

    _log_assembleia(pauta.assembleia_id, request.session['usuario_id'], 'votacao_aberta', {
        'pauta_id': pauta.id, 'pauta_titulo': pauta.titulo,
    }, ip=_get_client_ip(request))

    return JsonResponse({
        'status': 'ok',
        'pauta_id': pauta.id,
        'titulo': pauta.titulo,
        'tipo_votacao': pauta.tipo_votacao,
    })


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_encerrar_votacao(request, pk):
    pauta = get_object_or_404(PautaVotacao, pk=pk)
    papel = request.session['usuario']['papel']
    if papel != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores podem encerrar votaçÃµes.'}, status=403)
    pauta.status = 'Concluida'
    pauta.encerrado_em = timezone.now()
    pauta.apurar_resultado()

    _broadcast_ws(pauta.assembleia_id, 'votacao_encerrada', {
        'pauta_id': pauta.id,
        'resultado_final': pauta.resultado_final,
        'favor': pauta.votos_favor,
        'contra': pauta.votos_contra,
        'abstencao': pauta.votos_abstencao,
        'quorum': pauta.assembleia.presentes_count,
        'quorum_minimo': pauta.assembleia.quorum_minimo,
    })

    _log_assembleia(pauta.assembleia_id, request.session['usuario_id'], 'votacao_encerrada', {
        'pauta_id': pauta.id, 'pauta_titulo': pauta.titulo,
        'resultado': pauta.resultado_final,
    }, ip=_get_client_ip(request))

    return JsonResponse({
        'status': 'ok',
        'resultado': pauta.resultado_final,
        'favor': pauta.votos_favor,
        'contra': pauta.votos_contra,
        'abstencao': pauta.votos_abstencao,
        'total': pauta.total_votos,
    })


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_votar(request, pk):
    pauta = get_object_or_404(PautaVotacao, pk=pk)
    assembleia = pauta.assembleia

    print(f'[API_VOTAR] pauta={pk} status={pauta.status} tipo={pauta.tipo_votacao}')

    if pauta.status != 'Em Votacao':
        print(f'[API_VOTAR] ERRO: status={pauta.status} != Em Votacao')
        return JsonResponse({'status': 'error', 'message': 'Votação não está ativa.'}, status=400)

    usuario_id = request.session['usuario_id']

    elegivel, msg = _verificar_elegibilidade(usuario_id)
    if not elegivel:
        print(f'[API_VOTAR] ERRO: usuario {usuario_id} não elegível: {msg}')
        return JsonResponse({'status': 'error', 'message': msg}, status=403)

    data = json.loads(request.body)
    opcao = data.get('opcao', '')
    if opcao not in ('Favor', 'Contra', 'Abstencao'):
        print(f'[API_VOTAR] ERRO: opção inválida: {opcao}')
        return JsonResponse({'status': 'error', 'message': 'Opção inválida.'}, status=400)

    em_delegacao = data.get('em_delegacao', False)
    delegado_de_id = data.get('delegado_de_id')

    if Voto.objects.filter(pauta=pauta, usuario_id=usuario_id, em_delegacao=em_delegacao).exists():
        print(f'[API_VOTAR] ERRO: usuario {usuario_id} já votou pauta={pk}')
        return JsonResponse({'status': 'error', 'message': 'Já votou nesta pauta.'}, status=400)

    with transaction.atomic():
        voto = Voto.objects.create(
            pauta=pauta,
            usuario_id=usuario_id,
            opcao=opcao,
            em_delegacao=em_delegacao,
            delegado_de_id=delegado_de_id if em_delegacao else None,
        )
        if pauta.tipo_votacao == 'Secreta':
            voto.refresh_from_db()
            ReciboVoto.objects.create(
                voto=voto,
                recibo_hash=voto.recibo_hash,
                pauta_titulo=pauta.titulo,
                data_voto=voto.votado_em,
            )
            Voto.objects.filter(pk=voto.pk).update(opcao='')
    _log_assembleia(assembleia.id, usuario_id, 'votacao', {
        'pauta_id': pauta.id, 'pauta_titulo': pauta.titulo,
        'em_delegacao': em_delegacao, 'opcao': opcao,
    }, ip=_get_client_ip(request))

    if pauta.tipo_votacao == 'Aberta':
        _broadcast_ws(assembleia.id, 'voto_registado', {
            'action': 'voto_registado',
            'pauta_id': pauta.id,
            'nome': request.usuario_obj.nome,
            'opcao': opcao,
            'tipo_votacao': 'Aberta',
        })

    _broadcast_ws(assembleia.id, 'resultados_update', {
        'pauta_id': pauta.id,
        'titulo': pauta.titulo,
        'favor': pauta.votos_favor,
        'contra': pauta.votos_contra,
        'abstencao': pauta.votos_abstencao,
        'total': pauta.total_votos,
        'status': pauta.status,
    })

    return JsonResponse({
        'status': 'ok',
        'hash_auditoria': voto.hash_auditoria,
        'recibo_hash': voto.recibo_hash,
        'total_votos': pauta.total_votos,
        'tipo_votacao': pauta.tipo_votacao,
    })


@_requer_login
def api_resultados_pauta(request, pk):
    pauta = get_object_or_404(PautaVotacao, pk=pk)
    return JsonResponse({
        'pauta_id': pauta.id,
        'titulo': pauta.titulo,
        'status': pauta.status,
        'resultado_final': pauta.resultado_final,
        'favor': pauta.votos_favor,
        'contra': pauta.votos_contra,
        'abstencao': pauta.votos_abstencao,
        'total': pauta.total_votos,
        'votos_delegados': pauta.votos_delegados,
        'tipo_votacao': pauta.tipo_votacao,
    })


@_requer_login
def api_votos_pauta(request, pk):
    pauta = get_object_or_404(PautaVotacao, pk=pk)
    votos = Voto.objects.filter(pauta=pauta, em_delegacao=False).select_related('usuario').order_by('votado_em')
    data = []
    for v in votos:
        item = {'votado_em': v.votado_em.isoformat()}
        if pauta.tipo_votacao == 'Aberta':
            item['nome'] = v.usuario.nome
            item['opcao'] = v.opcao
        else:
            item['nome'] = '***'
            item['opcao'] = ''
        data.append(item)
    return JsonResponse({
        'votos': data,
        'tipo_votacao': pauta.tipo_votacao,
        'total': pauta.total_votos,
        'favor': pauta.votos_favor,
        'contra': pauta.votos_contra,
        'abstencao': pauta.votos_abstencao,
    })


@_requer_login
def api_verificar_voto(request, pk):
    pauta = get_object_or_404(PautaVotacao, pk=pk)
    recibo_hash = request.GET.get('recibo_hash', '')
    if not recibo_hash:
        return JsonResponse({'status': 'error', 'message': 'recibo_hash é obrigatório.'}, status=400)

    voto = Voto.objects.filter(pauta=pauta, recibo_hash=recibo_hash).first()
    if not voto:
        return JsonResponse({'status': 'error', 'message': 'Voto não encontrado.'}, status=404)

    return JsonResponse({
        'status': 'ok',
        'verificado': True,
        'pauta_titulo': pauta.titulo,
        'opcao': voto.opcao if pauta.tipo_votacao == 'Aberta' else '***',
        'hash_auditoria': voto.hash_auditoria,
        'votado_em': voto.votado_em.isoformat(),
        'em_delegacao': voto.em_delegacao,
    })


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# API - Assembleia (Status / Iniciar / Concluir / Cancelar)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@_requer_login
def api_status_assembleia(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    pauta_ativa = assembleia.pautas.filter(status='Em Votacao').first()
    return JsonResponse({
        'id': assembleia.id,
        'status': assembleia.status,
        'presentes': assembleia.presentes_count,
        'quorum_minimo': assembleia.quorum_minimo,
        'quorum_atingido': assembleia.quorum_atingido,
        'total_pautas': assembleia.total_pautas,
        'pautas_concluidas': assembleia.pautas_concluidas,
        'pauta_ativa_id': pauta_ativa.id if pauta_ativa else None,
        'pauta_ativa_titulo': pauta_ativa.titulo if pauta_ativa else '',
        'pauta_ativa_tipo': pauta_ativa.tipo_votacao if pauta_ativa else '',
    })


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_iniciar_assembleia(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    papel = request.session['usuario']['papel']
    if papel != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores podem iniciar assembleias.'}, status=403)
    if assembleia.status != 'Agendada':
        return JsonResponse({'status': 'error', 'message': 'Assembleia já foi iniciada ou concluída.'}, status=400)
    if not assembleia.convocatorias.filter(status='Publicada').exists():
        return JsonResponse({'status': 'error', 'message': 'É necessário publicar pelo menos uma Convocatória antes de iniciar a assembleia.'}, status=400)
    assembleia.status = 'Em Curso'
    assembleia.save()
    _notificar_para_papel('Administrador', 'assembleia_iniciada', f'Assembleia em curso: {assembleia.titulo}', 'A assembleia já está em curso. Entre na sala virtual!', f'/governanca/assembleia/{assembleia.pk}/sala/')
    _notificar_para_papel('Despachante Oficial', 'assembleia_iniciada', f'Assembleia em curso: {assembleia.titulo}', 'A assembleia já está em curso. Entre na sala virtual!', f'/governanca/assembleia/{assembleia.pk}/sala/')
    _log_assembleia(assembleia.id, request.session['usuario_id'], 'assembleia_iniciada', {}, ip=_get_client_ip(request))
    return JsonResponse({'status': 'ok'})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_concluir_assembleia(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    papel = request.session['usuario']['papel']
    if papel != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores podem concluir assembleias.'}, status=403)
    if assembleia.status != 'Em Curso':
        return JsonResponse({'status': 'error', 'message': 'Assembleia não está em curso.'}, status=400)

    pautas_em_votacao = assembleia.pautas.with_vote_counts().filter(status='Em Votacao')
    for pauta in pautas_em_votacao:
        pauta.status = 'Concluida'
        pauta.encerrado_em = timezone.now()
        pauta.apurar_resultado()

    assembleia.status = 'Concluida'
    assembleia.data_encerramento = timezone.now()
    assembleia.hash_integridade = assembleia.gerar_hash_integridade()
    assembleia.save()

    todas_pautas = assembleia.pautas.with_vote_counts()
    manifesto = ManifestoIntegridade.objects.create(
        assembleia=assembleia,
        hash_consolidado=assembleia.hash_integridade,
        dados_json=json.dumps({
            'presentes': assembleia.presentes_count,
            'total_pautas': assembleia.total_pautas,
            'pautas': [{'id': p.id, 'titulo': p.titulo, 'resultado': p.resultado_final} for p in todas_pautas],
        }, ensure_ascii=False),
        gerado_por=request.usuario_obj,
    )

    _notificar_para_papel('Administrador', 'resultado_publicado', f'Assembleia Concluida: {assembleia.titulo}', 'Os resultados já estão disponíveis.', f'/governanca/assembleia/{assembleia.pk}/')
    _log_assembleia(assembleia.id, request.session['usuario_id'], 'assembleia_concluida', {
        'hash': assembleia.hash_integridade,
        'total_pautas': assembleia.total_pautas,
    }, ip=_get_client_ip(request))
    return JsonResponse({'status': 'ok', 'hash': assembleia.hash_integridade})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_cancelar_assembleia(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    papel = request.session['usuario']['papel']
    if papel != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores podem cancelar assembleias.'}, status=403)
    assembleia.status = 'Cancelada'
    assembleia.save()
    _log_assembleia(assembleia.id, request.session['usuario_id'], 'assembleia_cancelada', {}, ip=_get_client_ip(request))
    return JsonResponse({'status': 'ok'})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# API - Manifesto / Ata
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_gerar_manifesto(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    if assembleia.status != 'Concluida':
        return JsonResponse({'status': 'error', 'message': 'Assembleia precisa estar concluída.'}, status=400)
    hash_val = assembleia.gerar_hash_integridade()
    manifesto, created = ManifestoIntegridade.objects.get_or_create(
        assembleia=assembleia,
        defaults={
            'hash_consolidado': hash_val,
            'dados_json': json.dumps({'gerado_em': str(timezone.now())}, ensure_ascii=False),
            'gerado_por': request.usuario_obj,
        },
    )
    return JsonResponse({
        'status': 'ok',
        'hash': manifesto.hash_consolidado,
        'gerado_em': manifesto.gerado_em.isoformat(),
    })


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_publicar_ata(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    data = json.loads(request.body)
    conteudo = data.get('conteudo', '')
    if not conteudo:
        return JsonResponse({'status': 'error', 'message': 'Conteúdo da ata é obrigatório.'}, status=400)

    raw = f'{assembleia.id}-{conteudo}-{timezone.now().isoformat()}'
    assinatura = hashlib.sha256(raw.encode()).hexdigest()

    ata = AtaDigital.objects.create(
        assembleia=assembleia,
        conteudo=conteudo,
        assinatura_hash=assinatura,
        assinado_por=request.usuario_obj,
        assinado_em=timezone.now(),
        assinatura_hash_presidente=assinatura,
        assinado_presidente_em=timezone.now(),
        status_assinatura='Aguardando Secretario',
    )
    _log_assembleia(assembleia.id, request.session['usuario_id'], 'criacao', {
        'ata_id': ata.id, 'status_assinatura': ata.status_assinatura,
    }, ip=_get_client_ip(request))

    _notificar_para_papel('Administrador', 'ata_publicada', f'Ata publicada: {assembleia.titulo}', 'A ata da assembleia foi publicada no repositório.', f'/governanca/atas/')
    _notificar_para_papel('Despachante Oficial', 'ata_publicada', f'Ata publicada: {assembleia.titulo}', 'A ata da assembleia está disponível para consulta.', f'/governanca/atas/')
    return JsonResponse({'status': 'ok', 'ata_id': ata.id, 'assinatura': assinatura, 'status_assinatura': ata.get_status_assinatura_display()})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# API - Documentos
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_upload_documento(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    papel = request.session['usuario']['papel']
    usuario_id = request.session['usuario_id']
    is_admin = papel == 'Administrador'
    usuario_obj = Usuario.objects.filter(pk=usuario_id).first()
    is_secretario = MembroMesa.objects.filter(
        assembleia=assembleia,
        usuario_id=usuario_id,
        funcao__in=('1º Secretário', '2º Secretário')
    ).exists() or (usuario_obj and (usuario_obj.is_secretario or usuario_obj.is_vice_secretario))
    if not is_admin and not is_secretario:
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores e secretários (1º/2º).'}, status=403)
    titulo = request.POST.get('titulo', '').strip()
    tipo = request.POST.get('tipo', 'ata')
    if not titulo:
        return JsonResponse({'status': 'error', 'message': 'Título obrigatório.'}, status=400)
    arquivo = request.FILES.get('arquivo')
    if not arquivo:
        return JsonResponse({'status': 'error', 'message': 'Ficheiro obrigatório.'}, status=400)
    doc = DocumentoAssembleia.objects.create(
        assembleia=assembleia,
        tipo=tipo, titulo=titulo,
        descricao=request.POST.get('descricao', ''),
        arquivo=arquivo,
        created_by=request.usuario_obj,
    )
    return JsonResponse({'status': 'ok', 'id': doc.id, 'titulo': doc.titulo, 'tipo': doc.tipo})


@_requer_login
def api_listar_documentos(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    docs = assembleia.documentos.all()
    data = [{
        'id': d.id, 'tipo': d.tipo, 'titulo': d.titulo,
        'descricao': d.descricao,
        'arquivo': d.arquivo.url if d.arquivo else '',
        'publicado': d.publicado,
        'publicado_em': d.publicado_em.isoformat() if d.publicado_em else None,
        'created_at': d.created_at.isoformat(),
        'created_by': d.created_by.nome if d.created_by else '',
    } for d in docs]
    return JsonResponse({'documentos': data})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_publicar_documento(request, pk, doc_pk):
    doc = get_object_or_404(DocumentoAssembleia, pk=doc_pk, assembleia_id=pk)
    papel = request.session['usuario']['papel']
    usuario_id = request.session['usuario_id']
    is_admin = papel == 'Administrador'
    usuario_obj = Usuario.objects.filter(pk=usuario_id).first()
    is_secretario = usuario_obj and (usuario_obj.is_secretario or usuario_obj.is_vice_secretario)
    if not is_admin and not is_secretario:
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores e secretários.'}, status=403)
    doc.publicado = True
    doc.publicado_em = timezone.now()
    doc.save()

    _notificar_para_papel(
        'Administrador', 'ata_publicada',
        f'Documento publicado: {doc.titulo}',
        f'Foi publicado o documento "{doc.titulo}" na assembleia {doc.assembleia.titulo}.',
        f'/governanca/assembleia/{pk}/'
    )
    _notificar_para_papel(
        'Despachante Oficial', 'ata_publicada',
        f'Documento disponível: {doc.titulo}',
        f'O documento "{doc.titulo}" está disponível para consulta.',
        f'/governanca/assembleia/{pk}/'
    )

    for u in Usuario.objects.filter(status='Ativo', papel='Despachante Oficial').exclude(email=''):
        _enviar(
            f'Documento publicado: {doc.titulo}',
            f'Prezado(a) {u.nome},\n\n'
            f'Foi publicado o documento "{doc.titulo}" referente à assembleia "{doc.assembleia.titulo}".\n\n'
            f'Aceda em: {getattr(settings, "SITE_URL", "http://127.0.0.1:8000")}/governanca/assembleia/{pk}/\n\n'
            f'Atenciosamente,\nCDOA',
            None, [u.email],
        )

    for u in Usuario.objects.filter(status='Ativo', papel='Administrador').exclude(email=''):
        _enviar(
            f'Documento publicado: {doc.titulo}',
            f'Prezado(a) {u.nome},\n\n'
            f'O documento "{doc.titulo}" foi publicado na assembleia "{doc.assembleia.titulo}".\n\n'
            f'Aceda em: {getattr(settings, "SITE_URL", "http://127.0.0.1:8000")}/governanca/assembleia/{pk}/\n\n'
            f'Atenciosamente,\nCDOA',
            None, [u.email],
        )

    return JsonResponse({'status': 'ok', 'id': doc.id})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_remover_documento(request, pk, doc_pk):
    doc = get_object_or_404(DocumentoAssembleia, pk=doc_pk, assembleia_id=pk)
    papel = request.session['usuario']['papel']
    usuario_id = request.session['usuario_id']
    is_admin = papel == 'Administrador'
    is_criador = doc.created_by_id == usuario_id if doc.created_by_id else False
    usuario_obj = Usuario.objects.filter(pk=usuario_id).first()
    is_secretario = MembroMesa.objects.filter(
        assembleia=doc.assembleia,
        usuario_id=usuario_id,
        funcao__in=('1º Secretário', '2º Secretário')
    ).exists() or (usuario_obj and (usuario_obj.is_secretario or usuario_obj.is_vice_secretario))
    if not is_admin and not is_criador and not is_secretario:
        return JsonResponse({'status': 'error', 'message': 'Sem permissão para remover este documento.'}, status=403)
    doc.delete()
    return JsonResponse({'status': 'ok'})


def _pode_admin_ou_secretario(papel, usuario_obj):
    if papel == 'Administrador':
        return True
    if usuario_obj and (usuario_obj.is_secretario or usuario_obj.is_vice_secretario):
        return True
    if usuario_obj:
        from rh.models import CargoMesa
        return CargoMesa.objects.filter(
            usuario=usuario_obj,
            funcao__in=('1º Secretário', '2º Secretário', 'Secretário', 'Vice-Presidente'),
        ).exists()
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# API: Gerar documento a partir de assembleia
# ═══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_gerar_documento(request):
    if not _pode_admin_ou_secretario(request.session['usuario']['papel'], request.usuario_obj):
        return JsonResponse({'status': 'error', 'message': 'Sem permissão.'}, status=403)

    assembleia_id = request.POST.get('assembleia_id', '').strip()
    tipo = request.POST.get('tipo', 'ata')
    if not assembleia_id:
        return JsonResponse({'status': 'error', 'message': 'Assembleia não especificada.'}, status=400)
    assembleia = get_object_or_404(Assembleia, pk=assembleia_id)
    if tipo not in dict(DocumentoAssembleia.TIPOS):
        return JsonResponse({'status': 'error', 'message': 'Tipo inválido.'}, status=400)

    from .utils import gerar_conteudo_documento
    titulo_map = {'ata': f'Ata — {assembleia.titulo}', 'relatorio': f'Relatório — {assembleia.titulo}', 'decreto': f'Decreto — {assembleia.titulo}'}
    titulo = titulo_map.get(tipo, f'Documento — {assembleia.titulo}')
    conteudo = gerar_conteudo_documento(assembleia, tipo, created_by=usuario_obj)

    doc = DocumentoAssembleia.objects.create(
        assembleia=assembleia,
        tipo=tipo,
        titulo=titulo,
        conteudo=conteudo,
        created_by=usuario_obj,
    )
    return JsonResponse({'status': 'ok', 'id': doc.id, 'titulo': doc.titulo, 'tipo': doc.tipo})


# ═══════════════════════════════════════════════════════════════════════════════
# Visualizar documento gerado (conteúdo HTML)
# ═══════════════════════════════════════════════════════════════════════════════

@_requer_login
def visualizar_documento(request, pk):
    doc = get_object_or_404(DocumentoAssembleia, pk=pk)
    context = {
        'usuario': request.session.get('usuario', {}),
        'nome': request.session.get('usuario', {}).get('nome', ''),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'active_menu': 'Governanca',
        'doc': doc,
    }
    return render(request, 'governanca/visualizar_documento.html', context)


# ═══════════════════════════════════════════════════════════════════════════════
# Secretário - Gestão de Actas, Decretos e Relatórios
# ═══════════════════════════════════════════════════════════════════════════════

@_requer_login
def secretario_documentos(request):
    usuario = _get_usuario(request)
    if not usuario:
        return redirect('login')
    papel = usuario.get('papel', '')
    usuario_id = usuario.get('id')
    usuario_obj = Usuario.objects.filter(pk=usuario_id).first()
    if not usuario_obj or not (usuario_obj.is_secretario or usuario_obj.is_vice_secretario):
        return redirect('governanca_index')

    from django.db.models import Count, Q, Prefetch
    todas_qs = DocumentoAssembleia.objects.select_related('assembleia', 'created_by')
    rascunhos = todas_qs.filter(publicado=False).order_by('-created_at')
    publicados = todas_qs.filter(publicado=True).order_by('-publicado_em')
    stats = todas_qs.aggregate(
        total=Count('id'),
        total_rascunhos=Count('id', filter=Q(publicado=False)),
        total_publicados=Count('id', filter=Q(publicado=True)),
        atas=Count('id', filter=Q(tipo='ata')),
        decretos=Count('id', filter=Q(tipo='decreto')),
        relatorios=Count('id', filter=Q(tipo='relatorio')),
    )
    assembleias = Assembleia.objects.prefetch_related(
        Prefetch('documentos', queryset=DocumentoAssembleia.objects.select_related('created_by').order_by('-created_at'), to_attr='todos_docs')
    ).annotate(
        total_docs=Count('documentos'),
        docs_rascunho=Count('documentos', filter=Q(documentos__publicado=False)),
    ).order_by('-data_hora')

    return render(request, 'governanca/secretario_documentos.html', {
        'usuario': usuario,
        'papel': papel,
        'stats': stats,
        'rascunhos': rascunhos[:20],
        'publicados': publicados[:20],
        'assembleias': assembleias,
        'active_menu': 'Governanca',
        'active_sub': 'secretario_docs',
        'TIPOS_DOC': DocumentoAssembleia.TIPOS,
    })


@_requer_login
def api_secretario_assembleias(request):
    usuario = _get_usuario(request)
    if not usuario:
        return JsonResponse({'status': 'error', 'message': 'Sessão expirada.'}, status=401)
    usuario_id = usuario.get('id')
    usuario_obj = Usuario.objects.filter(pk=usuario_id).first()
    if not usuario_obj or not (usuario_obj.is_secretario or usuario_obj.is_vice_secretario):
        return JsonResponse({'status': 'error', 'message': 'Apenas Secretário e Vice-Secretário.'}, status=403)
    assembleias = Assembleia.objects.all().order_by('-data_hora')
    data = []
    for assem in assembleias:
        docs = [{
            'id': d.id, 'tipo': d.tipo, 'titulo': d.titulo,
            'descricao': d.descricao,
            'arquivo': d.arquivo.url if d.arquivo else '',
            'publicado': d.publicado,
            'publicado_em': d.publicado_em.isoformat() if d.publicado_em else None,
            'created_at': d.created_at.isoformat(),
            'created_by': d.created_by.nome if d.created_by else '',
        } for d in assem.documentos.all()]
        data.append({
            'id': assem.id,
            'titulo': assem.titulo,
            'data_hora': assem.data_hora.isoformat(),
            'status': assem.status,
            'local': assem.local,
            'documentos': docs,
        })
    return JsonResponse({'assembleias': data})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# API - Mesa da Assembleia
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_mesa_adicionar(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores.'}, status=403)
    data = json.loads(request.body)
    usuario_id = data.get('usuario_id')
    funcao = data.get('funcao', '').strip()
    if not usuario_id or not funcao:
        return JsonResponse({'status': 'error', 'message': 'Usuário e função obrigatórios.'}, status=400)
    valida = dict(MembroMesa.FUNCOES)
    if funcao not in valida:
        return JsonResponse({'status': 'error', 'message': 'Função inválida.'}, status=400)
    membro, created = MembroMesa.objects.get_or_create(
        assembleia=assembleia, usuario_id=usuario_id,
        defaults={'funcao': funcao, 'ordem': MembroMesa.objects.filter(assembleia=assembleia).count()},
    )
    if not created:
        return JsonResponse({'status': 'error', 'message': 'Usuário já faz parte da mesa.'}, status=400)
    usuario = Usuario.objects.get(id=usuario_id)
    return JsonResponse({
        'status': 'ok',
        'id': membro.id,
        'nome': usuario.nome,
        'funcao': membro.funcao,
    })


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_mesa_remover(request, pk, membro_pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores.'}, status=403)
    membro = get_object_or_404(MembroMesa, pk=membro_pk, assembleia=assembleia)
    membro.delete()
    return JsonResponse({'status': 'ok'})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# API - Chat
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@_requer_login
def api_chat_historico(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    msgs = MensagemChat.objects.filter(assembleia=assembleia).select_related('usuario').order_by('-created_at')[:100]
    lista = []
    for m in reversed(msgs):
        item = {
            'id': m.id, 'tipo': m.tipo,
            'nome': m.usuario.nome, 'user_id': m.usuario.id,
            'created_at': m.created_at.isoformat(),
        }
        if m.tipo == 'reacao':
            emojis = {'mao': 'ðŸ–ï¸', 'palmas': 'ðŸ‘', 'coracao': 'â¤ï¸'}
            item['reacao'] = m.reacao
            item['emoji'] = emojis.get(m.reacao, 'â¤ï¸')
        else:
            item['texto'] = m.texto
        lista.append(item)
    return JsonResponse({'mensagens': lista})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# API - LiveKit Token & Control
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _livekit_rest_call(method, body=None):
    host = settings.LIVEKIT_URL.replace('wss://', 'https://').replace('ws://', 'http://')
    api_key = settings.LIVEKIT_API_KEY
    api_secret = settings.LIVEKIT_API_SECRET
    header = {'alg': 'HS256', 'typ': 'JWT'}
    now = int(__import__('time').time())
    payload = {
        'iss': api_key,
        'nbf': now - 10,
        'exp': now + 3600,
        'video': {'roomCreate': True, 'roomAdmin': True},
    }
    header_b64 = __import__('base64').urlsafe_b64encode(
        json.dumps(header).encode()).rstrip(b'=').decode()
    payload_b64 = __import__('base64').urlsafe_b64encode(
        json.dumps(payload).encode()).rstrip(b'=').decode()
    sig = __import__('hmac').new(
        api_secret.encode(), f'{header_b64}.{payload_b64}'.encode(),
        __import__('hashlib').sha256).digest()
    sig_b64 = __import__('base64').urlsafe_b64encode(sig).rstrip(b'=').decode()
    token = f'{header_b64}.{payload_b64}.{sig_b64}'

    url = f'{host}/twirp/livekit.RoomService/{method}'
    try:
        import requests
        r = requests.post(url, json=body or {},
                          headers={'Authorization': f'Bearer {token}',
                                   'Content-Type': 'application/json'},
                          timeout=5)
        return r.json() if r.status_code < 300 else {'error': r.text}
    except Exception as e:
        return {'error': str(e)}


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_livekit_mute(request):
    """Muta ou remove um participante do LiveKit."""
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores.'}, status=403)
    data = json.loads(request.body)
    room = data.get('room', '')
    identity = data.get('identity', '')
    acao = data.get('acao', 'mute')
    if not room or not identity:
        return JsonResponse({'status': 'error', 'message': 'Room e identity obrigatórios.'}, status=400)

    if acao == 'mute':
        resp = _livekit_rest_call('MutePublishedTrack', {
            'room': room, 'identity': identity,
        })
    elif acao == 'unmute':
        resp = _livekit_rest_call('UpdateParticipant', {
            'room': room, 'identity': identity,
            'permission': {'canPublish': True, 'canSubscribe': True},
        })
    elif acao == 'remove':
        resp = _livekit_rest_call('RemoveParticipant', {
            'room': room, 'identity': identity,
        })
    elif acao in ('camera_off', 'camera_on'):
        participants = _livekit_rest_call('ListParticipants', {'room': room})
        track_sid = None
        for p in participants.get('participants', []):
            if p.get('identity') == identity:
                for track in p.get('tracks', []):
                    if track.get('type') == 'video' and track.get('kind') == 'video' or track.get('source') == 'camera':
                        track_sid = track.get('sid')
                        break
                break
        if acao == 'camera_off' and track_sid:
            resp = _livekit_rest_call('MutePublishedTrack', {
                'room': room, 'identity': identity, 'track_sid': track_sid,
            })
        elif acao == 'camera_on':
            resp = _livekit_rest_call('UpdateParticipant', {
                'room': room, 'identity': identity,
                'permission': {'canPublish': True, 'canSubscribe': True},
            })
            if 'error' not in resp:
                resp = {'status': 'ok', 'info': 'Permissão reativada. Participante precisa ligar a câmara manualmente.'}
        else:
            resp = {'error': 'Track de vídeo não encontrado'}
    else:
        return JsonResponse({'status': 'error', 'message': 'Ação inválida.'}, status=400)

    if 'error' in resp:
        return JsonResponse({'status': 'error', 'message': resp['error']}, status=500)
    return JsonResponse({'status': 'ok'})


@_requer_login
def api_livekit_participants(request):
    """Lista participantes ativos numa sala LiveKit."""
    room = request.GET.get('room', '')
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Room obrigatória.'}, status=400)
    resp = _livekit_rest_call('ListParticipants', {'room': room})
    if 'error' in resp:
        return JsonResponse({'status': 'error', 'participants': [], 'message': resp['error']})
    participants = resp.get('participants', [])
    return JsonResponse({
        'status': 'ok',
        'participants': [{
            'identity': p.get('identity', ''),
            'name': p.get('name', ''),
            'isMuted': p.get('isMuted', False),
            'joinedAt': p.get('joinedAt', ''),
            'tracks': [{
                'sid': t.get('sid'),
                'type': t.get('type'),
                'source': t.get('source'),
                'muted': t.get('muted', False),
                'kind': t.get('kind'),
            } for t in p.get('tracks', [])],
            'camera_muted': any(
                t.get('muted', False)
                for t in p.get('tracks', [])
                if t.get('type') in ('video',) or t.get('kind') == 'video'
            ),
            'audio_muted': any(
                t.get('muted', False)
                for t in p.get('tracks', [])
                if t.get('type') in ('audio',) or t.get('kind') == 'audio'
            ),
        } for p in participants],
    })


@_requer_login
def api_livekit_token(request):
    room = request.GET.get('room', '')
    identity = request.session['usuario']['nome']
    token = _livekit_token(room, identity)
    return JsonResponse({
        'token': token,
        'url': settings.LIVEKIT_URL,
        'room': room,
        'identity': identity,
    })


@_requer_login
def api_livekit_refresh_token(request):
    """Refreshes the LiveKit token (extends session)."""
    room = request.GET.get('room', '')
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Room obrigatória.'}, status=400)
    identity = request.session['usuario']['nome']
    token = _livekit_token(room, identity)
    return JsonResponse({'token': token, 'identity': identity})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_recording_start(request):
    """Inicia gravação da assembleia via LiveKit Egress."""
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores.'}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido.'}, status=400)
    room = body.get('room', '')
    assembleia_id = body.get('assembleia_id', '')
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Room obrigatória.'}, status=400)
    # Chama o Egress do LiveKit para iniciar gravação
    payload = {
        'room_name': room,
        'output': {
            'file_type': 'mp4',
            'filepath': f'/recordings/{room}_{int(time.time())}.mp4',
        },
    }
    resp = _livekit_rest_call('Egress.StartRoomCompositeEgress', payload)
    if 'error' in resp:
        return JsonResponse({'status': 'error', 'message': resp['error']}, status=500)
    egress_id = resp.get('egress_id', '')
    return JsonResponse({'status': 'ok', 'egress_id': egress_id})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_recording_stop(request):
    """Para a gravação da assembleia."""
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores.'}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido.'}, status=400)
    egress_id = body.get('egress_id', '')
    if not egress_id:
        return JsonResponse({'status': 'error', 'message': 'egress_id obrigatório.'}, status=400)
    resp = _livekit_rest_call('Egress.StopEgress', {'egress_id': egress_id})
    if 'error' in resp:
        return JsonResponse({'status': 'error', 'message': resp['error']}, status=500)
    return JsonResponse({'status': 'ok'})


@_requer_login
def api_mesa_listar(request, pk):
    """Lista membros da mesa de uma assembleia."""
    mesa = MembroMesa.objects.filter(assembleia_id=pk).select_related('usuario')
    return JsonResponse({
        'membros': [{
            'id': m.id,
            'usuario_id': m.usuario.id,
            'usuario_nome': m.usuario.nome,
            'funcao': m.funcao,
        } for m in mesa]
    })


@_requer_login
def api_presencas_listar(request, pk):
    """Lista presenças de uma assembleia."""
    presencas = PresencaAssembleia.objects.filter(
        assembleia_id=pk, presente_em__isnull=False
    ).select_related('usuario')
    return JsonResponse({
        'presentes': [{
            'usuario_id': p.usuario.id,
            'nome': p.usuario.nome,
            'presente_em': p.presente_em.isoformat() if p.presente_em else None,
        } for p in presencas]
    })


@_requer_login
def api_assembleia_dados(request, pk):
    """Retorna dados completos da assembleia para o frontend."""
    a = get_object_or_404(Assembleia, pk=pk)
    pautas = a.pautas.with_vote_counts().order_by('ordem')
    user_id = request.session.get('usuario_id')
    votos_usuario = set(
        Voto.objects.filter(pauta__assembleia=a, usuario_id=user_id)
        .values_list('pauta_id', flat=True)
    )
    primeira_ata = a.atas.first()
    return JsonResponse({
        'assembleia': {
            'id': a.id,
            'titulo': a.titulo,
            'descricao': a.descricao,
            'data_hora': a.data_hora.isoformat(),
            'status': a.status,
            'quorum_minimo': a.quorum_minimo,
            'total_eleitores': a.total_eleitores,
            'presentes_count': a.presentes_count,
            'livekit_room': a.livekit_room,
        },
        'ata': {
            'id': primeira_ata.id,
            'status_assinatura': primeira_ata.status_assinatura,
            'assinado_presidente': bool(primeira_ata.assinatura_hash_presidente),
            'assinado_secretario': bool(primeira_ata.assinatura_hash_secretario),
            'created_at': primeira_ata.created_at.isoformat(),
        } if primeira_ata else None,
        'pautas': [{
            'id': p.id,
            'titulo': p.titulo,
            'descricao': p.descricao,
            'ordem': p.ordem,
            'status': p.status,
            'tipo_votacao': p.tipo_votacao,
            'resultado_final': p.resultado_final,
            'votos_favor': p.votos_favor,
            'votos_contra': p.votos_contra,
            'votos_abstencao': p.votos_abstencao,
            'total_votos': p.total_votos,
            'ja_votou': p.id in votos_usuario,
        } for p in pautas],
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API - Notificações
# ═══════════════════════════════════════════════════════════════════════════════
# Submódulo: Gestão Financeira de Quotas
# ═══════════════════════════════════════════════════════════════════════════════

import datetime as _dt
import uuid as _uuid
from decimal import Decimal as _Decimal
from utils.email_utils import _enviar as _email

def _get_estado_financeiro(despachante_id):
    ef, _ = EstadoFinanceiro.objects.get_or_create(despachante_id=despachante_id, defaults={'estado': 'Regular'})
    return ef

def _calcular_multa(pagamento, config_override=None):
    """Calcula multa por atraso para um PagamentoQuota."""
    if not pagamento or not pagamento.quota:
        return {'dias_atraso': 0, 'multa_valor': 0, 'total_sugerido': 0}
    if pagamento.quota.ano and pagamento.quota.mes:
        config = config_override or QuotaConfig.objects.filter(ano=pagamento.quota.ano, mes=pagamento.quota.mes).first()
    else:
        config = None
    vencimento = config.data_vencimento if config else pagamento.quota.data_vencimento
    if not config or not config.multa_percentual or not vencimento:
        return {'dias_atraso': 0, 'multa_valor': 0, 'total_sugerido': pagamento.quota.valor}
    hoje = timezone.now().date()
    inicio_multa = max(vencimento, pagamento.quota.created_at.date())
    dias_atraso = (hoje - inicio_multa).days
    if dias_atraso <= 0:
        return {'dias_atraso': 0, 'multa_valor': 0, 'total_sugerido': pagamento.quota.valor}
    multa_valor = pagamento.quota.valor * (config.multa_percentual / _Decimal(100)) * dias_atraso
    total = pagamento.quota.valor + multa_valor
    return {'dias_atraso': dias_atraso, 'multa_valor': multa_valor, 'total_sugerido': total}

def _atualizar_estado_financeiro(despachante_id):
    ef = _get_estado_financeiro(despachante_id)
    if ef.estado == 'Suspenso':
        return ef
    pendentes = QuotaGerada.objects.filter(despachante_id=despachante_id, status__in=['Pendente','Atrasada']).count()
    if pendentes == 0:
        ef.estado = 'Regular'
    else:
        ef.estado = 'Irregular'
    ef.save()
    return ef


# ─── Páginas HTML ───────────────────────────────────────────────────────────

@_requer_login
def quotas_dashboard(request):
    usuario_id = request.session['usuario_id']
    papel = request.session['usuario']['papel']
    ef = _get_estado_financeiro(usuario_id)
    quotas_pendentes = QuotaGerada.objects.filter(despachante_id=usuario_id, status__in=['Pendente','Atrasada']).count()
    total_quotas = QuotaGerada.objects.filter(despachante_id=usuario_id).count()
    ultimas_quotas_qs = QuotaGerada.objects.filter(despachante_id=usuario_id).order_by('-ano','-mes')
    paginator = Paginator(ultimas_quotas_qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    carteira = CarteiraProfissional.objects.filter(despachante_id=usuario_id).first()
    context = {
        'usuario': request.session['usuario'], 'nome': request.session['usuario']['nome'],
        'papel': papel, 'active_menu': 'Governanca', 'active_sub': 'quotas',
        'estado_financeiro': ef, 'quotas_pendentes': quotas_pendentes,
        'total_quotas': total_quotas, 'ultimas_quotas': page_obj, 'page_obj': page_obj, 'carteira': carteira,
    }
    return render(request, 'governanca/quotas/dashboard.html', context)


@_requer_login
def quotas_faturas(request):
    usuario_id = request.session['usuario_id']
    papel = request.session['usuario']['papel']
    if papel in ('Administrador',):
        quotas = QuotaGerada.objects.all().select_related('despachante').order_by('-ano','-mes')
    else:
        quotas = QuotaGerada.objects.filter(despachante_id=usuario_id).order_by('-ano','-mes')
    paginator = Paginator(quotas, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'usuario': request.session['usuario'], 'nome': request.session['usuario']['nome'],
        'papel': papel, 'active_menu': 'Governanca', 'active_sub': 'quotas',
        'quotas': page_obj, 'page_obj': page_obj, 'is_admin': papel == 'Administrador',
    }
    return render(request, 'governanca/quotas/faturas.html', context)


@_requer_login
def quotas_fatura_detalhe(request, fatura_uuid):
    quota = get_object_or_404(QuotaGerada, fatura_uuid=fatura_uuid)
    pagamentos_qs = PagamentoQuota.objects.filter(quota=quota).order_by('-data_pagamento')
    paginator = Paginator(pagamentos_qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    config = QuotaConfig.objects.filter(ano=quota.ano, mes=quota.mes).first() if quota.ano and quota.mes else None
    multa_info = {'dias_atraso': 0, 'multa_valor': 0, 'total_sugerido': quota.valor}
    if not quota.data_pagamento and config and config.multa_percentual and config.data_vencimento:
        dias_atraso = (timezone.now().date() - config.data_vencimento).days
        if dias_atraso > 0:
            multa_valor = quota.valor * (config.multa_percentual / _Decimal(100)) * dias_atraso
            multa_info = {'dias_atraso': dias_atraso, 'multa_valor': multa_valor, 'total_sugerido': quota.valor + multa_valor}
    context = {
        'usuario': request.session['usuario'], 'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'], 'active_menu': 'Governanca', 'active_sub': 'quotas',
        'quota': quota, 'pagamentos': page_obj, 'page_obj': page_obj,
        'multa_info': multa_info, 'config_multa': config.multa_percentual if config else 0,
    }
    return render(request, 'governanca/quotas/quota_detalhe.html', context)


@_requer_login
def quotas_certidao(request):
    usuario_id = request.session['usuario_id']
    ef = _get_estado_financeiro(usuario_id)
    certidoes_qs = CertidaoRegularidade.objects.filter(despachante_id=usuario_id).order_by('-data_emissao')
    paginator = Paginator(certidoes_qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'usuario': request.session['usuario'], 'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'], 'active_menu': 'Governanca', 'active_sub': 'quotas',
        'estado_financeiro': ef, 'certidoes': page_obj, 'page_obj': page_obj,
        'pode_emitir': ef.estado == 'Regular',
    }
    return render(request, 'governanca/quotas/certidao.html', context)


@_requer_login
def quotas_carteira(request):
    usuario_id = request.session['usuario_id']
    carteira = CarteiraProfissional.objects.filter(despachante_id=usuario_id).first()
    ef = _get_estado_financeiro(usuario_id)
    context = {
        'usuario': request.session['usuario'], 'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'], 'active_menu': 'Governanca', 'active_sub': 'quotas',
        'carteira': carteira, 'estado_financeiro': ef,
    }
    return render(request, 'governanca/quotas/carteira.html', context)


# ─── Admin ──────────────────────────────────────────────────────────────────

@_requer_login
def quotas_admin_dashboard(request):
    if request.session['usuario']['papel'] != 'Administrador':
        return redirect('governanca_quotas_dashboard')

    from django.db.models import Count, Q
    stats = QuotaGerada.objects.aggregate(
        total=Count('id'),
        pendentes=Count('id', filter=Q(status__in=['Pendente','Atrasada'])),
        pagas=Count('id', filter=Q(status='Paga')),
    )
    context = {
        'usuario': request.session['usuario'], 'nome': request.session['usuario']['nome'],
        'papel': 'Administrador', 'active_menu': 'Governanca', 'active_sub': 'quotas_admin',
        'total_quotas': stats['total'],
        'pendentes': stats['pendentes'],
        'pagas': stats['pagas'],
        'pagamentos_pendentes': PagamentoQuota.objects.filter(status='Pendente Confirmacao').count(),
        'config': QuotaConfig.objects.order_by('-ano','-mes').first(),
        'categorias': CategoriaMembro.objects.all(),
        'tipos_quota': TipoQuota.objects.all(),
    }
    return render(request, 'governanca/quotas/admin_dashboard.html', context)


@_requer_login
def quotas_admin_pagamentos(request):
    if request.session['usuario']['papel'] != 'Administrador':
        return redirect('governanca_quotas_dashboard')
    pagamentos_qs = PagamentoQuota.objects.all().select_related('despachante','quota').order_by('-data_pagamento')
    paginator = Paginator(pagamentos_qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    configs = {(c.ano, c.mes): c for c in QuotaConfig.objects.all()}
    pagamentos_com_multa = []
    for p in page_obj:
        config = configs.get((p.quota.ano, p.quota.mes))
        multa_info = _calcular_multa(p, config_override=config)
        pagamentos_com_multa.append({
            'pagamento': p,
            'dias_atraso': multa_info['dias_atraso'],
            'multa_valor': multa_info['multa_valor'],
            'total_sugerido': multa_info['total_sugerido'],
        })
    context = {
        'usuario': request.session['usuario'], 'nome': request.session['usuario']['nome'],
        'papel': 'Administrador', 'active_menu': 'Governanca', 'active_sub': 'quotas_admin',
        'pagamentos': page_obj, 'page_obj': page_obj,
        'pagamentos_com_multa': pagamentos_com_multa,
    }
    return render(request, 'governanca/quotas/admin_pagamentos.html', context)


@_requer_login
def quotas_admin_config(request):
    if request.session['usuario']['papel'] != 'Administrador':
        return redirect('governanca_quotas_dashboard')
    configs_qs = QuotaConfig.objects.order_by('-ano','-mes')
    paginator = Paginator(configs_qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'usuario': request.session['usuario'], 'nome': request.session['usuario']['nome'],
        'papel': 'Administrador', 'active_menu': 'Governanca', 'active_sub': 'quotas_admin',
        'configs': page_obj, 'page_obj': page_obj,
        'categorias': CategoriaMembro.objects.all(),
        'tipos_quota': TipoQuota.objects.all(),
    }
    return render(request, 'governanca/quotas/admin_config.html', context)


@_requer_login
def quotas_admin_relatorios(request):
    if request.session['usuario']['papel'] != 'Administrador':
        return redirect('governanca_quotas_dashboard')

    from django.db.models import Sum, Count, Q
    total_arrecadado = PagamentoQuota.objects.filter(
        status='Confirmado'
    ).aggregate(total=Sum('valor_pago'))['total'] or 0
    stats = QuotaGerada.objects.aggregate(
        atrasadas=Count('id', filter=Q(status='Atrasada')),
        pendentes=Count('id', filter=Q(status='Pendente')),
    )
    inadimplentes = list(
        Usuario.objects.filter(papel='Despachante Oficial', status='Ativo')
        .annotate(
            quotas_pend=Count('quotas', filter=Q(quotas__status__in=['Pendente', 'Atrasada'])),
            total_devido=Sum('quotas__valor', filter=Q(quotas__status__in=['Pendente', 'Atrasada']), distinct=True),
        )
        .filter(quotas_pend__gt=0)
        .order_by('-total_devido')
    )[:20]
    historico = list(
        PagamentoQuota.objects.filter(status='Confirmado').select_related(
            'quota', 'despachante', 'confirmado_por'
        ).order_by('-confirmado_em')[:50]
    )
    resumo_mensal = list(
        QuotaGerada.objects.values('ano', 'mes')
        .annotate(
            total=Count('id'),
            pagas=Count('id', filter=Q(status='Paga')),
            pendentes=Count('id', filter=Q(status='Pendente')),
            atrasadas=Count('id', filter=Q(status='Atrasada')),
            valor_total=Sum('valor'),
            arrecadado=Sum('valor', filter=Q(status='Paga'), distinct=True),
        )
        .order_by('-ano', '-mes')[:12]
    )
    context = {
        'usuario': request.session['usuario'], 'nome': request.session['usuario']['nome'],
        'papel': 'Administrador', 'active_menu': 'Governanca', 'active_sub': 'quotas_admin',
        'total_arrecadado': total_arrecadado,
        'quotas_em_atraso': stats['atrasadas'],
        'quotas_pendentes': stats['pendentes'],
        'inadimplentes': inadimplentes,
        'historico': historico,
        'resumo_mensal': resumo_mensal,
    }
    return render(request, 'governanca/quotas/admin_relatorios.html', context)


# ─── APIs ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_quotas_pagar(request, fatura_uuid):
    quota = get_object_or_404(QuotaGerada, fatura_uuid=fatura_uuid)
    if quota.status == 'Paga':
        return JsonResponse({'erro': 'Quota já foi paga'}, status=400)
    metodo = request.POST.get('metodo', '')
    if metodo not in ['Multicaixa Express', 'Transferencia IBAN']:
        return JsonResponse({'erro': 'Método de pagamento inválido'}, status=400)
    valor = request.POST.get('valor_pago', quota.valor)
    try:
        valor = _Decimal(valor)
    except Exception:
        return JsonResponse({'erro': 'Valor inválido'}, status=400)
    comprovativo = request.FILES.get('comprovativo')
    pag = PagamentoQuota(
        quota=quota, despachante_id=request.session['usuario_id'],
        metodo=metodo, valor_pago=valor,
        codigo_transferencia=request.POST.get('codigo_transferencia',''),
        iban_origem=request.POST.get('iban_origem',''),
    )
    if comprovativo:
        pag.comprovativo = comprovativo
    pag.save()
    return JsonResponse({'status': 'ok', 'pagamento_id': pag.id, 'mensagem': 'Pagamento submetido com sucesso. Aguarde confirmação.'})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_quotas_confirmar_pagamento(request, pk):
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    pag = get_object_or_404(PagamentoQuota, pk=pk)
    acao = request.POST.get('acao', 'confirmar')
    if acao == 'confirmar':
        multa_info = _calcular_multa(pag)
        pag.status = 'Confirmado'
        pag.confirmado_por_id = request.session['usuario_id']
        pag.confirmado_em = timezone.now()
        pag.save()
        pag.quota.status = 'Paga'
        pag.quota.data_pagamento = timezone.now()
        pag.quota.save()
        _atualizar_estado_financeiro(pag.despachante_id)
        multa_msg = ''
        if multa_info['dias_atraso'] > 0:
            multa_msg = f' ({multa_info["dias_atraso"]} dias de atraso, multa de Kz {multa_info["multa_valor"]:.2f})'
        Notificacao.objects.create(
            usuario=pag.despachante, tipo='pagamento_confirmado',
            titulo='Pagamento Confirmado',
            mensagem=f'O pagamento da quota {pag.quota.mes:02d}/{pag.quota.ano} foi confirmado.{multa_msg}',
            link='/governanca/quotas/',
        )
        if pag.despachante.email:
            _email('Pagamento Confirmado',
                f'Olá {pag.despachante.nome},\n\nO pagamento da sua quota {pag.quota.mes:02d}/{pag.quota.ano} foi confirmado.{multa_msg}\n\nCDOA Angola', None, [pag.despachante.email])
    elif acao == 'rejeitar':
        pag.status = 'Rejeitado'
        pag.confirmado_por_id = request.session['usuario_id']
        pag.confirmado_em = timezone.now()
        pag.observacoes = request.POST.get('observacoes', pag.observacoes)
        pag.save()
    return JsonResponse({'status': 'ok'})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_quotas_emitir_certidao(request):
    usuario_id = request.session['usuario_id']
    ef = _get_estado_financeiro(usuario_id)
    if ef.estado != 'Regular':
        return JsonResponse({'erro': 'Estado financeiro irregular. Regularize as suas quotas primeiro.'}, status=400)
    despachante = Usuario.objects.get(id=usuario_id)
    from utils.pdf_quotas import gerar_certidao_pdf
    result = gerar_certidao_pdf(despachante, request.session['usuario']['nome'])
    validade = timezone.now().date() + _dt.timedelta(days=90)
    cert = CertidaoRegularidade.objects.create(
        despachante_id=usuario_id, codigo_certidao=result['codigo'],
        data_validade=validade, arquivo_pdf=result['pdf_path'],
        assinatura_hash=result['hash'], emitido_por_id=usuario_id,
    )
    Notificacao.objects.create(
        usuario_id=usuario_id, tipo='certidao_emitida',
        titulo='Certidão de Regularidade Emitida',
        mensagem='A sua certidão de regularidade foi emitida com sucesso.',
        link='/governanca/quotas/certidao/',
    )
    return JsonResponse({'status': 'ok', 'codigo': result['codigo'], 'url': result['pdf_url']})


@_requer_login
def api_quotas_definir_estado(request, pk):
    """Admin define estado financeiro de um despachante."""
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido'}, status=405)
    estado = request.POST.get('estado', '').strip()
    if estado not in dict(EstadoFinanceiro.ESTADOS):
        return JsonResponse({'erro': 'Estado inválido'}, status=400)
    ef, _ = EstadoFinanceiro.objects.get_or_create(despachante_id=pk, defaults={'estado': estado})
    ef.estado = estado
    ef.observacoes = request.POST.get('observacoes', '')
    ef.save(update_fields=['estado', 'observacoes', 'ultima_atualizacao'])
    return JsonResponse({'status': 'ok', 'estado': ef.estado})


@_requer_login
def api_quotas_buscar_membros(request):
    """Busca membros (despachantes) para o admin definir estado financeiro."""
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    q = request.GET.get('q', '').strip()
    membros = Usuario.objects.filter(papel='Despachante Oficial', status='Ativo')
    if q:
        membros = membros.filter(
            Q(nome__icontains=q) | Q(email__icontains=q) | Q(nif__icontains=q)
        )
    membros = membros.order_by('nome')[:20]
    data = []
    for m in membros:
        ef = EstadoFinanceiro.objects.filter(despachante_id=m.id).first()
        data.append({
            'id': m.id,
            'nome': m.nome,
            'cedula': '',
            'estado_financeiro': ef.estado if ef else 'Regular',
        })
    return JsonResponse({'membros': data})


@_requer_login
def api_quotas_verificar_estado(request):
    usuario_id = request.session['usuario_id']
    ef = _get_estado_financeiro(usuario_id)
    pendentes = QuotaGerada.objects.filter(despachante_id=usuario_id, status__in=['Pendente','Atrasada']).count()
    return JsonResponse({
        'estado': ef.estado, 'quotas_pendentes': pendentes,
        'pode_votar': ef.estado == 'Regular',
        'pode_emitir_certidao': ef.estado == 'Regular',
    })


@_requer_login
def api_quotas_listar(request):
    usuario_id = request.session['usuario_id']
    papel = request.session['usuario']['papel']
    if papel == 'Administrador':
        quotas = QuotaGerada.objects.all().select_related('despachante').order_by('-ano','-mes')
    else:
        quotas = QuotaGerada.objects.filter(despachante_id=usuario_id).order_by('-ano','-mes')
    data = []
    for q in quotas:
        data.append({
            'id': q.id, 'fatura_uuid': q.fatura_uuid, 'ano': q.ano, 'mes': q.mes,
            'valor': str(q.valor), 'data_vencimento': str(q.data_vencimento),
            'status': q.status, 'despachante_nome': q.despachante.nome if papel == 'Administrador' else None,
        })
    return JsonResponse({'quotas': data})


@_requer_login
def api_quotas_dashboard(request):
    usuario_id = request.session['usuario_id']
    papel = request.session['usuario']['papel']
    ef = _get_estado_financeiro(usuario_id)
    pendentes = QuotaGerada.objects.filter(despachante_id=usuario_id, status__in=['Pendente','Atrasada']).count()
    pagas = QuotaGerada.objects.filter(despachante_id=usuario_id, status='Paga').count()
    return JsonResponse({
        'estado': ef.estado, 'quotas_pendentes': pendentes, 'quotas_pagas': pagas,
    })


# ─── Carteira Profissional ──────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_quotas_renovar_carteira(request):
    usuario_id = request.session['usuario_id']
    ef = _get_estado_financeiro(usuario_id)
    if ef.estado != 'Regular':
        return JsonResponse({'erro': 'Estado financeiro irregular. Regularize as suas quotas primeiro.'}, status=400)
    carteira = CarteiraProfissional.objects.filter(despachante_id=usuario_id).first()
    despachante = carteira.despachante if carteira else Usuario.objects.get(id=usuario_id)
    if not carteira:
        from datetime import date as _ddate
        hoje = _ddate.today()
        validade = _ddate(hoje.year + 2, hoje.month, hoje.day)
        from uuid import uuid4 as _uuid4
        numero = f'CDOA-{despachante.cedula or despachante.id}-{hoje.year}'
        carteira = CarteiraProfissional.objects.create(
            despachante=despachante, numero_carteira=numero,
            data_emissao=hoje, data_validade=validade,
        )
    carteira.data_renovacao = timezone.now().date()
    carteira.status = 'Activa'
    carteira.save()
    from utils.pdf_quotas import gerar_carteira_pdf
    pdf_path, pdf_url = gerar_carteira_pdf(despachante, carteira, request.session['usuario']['nome'])
    carteira.arquivo_pdf = pdf_path
    carteira.save(update_fields=['arquivo_pdf'])
    return JsonResponse({'status': 'ok', 'numero_carteira': carteira.numero_carteira, 'validade': str(carteira.data_validade), 'pdf_url': pdf_url})


@_requer_login
def api_quotas_carteira(request):
    usuario_id = request.session['usuario_id']
    carteira = CarteiraProfissional.objects.filter(despachante_id=usuario_id).first()
    if not carteira:
        return JsonResponse({'carteira': None})
    return JsonResponse({
        'carteira': {
            'numero': carteira.numero_carteira, 'data_emissao': str(carteira.data_emissao),
            'data_validade': str(carteira.data_validade), 'status': carteira.status,
        }
    })


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_quotas_salvar_config(request):
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    try:
        ano = int(request.POST.get('ano', 0))
        mes_s = request.POST.get('mes', '')
        mes = int(mes_s) if mes_s else None
        valor = _Decimal(request.POST.get('valor', '0'))
        vencimento = request.POST.get('data_vencimento', '')
        multa_percentual = _Decimal(request.POST.get('multa_percentual', '0.50'))
        ativa = request.POST.get('ativa', '1') == '1'
        publicar = request.POST.get('publicar', '0') == '1'
        categoria_id = request.POST.get('categoria_id', '') or None
        tipo_id = request.POST.get('tipo_id', '') or None
    except (ValueError, TypeError):
        return JsonResponse({'erro': 'Dados inválidos'}, status=400)
    if ano < 2000 or ano > 2100 or valor <= 0:
        return JsonResponse({'erro': 'Ano ou valor inválidos'}, status=400)
    if mes and (mes < 1 or mes > 12):
        return JsonResponse({'erro': 'Mês inválido'}, status=400)
    defaults = {
        'valor': valor,
        'multa_percentual': multa_percentual,
        'ativa': ativa,
    }
    if categoria_id:
        defaults['categoria_id'] = int(categoria_id)
    if tipo_id:
        defaults['tipo_id'] = int(tipo_id)
    if vencimento:
        try:
            defaults['data_vencimento'] = _dt.datetime.strptime(vencimento, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return JsonResponse({'erro': 'Data de vencimento inválida (use AAAA-MM-DD)'}, status=400)
    elif not QuotaConfig.objects.filter(ano=ano, mes=mes).exists():
        return JsonResponse({'erro': 'Data de vencimento é obrigatória na primeira configuração'}, status=400)

    lookup = {'ano': ano}
    if mes is not None:
        lookup['mes'] = mes
    config, created = QuotaConfig.objects.update_or_create(**lookup, defaults=defaults)

    if publicar and ativa:
        despachantes = Usuario.objects.filter(papel__in=['Despachante Oficial', 'Administrador'], status='Ativo')
        tipo = TipoQuota.objects.filter(id=tipo_id).first() if tipo_id else None
        if not tipo:
            tipo = TipoQuota.objects.filter(slug='mensal').first()
        descricao = f'{tipo.nome} {mes:02d}/{ano}' if mes else f'{tipo.nome} {ano}'
        geradas = 0
        for d in despachantes:
            if d.categoria and d.categoria.isento:
                continue
            if tipo.recorrente and mes:
                if QuotaGerada.objects.filter(despachante=d, tipo=tipo, ano=ano, mes=mes).exists():
                    continue
            elif not tipo.recorrente:
                if QuotaGerada.objects.filter(despachante=d, tipo=tipo, ano=ano).exists():
                    continue
            pi = _dt.date(ano, mes, 1) if mes else None
            pf = None
            if pi and tipo.dias_intervalo:
                from dateutil.relativedelta import relativedelta
                pf = pi + relativedelta(months=(tipo.dias_intervalo // 30)) - _dt.timedelta(days=1)
            QuotaGerada.objects.create(
                despachante=d, tipo=tipo, ano=ano, mes=mes,
                periodo_inicio=pi, periodo_fim=pf,
                descricao=descricao,
                valor=config.valor, data_vencimento=config.data_vencimento,
            )
            ef, _ = EstadoFinanceiro.objects.get_or_create(despachante=d, defaults={'estado': 'Irregular'})
            if ef.estado == 'Regular':
                ef.estado = 'Irregular'
                ef.save()
            multa_str = f' Multa de {config.multa_percentual}%/dia após o vencimento.' if config.multa_percentual else ''
            Notificacao.objects.create(
                usuario=d, tipo='quota_gerada',
                titulo=descricao + ' — Pagamento Disponível',
                mensagem=f'Foi publicada a sua {descricao} no valor de Kz {config.valor}. Vencimento: {config.data_vencimento}.{multa_str}',
                link='/governanca/quotas/',
            )
            if d.email:
                texto_multa = f"Multa de {config.multa_percentual}%/dia após o vencimento.\n" if config.multa_percentual else ""
                _enviar(
                    'Quota Associativa — Pagamento Disponível',
                    f'Olá {d.nome},\n\nA sua {descricao} no valor de Kz {config.valor} foi publicada.\n'
                    f'Data de vencimento: {config.data_vencimento}\n{texto_multa}'
                    f'\nAceda ao sistema para efetuar o pagamento dentro do prazo.\n\nCDOA Angola',
                    None, [d.email],
                )
            geradas += 1
        msg = f'Configuração de {descricao} publicada. {geradas} quotas geradas.'
    else:
        label = f'{mes:02d}/{ano}' if mes else f'{ano}'
        msg = f'Configuração de {label} salva: Kz {valor:.2f}'
    return JsonResponse({'status': 'ok', 'mensagem': msg})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_quotas_gerar_retroativo(request):
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    try:
        mes = int(request.POST.get('mes', 0))
        ano = int(request.POST.get('ano', 0))
        data_inicio = request.POST.get('data_inicio', '')
        data_fim = request.POST.get('data_fim', '')
        despachante_id = request.POST.get('despachante_id', '')
        todos = request.POST.get('todos', '1') == '1'
        force = request.POST.get('force', '0') == '1'
        tipo_id = request.POST.get('tipo_id', '') or None
    except (ValueError, TypeError):
        return JsonResponse({'erro': 'Dados inválidos'}, status=400)

    meses_para_gerar = []
    if mes and ano:
        meses_para_gerar.append((ano, mes))
    elif data_inicio and data_fim:
        try:
            di = _dt.datetime.strptime(data_inicio, '%Y-%m-%d').date()
            df = _dt.datetime.strptime(data_fim, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return JsonResponse({'erro': 'Datas inválidas (use AAAA-MM-DD)'}, status=400)
        m = di.replace(day=1)
        while m <= df:
            meses_para_gerar.append((m.year, m.month))
            if m.month == 12:
                m = m.replace(year=m.year + 1, month=1)
            else:
                m = m.replace(month=m.month + 1)
    else:
        return JsonResponse({'erro': 'Informe mês/ano ou um intervalo de datas'}, status=400)

    if todos:
        despachantes = Usuario.objects.filter(papel__in=['Despachante Oficial', 'Administrador'], status='Ativo')
    elif despachante_id:
        try:
            despachantes = Usuario.objects.filter(id=int(despachante_id), papel__in=['Despachante Oficial', 'Administrador'], status='Ativo')
            if not despachantes.exists():
                return JsonResponse({'erro': 'Despachante não encontrado ou inativo'}, status=404)
        except ValueError:
            return JsonResponse({'erro': 'ID de despachante inválido'}, status=400)
    else:
        despachantes = Usuario.objects.filter(papel__in=['Despachante Oficial', 'Administrador'], status='Ativo')

    tipo = TipoQuota.objects.filter(id=tipo_id).first() if tipo_id else TipoQuota.objects.filter(slug='mensal').first()
    erros = []
    geradas = 0
    for aa, mm in meses_para_gerar:
        config = QuotaConfig.objects.filter(ano=aa, mes=mm, ativa=True).first()
        if not config:
            erros.append(f'{mm:02d}/{aa}: sem configuração ativa')
            continue
        for d in despachantes:
            if d.categoria and d.categoria.isento:
                continue
            existente = QuotaGerada.objects.filter(despachante=d, tipo=tipo, ano=aa, mes=mm).first()
            if existente:
                if force:
                    existente.delete()
                else:
                    continue
            descricao = f'{tipo.nome} {mm:02d}/{aa}'
            QuotaGerada.objects.create(
                despachante=d, tipo=tipo, ano=aa, mes=mm,
                descricao=descricao,
                valor=config.valor, data_vencimento=config.data_vencimento,
            )
            ef, _ = EstadoFinanceiro.objects.get_or_create(despachante=d, defaults={'estado': 'Irregular'})
            if ef.estado == 'Regular':
                ef.estado = 'Irregular'
                ef.save()
            multa_str = f' Multa de {config.multa_percentual}%/dia após o vencimento.' if config.multa_percentual else ''
            Notificacao.objects.create(
                usuario=d, tipo='quota_gerada',
                titulo=f'{descricao} — Gerada Retroativamente',
                mensagem=f'Foi gerada retroativamente a sua {descricao} no valor de Kz {config.valor}.{multa_str}',
                link='/governanca/quotas/',
            )
            if d.email:
                texto_multa = f"Multa de {config.multa_percentual}%/dia após o vencimento.\n" if config.multa_percentual else ""
                _enviar(
                    'Quota Associativa — Geração Retroativa',
                    f'Olá {d.nome},\n\nA sua {descricao} no valor de Kz {config.valor} foi gerada retroativamente.\n'
                    f'Vencimento: {config.data_vencimento}\n{texto_multa}'
                    f'\nAceda ao sistema para efetuar o pagamento.\n\nCDOA Angola',
                    None, [d.email],
                )
            geradas += 1

    msg = f'{geradas} quotas geradas.'
    if erros:
        msg += ' Erros: ' + '; '.join(erros)
    return JsonResponse({'status': 'ok', 'mensagem': msg, 'geradas': geradas, 'erros': erros})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_quotas_marcar_paga(request, fatura_uuid):
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    quota = get_object_or_404(QuotaGerada, fatura_uuid=fatura_uuid)
    if quota.status == 'Paga':
        return JsonResponse({'erro': 'Esta quota já está paga'}, status=400)
    quota.status = 'Paga'
    quota.data_pagamento = timezone.now()
    quota.save()
    _atualizar_estado_financeiro(quota.despachante_id)
    Notificacao.objects.create(
        usuario=quota.despachante, tipo='pagamento_confirmado',
        titulo='Quota Marcada como Paga',
        mensagem=f'A sua quota {quota.mes:02d}/{quota.ano} foi marcada como paga pela administração.',
        link='/governanca/quotas/',
    )
    if quota.despachante.email:
        _email('Quota Marcada como Paga',
            f'Olá {quota.despachante.nome},\n\nA sua quota {quota.mes:02d}/{quota.ano} foi marcada como paga pela administração.\n\nCDOA Angola', None, [quota.despachante.email])
    return JsonResponse({'status': 'ok', 'mensagem': f'Quota {quota.mes:02d}/{quota.ano} marcada como paga'})


# ═══════════════════════════════════════════════════════════════════════════════
# Submódulo 3: Escuta Activa, Fórum & Transparência
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Páginas HTML ────────────────────────────────────────────────────────────

@_requer_login
def consulta_lista(request):
    status_filtro = request.GET.get('status', '')
    qs = ConsultaPublica.objects.select_related('criado_por').all()
    if status_filtro:
        qs = qs.filter(status=status_filtro)
    STATUS_CHOICES = [
        ('Rascunho', 'Rascunhos'),
        ('Publicada', 'Publicadas'),
        ('EmVotacao', 'Em Votação'),
        ('Encerrada', 'Encerradas'),
        ('Aprovada', 'Aprovadas'),
        ('Rejeitada', 'Rejeitadas'),
    ]
    paginator = Paginator(qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'active_sub': 'consulta',
        'page_obj': page_obj,
        'status_atual': status_filtro,
        'status_choices': STATUS_CHOICES,
    }
    return render(request, 'governanca/consulta/lista.html', context)


@_requer_login
def consulta_detalhe(request, pk):
    consulta = get_object_or_404(ConsultaPublica.objects.prefetch_related(
        'artigos__comentarios__autor', 'artigos__comentarios__respostas__autor',
        'votacoes__votos',
    ), pk=pk)
    total_comentarios = sum(a.comentarios.count() for a in consulta.artigos.all())
    votacao_ativa = consulta.votacoes.filter(ativa=True).first()
    ja_votou = False
    resultados_votacao = {}
    if votacao_ativa:
        usuario_obj = request.usuario_obj
        ja_votou = votacao_ativa.votos.filter(usuario=usuario_obj).exists()
        from django.db.models import Count
        qs_votos = votacao_ativa.votos.values('voto').annotate(total=Count('id'))
        resultados_votacao = {r['voto']: r['total'] for r in qs_votos}
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'active_sub': 'consulta',
        'consulta': consulta,
        'total_comentarios': total_comentarios,
        'votacao_ativa': votacao_ativa,
        'ja_votou': ja_votou,
        'resultados_votacao': resultados_votacao,
    }
    return render(request, 'governanca/consulta/detalhe.html', context)


@_requer_login
def consulta_criar(request):
    papel = request.session['usuario']['papel']
    usuario_obj = request.usuario_obj
    if not _pode_admin_ou_secretario(papel, usuario_obj):
        messages.error(request, 'Apenas administradores e secretários podem criar consultas.')
        return redirect('governanca_consultas')
    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        if not titulo:
            messages.error(request, 'O título é obrigatório.')
        else:
            consulta = ConsultaPublica.objects.create(
                titulo=titulo,
                descricao=request.POST.get('descricao', '').strip(),
                prazo_fim=request.POST.get('prazo_fim') or None,
                criado_por=request.usuario_obj,
            )
            if request.FILES.get('documento'):
                consulta.documento = request.FILES['documento']
                consulta.save()
            for key, value in request.POST.items():
                if key.startswith('artigo_numero_'):
                    idx = key.split('_')[-1]
                    numero = value
                    titulo_artigo = request.POST.get(f'artigo_titulo_{idx}', '')
                    conteudo = request.POST.get(f'artigo_conteudo_{idx}', '')
                    if numero:
                        ArtigoDocumento.objects.create(
                            consulta=consulta,
                            numero=int(numero),
                            titulo=titulo_artigo,
                            conteudo=conteudo,
                            ordem=int(numero),
                        )
            messages.success(request, 'Consulta criada com sucesso.')
            return redirect('governanca_consulta_detalhe', pk=consulta.id)
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'active_sub': 'consulta',
    }
    return render(request, 'governanca/consulta/criar.html', context)


@_requer_login
def consulta_editar(request, pk):
    consulta = get_object_or_404(ConsultaPublica, pk=pk)
    papel = request.session['usuario']['papel']
    usuario_obj = request.usuario_obj
    if not _pode_admin_ou_secretario(papel, usuario_obj):
        messages.error(request, 'Apenas administradores e secretários podem editar consultas.')
        return redirect('governanca_consultas')
    if consulta.status != 'Rascunho':
        messages.error(request, 'Apenas consultas em rascunho podem ser editadas.')
        return redirect('governanca_consulta_detalhe', pk=consulta.id)
    if request.method == 'POST':
        consulta.titulo = request.POST.get('titulo', consulta.titulo).strip()
        consulta.descricao = request.POST.get('descricao', '').strip()
        consulta.prazo_fim = request.POST.get('prazo_fim') or None
        if request.FILES.get('documento'):
            consulta.documento = request.FILES['documento']
        consulta.save()
        messages.success(request, 'Consulta atualizada com sucesso.')
        return redirect('governanca_consulta_detalhe', pk=consulta.id)
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'active_sub': 'consulta',
        'consulta': consulta,
    }
    return render(request, 'governanca/consulta/editar.html', context)


@_requer_login
def consulta_relatorio(request, pk):
    consulta = get_object_or_404(ConsultaPublica.objects.prefetch_related(
        'artigos__comentarios__autor', 'votacoes__votos'
    ), pk=pk)
    resultados = {}
    votacao = consulta.votacoes.filter(ativa=False).first()
    if votacao:
        from django.db.models import Count
        qs_votos = votacao.votos.values('voto').annotate(total=Count('id'))
        resultados = {r['voto']: r['total'] for r in qs_votos}
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'active_sub': 'consulta',
        'consulta': consulta,
        'resultados': resultados,
    }
    return render(request, 'governanca/consulta/relatorio.html', context)


# ─── API ─────────────────────────────────────────────────────────────────────

@_requer_login
def api_consulta_publicar(request, pk):
    if not _pode_admin_ou_secretario(request.session['usuario']['papel'], request.usuario_obj):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    consulta = get_object_or_404(ConsultaPublica, pk=pk, status='Rascunho')
    consulta.status = 'Publicada'
    consulta.publicado_em = timezone.now()
    consulta.save()
    from django.db.models import Q
    destinatarios = Usuario.objects.filter(
        Q(papel='Despachante Oficial') | Q(papel='Administrador'),
        status='Ativo'
    ).values_list('email', flat=True)
    for u in Usuario.objects.filter(
        Q(papel='Despachante Oficial') | Q(papel='Administrador'),
        status='Ativo'
    ):
        Notificacao.objects.create(
            usuario=u, tipo='consulta_publicada',
            titulo='Nova Consulta Pública',
            mensagem=f'Foi publicada a consulta "{consulta.titulo}". Participe até {consulta.prazo_fim.strftime("%d/%m/%Y %H:%M") if consulta.prazo_fim else "ao prazo indicado"}.',
            link=f'/governanca/consulta/{consulta.id}/',
        )
    return JsonResponse({'status': 'ok'})


@_requer_login
def api_consulta_comentar(request, pk):
    consulta = get_object_or_404(ConsultaPublica, pk=pk)
    if consulta.status not in ('Publicada', 'EmVotacao'):
        return JsonResponse({'erro': 'Consulta não está aberta a comentários'}, status=400)
    import json
    data = json.loads(request.body)
    artigo_id = data.get('artigo_id')
    texto = data.get('texto', '').strip()
    if not artigo_id or not texto:
        return JsonResponse({'erro': 'artigo_id e texto são obrigatórios'}, status=400)
    artigo = get_object_or_404(ArtigoDocumento, pk=artigo_id, consulta=consulta)
    comentario = Comentario.objects.create(
        artigo=artigo,
        autor=request.usuario_obj,
        texto=texto,
    )
    if consulta.criado_por_id != request.usuario_obj.id:
        Notificacao.objects.create(
            usuario=consulta.criado_por, tipo='novo_comentario',
            titulo='Novo comentário',
            mensagem=f'{request.usuario_obj.nome} comentou no Artigo {artigo.numero} de "{consulta.titulo}".',
            link=f'/governanca/consulta/{consulta.id}/',
        )
    return JsonResponse({'status': 'ok', 'id': comentario.id})


@_requer_login
def api_consulta_responder(request, pk):
    import json
    data = json.loads(request.body)
    comentario_id = data.get('comentario_id')
    texto = data.get('texto', '').strip()
    if not comentario_id or not texto:
        return JsonResponse({'erro': 'comentario_id e texto são obrigatórios'}, status=400)
    comentario = get_object_or_404(Comentario, pk=comentario_id)
    if comentario.artigo.consulta.pk != pk:
        return JsonResponse({'erro': 'Comentário não pertence a esta consulta'}, status=400)
    resposta = Comentario.objects.create(
        artigo=comentario.artigo,
        autor=request.usuario_obj,
        texto=texto,
        resposta_a=comentario,
    )
    return JsonResponse({'status': 'ok', 'id': resposta.id})


@_requer_login
def api_consulta_abrir_votacao(request, pk):
    papel = request.session['usuario']['papel']
    if not _pode_admin_ou_secretario(request.session['usuario']['papel'], request.usuario_obj):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    consulta = get_object_or_404(ConsultaPublica, pk=pk, status='Publicada')
    consulta.status = 'EmVotacao'
    consulta.save()
    VotacaoConsulta.objects.create(consulta=consulta)
    for u in Usuario.objects.filter(status='Ativo'):
        Notificacao.objects.create(
            usuario=u, tipo='votacao_aberta',
            titulo='Votação Aberta',
            mensagem=f'A votação para "{consulta.titulo}" está aberta. Participe!',
            link=f'/governanca/consulta/{consulta.id}/',
        )
    return JsonResponse({'status': 'ok'})


@_requer_login
def api_consulta_votar(request, pk):
    import json
    data = json.loads(request.body)
    voto = data.get('voto')
    if voto not in ('Favor', 'Contra', 'Abstencao'):
        return JsonResponse({'erro': 'Voto inválido'}, status=400)
    consulta = get_object_or_404(ConsultaPublica, pk=pk, status='EmVotacao')
    votacao = consulta.votacoes.filter(ativa=True).first()
    if not votacao:
        return JsonResponse({'erro': 'Nenhuma votação ativa'}, status=400)
    if votacao.votos.filter(usuario=request.usuario_obj).exists():
        return JsonResponse({'erro': 'Já votou'}, status=400)
    VotoConsulta.objects.create(votacao=votacao, usuario=request.usuario_obj, voto=voto)
    return JsonResponse({'status': 'ok'})


@_requer_login
def api_consulta_encerrar(request, pk):
    if not _pode_admin_ou_secretario(request.session['usuario']['papel'], request.usuario_obj):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    consulta = get_object_or_404(ConsultaPublica, pk=pk, status='EmVotacao')
    votacao = consulta.votacoes.filter(ativa=True).first()
    if votacao:
        votacao.ativa = False
        votacao.data_fim = timezone.now()
        votacao.save()
    consulta.status = 'Encerrada'
    consulta.save()
    for u in Usuario.objects.filter(status='Ativo'):
        Notificacao.objects.create(
            usuario=u, tipo='consulta_encerrada',
            titulo='Consulta Encerrada',
            mensagem=f'A consulta "{consulta.titulo}" foi encerrada. O relatório final será publicado em breve.',
            link=f'/governanca/consulta/{consulta.id}/',
        )
    return JsonResponse({'status': 'ok'})


@_requer_login
def api_consulta_gerar_relatorio(request, pk):
    if not _pode_admin_ou_secretario(request.session['usuario']['papel'], request.usuario_obj):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    consulta = get_object_or_404(ConsultaPublica, pk=pk, status='Encerrada')
    if hasattr(consulta, 'relatorio'):
        return JsonResponse({'erro': 'Relatório já gerado'}, status=400)
    import hashlib, json
    from django.utils import timezone
    sugestoes = {}
    for artigo in consulta.artigos.prefetch_related('comentarios__autor'):
        sugestoes[str(artigo.numero)] = {
            'titulo': artigo.titulo,
            'comentarios': [{'autor': c.autor.nome, 'texto': c.texto, 'data': c.created_at.isoformat()} for c in artigo.comentarios.all()],
        }
    votacao = consulta.votacoes.filter(ativa=False).first()
    resultados_votacao = {}
    if votacao:
        qs_votos = votacao.votos.values('voto').annotate(total=Count('id'))
        resultados_votacao = {r['voto']: r['total'] for r in qs_votos}
    relatorio_data = {
        'consulta': consulta.titulo,
        'criado_em': timezone.now().isoformat(),
        'sugestoes': sugestoes,
        'resultados_votacao': resultados_votacao,
    }
    relatorio = RelatorioConsulta.objects.create(
        consulta=consulta,
        conteudo=relatorio_data,
        criado_por=request.usuario_obj,
    )
    hash_str = json.dumps(relatorio_data, sort_keys=True)
    relatorio.assinatura_hash = hashlib.sha256(hash_str.encode()).hexdigest()
    relatorio.save()
    for u in Usuario.objects.filter(status='Ativo'):
        Notificacao.objects.create(
            usuario=u, tipo='relatorio_publicado',
            titulo='Relatório Disponível',
            mensagem=f'O relatório da consulta "{consulta.titulo}" já está disponível.',
            link=f'/governanca/consulta/{consulta.id}/relatorio/',
        )
    return JsonResponse({'status': 'ok'})


@_requer_login
def api_consulta_publicar_versao_final(request, pk):
    if not _pode_admin_ou_secretario(request.session['usuario']['papel'], request.usuario_obj):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    consulta = get_object_or_404(ConsultaPublica, pk=pk, status='Encerrada')
    consulta.status = 'Aprovada'
    consulta.save()
    for u in Usuario.objects.filter(status='Ativo'):
        Notificacao.objects.create(
            usuario=u, tipo='versao_final_publicada',
            titulo='Versão Final Publicada',
            mensagem=f'A versão final da consulta "{consulta.titulo}" foi publicada no Repositório Digital.',
            link='/governanca/atas/',
        )
    return JsonResponse({'status': 'ok'})


@_requer_login
def api_consulta_rejeitar(request, pk):
    if not _pode_admin_ou_secretario(request.session['usuario']['papel'], request.usuario_obj):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    consulta = get_object_or_404(ConsultaPublica, pk=pk, status='Encerrada')
    consulta.status = 'Rejeitada'
    consulta.save()
    return JsonResponse({'status': 'ok'})


# ═══════════════════════════════════════════════════════════════════════════════
# Submódulo 1 — Convocatórias
# ═══════════════════════════════════════════════════════════════════════════════

@_requer_login
def lista_convocatorias(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    if assembleia.status != 'Agendada':
        messages.error(request, 'Convocatórias só estão disponíveis para assembleias agendadas.')
        return redirect('governanca_detalhe', pk=pk)
    qs = assembleia.convocatorias.all()
    paginator = Paginator(qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'assembleia': assembleia,
        'convocatorias': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'governanca/convocatorias/lista.html', context)


@_requer_login
def criar_convocatoria(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    if request.session['usuario']['papel'] != 'Administrador':
        messages.error(request, 'Sem permissão.')
        return redirect('governanca_detalhe', pk=pk)
    if assembleia.status != 'Agendada':
        messages.error(request, 'Só é possível criar convocatórias para assembleias agendadas.')
        return redirect('governanca_detalhe', pk=pk)

    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        descricao = request.POST.get('descricao', '').strip()
        prazo = request.POST.get('prazo_confirmacao', '')
        documento = request.FILES.get('documento')
        if not titulo:
            messages.error(request, 'Título obrigatório.')
            return render(request, 'governanca/convocatorias/criar.html', locals())
        conv = Convocatoria.objects.create(
            assembleia=assembleia, titulo=titulo, descricao=descricao,
            documento=documento or '',
        )
        if prazo:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(prazo)
            if dt:
                conv.prazo_confirmacao = dt
                conv.save()
        messages.success(request, 'Convocatória criada como rascunho.')
        return redirect('governanca_convocatorias', pk=assembleia.pk)

    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'assembleia': assembleia,
    }
    return render(request, 'governanca/convocatorias/criar.html', context)


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_convocatoria_publicar(request, pk):
    conv = get_object_or_404(Convocatoria, pk=pk)
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Sem permissão.'}, status=403)
    if conv.assembleia.status != 'Agendada':
        return JsonResponse({'status': 'error', 'message': 'A assembleia já não está agendada.'}, status=400)
    conv.status = 'Publicada'
    conv.save()
    _notificar_para_papel('Administrador', 'convocatoria_publicada',
        f'Convocatória: {conv.titulo}',
        f'Foi publicada a convocatória "{conv.titulo}" para {conv.assembleia.titulo}.',
        f'/governanca/assembleia/{conv.assembleia.pk}/')
    _notificar_para_papel('Despachante Oficial', 'convocatoria_publicada',
        f'Convocatória: {conv.titulo}',
        f'Foi publicada a convocatória "{conv.titulo}". Confirme a sua presença.',
        f'/governanca/assembleia/{conv.assembleia.pk}/')
    return JsonResponse({'status': 'ok'})


@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_convocatoria_confirmar_rececao(request, pk):
    conv = get_object_or_404(Convocatoria, pk=pk)
    if conv.status != 'Publicada':
        return JsonResponse({'status': 'error', 'message': 'Convocatória não publicada.'}, status=400)
    return JsonResponse({'status': 'ok', 'message': 'Receção confirmada.'})


# ═══════════════════════════════════════════════════════════════════════════════
# RSVP — Confirmação de Participação
# ═══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_responder_presenca(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    if assembleia.status not in ('Agendada', 'Em Curso'):
        return JsonResponse({'status': 'error', 'message': 'Assembleia já foi concluída ou cancelada.'}, status=400)
    data = json.loads(request.body)
    resposta = data.get('resposta', '')
    if resposta not in ('Sim', 'Nao', 'Talvez'):
        return JsonResponse({'status': 'error', 'message': 'Resposta inválida.'}, status=400)
    rp, created = RespostaPresenca.objects.update_or_create(
        assembleia=assembleia,
        usuario_id=request.session['usuario_id'],
        defaults={'resposta': resposta},
    )
    return JsonResponse({
        'status': 'ok',
        'resposta': rp.resposta,
        'quorum_previsto': assembleia.quorum_previsto,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Reabertura de Votação
# ═══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_reabrir_votacao(request, pk):
    pauta = get_object_or_404(PautaVotacao, pk=pk)
    if request.session['usuario']['papel'] != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas administradores.'}, status=403)
    if pauta.status != 'Concluida':
        return JsonResponse({'status': 'error', 'message': 'Apenas pautas concluídas podem ser reabertas.'}, status=400)
    if pauta.assembleia.status != 'Em Curso':
        return JsonResponse({'status': 'error', 'message': 'Assembleia precisa estar em curso.'}, status=400)

    votos_anteriores = pauta.votos.count()
    with transaction.atomic():
        pauta.votos.all().delete()
        pauta.status = 'Pendente'
        pauta.reaberta = True
        pauta.reaberta_em = timezone.now()
        pauta.resultado_final = ''
        pauta.save()

    _log_assembleia(pauta.assembleia_id, request.session['usuario_id'], 'votacao_reaberta', {
        'pauta_id': pauta.id, 'pauta_titulo': pauta.titulo,
        'votos_anteriores_apagados': votos_anteriores,
    }, ip=_get_client_ip(request))

    _notificar_para_papel('Administrador', 'votacao_reaberta',
        f'Votação reaberta: {pauta.titulo}',
        f'A votação da pauta "{pauta.titulo}" foi reaberta pelo administrador.',
        f'/governanca/assembleia/{pauta.assembleia.pk}/sala/')
    _notificar_para_papel('Despachante Oficial', 'votacao_reaberta',
        f'Votação reaberta: {pauta.titulo}',
        f'A votação da pauta "{pauta.titulo}" foi reaberta. Volte a votar!',
        f'/governanca/assembleia/{pauta.assembleia.pk}/sala/')

    _broadcast_ws(pauta.assembleia_id, 'votacao_reaberta', {
        'pauta_id': pauta.id, 'titulo': pauta.titulo,
        'votos_anteriores': votos_anteriores,
    })

    return JsonResponse({
        'status': 'ok',
        'message': f'Votação reaberta. {votos_anteriores} voto(s) anterior(es) arquivado(s).',
        'votos_anteriores': votos_anteriores,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Exportação de Resultados (PDF / Excel / CSV)
# ═══════════════════════════════════════════════════════════════════════════════

from io import BytesIO


@_requer_login
def exportar_resultados_pdf(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setTitle(f'Resultados - {assembleia.titulo}')

    # Header
    c.saveState()
    c.setFillColor(HexColor('#1a3a5c'))
    c.rect(0, h - 50, w, 50, fill=1, stroke=0)
    c.setFillColor(HexColor('#ffffff'))
    c.setFont('Helvetica-Bold', 16)
    c.drawCentredString(w / 2, h - 35, 'CDOA — Resultados da Assembleia')
    c.setFont('Helvetica', 10)
    c.drawCentredString(w / 2, h - 20, assembleia.titulo)
    c.restoreState()

    y = h - 80
    c.saveState()
    c.setFont('Helvetica-Bold', 11)
    c.drawString(40, y, f'Data: {assembleia.data_hora:%d/%m/%Y %H:%M}')
    y -= 16
    c.drawString(40, y, f'Status: {assembleia.get_status_display()}')
    y -= 16
    c.drawString(40, y, f'Presentes: {assembleia.presentes_count} / Quórum: {assembleia.quorum_minimo}')
    y -= 25

    pautas_com_votos = assembleia.pautas.with_vote_counts()
    for pauta in pautas_com_votos:
        c.setFont('Helvetica-Bold', 12)
        c.setFillColor(HexColor('#1a3a5c'))
        c.drawString(40, y, f'{pauta.ordem}. {pauta.titulo}')
        y -= 18
        c.setFont('Helvetica', 10)
        c.setFillColor(HexColor('#333333'))
        c.drawString(60, y, f'Favor: {pauta.votos_favor}  |  Contra: {pauta.votos_contra}  |  Abstenção: {pauta.votos_abstencao}')
        y -= 14
        c.drawString(60, y, f'Total: {pauta.total_votos} votos  |  Resultado: {pauta.resultado_final or "---"}')
        y -= 22
        if y < 80:
            c.showPage()
            y = h - 50

    c.saveState()
    c.setFont('Helvetica', 8)
    c.setFillColor(HexColor('#888888'))
    c.drawCentredString(w / 2, 30, f'Documento gerado em {timezone.now():%d/%m/%Y %H:%M}  |  Hash: {assembleia.hash_integridade[:20]}...')
    c.restoreState()

    c.showPage()
    c.save()
    buf.seek(0)
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="resultados_{assembleia.pk}_{assembleia.titulo[:30]}.pdf"'
    return response


@_requer_login
def exportar_resultados_excel(request, pk):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    assembleia = get_object_or_404(Assembleia, pk=pk)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Resultados'

    header_fill = PatternFill(start_color='1a3a5c', end_color='1a3a5c', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')

    ws.cell(1, 1, 'Pauta').fill = header_fill
    ws.cell(1, 1).font = header_font
    ws.cell(1, 2, 'Favor').fill = header_fill
    ws.cell(1, 2).font = header_font
    ws.cell(1, 3, 'Contra').fill = header_fill
    ws.cell(1, 3).font = header_font
    ws.cell(1, 4, 'Abstenção').fill = header_fill
    ws.cell(1, 4).font = header_font
    ws.cell(1, 5, 'Total').fill = header_fill
    ws.cell(1, 5).font = header_font
    ws.cell(1, 6, 'Resultado').fill = header_fill
    ws.cell(1, 6).font = header_font

    pautas_com_votos = assembleia.pautas.with_vote_counts()

    for i, pauta in enumerate(pautas_com_votos, 2):
        ws.cell(i, 1, pauta.titulo)
        ws.cell(i, 2, pauta.votos_favor)
        ws.cell(i, 3, pauta.votos_contra)
        ws.cell(i, 4, pauta.votos_abstencao)
        ws.cell(i, 5, pauta.total_votos)
        ws.cell(i, 6, pauta.resultado_final or '---')

    # Sheet detalhe
    ws2 = wb.create_sheet('Detalhe Votos')
    ws2.cell(1, 1, 'Pauta').fill = header_fill
    ws2.cell(1, 1).font = header_font
    ws2.cell(1, 2, 'Eleitor').fill = header_fill
    ws2.cell(1, 2).font = header_font
    ws2.cell(1, 3, 'Voto').fill = header_fill
    ws2.cell(1, 3).font = header_font
    ws2.cell(1, 4, 'Delegação').fill = header_fill
    ws2.cell(1, 4).font = header_font
    row = 2
    for pauta in pautas_com_votos:
        for voto in pauta.votos.select_related('usuario', 'delegado_de').all():
            if pauta.tipo_votacao == 'Secreta':
                opcao = '*** (voto secreto)'
            else:
                opcao = voto.opcao
            ws2.cell(row, 1, pauta.titulo)
            ws2.cell(row, 2, voto.usuario.nome if voto.usuario else '---')
            ws2.cell(row, 3, opcao)
            ws2.cell(row, 4, 'Sim' if voto.em_delegacao else 'Não')
            row += 1

    for col in ws.columns:
        max_len = 0
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col[0].column_letter].width = max_len + 3

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="resultados_{assembleia.pk}_{assembleia.titulo[:30]}.xlsx"'
    wb.save(response)
    return response


@_requer_login
def exportar_resultados_csv(request, pk):
    import csv
    assembleia = get_object_or_404(Assembleia, pk=pk)
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="resultados_{assembleia.pk}_{assembleia.titulo[:30]}.csv"'
    w = csv.writer(response)
    w.writerow(['Pauta', 'Favor', 'Contra', 'Abstenção', 'Total', 'Resultado'])
    for pauta in assembleia.pautas.with_vote_counts():
        w.writerow([pauta.titulo, pauta.votos_favor, pauta.votos_contra, pauta.votos_abstencao, pauta.total_votos, pauta.resultado_final or '---'])
    return response


# ═══════════════════════════════════════════════════════════════════════════════
# Assinatura Digital da Ata
# ═══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
@require_http_methods(['POST'])
@_requer_login
def api_assinar_ata(request, pk):
    ata = get_object_or_404(AtaDigital, pk=pk)
    assembleia = ata.assembleia
    usuario = request.usuario_obj
    papel = request.session['usuario']['papel']

    # Verificar se usuário é membro da mesa
    membro = MembroMesa.objects.filter(assembleia=assembleia, usuario=usuario).first()
    if not membro and papel != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas membros da mesa podem assinar a ata.'}, status=403)

    funcao = membro.funcao if membro else 'Administrador'
    is_presidente = funcao == 'Presidente'
    is_secretario = funcao in ('Secretário', '1º Secretário')

    if not is_presidente and not is_secretario and papel != 'Administrador':
        return JsonResponse({'status': 'error', 'message': 'Apenas Presidente ou Secretário podem assinar.'}, status=403)

    # Gerar hash da assinatura
    raw = f'{ata.id}-{usuario.id}-{timezone.now().isoformat()}'
    assinatura = hashlib.sha256(raw.encode()).hexdigest()

    if is_presidente or papel == 'Administrador':
        if ata.assinatura_hash_presidente:
            return JsonResponse({'status': 'error', 'message': 'Presidente já assinou.'}, status=400)
        ata.assinatura_hash_presidente = assinatura
        ata.assinado_presidente_em = timezone.now()
        if not ata.assinatura_hash:
            ata.assinatura_hash = assinatura
            ata.assinado_por = usuario
            ata.assinado_em = timezone.now()

    if is_secretario:
        if ata.assinatura_hash_secretario:
            return JsonResponse({'status': 'error', 'message': 'Secretário já assinou.'}, status=400)
        ata.assinatura_hash_secretario = assinatura
        ata.assinado_secretario_em = timezone.now()

    # Atualizar status
    if ata.assinatura_hash_presidente and ata.assinatura_hash_secretario:
        ata.status_assinatura = 'Assinada'
    elif ata.assinatura_hash_presidente:
        ata.status_assinatura = 'Aguardando Secretario'
    elif ata.assinatura_hash_secretario:
        ata.status_assinatura = 'Aguardando Presidente'

    ata.save()

    _notificar_para_papel('Administrador', 'ata_assinada',
        f'Ata assinada: {assembleia.titulo}',
        f'{usuario.nome} assinou a ata da assembleia "{assembleia.titulo}". Status: {ata.get_status_assinatura_display()}.',
        f'/governanca/assembleia/{assembleia.pk}/')

    return JsonResponse({
        'status': 'ok',
        'assinatura': assinatura,
        'status_assinatura': ata.get_status_assinatura_display(),
        'funcao': funcao,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Logs da Assembleia
# ═══════════════════════════════════════════════════════════════════════════════

@_requer_login
def assembleia_logs(request, pk):
    assembleia = get_object_or_404(Assembleia, pk=pk)
    if request.session['usuario']['papel'] != 'Administrador':
        messages.error(request, 'Sem permissão.')
        return redirect('governanca_detalhe', pk=pk)

    qs = assembleia.logs.select_related('usuario').all()
    paginator = Paginator(qs, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'usuario': request.session['usuario'],
        'nome': request.session['usuario']['nome'],
        'papel': request.session['usuario']['papel'],
        'active_menu': 'Governanca',
        'assembleia': assembleia,
        'logs': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'governanca/assembleia_logs.html', context)


# ═══════════════════════════════════════════════════════════════════════════════
# Notificações
# ═══════════════════════════════════════════════════════════════════════════════

def pagina_notificacoes(request):
    usuario = _get_usuario(request)
    if not usuario:
        return redirect('login')
    usuario_id = request.session['usuario_id']
    qs = Notificacao.objects.filter(usuario_id=usuario_id).order_by('-created_at')
    nao_lidas = qs.filter(lida=False).count()
    context = {
        'usuario': usuario,
        'nome': usuario['nome'],
        'papel': usuario['papel'],
        'active_menu': 'Governanca',
        'notificacoes': qs[:100],
        'nao_lidas': nao_lidas,
    }
    return render(request, 'governanca/notificacoes.html', context)


def api_notificacoes(request):
    usuario = _get_usuario(request)
    if not usuario:
        return JsonResponse({'error': 'Login required'}, status=401)
    qs = Notificacao.objects.filter(usuario_id=request.session['usuario_id']).order_by('-created_at')[:50]
    data = [{
        'id': n.id, 'tipo': n.tipo, 'titulo': n.titulo,
        'mensagem': n.mensagem, 'link': n.link,
        'lida': n.lida, 'created_at': n.created_at.isoformat(),
    } for n in qs]
    return JsonResponse({'notificacoes': data})


@csrf_exempt
@require_http_methods(['POST'])
def api_notificacao_marcar_lida(request, pk):
    usuario = _get_usuario(request)
    if not usuario:
        return JsonResponse({'error': 'Login required'}, status=401)
    n = get_object_or_404(Notificacao, pk=pk, usuario_id=request.session['usuario_id'])
    n.lida = True
    n.save(update_fields=['lida'])
    return JsonResponse({'status': 'ok'})


@csrf_exempt
@require_http_methods(['POST'])
def api_notificacoes_marcar_todas_lidas(request):
    usuario = _get_usuario(request)
    if not usuario:
        return JsonResponse({'error': 'Login required'}, status=401)
    Notificacao.objects.filter(usuario_id=request.session['usuario_id'], lida=False).update(lida=True)
    return JsonResponse({'status': 'ok'})

