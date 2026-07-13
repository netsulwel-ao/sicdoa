from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.cache import cache
from django.db import models
from django.db.models import Count, Sum, Prefetch, Q
from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import ValidationError
from decimal import Decimal
import calendar
import json
from datetime import date
from utils.format_kz import parse_kz, fmt_kz
from utils.email_utils import gerar_senha_aleatoria, enviar_senha_colaborador
from utils.cache_utils import cache_get_or_set, safe_cache_key
from utils.validators import email_ja_existe
from .acesso import (
    obter_acesso_rh,
    escopo_colaboradores,
    escopo_colaboradores_ativos,
    escopo_vagas,
    pode_aceder_colaborador,
    pode_aceder_vaga,
    pode_avaliar_colaborador,
    pode_aprovar_presenca,
    filial_id_obrigatoria_gestor,
    redirect_sem_acesso_rh,
)
from users.permissoes import get_usuario_permissoes
from users.auth_decorators import sessao_expirada, limpar_sessao
import time
from .models import (
    Banca, FilialBanca, Colaborador, GestorFilial, CargoBanca, DocumentoColaborador,
    ProcessamentoSalarial, ReciboSalarial, Subsidio, SubsidioRecibo, Fatura,
    Vaga, Candidatura, Entrevista, PlanoIntegracao, TarefaIntegracao,
    RegistoPresenca, PedidoFerias, HistoricoPresenca, DelegacaoAprovacao,
    CicloAvaliacao, Avaliacao, MetricaAvaliacao, NotaMetrica,
)
from .notificacoes import (
    notificar_presenca_pendente, notificar_ferias_pendente,
    notificar_aprovado, notificar_rejeitado,
)
from .tax_utils import _dec, _hash_password, _calcular_irt, MESES, DIAS_UTEIS_MES
from users.models import Permissao, LogAtividade
from aduaneiro.models import DeclaracaoUnica
from clientes.models import Cliente
from financeiro.models import FacturaCliente, ReciboCliente, NotaCredito, NotaDebito

# ─── Constantes ───────────────────────────────────────────────────────────────
PROVINCIAS = [
    'Bengo', 'Benguela', 'Bié', 'Cabinda', 'Cuando Cubango',
    'Cuanza Norte', 'Cuanza Sul', 'Cunene', 'Huambo', 'Huíla',
    'Luanda', 'Lunda Norte', 'Lunda Sul', 'Malanje', 'Moxico',
    'Namibe', 'Uíge', 'Zaire',
]
BANCA_TIPOS = Banca.TIPOS
CARGOS      = Colaborador.CARGOS
ESTADOS_COL = Colaborador.ESTADOS
MESES = MESES  # imported from tax_utils


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _requer_sessao(fn):
    """Decorator para verificar se o usuário está autenticado e sessão ativa"""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            return redirect('login')
        if sessao_expirada(request):
            limpar_sessao(request)
            return redirect('login')
        request.session['login_time'] = time.time()
        request.session.modified = True
        return fn(request, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


# Permissões que o gestor de filial pode atribuir a cargos que cria
PERMISSOES_GESTOR_CARGO = {
    # Aduaneiro (âmbito filial)
    'criar_declaracao_unica', 'ver_pauta_aduaneira', 'gerir_clientes_filial', 'gerir_aduaneiro',
    # RH (âmbito filial)
    'gerir_rh', 'ver_minha_banca', 'gerir_colaboradores_banca',
    'gerir_processamento_salarial', 'gerir_recrutamento_banca',
    'gerir_presencas_banca', 'gerir_avaliacoes_banca',
    # Financeiro (âmbito filial)
    'gerir_financeiro_filial', 'ver_requisicoes', 'ver_recibos', 'ver_notas_financeiro',
    'ver_facturas', 'ver_conta_corrente', 'ver_relatorios_financeiros',
}


# Pares de permissões que não podem coexistir (sede vs filial)
PERMISSOES_SEDE_FILIAL = {
    'gerir_clientes': 'gerir_clientes_filial',
    'gerir_financeiro': 'gerir_financeiro_filial',
}
PERMISSOES_SEDE_FILIAL_SET = set(PERMISSOES_SEDE_FILIAL.keys()) | set(PERMISSOES_SEDE_FILIAL.values())


def _validar_mistura_sede_filial(codigos_perm):
    """Retorna mensagem de erro se houver mistura de permissões sede+filial, ou None."""
    for sede_cod, filial_cod in PERMISSOES_SEDE_FILIAL.items():
        if sede_cod in codigos_perm and filial_cod in codigos_perm:
            _sede = Permissao.objects.filter(codigo=sede_cod).values_list('nome', flat=True).first() or sede_cod
            _filial = Permissao.objects.filter(codigo=filial_cod).values_list('nome', flat=True).first() or filial_cod
            return (
                f'Não pode misturar permissões de Sede e Filial no mesmo cargo. '
                f'Encontradas: "{_sede}" (Sede) e "{_filial}" (Filial). '
                f'Remova uma delas.'
            )
    return None


def _ctx(request, sub='', extra=None):
    u = request.session['usuario']
    from users.permissoes import get_usuario_permissoes
    user_permissoes = get_usuario_permissoes(request)
    ctx = {'usuario': u, 'nome': u['nome'], 'papel': u['papel'],
           'active_menu': 'RH', 'active_sub': sub,
           'user_permissoes': user_permissoes}
    acc = obter_acesso_rh(request)
    if acc:
        banca, col_log, gestor, is_desp = acc
        ctx['is_despachante'] = is_desp
        ctx['e_gestor_filial'] = bool(gestor and not is_desp)
        ctx['e_responsavel'] = ctx['e_gestor_filial'] or bool(
            col_log and not is_desp and 'gerir_rh' in user_permissoes and not col_log.filial_id
        )
        ctx['filial_gestor'] = banca.filiais.filter(pk=gestor.filial_id).first() if gestor and gestor.filial_id else None
        ctx['colaborador_logado'] = col_log
    if extra:
        ctx.update(extra)
    return ctx


def _acesso_rh(request):
    """Tuplo de acesso RH ou None."""
    return obter_acesso_rh(request)


def _banca(request):
    """Banca do despachante ou do gestor de filial em sessão."""
    acc = obter_acesso_rh(request)
    return acc[0] if acc else None


def _redirect_se_nao_despachante(request, acc, destino='rh_presencas'):
    """
    Bloqueia gestores de filial em acções reservadas ao despachante,
    a menos que o colaborador tenha gerir_rh, admin_banca, ou qualquer
    permissão granular RH (ver_minha_banca, gerir_colaboradores_banca, etc.).
    """
    if acc and not acc[3]:
        permissoes = get_usuario_permissoes(request)
        perms_rh_granular = [
            'gerir_rh', 'gerir_filial', 'admin_banca',
            'ver_minha_banca', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
            'gerir_processamento_salarial', 'gerir_recrutamento_banca',
            'gerir_presencas_banca', 'gerir_avaliacoes_banca',
        ]
        if any(p in permissoes for p in perms_rh_granular):
            return None
        messages.error(request, 'Apenas o despachante pode realizar esta acção.')
        return redirect(destino)
    return None



# ─── Helpers de Presenças / Férias ─────────────────────────────────────────────

def marcar_ferias_no_registo(pedido):
    """
    Quando férias são aprovadas, marca dias úteis como 'Ferias'.
    Só sobrescreve registos do tipo 'Falta' ou 'Falta_Justificada';
    preserva presenças reais ('Entrada', 'Hora_Extra').
    Vide rh/acesso.py docstring para fluxo completo de aprovacao.
    """
    from datetime import timedelta
    data = pedido.data_inicio
    while data <= pedido.data_fim:
        if data.weekday() < 5:
            existing = RegistoPresenca.objects.filter(
                colaborador=pedido.colaborador, data=data,
            ).first()
            if not existing or existing.tipo in ('Falta', 'Falta_Justificada'):
                RegistoPresenca.objects.update_or_create(
                    colaborador=pedido.colaborador, data=data,
                    defaults={
                        'tipo': 'Ferias', 'estado': 'Aprovado',
                        'hora_entrada': None, 'hora_saida': None,
                        'horas_extras': 0, 'justificacao': '',
                    },
                )
        data += timedelta(days=1)


def _registrar_historico_presenca(banca, filial, tipo_registo, registo_id, accao,
                                   estado_anterior, estado_novo, colaborador, aprovador,
                                   observacao=''):
    HistoricoPresenca.objects.create(
        banca=banca,
        filial=filial,
        tipo_registo=tipo_registo,
        registo_id=registo_id,
        accao=accao,
        estado_anterior=estado_anterior,
        estado_novo=estado_novo,
        colaborador=colaborador,
        colaborador_nome=colaborador.nome if colaborador else '',
        aprovador=aprovador,
        aprovador_nome=aprovador.nome if aprovador else '',
        observacao=observacao,
    )


def _primeiro_aprovador_rh(banca, filial_id=None):
    """Retorna QuerySet com o primeiro colaborador RH encontrado
    (prioridade: gerir_rh → gerir_filial → gerir_presencas_banca)."""
    base = banca.colaboradores.filter(estado='Ativo', filial_id=filial_id)
    for perm in ('gerir_rh', 'gerir_filial', 'gerir_presencas_banca'):
        col = base.filter(cargo_banca__permissoes__codigo=perm).first()
        if col:
            return base.filter(pk=col.pk)
    return base.none()


def _encontrar_responsavel_aprovacao(banca, target_col):
    """
    Encontra o colaborador responsável por aprovar presenças/férias do target.
    Retorna o Colaborador ou None.
    Ordem: RH Filial → Gestor Filial → RH Sede → Despachante (None = despachante).
    """
    from users.permissoes import get_usuario_permissoes
    perm_target = set(target_col.cargo_banca.permissoes.values_list('codigo', flat=True)) if target_col.cargo_banca_id else set()
    target_is_sede_rh = 'gerir_rh' in perm_target and not target_col.filial_id
    target_is_filial_rh = 'gerir_rh' in perm_target and target_col.filial_id

    # Alvo é RH Sede → só o despachante
    if target_is_sede_rh:
        return None
    # Alvo é RH Filial → RH Sede
    if target_is_filial_rh:
        sede_rh = _primeiro_aprovador_rh(banca, filial_id=None).exclude(pk=target_col.pk).first()
        if sede_rh:
            return sede_rh
        return None  # fallback: despachante

    # Alvo regular Sede → RH Sede
    if not target_col.filial_id:
        sede_rh = _primeiro_aprovador_rh(banca, filial_id=None).exclude(pk=target_col.pk).first()
        if sede_rh:
            return sede_rh
        return None

    # Alvo regular Filial → RH Filial (mesma filial) ou Gestor ou RH Sede
    filial_rh = _primeiro_aprovador_rh(banca, filial_id=target_col.filial_id).exclude(pk=target_col.pk).first()
    if filial_rh:
        return filial_rh
    # Fallback: Gestor de Filial (Responsável) da mesma filial
    gestor = banca.colaboradores.filter(
        estado='Ativo', gestor_filial__filial_id=target_col.filial_id,
        gestor_filial__ativo=True,
    ).exclude(pk=target_col.pk).first()
    if gestor:
        return gestor
    # Fallback: RH Sede
    sede_rh = _primeiro_aprovador_rh(banca, filial_id=None).exclude(pk=target_col.pk).first()
    if sede_rh:
        return sede_rh
    return None


def _redirect_se_vaga_inacessivel(request, acc, vaga):
    banca, col_log, gestor, is_desp = acc
    if not pode_aceder_vaga(gestor, is_desp, vaga):
        messages.error(request, 'Sem permissão para aceder a esta vaga.')
        return redirect('rh_vagas')
    return None


def _e_despachante_principal(request):
    """Verifica se utilizador atual é despachante principal (dono da banca)"""
    acc = obter_acesso_rh(request)
    return acc is not None and acc[3]


# _dec, _hash_password imported from tax_utils


def _colaboradores_elegiveis_gestor(banca, filial=None):
    """Colaboradores que podem ser designados gestor (sem gestão ativa noutra filial)."""
    qs_ocupados = GestorFilial.objects.filter(ativo=True, filial__banca=banca)
    if filial:
        gestor_atual = filial.gestores.filter(ativo=True).first()
        if gestor_atual:
            qs_ocupados = qs_ocupados.exclude(colaborador_id=gestor_atual.colaborador_id)
    ids_ocupados = qs_ocupados.values_list('colaborador_id', flat=True)
    return banca.colaboradores.exclude(pk__in=ids_ocupados).order_by('nome')


def _colaborador_para_json(col):
    return {
        'id': col.pk,
        'nome': col.nome,
        'email': col.email,
        'telefone': col.telefone,
        'bi': col.bi,
        'nif': col.nif,
        'genero': col.genero,
        'data_nascimento': col.data_nascimento.isoformat() if col.data_nascimento else '',
        'departamento': col.departamento,
        'data_admissao': col.data_admissao.isoformat() if col.data_admissao else '',
        'salario_base': str(col.salario_base) if col.salario_base is not None else '',
        'observacoes': col.observacoes,
        'banco': col.banco,
        'num_conta': col.num_conta,
        'iban': col.iban,
        'titular_conta': col.titular_conta,
    }


def _atribuir_gestor_filial(col, filial):
    """Designa colaborador como gestor responsável da filial."""
    col.filial = filial
    col.cargo = 'Gestor'
    col.cargo_personalizado = 'Responsável de Filial'
    col.save()

    gf, _created = GestorFilial.objects.update_or_create(
        colaborador=col,
        defaults={
            'filial': filial,
            'ativo': True,
            'nome_gestor': col.nome,
        },
    )

    filial.responsavel = col.nome
    filial.tem_responsavel = True
    filial.save(update_fields=['responsavel', 'tem_responsavel'])

    # Garantir que o colaborador tem o cargo "Gestor de Filial" com as permissões necessárias
    # O escopo à filial é automático via gestor.filial_id no escopo_colaboradores().
    perm_cods = [
        'gerir_filial',              # Responsável de Filial
        'criar_declaracao_unica',     # Criar DU
        'gerir_clientes_filial',      # Gerir Clientes (scope filial)
        'gerir_financeiro_filial',    # Gestão Financeira (scope filial)
        'ver_pauta_aduaneira',        # Ver Pauta Aduaneira
        'alterar_perfil',             # Alterar Próprio Perfil
    ]
    cargo_gf, _criado = CargoBanca.objects.get_or_create(
        banca=col.banca,
        nome='Gestor de Filial',
        defaults={
            'descricao': 'Cargo auto-atribuído pelo sistema para gestores de filial',
            'locked': True,
        },
    )
    permissoes = list(Permissao.objects.filter(codigo__in=perm_cods))
    cargo_gf.permissoes.set(permissoes)
    col.cargo_banca = cargo_gf
    col.save(update_fields=['cargo_banca'])
    return gf


def _remover_gestor_filial(col):
    """Remove a responsabilidade de gestão de filial do colaborador."""
    try:
        gf = col.gestor_filial
    except GestorFilial.DoesNotExist:
        return False

    filial = gf.filial
    gf.ativo = False
    gf.save(update_fields=['ativo'])

    if filial.responsavel == col.nome:
        filial.responsavel = ''
        filial.save(update_fields=['responsavel'])

    if col.cargo_personalizado == 'Responsável de Filial':
        col.cargo_personalizado = ''
        if col.cargo == 'Gestor':
            col.cargo = 'Assistente'
        col.save(update_fields=['cargo', 'cargo_personalizado'])
    return True


def _processar_documentos_colaborador(col, request):
    for i in range(5):
        arquivo_key = f'documento_arquivo_{i}'
        tipo_key = f'documento_tipo_{i}'
        desc_key = f'documento_desc_{i}'
        if arquivo_key in request.FILES and tipo_key in request.POST:
            arquivo = request.FILES[arquivo_key]
            tipo = request.POST[tipo_key]
            descricao = request.POST.get(desc_key, '').strip()
            if arquivo and tipo:
                DocumentoColaborador.objects.create(
                    colaborador=col,
                    tipo=tipo,
                    arquivo=arquivo,
                    descricao=descricao,
                )


def _criar_colaborador_responsavel(request, banca, filial):
    """Cria novo colaborador e designa-o gestor da filial. Retorna (col, mensagem_email)."""
    nome = request.POST.get('nome', '').strip()
    email_gestor = request.POST.get('email', '').strip()

    if not email_gestor:
        return None, 'Gestor de filial precisa de email para aceder ao sistema.'

    if email_gestor and email_ja_existe(email_gestor):
        return None, 'Este email já está registado no sistema.'

    senha_gerada = None
    senha_hash = None

    if email_gestor:
        senha_gerada = gerar_senha_aleatoria()
        senha_hash = _hash_password(senha_gerada)

    col = Colaborador(
        banca=banca,
        filial=filial,
        nome=nome,
        bi=request.POST.get('bi', '').strip(),
        nif=request.POST.get('nif', '').strip(),
        genero=request.POST.get('genero', ''),
        data_nascimento=request.POST.get('data_nascimento') or None,
        cargo='Gestor',
        cargo_personalizado='Responsável de Filial',
        departamento=request.POST.get('departamento', '').strip(),
        email=email_gestor,
        telefone=request.POST.get('telefone', '').strip(),
        data_admissao=request.POST.get('data_admissao') or None,
        salario_base=_dec(request.POST.get('salario_base')) or None,
        estado='Ativo',
        observacoes=request.POST.get('observacoes', '').strip(),
        password=senha_hash,
    )
    if 'foto' in request.FILES:
        col.foto = request.FILES['foto']
    col.save()

    _atribuir_gestor_filial(col, filial)
    _processar_documentos_colaborador(col, request)

    mensagem_email = None
    if email_gestor and senha_gerada:
        sucesso, msg = enviar_senha_colaborador(col, senha_gerada)
        mensagem_email = (
            f"Senha enviada com sucesso para {email_gestor}"
            if sucesso else f"Erro ao enviar email: {msg}"
        )
    return col, mensagem_email


def _processar_responsavel_filial_post(request, banca, filial):
    """
    Processa POST do formulário de responsável.
    Retorna (sucesso, col, mensagem_email, erro).
    """
    col_existente_id = request.POST.get('colaborador_existente_id', '').strip()
    modo = request.POST.get('modo_responsavel', 'novo')

    if modo == 'existente' and col_existente_id:
        col = get_object_or_404(Colaborador, pk=col_existente_id, banca=banca)
        elegiveis = _colaboradores_elegiveis_gestor(banca, filial=filial)
        if not elegiveis.filter(pk=col.pk).exists():
            return False, None, None, (
                'Este colaborador já é gestor de outra filial ou não está disponível.'
            )

        gestor_outra = GestorFilial.objects.filter(
            colaborador=col, ativo=True,
        ).exclude(filial=filial).first()
        if gestor_outra:
            return False, None, None, (
                f'{col.nome} já gere a filial de {gestor_outra.filial.provincia}.'
            )

        _atribuir_gestor_filial(col, filial)
        return True, col, None, None

    nome = request.POST.get('nome', '').strip()
    if not nome:
        return False, None, None, 'O nome é obrigatório.'

    col, mensagem_email = _criar_colaborador_responsavel(request, banca, filial)
    if col is None:
        return False, None, None, mensagem_email or 'Erro ao criar responsável.'
    return True, col, mensagem_email, None


def _gerar_pdf_processamento(processamento, request):
    """Gera um PDF do processamento salarial usando ReportLab e salva no sistema de arquivos"""
    import logging as _log
    _logger = _log.getLogger(__name__)
    try:
        from django.conf import settings
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.colors import black, gray, green, HexColor, white
        from decimal import Decimal
        import os

        recibos = processamento.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()
        banca = processamento.banca
        estado_display = processamento.get_estado_display()

        # Criar diretório se não existir
        pdf_dir = os.path.join(settings.MEDIA_ROOT, 'processamentos_salariais')
        os.makedirs(pdf_dir, exist_ok=True)

        # Gerar PDF usando ReportLab
        filename = f"processamento_{processamento.mes:02d}_{processamento.ano}_{processamento.pk}.pdf"
        filepath = os.path.join(pdf_dir, filename)

        # Criar o canvas do PDF
        c = canvas.Canvas(filepath, pagesize=A4)
        width, height = A4

        # Configurar margens
        margin_left = 2 * cm
        margin_right = 2 * cm
        margin_top = 2 * cm
        margin_bottom = 2 * cm

        # Cabeçalho CDOA
        cor_cdoa = HexColor('#1a3a5c')
        cor_cdoa_gold = HexColor('#c9a84c')
        c.setFillColor(cor_cdoa)
        c.rect(0, height - 50, width, 50, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont('Helvetica-Bold', 12)
        c.drawString(30, height - 35, 'REPÚBLICA DE ANGOLA')
        c.setFont('Helvetica', 9)
        c.drawString(30, height - 20, 'CÂMARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA)')
        c.setFillColor(cor_cdoa_gold)
        c.setFont('Helvetica-Bold', 11)
        c.drawRightString(width - 30, height - 30, estado_display)

        y_position = height - 70

        # Título
        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(cor_cdoa)
        title_text = "PROCESSAMENTO SALARIAL - COMPROVANTE DE PAGAMENTO"
        text_width = c.stringWidth(title_text, "Helvetica-Bold", 18)
        c.drawCentredString(width / 2, y_position, title_text)
        y_position -= 25

        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(black)
        banca_text = banca.nome
        text_width = c.stringWidth(banca_text, "Helvetica-Bold", 12)
        c.drawCentredString(width / 2, y_position, banca_text)
        y_position -= 20

        c.setFont("Helvetica", 10)
        periodo_text = f"Período: {processamento.mes:02d}/{processamento.ano} | Status: {estado_display}"
        text_width = c.stringWidth(periodo_text, "Helvetica", 10)
        c.drawCentredString(width / 2, y_position, periodo_text)
        y_position -= 15

        from django.utils import timezone
        data_text = f"Data de pagamento: {timezone.now().strftime('%d/%m/%Y %H:%M')}"
        text_width = c.stringWidth(data_text, "Helvetica", 10)
        c.drawCentredString(width / 2, y_position, data_text)
        y_position -= 30

        # Linha separadora
        c.line(margin_left, y_position, width - margin_right, y_position)
        y_position -= 30

        # Cabeçalho da tabela
        c.setFont("Helvetica-Bold", 8)
        headers = [
            "Colaborador", "Salário Base", "Subsídios",
            "Bruto", "Faltas", "IRT", "INSS 3%", "Líquido",
        ]
        col_widths = [6, 2, 2, 2, 1.5, 1.5, 1.5, 2]  # proporções
        total_width = width - margin_left - margin_right

        x_position = margin_left
        for i, header in enumerate(headers):
            col_width = total_width * col_widths[i] / sum(col_widths)
            c.drawString(x_position, y_position, header)
            x_position += col_width

        y_position -= 20

        # Dados dos recibos
        c.setFont("Helvetica", 8)
        total_liquido = Decimal('0')

        for recibo in recibos:
            # Verificar se há espaço suficiente
            if y_position < margin_bottom + 100:
                c.showPage()
                # Cabeçalho CDOA na nova página
                c.setFillColor(cor_cdoa)
                c.rect(0, height - 50, width, 50, fill=1, stroke=0)
                c.setFillColor(white)
                c.setFont('Helvetica-Bold', 12)
                c.drawString(30, height - 35, 'REPÚBLICA DE ANGOLA')
                c.setFont('Helvetica', 9)
                c.drawString(30, height - 20, 'CÂMARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA)')
                c.setFillColor(cor_cdoa_gold)
                c.setFont('Helvetica-Bold', 11)
                c.drawRightString(width - 30, height - 30, estado_display)

                y_position = height - 70

                # Repetir cabeçalho da tabela
                c.setFont("Helvetica-Bold", 8)
                x_position = margin_left
                for i, header in enumerate(headers):
                    col_width = total_width * col_widths[i] / sum(col_widths)
                    c.drawString(x_position, y_position, header)
                    x_position += col_width
                y_position -= 20
                c.setFont("Helvetica", 8)

            # Calcular total de subsídios
            total_subsidios = Decimal('0')
            for vinculo in recibo.subsidios_vinculados.all():
                total_subsidios += vinculo.valor

            # Dados do recibo
            dados = [
                recibo.colaborador.nome[:30],  # Limitar nome
                fmt_kz(recibo.salario_base),
                fmt_kz(total_subsidios),
                fmt_kz(recibo.bruto),
                fmt_kz(recibo.outros_descontos),
                fmt_kz(recibo.irt),
                fmt_kz(recibo.inss_trabalhador),
                fmt_kz(recibo.liquido)
            ]

            x_position = margin_left
            for i, dado in enumerate(dados):
                col_width = total_width * col_widths[i] / sum(col_widths)
                if i == 0:  # Nome do colaborador - alinhado à esquerda
                    c.drawString(x_position, y_position, dado)
                else:  # Valores - alinhados à direita
                    c.drawRightString(x_position + col_width, y_position, dado)
                x_position += col_width

            total_liquido += recibo.liquido
            y_position -= 15

        # Linha separadora antes do total
        y_position -= 10
        c.line(margin_left, y_position, width - margin_right, y_position)
        y_position -= 15

        # Total
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin_left, y_position, "Total Líquido Pago:")
        c.drawRightString(width - margin_right, y_position, f"{fmt_kz(total_liquido)} KZ")
        y_position -= 40

        # Assinatura do Despachante (centrada)
        y_position -= 30
        c.setFont("Helvetica", 9)
        sig_line_width = 200
        sig_x = (width - sig_line_width) / 2
        c.line(sig_x, y_position, sig_x + sig_line_width, y_position)
        y_position -= 14
        label = f"Despachante — {banca.nome}"
        label_width = c.stringWidth(label, "Helvetica", 9)
        c.drawString((width - label_width) / 2, y_position, label)
        y_position -= 11
        sub_label = "Assinatura e Carimbo"
        sub_width = c.stringWidth(sub_label, "Helvetica", 9)
        c.drawString((width - sub_width) / 2, y_position, sub_label)

        y_position -= 40

        # Rodapé
        c.setFont("Helvetica-Bold", 8)
        footer_text = "DOCUMENTO FISCAL - COMPROVANTE DE PAGAMENTO"
        text_width = c.stringWidth(footer_text, "Helvetica-Bold", 8)
        c.drawString((width - text_width) / 2, y_position, footer_text)
        y_position -= 12

        c.setFont("Helvetica", 7)
        footer_text2 = "Este documento foi gerado automaticamente pelo Sistema de Gestão de Recursos Humanos"
        text_width = c.stringWidth(footer_text2, "Helvetica", 7)
        c.drawString((width - text_width) / 2, y_position, footer_text2)
        y_position -= 10

        footer_text3 = f"Válido para fins fiscais e de auditoria - Código: PROC-{processamento.pk:04d}"
        text_width = c.stringWidth(footer_text3, "Helvetica", 7)
        c.drawString((width - text_width) / 2, y_position, footer_text3)
        y_position -= 10

        footer_text4 = f"Data de geração: {timezone.now().strftime('%d/%m/%Y %H:%M:%S')}"
        text_width = c.stringWidth(footer_text4, "Helvetica", 7)
        c.drawString((width - text_width) / 2, y_position, footer_text4)

        # Salvar o PDF
        c.save()

        # Salvar referência no processamento
        processamento.pdf_gerado = True
        processamento.save()
    except Exception:
        _logger.exception("Erro ao gerar PDF do processamento %s", processamento.pk)


def _gerar_faturas_processamento(processamento, request):
    """Gera faturas para despachante e colaboradores quando o processamento é marcado como pago."""
    from .models import Fatura

    # Verificar se já existem faturas para este processamento
    if processamento.faturas.exists():
        return  # Já foram geradas

    # Calcular valor total do processamento
    valor_total = sum(r.liquido for r in processamento.recibos.all())

    # Gerar fatura para o despachante (serviço de processamento salarial)
    taxa_servico = (valor_total * Decimal('0.05')).quantize(Decimal('0.01'))  # 5% de taxa de serviço
    codigo_despachante = f"FAT-DESP-{timezone.now().year}-{str(processamento.pk).zfill(4)}"

    Fatura.objects.create(
        codigo=codigo_despachante,
        tipo='SALARIO_DESPACHANTE',
        processamento_salarial=processamento,
        banca=processamento.banca,
        filial=processamento.filial,
        valor_bruto=taxa_servico,
        valor_liquido=taxa_servico,
        valor_imposto=Decimal('0'),
        data_vencimento=timezone.now().date() + timezone.timedelta(days=7),
        descricao=(
            f"Taxa de serviço - Processamento salarial "
            f"{processamento.mes:02d}/{processamento.ano}"
        ),
        observacoes="Taxa de 5% sobre o valor total processado",
        criado_por=request.session.get('usuario_id')
    )

    # Gerar faturas para cada colaborador
    for recibo in processamento.recibos.all():
        codigo_colaborador = f"FAT-COL-{timezone.now().year}-{str(recibo.pk).zfill(4)}"

        Fatura.objects.create(
            codigo=codigo_colaborador,
            tipo='SALARIO_COLABORADOR',
            processamento_salarial=processamento,
            banca=processamento.banca,
            filial=processamento.filial,
            colaborador=recibo.colaborador,
            valor_bruto=recibo.bruto,
            valor_liquido=recibo.liquido,
            valor_imposto=(recibo.irt + recibo.inss_trabalhador).quantize(Decimal('0.01')),
            data_vencimento=timezone.now().date() + timezone.timedelta(days=30),
            descricao=(
                f"Pagamento de salário - {recibo.colaborador.nome} "
                f"({processamento.mes:02d}/{processamento.ano})"
            ),
            observacoes=(
                f"Salário base: {recibo.salario_base} Kz "
                f"| Líquido: {recibo.liquido} Kz"
            ),
            criado_por=request.session.get('usuario_id')
        )


# _calcular_irt imported from tax_utils


# ══════════════════════════════════════════════════════════════════════════════
# BANCA
# ══════════════════════════════════════════════════════════════════════════════
@_requer_sessao
def banca_view(request):
    """Dashboard da banca com visão geral das filiais, colaboradores e recrutamento."""
    acc = obter_acesso_rh(request)
    if acc:
        banca, col_log, gestor, is_desp = acc
    else:
        # Colaborador sem acesso RH mas com admin_banca
        if request.session.get('tipo_usuario') == 'colaborador':
            from rh.models import Colaborador
            col_id = request.session.get('colaborador_id')
            try:
                col = Colaborador.objects.select_related('banca', 'filial', 'gestor_filial__filial').get(pk=col_id)
                banca = col.banca if col.banca_id else None
                col_log, gestor, is_desp = col, col.gestor_filial, False
                acc = (banca, col_log, gestor, is_desp) if banca else None
            except Colaborador.DoesNotExist:
                acc = None
        else:
            acc = None

    if not acc or not banca:
        # Verificar se existe banca (activa ou inactiva) via usuario_id
        uid = request.session['usuario_id']
        banca = Banca.objects.filter(usuario_id=uid).first()
        if not banca:
            return redirect('rh_banca_criar')
        if not banca.ativa:
            return render(request, 'rh/banca/bloqueada.html', _ctx(request, 'banca', {
                'banca': banca,
            }))
        return redirect('rh_banca_criar')

    if not banca.ativa:
        return render(request, 'rh/banca/bloqueada.html', _ctx(request, 'banca', {
            'banca': banca,
        }))

    _perm_set = get_usuario_permissoes(request)
    if not is_desp and 'admin_banca' not in _perm_set and not ('gerir_rh' in _perm_set and col_log and not col_log.filial_id):
        return redirect('rh_presencas')

    filiais = list(banca.filiais.filter(ativa=True).annotate(
        num_colaboradores=Count('colaboradores', distinct=True)
    ).order_by('provincia'))
    colaboradores_recentes = list(
        banca.colaboradores.select_related('filial').order_by('-criado_em')[:5]
    )
    stats_colab = banca.colaboradores.aggregate(
        total=Count('id'),
        sede=Count('id', filter=Q(filial__isnull=True)),
    )
    colaboradores_filiais = stats_colab['total'] - stats_colab['sede']
    filiais_stats = list(
        banca.colaboradores
        .values('filial__provincia')
        .annotate(total=Count('id'))
        .order_by('filial__provincia')
    )
    colaboradores_stats = [{'filial': 'Sede', 'total': stats_colab['sede']}] + [
        {'filial': s['filial__provincia'] or 'Sede', 'total': s['total']}
        for s in filiais_stats if s['filial__provincia']
    ]
    vagas_qs = banca.vagas.aggregate(
        vagas_abertas=Count('id', filter=Q(estado='Aberta')),
        total_vagas=Count('id'),
        total_candidaturas=Count('candidaturas'),
        candidaturas_pendentes=Count('candidaturas', filter=Q(candidaturas__estado='Recebida')),
        entrevistas_agendadas=Count('candidaturas', filter=Q(candidaturas__estado='Entrevista')),
        candidatos_aprovados=Count('candidaturas', filter=Q(candidaturas__estado='Aprovado')),
        integracoes_em_curso=Count(
            'candidaturas',
            filter=Q(candidaturas__plano_integracao__estado='Em Curso')
        ),
    )
    candidaturas_recentes = list(
        Candidatura.objects
        .filter(vaga__banca=banca)
        .select_related('vaga')
        .order_by('-criado_em')[:5]
    )
    cached_data = {
        'banca': banca,
        'filiais': filiais,
        'colaboradores_recentes': colaboradores_recentes,
        'total_colaboradores': stats_colab['total'],
        'total_filiais': len(filiais),
        'colaboradores_stats': colaboradores_stats,
        'colaboradores_filiais': colaboradores_filiais,
        'vagas_abertas': vagas_qs['vagas_abertas'],
        'total_vagas': vagas_qs['total_vagas'],
        'total_candidaturas': vagas_qs['total_candidaturas'],
        'candidaturas_pendentes': vagas_qs['candidaturas_pendentes'],
        'entrevistas_agendadas': vagas_qs['entrevistas_agendadas'],
        'candidatos_aprovados': vagas_qs['candidatos_aprovados'],
        'candidaturas_recentes': candidaturas_recentes,
        'integracoes_em_curso': vagas_qs['integracoes_em_curso'],
    }
    return render(request, 'rh/banca/dashboard.html', _ctx(request, 'banca', cached_data))


@_requer_sessao
def banca_detalhe_view(request):
    """Exibe as informações detalhadas da banca do utilizador logado."""
    acc = obter_acesso_rh(request)
    if acc:
        banca = acc[0]
    else:
        uid = request.session['usuario_id']
        banca = Banca.objects.filter(usuario_id=uid).first()

    if not banca:
        return redirect('rh_banca_criar')

    ctx = _ctx(request, 'banca', extra={'banca': banca})
    return render(request, 'rh/banca/info.html', ctx)


@_requer_sessao
def banca_criar_view(request):
    """Criação da banca (apenas se não existir)."""
    uid = request.session['usuario_id']

    # Verificar se já existe banca (activa ou inactiva)
    if Banca.objects.filter(usuario_id=uid).exists():
        banca = Banca.objects.filter(usuario_id=uid).first()
        if banca:
            request.session['banca_id'] = banca.id
        next_url = request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('rh_banca')

    next_url = request.GET.get('next') or ''

    def _render(extra=None):
        return render(request, 'rh/banca/criar.html', _ctx(request, 'banca', {
            'banca_tipos': BANCA_TIPOS, 'provincias': PROVINCIAS,
            'next_url': next_url,
            **(extra or {}),
        }))

    if request.method == 'POST':
        dados = {k: request.POST.get(k, '').strip() for k in
                 ['nome', 'nif', 'tipo', 'email', 'telefone',
                  'endereco', 'provincia', 'municipio', 'licenca_cdoa']}
        dados['instrucoes_pagamento'] = request.POST.get('instrucoes_pagamento', '').strip()

        # Parse dados bancários JSON
        bancos_json_raw = request.POST.get('dados_bancarios_json', '[]').strip()
        try:
            bancos_lista = json.loads(bancos_json_raw) if bancos_json_raw else []
        except (json.JSONDecodeError, ValueError):
            bancos_lista = []
        if not isinstance(bancos_lista, list):
            bancos_lista = []
        bancos_lista = [b for b in bancos_lista if isinstance(b, dict) and b.get('banco')]
        if len(bancos_lista) > 4:
            bancos_lista = bancos_lista[:4]

        if not dados['nome'] or not dados['nif']:
            return _render({'erro': 'Nome e NIF são obrigatórios.'})

        # Verificar se NIF já existe
        if Banca.objects.filter(nif=dados['nif']).exists():
            return _render({'erro': 'Já existe uma banca com este NIF.'})

        # Verificar se email já existe no sistema
        if dados['email'] and email_ja_existe(dados['email']):
            return _render({'erro': 'Este email já está registado no sistema.'})

        banca = Banca(usuario_id=uid, **dados)
        banca.dados_bancarios_json = json.dumps(bancos_lista, ensure_ascii=False)
        if bancos_lista:
            banca.banco = bancos_lista[0].get('banco', '')
            banca.iban = bancos_lista[0].get('iban', '')
        if 'logo' in request.FILES:
            banca.logo = request.FILES['logo']
        banca.save()

        from django.contrib import messages
        messages.success(request, 'Banca criada com sucesso.')
        next_url = request.GET.get('next') or request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('rh_banca')

    return _render()


@_requer_sessao
def banca_editar_view(request):
    """Edição dos dados da banca."""
    banca = _banca(request)
    if not banca or not banca.ativa:
        return redirect('rh_banca')

    def _render(extra=None):
        form_data = {
            'nome': banca.nome, 'nif': banca.nif, 'tipo': banca.tipo,
            'email': banca.email, 'telefone': banca.telefone,
            'endereco': banca.endereco, 'provincia': banca.provincia,
            'municipio': banca.municipio, 'licenca_cdoa': banca.licenca_cdoa,
            'instrucoes_pagamento': banca.instrucoes_pagamento,
            'dados_bancarios_json': banca.dados_bancarios_json or '[]',
        }
        return render(request, 'rh/banca/editar.html', _ctx(request, 'banca', {
            'banca': banca, 'banca_tipos': BANCA_TIPOS,
            'provincias': PROVINCIAS, 'form': form_data, **(extra or {}),
        }))

    if request.method == 'POST':
        dados = {k: request.POST.get(k, '').strip() for k in
                 ['nome', 'nif', 'tipo', 'email', 'telefone',
                  'endereco', 'provincia', 'municipio', 'licenca_cdoa']}
        dados['instrucoes_pagamento'] = request.POST.get('instrucoes_pagamento', '').strip()

        # Parse dados bancários JSON (máx 4 bancos)
        bancos_json_raw = request.POST.get('dados_bancarios_json', '[]').strip()
        try:
            bancos_lista = json.loads(bancos_json_raw) if bancos_json_raw else []
        except (json.JSONDecodeError, ValueError):
            bancos_lista = []
        if not isinstance(bancos_lista, list):
            bancos_lista = []
        bancos_lista = [b for b in bancos_lista if isinstance(b, dict) and b.get('banco')]
        if len(bancos_lista) > 4:
            bancos_lista = bancos_lista[:4]

        if not dados['nome'] or not dados['nif']:
            return _render({'erro': 'Nome e NIF são obrigatórios.'})

        # Verificar se NIF já existe (excluindo atual)
        if Banca.objects.filter(nif=dados['nif']).exclude(pk=banca.pk).exists():
            return _render({'erro': 'Já existe outra banca com este NIF.'})

        # Verificar se email já existe no sistema (excluindo atual)
        if dados['email'] and email_ja_existe(dados['email'], exclude_model=Banca, exclude_pk=banca.pk):
            return _render({'erro': 'Este email já está registado no sistema.'})

        for k, v in dados.items():
            setattr(banca, k, v)

        banca.dados_bancarios_json = json.dumps(bancos_lista, ensure_ascii=False)
        if bancos_lista:
            banca.banco = bancos_lista[0].get('banco', '')
            banca.iban = bancos_lista[0].get('iban', '')
        else:
            banca.banco = ''
            banca.iban = ''

        if 'logo' in request.FILES:
            banca.logo = request.FILES['logo']
        banca.save()

        from django.contrib import messages
        messages.success(request, 'Dados da banca actualizados com sucesso.')
        return redirect('rh_banca')

    return _render()


@_requer_sessao
def filial_nova_view(request):
    """Criação de nova filial."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_banca')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    def _render(extra=None):
        return render(request, 'rh/filiais/criar.html', _ctx(request, 'filiais', {
            'banca': banca, 'provincias': PROVINCIAS,
            **(extra or {}),
        }))

    if request.method == 'POST':
        dados = {k: request.POST.get(k, '').strip() for k in
                 ['provincia', 'municipio', 'endereco', 'telefone', 'email', 'responsavel']}

        # Campo booleano para responsável
        tem_responsavel = request.POST.get('tem_responsavel') == 'on'
        dados['tem_responsavel'] = tem_responsavel

        if not dados['provincia']:
            return _render({'erro': 'A província é obrigatória.'})

        # Verificar se já existe filial nesta província
        if FilialBanca.objects.filter(banca=banca, provincia=dados['provincia']).exists():
            return _render({'erro': 'Já existe uma filial nesta província.'})

        # Verificar se email já existe no sistema
        if dados['email'] and email_ja_existe(dados['email']):
            return _render({'erro': 'Este email já está registado no sistema.'})

        # Se tem responsável, criar o colaborador responsável primeiro
        if tem_responsavel:
            # Criar filial temporária sem salvar
            filial_temp = FilialBanca(banca=banca, **dados)

            # Salvar dados temporários na sessão para usar após criar responsável
            request.session['filial_temp_data'] = {
                'provincia': dados['provincia'],
                'municipio': dados['municipio'],
                'endereco': dados['endereco'],
                'telefone': dados['telefone'],
                'email': dados['email'],
                'responsavel': dados['responsavel'],
                'tem_responsavel': tem_responsavel
            }

            # Redirecionar para criar responsável primeiro
            return redirect('rh_filial_responsavel_novo_temp')
        else:
            # Criar filial diretamente se não houver responsável
            filial = FilialBanca(banca=banca, **dados)
            filial.save()
            return redirect('rh_banca')

    return _render()


@_requer_sessao
def filial_editar_view(request, pk):
    """Edição de filial existente."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_banca')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    filial = get_object_or_404(FilialBanca, pk=pk, banca=banca)

    def _render(extra=None):
        form_data = {
            'provincia': filial.provincia, 'municipio': filial.municipio,
            'endereco': filial.endereco, 'telefone': filial.telefone,
            'email': filial.email, 'responsavel': filial.responsavel,
        }
        return render(request, 'rh/filiais/editar.html', _ctx(request, 'filiais', {
            'banca': banca, 'filial': filial, 'provincias': PROVINCIAS,
            'form': form_data, **(extra or {}),
        }))

    if request.method == 'POST':
        dados = {k: request.POST.get(k, '').strip() for k in
                 ['provincia', 'municipio', 'endereco', 'telefone', 'email', 'responsavel']}

        if not dados['provincia']:
            return _render({'erro': 'A província é obrigatória.'})

        # Verificar se já existe filial nesta província (excluindo atual)
        if FilialBanca.objects.filter(
            banca=banca, provincia=dados['provincia']
        ).exclude(pk=filial.pk).exists():
            return _render({'erro': 'Já existe uma filial nesta província.'})

        # Verificar se email já existe no sistema (excluindo atual)
        if dados['email'] and email_ja_existe(dados['email'], exclude_model=FilialBanca, exclude_pk=filial.pk):
            return _render({'erro': 'Este email já está registado no sistema.'})

        for k, v in dados.items():
            setattr(filial, k, v)
        filial.save()

        return redirect('rh_banca')

    return _render()


@_requer_sessao
def filial_detalhe_view(request, pk):
    """Página de visualização simples da filial — dados, responsável, gestor e nº de colaboradores."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    if not is_desp and not ('gerir_rh' in _perm_set and col_log and not col_log.filial_id):
        messages.error(request, 'Apenas o despachante pode ver os dados da filial.')
        return redirect('rh_banca')

    try:
        filial = FilialBanca.objects.get(pk=pk, banca=banca)
    except FilialBanca.DoesNotExist:
        messages.error(request, 'A filial que tentou aceder não existe ou foi removida.')
        return redirect('rh_banca')

    total_colaboradores = filial.colaboradores.count()

    gestor_obj = None
    if hasattr(filial, 'gestores'):
        gestor_ativo = filial.gestores.select_related('colaborador').filter(ativo=True).first()
        if gestor_ativo:
            gestor_obj = gestor_ativo.colaborador

    ctx = _ctx(request, sub='filial_visualizar', extra={
        'filial': filial,
        'gestor': gestor_obj,
        'total_colaboradores': total_colaboradores,
    })
    return render(request, 'rh/filiais/visualizar.html', ctx)


@_requer_sessao
def filial_dashboard_view(request, pk):
    """Dashboard completo da filial para o despachante: RH, DU, Financeiro, Clientes, Logs."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    if not is_desp and not ('gerir_rh' in _perm_set and col_log and not col_log.filial_id):
        messages.error(request, 'Apenas o despachante pode ver o dashboard da filial.')
        return redirect('rh_banca')

    try:
        filial = FilialBanca.objects.get(pk=pk, banca=banca)
    except FilialBanca.DoesNotExist:
        messages.error(request, 'A filial que tentou aceder não existe ou foi removida.')
        return redirect('rh_banca')

    # Gestor da filial
    gestor = None
    if hasattr(filial, 'gestores'):
        gestor_ativo = filial.gestores.select_related('colaborador').filter(ativo=True).first()
        if gestor_ativo:
            gestor = gestor_ativo.colaborador

    # ── RH ──
    colaboradores = filial.colaboradores.all()
    total_colaboradores = colaboradores.count()
    colaboradores_ativos = colaboradores.filter(estado='Ativo').count()

    # ── DU ──
    dus = DeclaracaoUnica.objects.filter(filial_id=pk, banca=banca)
    total_du = dus.count()
    du_por_status = list(
        dus.values('status').annotate(total=Count('id')).order_by('status')
    )

    # ── Financeiro ──
    hoje = timezone.now()
    inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    facturas = FacturaCliente.objects.filter(filial_id=pk, banca=banca)
    total_facturado = facturas.aggregate(t=Sum('valor_total'))['t'] or 0
    total_pago = facturas.aggregate(t=Sum('valor_pago'))['t'] or 0
    facturas_pendentes = facturas.filter(estado__in=['Pendente', 'Parcialmente Paga']).count()
    facturado_mes = facturas.filter(data_emissao__gte=inicio_mes).aggregate(t=Sum('valor_total'))['t'] or 0

    recibos = ReciboCliente.objects.filter(filial_id=pk, banca=banca)
    total_recebido = recibos.aggregate(t=Sum('valor_recebido'))['t'] or 0
    recebido_mes = recibos.filter(data_pagamento__gte=inicio_mes).aggregate(t=Sum('valor_recebido'))['t'] or 0

    notas_credito = NotaCredito.objects.filter(filial_id=pk, banca=banca, estado='Aprovada')
    total_creditado = notas_credito.aggregate(t=Sum('valor_creditado'))['t'] or 0

    notas_debito = NotaDebito.objects.filter(filial_id=pk, banca=banca, estado='Aprovada')
    total_debitado = notas_debito.aggregate(t=Sum('valor'))['t'] or 0

    # ── Clientes ──
    total_clientes = Cliente.objects.filter(filial_id=pk, banca=banca).count()

    # ── Logs Recentes (paginados 20/20) ──
    logs_qs = LogAtividade.objects.filter(filial_id=pk).select_related('usuario').order_by('-created_at')
    paginator = Paginator(logs_qs, 20)
    page_num = request.GET.get('page')
    logs_recentes = paginator.get_page(page_num)

    # ── Facturas recentes (últimos 10) ──
    facturas_recentes = facturas.select_related('cliente').order_by('-data_emissao')[:10]

    return render(request, 'rh/filiais/detalhe.html', _ctx(request, 'filiais', {
        'banca': banca,
        'filial': filial,
        'gestor': gestor,
        # RH
        'total_colaboradores': total_colaboradores,
        'colaboradores_ativos': colaboradores_ativos,
        'colaboradores': colaboradores,
        # DU
        'total_du': total_du,
        'du_por_status': du_por_status,
        # Financeiro
        'total_facturado': total_facturado,
        'total_pago': total_pago,
        'facturas_pendentes': facturas_pendentes,
        'facturado_mes': facturado_mes,
        'total_recebido': total_recebido,
        'recebido_mes': recebido_mes,
        'total_creditado': total_creditado,
        'total_debitado': total_debitado,
        # Clientes
        'total_clientes': total_clientes,
        # Logs
        'logs_recentes': logs_recentes,
        # Facturas recentes
        'facturas_recentes': facturas_recentes,
    }))


@_requer_sessao
def filial_responsavel_novo_temp_view(request):
    """Criação de responsável para filial (fluxo temporário)."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_banca')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    # Obter dados temporários da sessão
    filial_data = request.session.get('filial_temp_data')
    if not filial_data:
        return redirect('rh_banca')

    colaboradores_elegiveis = _colaboradores_elegiveis_gestor(banca)

    def _render(extra=None):
        return render(request, 'rh/filiais/responsavel_form.html', _ctx(request, 'filiais', {
            'banca': banca, 'filial_data': filial_data,
            'cargos': CARGOS, 'estados': ESTADOS_COL,
            'colaboradores_elegiveis': colaboradores_elegiveis,
            **(extra or {}),
        }))

    if request.method == 'POST':
        if FilialBanca.objects.filter(banca=banca, provincia=filial_data['provincia']).exists():
            del request.session['filial_temp_data']
            messages.error(request, 'Já existe uma filial nesta província.')
            return _render()

        filial = FilialBanca(banca=banca, **filial_data)
        filial.save()

        ok, col, mensagem_email, erro = _processar_responsavel_filial_post(
            request, banca, filial,
        )
        if not ok:
            filial.delete()
            messages.error(request, erro or 'Não foi possível criar o responsável.')
            return _render()

        del request.session['filial_temp_data']
        messages.success(request, f'Gestor da filial {filial.provincia} definido com sucesso!')
        if mensagem_email:
            messages.success(request, mensagem_email)
        return redirect('rh_filial_detalhe', pk=filial.pk)

    return _render()


@_requer_sessao
def filial_responsavel_novo_view(request, pk):
    """Criação de responsável para filial existente."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_banca')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    filial = get_object_or_404(FilialBanca, pk=pk, banca=banca)

    colaboradores_elegiveis = _colaboradores_elegiveis_gestor(banca, filial=filial)

    def _render(extra=None):
        return render(request, 'rh/filiais/responsavel_form.html', _ctx(request, 'filiais', {
            'banca': banca, 'filial': filial,
            'cargos': CARGOS, 'estados': ESTADOS_COL,
            'colaboradores_elegiveis': colaboradores_elegiveis,
            **(extra or {}),
        }))

    if request.method == 'POST':
        ok, col, mensagem_email, erro = _processar_responsavel_filial_post(
            request, banca, filial,
        )
        if not ok:
            messages.error(request, erro or 'Não foi possível criar o responsável.')
            return _render()

        messages.success(request, f'Gestor da filial {filial.provincia} definido com sucesso!')
        if mensagem_email:
            messages.success(request, mensagem_email)
        return redirect('rh_filial_detalhe', pk=filial.pk)

    return _render()


@_requer_sessao
def filial_apagar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_banca')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    if request.method != 'POST':
        return redirect('rh_banca')

    filial = get_object_or_404(FilialBanca, pk=pk, banca=banca)
    provincia = filial.provincia

    try:
        # Desassociar gestores antes de remover a filial
        gestores = list(filial.gestores.select_related('colaborador').all())
        for gestor in gestores:
            colaborador = gestor.colaborador
            gestor.delete()
            if colaborador.filial_id == filial.pk:
                colaborador.filial = None
                colaborador.save(update_fields=['filial'])
        # Desassociar colaboradores e vagas antes de remover a filial
        filial.colaboradores.exclude(
            pk__in=[g.colaborador.pk for g in gestores]
        ).update(filial=None)
        filial.vagas.update(filial=None)
        filial.delete()
        messages.success(request, f'Filial {provincia} removida com sucesso.')
    except Exception as exc:
        messages.error(
            request,
            f'Não foi possível remover a filial {provincia}: {exc}',
        )

    return redirect('rh_banca')


# ══════════════════════════════════════════════════════════════════════════════
# COLABORADORES
# ══════════════════════════════════════════════════════════════════════════════

def _cargos_banca_para_gestor(banca, is_desp, pode_ver_todos=False):
    """Retorna cargos conforme o âmbito:
    - Despachante (is_desp=True) ou RH Sede (pode_ver_todos=True): TODOS os cargos
    - Gestor ou RH Filial:                                          só filial-level
    Cada cargo tem o atributo `.tem_perm_fora` (True = banca-level, False = filial-level).
    """
    from django.db.models import Exists, OuterRef
    perm_fora = Permissao.objects.filter(
        cargos_banca=OuterRef('pk')
    ).exclude(codigo__in=PERMISSOES_GESTOR_CARGO)
    cargos = banca.cargos.annotate(
        tem_perm_fora=Exists(perm_fora)
    )
    if is_desp or pode_ver_todos:
        return cargos.prefetch_related('permissoes')
    return cargos.filter(tem_perm_fora=False).prefetch_related('permissoes')


def _pode_gerir_cargo(col_alvo, col_log, gestor, is_desp, perm_set):
    """Hierarquia: quem pode atribuir/remover cargo de col_alvo?
    Apenas Despachantes (toda a banca) e Gestores de Filial (mesma filial)."""
    # Despachante: pode tudo
    if is_desp:
        return True
    # Ninguém se auto-atribui ou auto-remove cargo
    if col_alvo.pk == col_log.pk:
        return False
    # GestorFilial: ninguém mais pode mexer no cargo de um gestor
    try:
        alvo_e_gestor = col_alvo.gestor_filial.ativo if col_alvo.gestor_filial else False
    except Exception:
        alvo_e_gestor = False
    if alvo_e_gestor:
        return False
    # Gestor de Filial: gere cargos na sua filial
    if gestor and gestor.filial_id and col_alvo.filial_id == gestor.filial_id:
        return True
    return False


@_requer_sessao
def colaboradores_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    papel = request.session.get('usuario', {}).get('papel', '')
    from users.permissoes import _is_admin_ou_acesso_total
    # Administrador vê todos os colaboradores da banca
    if papel == 'Administrador':
        cols = banca.colaboradores.all().select_related('filial', 'cargo_banca').prefetch_related('documentos')
        filiais = list(banca.filiais.all())
    else:
        cols = escopo_colaboradores(
            banca, col_log, gestor, is_desp, request=request,
        ).select_related('filial', 'cargo_banca').prefetch_related('documentos')
        filiais = (
            list(banca.filiais.all()) if is_desp
            else [f for f in [banca.filiais.filter(pk=gestor.filial_id).first()] if f] if gestor else []
        )
    # Filtro por filial (0 = Sede)
    filial_id = request.GET.get('filial')
    filial_selected = None
    if filial_id:
        try:
            filial_selected = int(filial_id)
            if filial_selected == 0:
                cols = cols.filter(filial__isnull=True)
            else:
                cols = cols.filter(filial_id=filial_selected)
        except (ValueError, TypeError):
            pass
    cols = cols.order_by('nome')
    paginator = Paginator(cols, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    perm_set = get_usuario_permissoes(request)
    pode_ver_todos = not is_desp and 'gerir_rh' in perm_set and not col_log.filial_id
    cargos_banca = _cargos_banca_para_gestor(banca, is_desp, pode_ver_todos=pode_ver_todos)
    stats = cols.aggregate(
        total=Count('pk'),
        ativos=Count('pk', filter=Q(estado='Ativo')),
        inativos=Count('pk', filter=Q(estado='Inativo')),
        suspensos=Count('pk', filter=Q(estado='Suspenso')),
    )
    return render(request, 'rh/colaboradores/lista.html',
                  _ctx(request, 'colaboradores', {
                      'banca': banca, 'colaboradores': page_obj, 'filiais': filiais,
                      'filial_selected': filial_selected, 'page_obj': page_obj,
                      'cargos_banca': cargos_banca, 'stats': stats,
                  }))


@_requer_sessao
def colaborador_novo_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    _perm_set = get_usuario_permissoes(request)
    _pode_todos = not is_desp and 'gerir_rh' in _perm_set and not col_log.filial_id
    pode_todas_filiais = is_desp or ('gerir_rh' in _perm_set and not col_log.filial_id)
    filiais = (
        list(banca.filiais.prefetch_related('gestores').all()) if pode_todas_filiais
        else [f for f in [banca.filiais.filter(pk=gestor.filial_id).first()] if f] if gestor
        else [banca.filiais.filter(pk=col_log.filial_id).first()] if col_log and col_log.filial_id else []
    )
    filiais_sem_gestor = [f for f in filiais if not any(g.ativo for g in f.gestores.all())]

    cargos_banca = _cargos_banca_para_gestor(banca, is_desp, pode_ver_todos=_pode_todos)
    cargos_permissoes_json = json.dumps({
        str(cb.pk): {
            'nome': cb.nome,
            'descricao': cb.descricao or '',
            'permissoes': [{'codigo': p.codigo, 'nome': p.nome} for p in cb.permissoes.all()]
        }
        for cb in cargos_banca
    })
    def _render(extra=None):
        return render(request, 'rh/colaboradores/form.html',
                      _ctx(request, 'colaboradores', {
                          'banca': banca, 'filiais': filiais,
                          'filiais_sem_gestor': filiais_sem_gestor,
                          'gestor_filial': None,
                          'cargos': CARGOS, 'estados': ESTADOS_COL,
                          'cargos_banca': cargos_banca,
                          'cargos_permissoes_json': cargos_permissoes_json,
                          'col': None, **(extra or {}),
                      }))

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if not nome:
            messages.error(request, 'O nome é obrigatório.')
            return _render()
        
        email_colaborador = request.POST.get('email', '').strip()

        # Verificar se email já existe no sistema
        if email_colaborador and email_ja_existe(email_colaborador):
            messages.error(request, 'Este email já está registado no sistema.')
            return _render()

        # Gerar senha apenas se tiver email
        senha_gerada = None
        senha_hash = None
        if email_colaborador:
            senha_gerada = gerar_senha_aleatoria()
            senha_hash = _hash_password(senha_gerada)
        
        filial_id = filial_id_obrigatoria_gestor(
            gestor, is_desp, request.POST.get('filial') or None, col_log=col_log, banca=banca,
        )
        col = Colaborador(
            banca=banca,
            filial_id=filial_id,
            nome=nome,
            bi=request.POST.get('bi', '').strip(),
            nif=request.POST.get('nif', '').strip(),
            genero=request.POST.get('genero', ''),
            data_nascimento=request.POST.get('data_nascimento') or None,
            cargo=request.POST.get('cargo', 'Assistente'),
            cargo_personalizado=request.POST.get('cargo_personalizado', '').strip(),
            departamento=request.POST.get('departamento', '').strip(),
            email=email_colaborador,
            telefone=request.POST.get('telefone', '').strip(),
            data_admissao=request.POST.get('data_admissao') or None,
            salario_base=_dec(request.POST.get('salario_base')) or None,
            estado=request.POST.get('estado', 'Ativo'),
            observacoes=request.POST.get('observacoes', '').strip(),
            password=senha_hash,
            banco=request.POST.get('banco', '').strip(),
            num_conta=request.POST.get('num_conta', '').strip(),
            iban=request.POST.get('iban', '').strip(),
            titular_conta=request.POST.get('titular_conta', '').strip(),
        )
        if 'foto' in request.FILES:
            col.foto = request.FILES['foto']
        try:
            col.save()
        except ValidationError as e:
            for campo, erros in e.message_dict.items():
                for erro in erros:
                    messages.error(request, f'{campo}: {erro}')
            return _render()

        # Atribuir cargo_banca com sincronização integrada do GestorFilial
        cargo_banca_pk = request.POST.get('cargo_banca', '').strip()

        # Identificar o PK do cargo "Gestor de Filial"
        cargo_gf = None
        try:
            cargo_gf = banca.cargos.get(nome='Gestor de Filial')
        except CargoBanca.DoesNotExist:
            pass
        cargo_gf_pk = str(cargo_gf.pk) if cargo_gf else ''

        # Colaborador sem email não pode ter cargo ou função
        if cargo_banca_pk and not email_colaborador:
            messages.error(request, 'Colaborador sem email não pode receber cargos ou funções no sistema.')
            return _render()

        if cargo_banca_pk and cargo_banca_pk == cargo_gf_pk:
            # ── "Gestor de Filial": requer filial e cria GestorFilial ──
            if not email_colaborador:
                messages.error(request, 'Gestor de filial precisa de email para aceder ao sistema.')
                col.delete()
                return _render()
            if not is_desp and not ('gerir_rh' in _perm_set and not col_log.filial_id):
                messages.error(request, 'Não pode atribuir este cargo.')
                return redirect('rh_colaboradores')
            filial_pk = request.POST.get('filial_gestor', '').strip()
            if not filial_pk:
                messages.error(request, 'Seleccione a filial para o gestor.')
                col.delete()
                return _render()
            try:
                filial = banca.filiais.get(pk=filial_pk)
            except FilialBanca.DoesNotExist:
                messages.error(request, 'Filial inválida.')
                col.delete()
                return _render()
            if filial.gestores.filter(ativo=True).exists():
                messages.error(request, f'A filial {filial.provincia} já tem gestor.')
                col.delete()
                return _render()
            _atribuir_gestor_filial(col, filial)
            msg_cargo = f' — Cargo: Gestor de Filial (alocado à {filial.provincia})'
        else:
            # ── Qualquer outro cargo (ou "Sem cargo especial") ──
            if cargo_banca_pk:
                try:
                    cargo = banca.cargos.get(pk=cargo_banca_pk)
                    pode_banca = 'gerir_rh' in _perm_set and not col_log.filial_id
                    if not is_desp and not pode_banca and (
                        cargo.nome == 'Gestor de Filial' or
                        cargo.permissoes.exclude(codigo__in=PERMISSOES_GESTOR_CARGO).exists()
                    ):
                        pass  # gestor / RH Filial não pode atribuir este cargo
                    else:
                        col.cargo_banca = cargo
                        col.save(update_fields=['cargo_banca'])
                except CargoBanca.DoesNotExist:
                    pass
            msg_cargo = f' — Cargo: {col.cargo_banca.nome}' if col.cargo_banca_id else ''
        
        # Scope info
        if col.filial_id:
            try:
                nome_filial = col.filial.provincia
            except Exception:
                nome_filial = f"Filial #{col.filial_id}"
            scope_msg = f" (alocado à {nome_filial})"
        else:
            scope_msg = " (âmbito: Sede / Banca)"
        scope_msg = f'{msg_cargo}{scope_msg}'

        # Enviar email com senha se tiver email
        if email_colaborador and senha_gerada:
            sucesso_email, msg_email = enviar_senha_colaborador(col, senha_gerada)
            if sucesso_email:
                messages.success(request, f'Colaborador {nome} criado! Credenciais enviadas para {email_colaborador}.')
            else:
                messages.success(request, f'Colaborador {nome} criado com sucesso!{scope_msg}')
                messages.warning(request, f'Não foi possível enviar o email de credenciais: {msg_email}. Use o botão "Reenviar" na lista.')
        else:
            messages.success(request, f'Colaborador {nome} criado com sucesso!{scope_msg}')
            if not email_colaborador:
                messages.info(request, 'Sem email registado — o colaborador não receberá credenciais de acesso.')

        # Processar documentos enviados
        for i in range(5):
            arquivo_key = f'documento_arquivo_{i}'
            tipo_key = f'documento_tipo_{i}'
            desc_key = f'documento_desc_{i}'
            if arquivo_key in request.FILES and tipo_key in request.POST:
                arquivo = request.FILES[arquivo_key]
                tipo = request.POST[tipo_key]
                descricao = request.POST.get(desc_key, '').strip()
                if arquivo and tipo:
                    DocumentoColaborador.objects.create(
                        colaborador=col,
                        tipo=tipo,
                        arquivo=arquivo,
                        descricao=descricao,
                    )

        return redirect('rh_colaboradores')
    return _render()


@_requer_sessao
def colaborador_dados_api(request, pk):
    """Devolve dados do colaborador em JSON (preenchimento automático do formulário de gestor)."""
    acc = obter_acesso_rh(request)
    if not acc:
        return JsonResponse({'erro': 'Sem acesso RH'}, status=403)
    banca, col_log, gestor, is_desp = acc
    col = get_object_or_404(Colaborador, pk=pk, banca=banca)
    if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, col):
        return JsonResponse({'erro': 'Sem permissão para aceder a este colaborador'}, status=403)
    return JsonResponse(_colaborador_para_json(col))


@_requer_sessao
def colaborador_editar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    col = get_object_or_404(Colaborador, pk=pk, banca=banca)
    if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, col):
        messages.error(request, 'Sem permissão para editar este colaborador.')
        return redirect('rh_colaboradores')
    _perm_set = get_usuario_permissoes(request)
    pode_todas_filiais = is_desp or ('gerir_rh' in _perm_set and not col_log.filial_id)
    filiais = (
        list(banca.filiais.prefetch_related('gestores').all()) if pode_todas_filiais
        else [f for f in [banca.filiais.filter(pk=gestor.filial_id).first()] if f] if gestor
        else [banca.filiais.filter(pk=col_log.filial_id).first()] if col_log and col_log.filial_id else []
    )
    gestor_filial = None
    try:
        gf = col.gestor_filial
        if gf.ativo:
            gestor_filial = gf
    except GestorFilial.DoesNotExist:
        pass

    filiais_sem_gestor = []
    for f in filiais:
        if not any(g.ativo for g in f.gestores.all()):
            filiais_sem_gestor.append(f)
        elif gestor_filial and gestor_filial.filial_id == f.pk:
            filiais_sem_gestor.append(f)

    _pode_todos = not is_desp and 'gerir_rh' in _perm_set and not col_log.filial_id
    cargos_banca = _cargos_banca_para_gestor(banca, is_desp, pode_ver_todos=_pode_todos)
    cargos_permissoes_json = json.dumps({
        str(cb.pk): {
            'nome': cb.nome,
            'descricao': cb.descricao or '',
            'permissoes': [{'codigo': p.codigo, 'nome': p.nome} for p in cb.permissoes.all()]
        }
        for cb in cargos_banca
    })

    def _render(extra=None):
        return render(request, 'rh/colaboradores/form.html',
                      _ctx(request, 'colaboradores', {
                          'banca': banca, 'col': col, 'filiais': filiais,
                          'cargos': CARGOS, 'estados': ESTADOS_COL,
                          'cargos_banca': cargos_banca,
                          'cargos_permissoes_json': cargos_permissoes_json,
                          'gestor_filial': gestor_filial,
                          'filiais_sem_gestor': filiais_sem_gestor,
                          **(extra or {}),
                      }))

    if request.method == 'POST':
        col.filial_id = filial_id_obrigatoria_gestor(
            gestor, is_desp, request.POST.get('filial') or None, col_log=col_log, banca=banca,
        ) if is_desp or col.pk != col_log.pk else col_log.filial_id
        col.nome = request.POST.get('nome', '').strip()
        col.bi = request.POST.get('bi', '').strip()
        col.nif = request.POST.get('nif', '').strip()
        col.genero = request.POST.get('genero', '')
        col.data_nascimento = request.POST.get('data_nascimento') or None
        col.cargo = request.POST.get('cargo', 'Assistente')
        col.cargo_personalizado = request.POST.get('cargo_personalizado', '').strip()
        col.departamento = request.POST.get('departamento', '').strip()
        col.email = request.POST.get('email', '').strip()
        if col.email and email_ja_existe(col.email, exclude_model=Colaborador, exclude_pk=col.pk):
            messages.error(request, 'Este email já está registado no sistema.')
            return _render()
        col.telefone = request.POST.get('telefone', '').strip()
        col.data_admissao = request.POST.get('data_admissao') or None
        col.salario_base = _dec(request.POST.get('salario_base')) or None
        col.estado = request.POST.get('estado', 'Ativo')
        col.observacoes = request.POST.get('observacoes', '').strip()
        col.banco = request.POST.get('banco', '').strip()
        col.num_conta = request.POST.get('num_conta', '').strip()
        col.iban = request.POST.get('iban', '').strip()
        col.titular_conta = request.POST.get('titular_conta', '').strip()
        if 'foto' in request.FILES:
            col.foto = request.FILES['foto']

        # Colaborador sem email — limpar password e impedir cargos
        email_vazio = not col.email
        if email_vazio:
            col.password = None

        # Processar cargo_banca com sincronização integrada do GestorFilial
        cargo_banca_pk = request.POST.get('cargo_banca', '').strip()
        cargo_mudou = cargo_banca_pk != (str(col.cargo_banca_id) if col.cargo_banca_id else '')

        # Identificar o PK do cargo "Gestor de Filial"
        cargo_gf = None
        try:
            cargo_gf = banca.cargos.get(nome='Gestor de Filial')
        except CargoBanca.DoesNotExist:
            pass
        cargo_gf_pk = str(cargo_gf.pk) if cargo_gf else ''

        # Colaborador sem email não pode ter cargo ou função
        if cargo_banca_pk and email_vazio:
            messages.error(request, 'Colaborador sem email não pode receber cargos ou funções no sistema.')
            return _render()

        if cargo_banca_pk and cargo_banca_pk == cargo_gf_pk:
            # ── "Gestor de Filial": requer filial e cria/actualiza GestorFilial ──
            if email_vazio:
                messages.error(request, 'Gestor de filial precisa de email para aceder ao sistema.')
                return _render()
            if cargo_mudou:
                perm_set = get_usuario_permissoes(request)
                if not _pode_gerir_cargo(col, col_log, gestor, is_desp, perm_set):
                    messages.error(request, 'Não tem permissão para alterar o cargo deste colaborador.')
                    return redirect('rh_colaborador_editar', pk=col.pk)
            filial_pk = request.POST.get('filial_gestor', '').strip()
            if not filial_pk:
                messages.error(request, 'Seleccione a filial para o gestor.')
                return _render()
            try:
                filial = banca.filiais.get(pk=filial_pk)
            except FilialBanca.DoesNotExist:
                messages.error(request, 'Filial inválida.')
                return _render()
            outro_gestor_ativo = filial.gestores.filter(ativo=True).exclude(colaborador=col).first()
            if outro_gestor_ativo:
                messages.error(
                    request,
                    f'A filial {filial.provincia} já tem gestor: {outro_gestor_ativo.colaborador.nome}.',
                )
                return _render()
            try:
                gf_atual = col.gestor_filial
                if gf_atual.ativo and gf_atual.filial_id != filial.pk:
                    messages.error(
                        request,
                        f'{col.nome} já gere a filial {gf_atual.filial.provincia}.',
                    )
                    return _render()
            except GestorFilial.DoesNotExist:
                pass
            _atribuir_gestor_filial(col, filial)
            messages.success(
                request,
                f'{col.nome} — Cargo: Gestor de Filial (alocado à {filial.provincia}).',
            )
            _processar_documentos_colaborador(col, request)
            return redirect('rh_colaboradores')

        # ── Qualquer outro cargo (ou "Sem cargo especial") ──
        if cargo_mudou:
            perm_set = get_usuario_permissoes(request)
            if not _pode_gerir_cargo(col, col_log, gestor, is_desp, perm_set):
                messages.error(request, 'Não tem permissão para alterar o cargo deste colaborador.')
                return redirect('rh_colaborador_editar', pk=col.pk)
        if cargo_banca_pk:
            try:
                cargo = banca.cargos.get(pk=cargo_banca_pk)
                pode_banca = 'gerir_rh' in get_usuario_permissoes(request) and not col_log.filial_id
                if not is_desp and not pode_banca and (
                    cargo.nome == 'Gestor de Filial' or
                    cargo.permissoes.exclude(codigo__in=PERMISSOES_GESTOR_CARGO).exists()
                ):
                    messages.error(request, 'Não pode atribuir este cargo.')
                    return redirect('rh_colaborador_editar', pk=col.pk)
                col.cargo_banca = cargo
            except CargoBanca.DoesNotExist:
                messages.error(request, 'Cargo inválido.')
                return _render()
        else:
            col.cargo_banca = None

        # Se o cargo mudou e o novo NÃO é "Gestor de Filial", remover GestorFilial se existir
        if cargo_mudou:
            e_gestor_filial_agora = bool(cargo_gf and col.cargo_banca_id == cargo_gf.pk)
            if not e_gestor_filial_agora:
                try:
                    if col.gestor_filial and col.gestor_filial.ativo:
                        _remover_gestor_filial(col)
                except GestorFilial.DoesNotExist:
                    pass

        col.save()
        _processar_documentos_colaborador(col, request)

        # Mensagem com scope
        if col.filial_id:
            try:
                nome_filial = col.filial.provincia
            except Exception:
                nome_filial = f"Filial #{col.filial_id}"
            scope_msg = f" (alocado à {nome_filial})"
        else:
            scope_msg = " (âmbito: Sede / Banca)"
        if col.cargo_banca:
            messages.success(
                request,
                f'{col.nome} actualizado — Cargo: {col.cargo_banca.nome}{scope_msg}',
            )
        else:
            messages.success(request, f'{col.nome} actualizado{scope_msg}')
        return redirect('rh_colaboradores')
    return _render()


@_requer_sessao
def colaborador_detalhe_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    col = get_object_or_404(Colaborador, pk=pk, banca=banca)
    if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, col):
        messages.error(request, 'Sem permissão para visualizar este colaborador.')
        return redirect('rh_colaboradores')
    return render(request, 'rh/colaboradores/detalhe.html',
                  _ctx(request, 'colaboradores', {
                      'col': col,
                      'cargos_banca': _cargos_banca_para_gestor(banca, is_desp),
                  }))


@_requer_sessao
def colaborador_apagar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    if not is_desp and not ('gerir_rh' in _perm_set and col_log and not col_log.filial_id):
        messages.error(request, 'Apenas o despachante pode remover colaboradores.')
        return redirect('rh_colaboradores')
    col = get_object_or_404(Colaborador, pk=pk, banca=banca)
    col.delete()
    messages.success(request, 'Colaborador removido com sucesso.')
    return redirect('rh_colaboradores')


@_requer_sessao
def colaborador_reenviar_email_view(request, pk):
    """Gera nova senha e reenvia email de credenciais ao colaborador."""
    banca = _banca(request)
    if not banca:
        return redirect('rh_banca')

    col = get_object_or_404(Colaborador, pk=pk, banca=banca)

    if request.method != 'POST':
        return redirect('rh_colaboradores')

    if not col.email:
        messages.error(request, f'{col.nome} não tem email registado.')
        return redirect('rh_colaboradores')

    # Gerar nova senha e guardar hash
    nova_senha = gerar_senha_aleatoria()
    col.password = _hash_password(nova_senha)
    col.save(update_fields=['password'])

    # Enviar email
    from utils.email_utils import enviar_senha_colaborador
    sucesso, msg = enviar_senha_colaborador(col, nova_senha)
    if sucesso:
        messages.success(request, f'Nova senha gerada e enviada para {col.email}.')
    else:
        messages.error(request, f'Falhou o envio para {col.email}: {msg}')

    return redirect('rh_colaboradores')


@_requer_sessao
def documento_colaborador_download(request, pk):
    """Faz o download de um documento específico do colaborador"""
    banca = _banca(request)
    if not banca:
        return redirect('rh_banca')

    documento = get_object_or_404(DocumentoColaborador, pk=pk, colaborador__banca=banca)

    if not documento.arquivo:
        return render(request, 'rh/colaboradores/erro_documento.html',
                      _ctx(request, 'colaboradores', {
                          'banca': banca, 'documento': documento,
                          'erro': 'Este documento não possui arquivo associado.'
                      }))

    # Configurar response para download
    response = HttpResponse(documento.arquivo.read(), content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{documento.nome_arquivo}"'
    response['Content-Length'] = documento.arquivo.size

    return response


@_requer_sessao
def documento_colaborador_apagar_view(request, pk):
    """Remove um documento específico do colaborador"""
    banca = _banca(request)
    if not banca:
        return redirect('rh_banca')

    documento = get_object_or_404(DocumentoColaborador, pk=pk, colaborador__banca=banca)
    colaborador_pk = documento.colaborador.pk

    if request.method == 'POST':
        # Remover o arquivo do sistema
        if documento.arquivo:
            documento.arquivo.delete()
        documento.delete()
        return redirect('rh_colaborador_editar', pk=colaborador_pk)

    return render(request, 'rh/colaboradores/apagar_documento.html',
                  _ctx(request, 'colaboradores', {
                      'banca': banca, 'documento': documento,
                  }))


# ══════════════════════════════════════════════════════════════════════════════
# Subsídios
@_requer_sessao
def subsidios_view(request):
    """Lista todos os subsídios configurados para a banca."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'dashboard_colaborador')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    from .models import Subsidio
    subsidios = banca.subsidios.all().order_by('codigo')
    paginator = Paginator(subsidios, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'rh/subsidios/lista.html',
                  _ctx(request, 'subsidios', {
                      'banca': banca,
                      'subsidios': page_obj,
                      'page_obj': page_obj,
                  }))


@_requer_sessao
def subsidio_novo_view(request):
    """Cria um novo tipo de subsídio"""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc)
    if bloqueio:
        return bloqueio
    banca = acc[0]

    from .models import Subsidio, Colaborador

    def _render(extra=None):
        return render(request, 'rh/subsidios/form.html',
                      _ctx(request, 'subsidios', {
                          'banca': banca, 'subsidio': None, 'form': {},
                          'tipos_calculo': Subsidio.TIPOS_CALCULO,
                          'colaboradores_banca': banca.colaboradores.filter(estado='Ativo').order_by('nome'),
                          **(extra or {}),
                      }))

    if request.method == 'POST':
        apenas_especificos = request.POST.get('apenas_especificos') == 'on'
        dados = {
            'nome': request.POST.get('nome', '').strip(),
            'codigo': request.POST.get('codigo', '').strip().upper(),
            'tipo_calculo': request.POST.get('tipo_calculo', 'FIXO'),
            'valor_padrao': _dec(request.POST.get('valor_padrao', '0')),
            'percentual': (
                _dec(request.POST.get('percentual', '0'))
                if request.POST.get('percentual') else None
            ),
            'ativo': request.POST.get('ativo') == 'on',
            'obrigatorio': request.POST.get('obrigatorio') == 'on',
            'apenas_especificos': apenas_especificos,
            'descricao': request.POST.get('descricao', '').strip(),
        }

        # Validações
        if not dados['nome']:
            return _render({'erro': 'Nome do subsídio é obrigatório.'})
        if not dados['codigo']:
            return _render({'erro': 'Código do subsídio é obrigatório.'})
        if dados['tipo_calculo'] == 'PERCENTUAL' and not dados['percentual']:
            return _render({'erro': 'Percentual é obrigatório para tipo Percentual.'})
        if apenas_especificos and not request.POST.getlist('colaboradores_ids'):
            return _render({'erro': 'Selecione pelo menos um colaborador para subsídio específico.'})

        # obrigatorio e apenas_especificos são mutuamente exclusivos
        if dados['obrigatorio']:
            dados['apenas_especificos'] = False

        # Verificar código duplicado
        if banca.subsidios.filter(codigo=dados['codigo']).exists():
            return _render({'erro': 'Já existe um subsídio com este código.'})

        subsidio = Subsidio(banca=banca, **dados)
        subsidio.save()

        # Guardar colaboradores específicos
        if dados['apenas_especificos']:
            ids = request.POST.getlist('colaboradores_ids')
            cols = banca.colaboradores.filter(pk__in=ids)
            subsidio.colaboradores_especificos.set(cols)

        return redirect('rh_subsidios')

    return _render()


@_requer_sessao
def subsidio_editar_view(request, pk):
    """Edita um subsídio existente — sempre editável, independente dos processamentos."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc)
    if bloqueio:
        return bloqueio
    banca = acc[0]

    from .models import Subsidio
    subsidio = get_object_or_404(Subsidio, pk=pk, banca=banca)

    def _render(extra=None):
        form_data = {
            'nome': subsidio.nome,
            'codigo': subsidio.codigo,
            'tipo_calculo': subsidio.tipo_calculo,
            'valor_padrao': subsidio.valor_padrao,
            'percentual': subsidio.percentual,
            'ativo': subsidio.ativo,
            'obrigatorio': subsidio.obrigatorio,
            'apenas_especificos': subsidio.apenas_especificos,
            'descricao': subsidio.descricao,
        }
        return render(request, 'rh/subsidios/form.html',
                      _ctx(request, 'subsidios', {
                          'banca': banca, 'subsidio': subsidio, 'form': form_data,
                          'tipos_calculo': Subsidio.TIPOS_CALCULO,
                          'colaboradores_banca': banca.colaboradores.filter(estado='Ativo').order_by('nome'),
                          'colaboradores_selecionados': list(subsidio.colaboradores_especificos.values_list('pk', flat=True)),
                          'form': form_data, **(extra or {}),
                      }))

    if request.method == 'POST':
        apenas_especificos = request.POST.get('apenas_especificos') == 'on'
        dados = {
            'nome': request.POST.get('nome', '').strip(),
            'codigo': request.POST.get('codigo', '').strip().upper(),
            'tipo_calculo': request.POST.get('tipo_calculo', 'FIXO'),
            'valor_padrao': _dec(request.POST.get('valor_padrao', '0')),
            'percentual': (
                _dec(request.POST.get('percentual', '0'))
                if request.POST.get('percentual') else None
            ),
            'ativo': request.POST.get('ativo') == 'on',
            'obrigatorio': request.POST.get('obrigatorio') == 'on',
            'apenas_especificos': apenas_especificos,
            'descricao': request.POST.get('descricao', '').strip(),
        }

        # Validações
        if not dados['nome']:
            return _render({'erro': 'Nome do subsídio é obrigatório.'})
        if not dados['codigo']:
            return _render({'erro': 'Código do subsídio é obrigatório.'})
        if dados['tipo_calculo'] == 'PERCENTUAL' and not dados['percentual']:
            return _render({'erro': 'Percentual é obrigatório para tipo Percentual.'})
        if apenas_especificos and not request.POST.getlist('colaboradores_ids'):
            return _render({'erro': 'Selecione pelo menos um colaborador para subsídio específico.'})

        if dados['obrigatorio']:
            dados['apenas_especificos'] = False

        # Verificar código duplicado (exceto o atual)
        if banca.subsidios.filter(codigo=dados['codigo']).exclude(pk=pk).exists():
            return _render({'erro': 'Já existe um subsídio com este código.'})

        for campo, valor in dados.items():
            setattr(subsidio, campo, valor)
        subsidio.save()

        # Atualizar colaboradores específicos
        if subsidio.apenas_especificos:
            ids = request.POST.getlist('colaboradores_ids')
            cols = banca.colaboradores.filter(pk__in=ids)
            subsidio.colaboradores_especificos.set(cols)
        else:
            subsidio.colaboradores_especificos.clear()

        return redirect('rh_subsidios')

    return _render()


@_requer_sessao
def subsidio_apagar_view(request, pk):
    """Remove um subsídio — apenas bloqueado se estiver em recibos existentes."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc)
    if bloqueio:
        return bloqueio
    banca = acc[0]

    from .models import Subsidio
    subsidio = get_object_or_404(Subsidio, pk=pk, banca=banca)

    if request.method == 'POST':
        # Bloquear apenas se já está vinculado a recibos (qualquer estado)
        if subsidio.subsidiorecibo_set.exists():
            return render(request, 'rh/subsidios/erro.html',
                          _ctx(request, 'subsidios', {
                              'banca': banca, 'subsidio': subsidio,
                              'erro': 'Este subsídio não pode ser removido pois já está sendo usado em recibos salariais.',
                          }))

        subsidio.delete()
        messages.success(request, f'Subsídio "{subsidio.nome}" removido com sucesso.')
        return redirect('rh_subsidios')

    return render(request, 'rh/subsidios/apagar.html',
                  _ctx(request, 'subsidios', {
                      'banca': banca, 'subsidio': subsidio,
                  }))


# PROCESSAMENTO SALARIAL
# ══════════════════════════════════════════════════════════════════════════════
@_requer_sessao
def salarios_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'colaborador_salario')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    todos = banca.processamentos.annotate(
        total_recibos=Count('recibos'),
    ).prefetch_related('recibos').order_by('-ano', '-mes')

    paginator = Paginator(todos, 8)
    pagina_num = request.GET.get('pagina', 1)
    try:
        pagina_num = int(pagina_num)
    except (ValueError, TypeError):
        pagina_num = 1
    pagina = paginator.get_page(pagina_num)

    return render(request, 'rh/salarios/lista.html',
                  _ctx(request, 'salarios', {
                      'banca': banca,
                      'processamentos': pagina,
                      'paginator': paginator,
                      'pagina_actual': pagina_num,
                      'total': todos.count(),
                  }))


@_requer_sessao
def salario_novo_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_salarios')
    if bloqueio:
        return bloqueio
    banca = acc[0]
    colaboradores = banca.colaboradores.filter(estado='Ativo')
    if request.method == 'POST':
        mes = int(request.POST.get('mes') or 1)
        ano = int(request.POST.get('ano') or timezone.now().year)
        proc, criado = ProcessamentoSalarial.objects.get_or_create(
            banca=banca, mes=mes, ano=ano,
            filial_id=request.session.get('colaborador_filial_id'),
            defaults={'estado': 'Rascunho'}
        )
        if not criado:
            return render(request, 'rh/salarios/novo.html',
                          _ctx(request, 'salarios', {
                              'banca': banca, 'colaboradores': colaboradores,
                              'meses': MESES,
                              'ano_atual': timezone.now().year,
                              'erro': f'Já existe processamento para {MESES[mes-1]}/{ano}.',
                          }))
        # Colaboradores seleccionados para processar
        cols_selecionados = set(map(int, request.POST.getlist('colaboradores')))
        cols_processar = [col for col in colaboradores if col.id in cols_selecionados]
        if not cols_processar:
            return render(request, 'rh/salarios/novo.html',
                          _ctx(request, 'salarios', {
                              'banca': banca, 'colaboradores': colaboradores,
                              'meses': MESES, 'ano_atual': timezone.now().year,
                              'erro': 'Seleccione pelo menos um colaborador para processar.',
                          }))
        # Obter todos os subsídios ativos da banca
        subsidios_banca = list(banca.subsidios.filter(ativo=True))

        # Pré-carregar M2M de subsídios específicos (bulk, 1 query por subsídio)
        subsidio_colab_ids = {}
        for s in subsidios_banca:
            if s.apenas_especificos:
                subsidio_colab_ids[s.pk] = set(
                    s.colaboradores_especificos.values_list('id', flat=True)
                )

        for col in cols_processar:
            salario = col.salario_efetivo
            # Colaborador sem email não tem controlo de presença — faltas zero
            if not col.email:
                faltas = 0
            else:
                faltas = RegistoPresenca.objects.filter(
                    colaborador=col,
                    data__month=mes, data__year=ano,
                    tipo='Falta',
                    estado__in=['Pendente', 'Aprovado'],
                ).count()
            # Dias úteis no mês; desconto proporcional por falta
            dias_uteis = Decimal(str(max(1, sum(
                1 for d in range(1, calendar.monthrange(ano, mes)[1] + 1)
                if date(ano, mes, d).weekday() < 5
            ))))
            desconto_faltas = (salario / dias_uteis * faltas).quantize(Decimal('0.01')) if faltas > 0 else Decimal('0')
            salario_apos_faltas = max(salario - desconto_faltas, Decimal('0'))
            # IRT Angola — tabela simplificada (sobre salário bruto)
            irt = _calcular_irt(salario_apos_faltas)
            # INSS trabalhador 3%
            inss_trab = (salario_apos_faltas * Decimal('0.03')).quantize(Decimal('0.01'))
            # INSS entidade 8%
            inss_ent = (salario_apos_faltas * Decimal('0.08')).quantize(Decimal('0.01'))

            # Filtrar subsídios aplicáveis ao colaborador
            subsidios_aplicaveis = []
            for subsidio in subsidios_banca:
                if subsidio.apenas_especificos:
                    # Verificar em Python (dict O(1)) em vez de N×M queries
                    if col.id in subsidio_colab_ids.get(subsidio.pk, set()):
                        subsidios_aplicaveis.append(subsidio)
                else:
                    # Subsídio geral para todos os colaboradores
                    subsidios_aplicaveis.append(subsidio)

            # Calcular total dos subsídios aplicáveis
            total_subsidios = Decimal('0')
            
            for subsidio in subsidios_aplicaveis:
                if subsidio.tipo_calculo == 'PERCENTUAL':
                    # Para percentual, calcular baseado no salário do colaborador
                    if subsidio.percentual and salario:
                        valor_calculado = (salario * subsidio.percentual) / 100
                        total_subsidios += valor_calculado
                    else:
                        total_subsidios += subsidio.valor_padrao
                elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                    # Por dias de trabalho (assumir 22 dias úteis)
                    dias_trabalho = 22  # Padrão, pode ser ajustado
                    valor_calculado = subsidio.valor_padrao * dias_trabalho
                    total_subsidios += valor_calculado
                elif subsidio.tipo_calculo == 'DEPENDENTES':
                    # Por dependentes (assumir 1 dependente padrão)
                    dependentes = 1  # Padrão, pode ser personalizado por colaborador
                    valor_calculado = subsidio.valor_padrao * dependentes
                    total_subsidios += valor_calculado
                else:
                    # FIXO - usar valor padrão
                    total_subsidios += subsidio.valor_padrao

            recibo, recibo_criado = ReciboSalarial.objects.get_or_create(
                processamento=proc, colaborador=col,
                defaults={
                    'salario_base': salario,
                    'subsidio_alimentacao': Decimal('0'),
                    'subsidio_transporte': Decimal('0'),
                    'outros_subsidios': total_subsidios,
                    'outros_descontos': desconto_faltas,
                    'irt': irt,
                    'inss_trabalhador': inss_trab,
                    'inss_entidade': inss_ent,
                }
            )

            # Inicializar SubsidioRecibo com os valores calculados para cada subsídio aplicável
            if recibo_criado:
                for subsidio in subsidios_aplicaveis:
                    # Calcular valor baseado no tipo de cálculo
                    if subsidio.tipo_calculo == 'PERCENTUAL':
                        if subsidio.percentual and salario:
                            valor_calculado = (salario * subsidio.percentual) / 100
                        else:
                            valor_calculado = subsidio.valor_padrao
                    elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                        dias_trabalho = 22  # Padrão
                        valor_calculado = subsidio.valor_padrao * dias_trabalho
                    elif subsidio.tipo_calculo == 'DEPENDENTES':
                        dependentes = 1  # Padrão
                        valor_calculado = subsidio.valor_padrao * dependentes
                    else:
                        # FIXO
                        valor_calculado = subsidio.valor_padrao
                    
                    SubsidioRecibo.objects.get_or_create(
                        recibo=recibo,
                        subsidio=subsidio,
                        defaults={
                            'valor': valor_calculado,
                            'valor_padrao': subsidio.valor_padrao,
                        }
                    )
        if proc.total_liquido == 0:
            proc.delete()
            return render(request, 'rh/salarios/novo.html',
                          _ctx(request, 'salarios', {
                              'banca': banca, 'colaboradores': colaboradores,
                              'meses': MESES,
                              'ano_atual': timezone.now().year,
                              'erro': 'Não é possível gerar o processamento porque o total líquido é 0,00 KZ. Verifique os salários base e subsídios dos colaboradores ativos.',
                          }))
        return redirect('rh_salario_detalhe', pk=proc.pk)
    return render(request, 'rh/salarios/novo.html',
                  _ctx(request, 'salarios', {
                      'banca': banca, 'colaboradores': colaboradores,
                      'meses': MESES, 'ano_atual': timezone.now().year,
                  }))


@_requer_sessao
def salario_apagar_view(request, pk):
    """Apaga um processamento — apenas Rascunho ou Processado, nunca Pago."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_salarios')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    proc = get_object_or_404(ProcessamentoSalarial, pk=pk, banca=banca)

    if proc.estado == 'Pago':
        messages.error(request, 'Processamentos com estado Pago são permanentes e não podem ser apagados.')
        return redirect('rh_salarios')

    if request.method == 'POST':
        label = f'{proc.mes:02d}/{proc.ano}'
        proc.delete()
        messages.success(request, f'Processamento {label} apagado com sucesso.')
        return redirect('rh_salarios')

    return render(request, 'rh/salarios/apagar.html',
                  _ctx(request, 'salarios', {'banca': banca, 'proc': proc}))


@_requer_sessao
def salario_download_view(request, pk):
    """Faz download do PDF gerado automaticamente do processamento salarial"""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_salarios')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    proc = get_object_or_404(ProcessamentoSalarial, pk=pk, banca=banca)

    # Verificar se o processamento está pago
    if proc.estado != 'Pago':
        return render(request, 'rh/salarios/erro_download.html',
                      _ctx(request, 'salarios', {
                          'banca': banca, 'proc': proc,
                          'erro': 'O PDF só está disponível para processamentos marcados como "Pago".'
                      }))

    from django.conf import settings
    import os

    # Caminho do arquivo PDF
    pdf_dir = os.path.join(settings.MEDIA_ROOT, 'processamentos_salariais')
    pdf_filename = f"processamento_{proc.mes:02d}_{proc.ano}_{proc.pk}.pdf"
    pdf_filepath = os.path.join(pdf_dir, pdf_filename)

    # Sempre gerar o PDF (ou regenerar se não existir)
    try:
        _gerar_pdf_processamento(proc, request)

        # Verificar se o PDF foi criado com sucesso
        if os.path.exists(pdf_filepath):
            with open(pdf_filepath, 'rb') as f:
                pdf_content = f.read()

            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="comprovante_pagamento_{proc.mes:02d}_{proc.ano}.pdf"'
            response['Content-Length'] = len(pdf_content)

            return response
        else:
            raise FileNotFoundError("PDF não foi gerado")

    except Exception as e:
        return render(request, 'rh/salarios/erro_download.html',
                      _ctx(request, 'salarios', {
                          'banca': banca, 'proc': proc,
                          'erro': f'Erro ao gerar o PDF: {str(e)}. Verifique se todos os dados estão corretos.'
                      }))


@_requer_sessao
def salario_detalhe_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_salarios')
    if bloqueio:
        return bloqueio
    banca = acc[0]
    proc = get_object_or_404(ProcessamentoSalarial, pk=pk, banca=banca)
    recibos = proc.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()
    if request.method == 'POST':
        # ── Processamento PAGO é imutável ─────────────────────────────────
        if proc.estado == 'Pago':
            messages.error(request, 'Este processamento está marcado como Pago e não pode ser alterado.')
            return redirect('rh_salario_detalhe', pk=proc.pk)

        action = request.POST.get('action', '')
        if action == 'salvar':
            subsidios_ativos = list(banca.subsidios.filter(ativo=True))

            for r in recibos:
                p = f'rec_{r.pk}_'
                total_subsidios_dinamicos = Decimal('0')

                # Filtrar subsídios aplicáveis ao colaborador do recibo
                subsidios_aplicaveis = []
                for subsidio in subsidios_ativos:
                    if subsidio.apenas_especificos:
                        # Se o subsídio é apenas para específicos, verificar se o colaborador está na lista
                        if subsidio.colaboradores_especificos.filter(id=r.colaborador.id).exists():
                            subsidios_aplicaveis.append(subsidio)
                    else:
                        # Subsídio geral para todos os colaboradores
                        subsidios_aplicaveis.append(subsidio)

                # Guardar cada subsídio dinâmico aplicável e acumular o total
                for subsidio in subsidios_aplicaveis:
                    valor_subsidio = _dec(request.POST.get(f'{p}subsidio_{subsidio.pk}', '0'))

                    # Criar ou atualizar vínculo do subsídio com o recibo
                    vinculo, criado = SubsidioRecibo.objects.get_or_create(
                        recibo=r,
                        subsidio=subsidio,
                        defaults={
                            'valor': valor_subsidio,
                            'valor_padrao': subsidio.valor_padrao
                        }
                    )
                    if not criado:
                        vinculo.valor = valor_subsidio
                        vinculo.save()

                    total_subsidios_dinamicos += valor_subsidio

                # Remover vínculos de subsídios que não são mais aplicáveis
                subsidios_aplicaveis_ids = [s.pk for s in subsidios_aplicaveis]
                SubsidioRecibo.objects.filter(recibo=r).exclude(subsidio_id__in=subsidios_aplicaveis_ids).delete()

                # Sincronizar o total dos subsídios dinâmicos no campo outros_subsidios
                # para que bruto e liquido reflitam os valores alterados pelo utilizador
                r.outros_subsidios = total_subsidios_dinamicos
                # Limpar campos legados (os subsídios dinâmicos substituem-nos)
                r.subsidio_alimentacao = Decimal('0')
                r.subsidio_transporte  = Decimal('0')

                # Ler faltas (contagem) do formulário e converter para valor monetário
                faltas_count = int(request.POST.get(f'{p}faltas', '0') or '0')
                r.outros_descontos = (r.salario_base / Decimal('22') * faltas_count).quantize(Decimal('0.01')) if faltas_count > 0 else Decimal('0')

                # Recalcular IRT e INSS com base no salário base subtraído das faltas
                base_impostos = r.base_calculo_impostos
                r.irt = _calcular_irt(base_impostos)
                r.inss_trabalhador = (base_impostos * Decimal('0.03')).quantize(Decimal('0.01'))
                r.inss_entidade    = (base_impostos * Decimal('0.08')).quantize(Decimal('0.01'))
                r.save()
        elif action == 'processar':
            if proc.total_liquido == 0:
                messages.error(request, 'Não é possível processar porque o total líquido é 0,00 KZ. Atribua salários ou subsídios antes de processar.')
                return redirect('rh_salario_detalhe', pk=proc.pk)
            proc.estado = 'Processado'
            proc.processado_em = timezone.now()
            proc.save()
            messages.success(request, f'Processamento {proc.mes:02d}/{proc.ano} marcado como Processado.')
        elif action == 'pagar':
            if proc.total_liquido == 0:
                messages.error(request, 'Não é possível pagar porque o total líquido é 0,00 KZ.')
                return redirect('rh_salario_detalhe', pk=proc.pk)
            # Gerar faturas para o despachante e colaboradores
            _gerar_faturas_processamento(proc, request)
            # Gerar PDF automaticamente quando marcado como pago
            _gerar_pdf_processamento(proc, request)
            proc.estado = 'Pago'
            proc.save()
            messages.success(request, f'Processamento {proc.mes:02d}/{proc.ano} marcado como Pago.')
        elif action == 'reabrir':
            # Voltar a Rascunho — só permitido em estado Processado
            if proc.estado == 'Processado':
                proc.estado = 'Rascunho'
                proc.processado_em = None
                proc.save()
                messages.success(request, f'Processamento {proc.mes:02d}/{proc.ano} reaberto para edição.')
            else:
                messages.error(request, 'Apenas processamentos no estado Processado podem ser reabertos.')
        elif action == 'atualizar_colaboradores':
            if proc.estado != 'Rascunho':
                messages.error(request, 'Apenas processamentos em Rascunho podem ter a lista de colaboradores alterada.')
                return redirect('rh_salario_detalhe', pk=proc.pk)
            cols_selecionados = set(map(int, request.POST.getlist('colaboradores')))
            cols_atuais = set(recibos.values_list('colaborador_id', flat=True))
            # Colaboradores a adicionar
            ids_adicionar = cols_selecionados - cols_atuais
            # Colaboradores a remover
            ids_remover = cols_atuais - cols_selecionados
            if ids_adicionar:
                from datetime import date
                mes, ano = proc.mes, proc.ano
                cols_novos = banca.colaboradores.filter(id__in=ids_adicionar, estado='Ativo')
                subsidios_banca = list(banca.subsidios.filter(ativo=True))
                subsidio_colab_ids = {}
                for s in subsidios_banca:
                    if s.apenas_especificos:
                        subsidio_colab_ids[s.pk] = set(s.colaboradores_especificos.values_list('id', flat=True))
                for col in cols_novos:
                    salario = col.salario_efetivo
                    if not col.email:
                        faltas = 0
                    else:
                        faltas = RegistoPresenca.objects.filter(
                            colaborador=col, data__month=mes, data__year=ano,
                            tipo__in=['Falta', 'Falta_Justificada'], estado='Aprovado'
                        ).count()
                    dias_uteis = Decimal(str(max(1, sum(
                        1 for d in range(1, calendar.monthrange(ano, mes)[1] + 1)
                        if date(ano, mes, d).weekday() < 5
                    ))))
                    desconto_faltas = (salario / dias_uteis * faltas).quantize(Decimal('0.01')) if faltas else Decimal('0')
                    irt = _calcular_irt(max(salario - desconto_faltas, Decimal('0')))
                    inss_trab = (max(salario - desconto_faltas, Decimal('0')) * Decimal('0.03')).quantize(Decimal('0.01'))
                    inss_ent = (max(salario - desconto_faltas, Decimal('0')) * Decimal('0.08')).quantize(Decimal('0.01'))
                    subsidios_aplicaveis = []
                    for s in subsidios_banca:
                        if s.apenas_especificos and col.id not in subsidio_colab_ids.get(s.pk, set()):
                            continue
                        subsidios_aplicaveis.append(s)
                    total_subsidios = Decimal('0')
                    for s in subsidios_aplicaveis:
                        if s.tipo_calculo == 'PERCENTUAL' and s.percentual and salario:
                            total_subsidios += (salario * s.percentual) / 100
                        elif s.tipo_calculo == 'DIAS_TRABALHO':
                            total_subsidios += s.valor_padrao * 22
                        elif s.tipo_calculo == 'DEPENDENTES':
                            total_subsidios += s.valor_padrao * 1
                        else:
                            total_subsidios += s.valor_padrao
                    recibo = ReciboSalarial.objects.create(
                        processamento=proc, colaborador=col,
                        salario_base=salario, outros_subsidios=total_subsidios,
                        outros_descontos=desconto_faltas, irt=irt,
                        inss_trabalhador=inss_trab, inss_entidade=inss_ent,
                    )
                    for s in subsidios_aplicaveis:
                        if s.tipo_calculo == 'PERCENTUAL' and s.percentual and salario:
                            v = (salario * s.percentual) / 100
                        elif s.tipo_calculo == 'DIAS_TRABALHO':
                            v = s.valor_padrao * 22
                        elif s.tipo_calculo == 'DEPENDENTES':
                            v = s.valor_padrao * 1
                        else:
                            v = s.valor_padrao
                        SubsidioRecibo.objects.create(recibo=recibo, subsidio=s, valor=v, valor_padrao=s.valor_padrao)
            if ids_remover:
                ReciboSalarial.objects.filter(processamento=proc, colaborador_id__in=ids_remover).delete()
            n_adicionados = len(ids_adicionar)
            n_removidos = len(ids_remover)
            partes = []
            if n_adicionados:
                partes.append(f'{n_adicionados} colaborador{"es" if n_adicionados != 1 else ""} adicionado{"s" if n_adicionados != 1 else ""}')
            if n_removidos:
                partes.append(f'{n_removidos} colaborador{"es" if n_removidos != 1 else ""} removido{"s" if n_removidos != 1 else ""}')
            if partes:
                messages.success(request, f'Lista de colaboradores actualizada: {", ".join(partes)}.')
            else:
                messages.info(request, 'Nenhuma alteração na lista de colaboradores.')
        return redirect('rh_salario_detalhe', pk=proc.pk)
    # Obter subsídios ativos para o template
    subsidios_ativos = banca.subsidios.filter(ativo=True)

    # Garantir que subsídios obrigatórios tenham SubsidioRecibo (mesmo que criados após o processamento)
    tem_faltantes = False
    for r in recibos:
        for subsidio in subsidios_ativos:
            if not subsidio.obrigatorio:
                continue
            if SubsidioRecibo.objects.filter(recibo=r, subsidio=subsidio).exists():
                continue
            tem_faltantes = True
            if subsidio.tipo_calculo == 'PERCENTUAL':
                if subsidio.percentual and r.salario_base:
                    valor = (r.salario_base * subsidio.percentual) / 100
                else:
                    valor = subsidio.valor_padrao
            elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                valor = subsidio.valor_padrao * 22
            elif subsidio.tipo_calculo == 'DEPENDENTES':
                valor = subsidio.valor_padrao * 1
            else:
                valor = subsidio.valor_padrao
            SubsidioRecibo.objects.get_or_create(
                recibo=r, subsidio=subsidio,
                defaults={'valor': valor, 'valor_padrao': subsidio.valor_padrao}
            )
    if tem_faltantes:
        # Re-fetch para o prefetch_related incluir os novos vínculos
        recibos = proc.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()

    todas_cols = banca.colaboradores.filter(estado='Ativo')
    ids_processados = list(recibos.values_list('colaborador_id', flat=True))
    return render(request, 'rh/salarios/detalhe.html',
                  _ctx(request, 'salarios', {
                      'banca': banca, 'proc': proc, 'recibos': recibos, 'meses': MESES,
                      'subsidios_ativos': subsidios_ativos,
                      'todas_cols': todas_cols,
                      'ids_processados': ids_processados,
                  }))


# ══════════════════════════════════════════════════════════════════════════════
# RECRUTAMENTO
# ══════════════════════════════════════════════════════════════════════════════
@_requer_sessao
def vagas_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc

    vagas_base = escopo_vagas(banca, col_log, gestor, is_desp)
    filiais = (
        list(banca.filiais.all()) if is_desp
        else [f for f in [banca.filiais.filter(pk=gestor.filial_id).first()] if f] if gestor else []
    )

    # Filtros
    estado_filter = request.GET.get('estado', '')
    filial_filter = request.GET.get('filial', '')
    search_query = request.GET.get('search', '')

    vagas_queryset = vagas_base
    if estado_filter:
        vagas_queryset = vagas_queryset.filter(estado=estado_filter)

    if filial_filter:
        vagas_queryset = vagas_queryset.filter(filial_id=filial_filter)

    if search_query:
        vagas_queryset = vagas_queryset.filter(
            models.Q(titulo__icontains=search_query) |
            models.Q(departamento__icontains=search_query) |
            models.Q(descricao__icontains=search_query)
        )

    vagas = vagas_queryset.select_related('filial').annotate(
        num_candidatos=Count('candidaturas')
    ).order_by('-criado_em')
    paginator = Paginator(vagas, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Estatísticas — reusa vagas_base em vez de chamar escopo_vagas novamente
    from django.db.models import Q as _Q
    stats = vagas_base.aggregate(
        total_vagas=Count('id'),
        vagas_abertas=Count('id', filter=_Q(estado='Aberta')),
        vagas_em_analise=Count('id', filter=_Q(estado='Em Análise')),
        vagas_encerradas=Count('id', filter=_Q(estado='Encerrada')),
        total_candidaturas=Count('candidaturas'),
        candidaturas_hoje=Count(
            'candidaturas',
            filter=_Q(candidaturas__criado_em__date=timezone.now().date())
        ),
    )

    from django.conf import settings as _settings
    return render(request, 'rh/recrutamento/vagas.html',
                  _ctx(request, 'recrutamento', {
                      'banca': banca,
                      'vagas': page_obj,
                      'filiais': filiais,
                      'stats': stats,
                      'estado_filter': estado_filter,
                      'filial_filter': filial_filter,
                      'search_query': search_query,
                      'page_obj': page_obj,
                      'site_url': _settings.SITE_URL.rstrip('/'),
                  }))


@_requer_sessao
def vaga_nova_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    filiais = (
        list(banca.filiais.all()) if is_desp
        else [f for f in [banca.filiais.filter(pk=gestor.filial_id).first()] if f] if gestor else []
    )
    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        if not titulo:
            return render(request, 'rh/recrutamento/vaga_form.html',
                          _ctx(request, 'recrutamento', {
                              'banca': banca, 'vaga': None, 'filiais': filiais,
                              'erro': 'O título é obrigatório.',
                          }))
        try:
            Vaga.objects.create(
                banca=banca,
                filial_id=filial_id_obrigatoria_gestor(
                    gestor, is_desp, request.POST.get('filial') or None, banca=banca,
                ),
                titulo=titulo,
                departamento=request.POST.get('departamento', '').strip(),
                descricao=request.POST.get('descricao', '').strip(),
                requisitos=request.POST.get('requisitos', '').strip(),
                salario_min=_dec(request.POST.get('salario_min')) or None,
                salario_max=_dec(request.POST.get('salario_max')) or None,
                vagas_numero=int(request.POST.get('vagas_numero') or 1),
                data_encerramento=request.POST.get('data_encerramento') or None,
            )
            return redirect('rh_vagas')
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                for field, messages_list in e.message_dict.items():
                    for msg in messages_list:
                        messages.error(request, msg)
            else:
                messages.error(request, str(e))
    return render(request, 'rh/recrutamento/vaga_form.html',
                  _ctx(request, 'recrutamento', {
                      'banca': banca, 'vaga': None, 'filiais': filiais,
                  }))


@_requer_sessao
def vaga_editar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    vaga = get_object_or_404(Vaga, pk=pk, banca=banca)
    if not pode_aceder_vaga(gestor, is_desp, vaga):
        messages.error(request, 'Sem permissão para editar esta vaga.')
        return redirect('rh_vagas')
    filiais = (
        list(banca.filiais.all()) if is_desp
        else [f for f in [banca.filiais.filter(pk=gestor.filial_id).first()] if f] if gestor else []
    )
    if request.method == 'POST':
        try:
            vaga.filial_id = filial_id_obrigatoria_gestor(
                gestor, is_desp, request.POST.get('filial') or None, banca=banca,
            )
            vaga.titulo = request.POST.get('titulo', '').strip()
            vaga.departamento = request.POST.get('departamento', '').strip()
            vaga.descricao = request.POST.get('descricao', '').strip()
            vaga.requisitos = request.POST.get('requisitos', '').strip()
            vaga.salario_min = _dec(request.POST.get('salario_min')) or None
            vaga.salario_max = _dec(request.POST.get('salario_max')) or None
            vaga.vagas_numero = int(request.POST.get('vagas_numero') or 1)
            vaga.estado = request.POST.get('estado', 'Aberta')
            vaga.data_encerramento = request.POST.get('data_encerramento') or None
            vaga.save()
            return redirect('rh_vagas')
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                for field, messages_list in e.message_dict.items():
                    for msg in messages_list:
                        messages.error(request, msg)
            else:
                messages.error(request, str(e))
    return render(request, 'rh/recrutamento/vaga_form.html',
                  _ctx(request, 'recrutamento', {
                      'banca': banca, 'vaga': vaga, 'filiais': filiais,
                  }))


@_requer_sessao
def vaga_eliminar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    vaga = get_object_or_404(Vaga, pk=pk, banca=banca)
    if not pode_aceder_vaga(gestor, is_desp, vaga):
        messages.error(request, 'Sem permissão para eliminar esta vaga.')
        return redirect('rh_vagas')
    if request.method == 'POST':
        vaga.delete()
        messages.success(request, f'Vaga "{vaga.titulo}" eliminada com sucesso.')
        return redirect('rh_vagas')
    return redirect('rh_vagas')


@_requer_sessao
def candidaturas_view(request, vaga_pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    vaga = get_object_or_404(Vaga, pk=vaga_pk, banca=banca)
    if not pode_aceder_vaga(gestor, is_desp, vaga):
        messages.error(request, 'Sem permissão para ver candidaturas desta vaga.')
        return redirect('rh_vagas')
    candidaturas_qs = vaga.candidaturas.prefetch_related(
        'entrevistas',
        Prefetch('plano_integracao', queryset=PlanoIntegracao.objects.only('id', 'estado'))
    ).order_by('-criado_em')

    # Mapeamento estado → etapa do pipeline
    MAPA_ETAPA = {
        'Recebida':   'candidaturas',
        'Em Análise': 'candidaturas',
        'Entrevista': 'entrevistas',
        'Aprovado':   'integracao',
        'Rejeitado':  'candidaturas',
    }
    # Enriquecer cada candidatura com etapa_key
    candidaturas = []
    for c in candidaturas_qs:
        c.etapa_key = MAPA_ETAPA.get(c.estado, 'candidaturas')
        candidaturas.append(c)

    paginator = Paginator(candidaturas, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    etapas = [
        ('candidaturas', 'Candidaturas',  'gray',   'inbox'),
        ('entrevistas',  'Entrevistas',   'blue',   'event'),
        ('integracao',   'Integração',    'green',  'person_check'),
    ]

    return render(request, 'rh/recrutamento/candidaturas.html',
                  _ctx(request, 'recrutamento', {
                      'banca': banca, 'vaga': vaga,
                      'candidaturas': page_obj, 'etapas': etapas,
                      'page_obj': page_obj,
                  }))


@_requer_sessao
def candidatura_estado_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca = acc[0]
    cand = get_object_or_404(Candidatura, pk=pk, vaga__banca=banca)
    bloqueio = _redirect_se_vaga_inacessivel(request, acc, cand.vaga)
    if bloqueio:
        return bloqueio
    if request.method == 'POST':
        estado_anterior = cand.estado
        cand.estado = request.POST.get('estado', cand.estado)
        cand.notas = request.POST.get('notas', '').strip()
        cand.save()

        # Enviar email ao candidato quando aprovado ou rejeitado
        if cand.estado in ('Aprovado', 'Rejeitado') and cand.estado != estado_anterior:
            from utils.email_utils import enviar_resultado_candidatura
            sucesso, msg = enviar_resultado_candidatura(cand)
            if sucesso:
                messages.success(request, f'Estado actualizado e email enviado para {cand.email}.')
            else:
                messages.warning(request, f'Estado actualizado, mas falhou o envio de email: {msg}')
        else:
            messages.success(request, 'Estado da candidatura actualizado.')

    return redirect('rh_candidaturas', vaga_pk=cand.vaga.pk)


# ─── Entrevistas ──────────────────────────────────────────────────────────────

@_requer_sessao
def entrevista_nova_view(request, candidatura_pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca = acc[0]
    cand = get_object_or_404(Candidatura, pk=candidatura_pk, vaga__banca=banca)
    bloqueio = _redirect_se_vaga_inacessivel(request, acc, cand.vaga)
    if bloqueio:
        return bloqueio

    if request.method == 'POST':
        Entrevista.objects.create(
            candidatura=cand,
            data_hora=request.POST.get('data_hora'),
            tipo=request.POST.get('tipo', 'Presencial'),
            local_link=request.POST.get('local_link', '').strip(),
            entrevistador=request.POST.get('entrevistador', '').strip(),
            observacoes=request.POST.get('observacoes', '').strip(),
        )
        # Avançar estado da candidatura para "Entrevista"
        if cand.estado not in ('Aprovado', 'Rejeitado'):
            cand.estado = 'Entrevista'
            cand.save()

        # Enviar convocatória por email ao candidato
        entrevista_criada = cand.entrevistas.order_by('-criado_em').first()
        if entrevista_criada and cand.email:
            from utils.email_utils import enviar_convocatoria_entrevista
            sucesso, msg = enviar_convocatoria_entrevista(entrevista_criada)
            if sucesso:
                messages.success(request, f'Entrevista agendada e convocatória enviada para {cand.email}.')
            else:
                messages.warning(request, f'Entrevista agendada, mas falhou o envio de email: {msg}')
        else:
            messages.success(request, 'Entrevista agendada com sucesso.')

        return redirect('rh_candidatura_detalhe', pk=cand.pk)

    return render(request, 'rh/recrutamento/entrevista_form.html',
                  _ctx(request, 'recrutamento', {'banca': banca, 'cand': cand}))


@_requer_sessao
def entrevista_resultado_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca = acc[0]
    entrevista = get_object_or_404(Entrevista, pk=pk, candidatura__vaga__banca=banca)
    bloqueio = _redirect_se_vaga_inacessivel(request, acc, entrevista.candidatura.vaga)
    if bloqueio:
        return bloqueio
    if request.method == 'POST':
        entrevista.resultado = request.POST.get('resultado', 'Pendente')
        entrevista.nota = request.POST.get('nota') or None
        entrevista.observacoes = request.POST.get('observacoes', '').strip()
        entrevista.save()
        # Sincronizar estado da candidatura
        cand = entrevista.candidatura
        if entrevista.resultado == 'Aprovado':
            cand.estado = 'Aprovado'
            cand.save()
        elif entrevista.resultado == 'Reprovado':
            cand.estado = 'Rejeitado'
            cand.save()
        return redirect('rh_candidatura_detalhe', pk=cand.pk)
    return redirect('rh_candidatura_detalhe', pk=entrevista.candidatura.pk)


@_requer_sessao
def candidatura_detalhe_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca = acc[0]
    cand = get_object_or_404(Candidatura, pk=pk, vaga__banca=banca)
    bloqueio = _redirect_se_vaga_inacessivel(request, acc, cand.vaga)
    if bloqueio:
        return bloqueio
    entrevistas = cand.entrevistas.all()
    plano = getattr(cand, 'plano_integracao', None)

    # Fluxo de etapas para o indicador de progresso
    fluxo_etapas = [
        (1, 'Candidatura',  ['Recebida', 'Em Análise']),
        (2, 'Entrevista',   ['Entrevista']),
        (3, 'Aprovação',    ['Aprovado', 'Rejeitado']),
        (4, 'Integração',   []),
    ]
    etapa_map = {'Recebida': 1, 'Em Análise': 1, 'Entrevista': 2,
                 'Aprovado': 3, 'Rejeitado': 3}
    fluxo_etapa_atual = etapa_map.get(cand.estado, 1)
    if plano:
        fluxo_etapa_atual = 4

    return render(request, 'rh/recrutamento/candidatura_detalhe.html',
                  _ctx(request, 'recrutamento', {
                      'banca': banca, 'cand': cand,
                      'entrevistas': entrevistas, 'plano': plano,
                      'fluxo_etapas': fluxo_etapas,
                      'fluxo_etapa_atual': fluxo_etapa_atual,
                  }))


# ─── Integração ───────────────────────────────────────────────────────────────

@_requer_sessao
def integracao_nova_view(request, candidatura_pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    cand = get_object_or_404(Candidatura, pk=candidatura_pk, vaga__banca=banca,
                             estado='Aprovado')
    bloqueio = _redirect_se_vaga_inacessivel(request, acc, cand.vaga)
    if bloqueio:
        return bloqueio
    # Não criar duplicado
    if hasattr(cand, 'plano_integracao'):
        return redirect('rh_integracao_detalhe', pk=cand.plano_integracao.pk)

    filiais = (
        list(banca.filiais.all()) if is_desp
        else [f for f in [banca.filiais.filter(pk=gestor.filial_id).first()] if f] if gestor else []
    )
    colaborador_atual = col_log
    responsavel_nome = colaborador_atual.nome if colaborador_atual else "Despachante"

    # Preparar dados para preenchimento automático
    cargo_sugerido = cand.vaga.titulo if cand.vaga.titulo else 'Assistente'
    departamento_sugerido = cand.vaga.departamento if cand.vaga.departamento else ''

    if request.method == 'POST':
        plano = PlanoIntegracao.objects.create(
            candidatura=cand,
            data_inicio=request.POST.get('data_inicio'),
            data_fim_prevista=request.POST.get('data_fim_prevista') or None,
            responsavel=request.POST.get('responsavel', responsavel_nome).strip(),
            notas=request.POST.get('notas', '').strip(),
        )
        # Criar colaborador automaticamente se solicitado
        if request.POST.get('criar_colaborador') == '1':
            email_col = cand.email.strip() if cand.email else ''
            if email_col and email_ja_existe(email_col):
                messages.error(request, f'O email {email_col} já está registado no sistema.')
                return redirect('rh_integracao_detalhe', pk=plano.pk)
            senha_gerada = None
            senha_hash = None
            if email_col:
                senha_gerada = gerar_senha_aleatoria()
                senha_hash = _hash_password(senha_gerada)
            filial_id = filial_id_obrigatoria_gestor(
                gestor, is_desp, request.POST.get('filial') or None, col_log=col_log, banca=banca,
            )
            col = Colaborador.objects.create(
                banca=banca,
                filial_id=filial_id,
                nome=cand.nome,
                email=email_col,
                telefone=cand.telefone,
                cargo=request.POST.get('cargo', cargo_sugerido),
                cargo_personalizado=request.POST.get('cargo_personalizado', '').strip(),
                departamento=request.POST.get('departamento', departamento_sugerido),
                data_admissao=request.POST.get('data_inicio'),
                salario_base=_dec(request.POST.get('salario_base')) or None,
                estado='Ativo',
                password=senha_hash,
            )
            plano.colaborador = col
            plano.save()
            if email_col and senha_gerada:
                ok_email, msg_email = enviar_senha_colaborador(col, senha_gerada)
                if ok_email:
                    messages.success(
                        request,
                        f'Colaborador criado. Credenciais enviadas para {email_col}.',
                    )
                else:
                    messages.warning(
                        request,
                        f'Colaborador criado, mas falhou o envio de credenciais: {msg_email}. '
                        'Use "Reenviar" na lista de colaboradores.',
                    )
            elif not email_col:
                messages.info(
                    request,
                    'Colaborador criado sem email — não foi possível enviar credenciais.',
                )
        # Tarefas padrão de integração
        tarefas_padrao = [
            'Apresentação à equipa e instalações',
            'Entrega de equipamentos e acessos',
            'Formação inicial sobre processos internos',
            'Revisão de políticas e regulamentos',
            'Acompanhamento pelo responsável durante o período de integração',
        ]
        for t in tarefas_padrao:
            TarefaIntegracao.objects.create(plano=plano, titulo=t,
                                            prazo=request.POST.get('data_fim_prevista') or None)
        return redirect('rh_integracao_detalhe', pk=plano.pk)

    return render(request, 'rh/recrutamento/integracao_form.html',
                  _ctx(request, 'recrutamento', {
                      'banca': banca, 'cand': cand,
                      'filiais': filiais, 'cargos': CARGOS,
                      'cargo_sugerido': cargo_sugerido,
                      'departamento_sugerido': departamento_sugerido,
                      'responsavel_nome': responsavel_nome,
                  }))


@_requer_sessao
def integracao_detalhe_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca = acc[0]
    plano = get_object_or_404(PlanoIntegracao, pk=pk, candidatura__vaga__banca=banca)
    bloqueio = _redirect_se_vaga_inacessivel(request, acc, plano.candidatura.vaga)
    if bloqueio:
        return bloqueio
    tarefas = plano.tarefas.all()

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'tarefa_toggle':
            tarefa_pk = request.POST.get('tarefa_pk')
            tarefa = get_object_or_404(TarefaIntegracao, pk=tarefa_pk, plano=plano)
            tarefa.concluida = not tarefa.concluida
            tarefa.save()
        elif action == 'tarefa_nova':
            titulo = request.POST.get('titulo', '').strip()
            if titulo:
                TarefaIntegracao.objects.create(
                    plano=plano, titulo=titulo,
                    responsavel=request.POST.get('responsavel', '').strip(),
                    prazo=request.POST.get('prazo') or None,
                )
        elif action == 'concluir':
            plano.estado = 'Concluído'
            plano.save()
        elif action == 'iniciar':
            plano.estado = 'Em Curso'
            plano.save()
        return redirect('rh_integracao_detalhe', pk=plano.pk)

    return render(request, 'rh/recrutamento/integracao_detalhe.html',
                  _ctx(request, 'recrutamento', {
                      'banca': banca, 'plano': plano, 'tarefas': tarefas,
                  }))


# ══════════════════════════════════════════════════════════════════════════════
# CONTROLO DE PRESENÇAS
# ══════════════════════════════════════════════════════════════════════════════
@_requer_sessao
def presencas_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    hoje = timezone.now().date()
    data_inicio = request.GET.get('data_inicio', '').strip()
    data_fim    = request.GET.get('data_fim', '').strip()
    colaborador_id = request.GET.get('colaborador')
    cols = escopo_colaboradores_ativos(banca, col_log, gestor, is_desp, request=request).only(
        'id', 'nome', 'cargo', 'cargo_personalizado', 'filial_id'
    )
    # Excluir Gestores de Filial — estão isentos de marcar presença
    gestor_ids = set(
        banca.colaboradores.filter(
            gestor_filial__isnull=False, gestor_filial__ativo=True
        ).values_list('id', flat=True)
    )
    cols = cols.exclude(id__in=gestor_ids).exclude(email='')

    registos = RegistoPresenca.objects.filter(
        colaborador__in=cols,
    )
    if data_inicio:
        registos = registos.filter(data__gte=data_inicio)
    if data_fim:
        registos = registos.filter(data__lte=data_fim)
    if not data_inicio and not data_fim:
        registos = registos.filter(data__year=hoje.year, data__month=hoje.month)
    if colaborador_id:
        registos = registos.filter(colaborador_id=colaborador_id)
    registos = registos.select_related('colaborador').order_by('-data')
    pedidos_pendentes = PedidoFerias.objects.filter(
        colaborador__in=cols, estado='Pendente',
    ).select_related('colaborador').only(
        'id', 'colaborador_id', 'data_inicio', 'data_fim', 'motivo', 'estado', 'criado_em'
    )
    hoje_dt = timezone.now()
    primeiro_dia_mes = hoje_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if hoje_dt.month == 12:
        ultimo_dia_mes = hoje_dt.replace(month=12, day=31, hour=23, minute=59, second=59)
    else:
        from datetime import timedelta
        ultimo_dia_mes = (hoje_dt.replace(month=hoje_dt.month + 1, day=1) - timedelta(days=1)).replace(hour=23, minute=59, second=59)
    pedidos_todos = PedidoFerias.objects.filter(
        colaborador__in=cols,
        data_inicio__lte=ultimo_dia_mes, data_fim__gte=primeiro_dia_mes,
    ).select_related('colaborador').order_by('-criado_em')
    # Anotar can_approve em cada registo
    for r in registos:
        r.can_approve = (
            r.estado == 'Pendente' and
            pode_aprovar_presenca(request, banca, col_log, is_desp, r.colaborador)
        )
    for p in pedidos_pendentes:
        p.can_approve = (
            p.estado == 'Pendente' and
            pode_aprovar_presenca(request, banca, col_log, is_desp, p.colaborador)
        )
    for p in pedidos_todos:
        if not hasattr(p, 'can_approve'):
            p.can_approve = (
                p.estado == 'Pendente' and
                pode_aprovar_presenca(request, banca, col_log, is_desp, p.colaborador)
            )
    paginator = Paginator(registos, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    extra_params = {}
    for k in ('colaborador', 'data_inicio', 'data_fim'):
        v = request.GET.get(k, '')
        if v:
            extra_params[k] = v
    from urllib.parse import urlencode
    extra_qs = urlencode(extra_params)

    return render(request, 'rh/presencas/lista.html',
                  _ctx(request, 'presencas', {
                      'banca': banca, 'colaboradores': cols,
                      'registos': page_obj, 'pedidos': pedidos_pendentes,
                      'page_obj': page_obj,
                      'pedidos_todos': pedidos_todos,
                      'hoje': hoje,
                      'colaborador_id': colaborador_id,
                      'data_inicio': data_inicio, 'data_fim': data_fim,
                      'extra_params': extra_qs,
                  }))


@_requer_sessao
def presenca_registar_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    if request.method == 'POST':
        col = get_object_or_404(
            Colaborador, pk=request.POST.get('colaborador'), banca=banca,
        )
        if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, col):
            messages.error(request, 'Sem permissão para registar presença deste colaborador.')
            return redirect('rh_presencas')
        if col.e_gestor_filial:
            messages.error(request, 'Gestor de filial está isento de registar presença.')
            return redirect('rh_presencas')
        if not col.email:
            messages.error(request, 'Colaborador sem acesso ao sistema não pode registar presença.')
            return redirect('rh_presencas')
        try:
            data_str = request.POST.get('data')
            foi_criacao = not RegistoPresenca.objects.filter(colaborador=col, data=data_str).exists()
            reg, created = RegistoPresenca.objects.get_or_create(
                colaborador=col,
                data=data_str,
            )
            pode_aprovar = pode_aprovar_presenca(request, banca, col_log, is_desp, col)
            if not foi_criacao and reg.estado in ('Aprovado', 'Rejeitado') and not pode_aprovar:
                messages.error(request, f'Registo já {reg.estado.lower()}, não pode ser alterado.')
                return redirect('rh_presencas')
            estado_anterior = reg.estado if not foi_criacao else ''
            reg.tipo = request.POST.get('tipo', 'Entrada')
            reg.hora_entrada = request.POST.get('hora_entrada') or None
            reg.hora_saida = request.POST.get('hora_saida') or None
            reg.horas_extras = _dec(request.POST.get('horas_extras', '0'))
            reg.justificacao = request.POST.get('justificacao', '').strip()
            reg.estado = 'Pendente'
            reg.full_clean()
            reg.save()
            _registrar_historico_presenca(
                banca=banca, filial=col.filial,
                tipo_registo='presenca', registo_id=reg.pk,
                accao='CRIADA' if foi_criacao else 'ALTERADA',
                estado_anterior=estado_anterior, estado_novo='Pendente',
                colaborador=col, aprovador=col_log,
            )
            messages.success(request, 'Registo de presença salvo com sucesso.')
            # Notificar responsável
            responsavel = _encontrar_responsavel_aprovacao(banca, col)
            if responsavel and (not col_log or responsavel.pk != col_log.pk):
                notificar_presenca_pendente(reg, banca, responsavel, request)
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                for field, msgs in e.message_dict.items():
                    for msg in msgs:
                        messages.error(request, msg)
            else:
                messages.error(request, str(e))
    return redirect('rh_presencas')


@_requer_sessao
def presenca_aprovar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    reg = get_object_or_404(RegistoPresenca, pk=pk, colaborador__banca=banca)
    if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, reg.colaborador):
        messages.error(request, 'Sem permissão para aceder a este registo.')
        return redirect('rh_presencas')
    if not pode_aprovar_presenca(request, banca, col_log, is_desp, reg.colaborador):
        messages.error(request, 'Não tem autoridade para aprovar esta presença.')
        return redirect('rh_presencas')
    if request.method == 'POST':
        estado_anterior = reg.estado
        novo_estado = request.POST.get('estado', 'Aprovado')
        if novo_estado not in ('Aprovado', 'Rejeitado'):
            novo_estado = 'Aprovado'
        observacao = request.POST.get('observacao', '') if novo_estado == 'Rejeitado' else ''
        reg.estado = novo_estado
        reg.aprovado_por = col_log
        reg.data_aprovacao = timezone.now()
        reg.save()
        _registrar_historico_presenca(
            banca=banca, filial=reg.colaborador.filial,
            tipo_registo='presenca', registo_id=reg.pk,
            accao='APROVADA' if novo_estado == 'Aprovado' else 'REJEITADA',
            estado_anterior=estado_anterior, estado_novo=novo_estado,
            colaborador=reg.colaborador, aprovador=col_log,
            observacao=observacao,
        )
        if novo_estado == 'Aprovado':
            notificar_aprovado(reg, banca, reg.colaborador, 'presenca')
        else:
            notificar_rejeitado(reg, banca, reg.colaborador, 'presenca', motivo=observacao)
        messages.success(request, f'Presença de {reg.colaborador.nome} {novo_estado.lower()}.')
    return redirect('rh_presencas')


@_requer_sessao
def ferias_pedir_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    if request.method == 'POST':
        col = get_object_or_404(Colaborador, pk=request.POST.get('colaborador'), banca=banca)
        if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, col):
            messages.error(request, 'Sem permissão para criar/editar pedido para este colaborador.')
            return redirect('rh_presencas')
        try:
            pedido_pk = request.POST.get('pedido_pk')
            if pedido_pk:
                pedido = get_object_or_404(PedidoFerias, pk=pedido_pk, colaborador__banca=banca)
                if pedido.estado != 'Pendente':
                    messages.error(request, 'Apenas pedidos pendentes podem ser editados.')
                    return redirect('rh_presencas')
                estado_anterior = pedido.estado
                pedido.data_inicio = request.POST.get('data_inicio')
                pedido.data_fim = request.POST.get('data_fim')
                pedido.motivo = request.POST.get('motivo', '').strip()
                pedido.full_clean()
                pedido.save()
                _registrar_historico_presenca(
                    banca=banca, filial=col.filial,
                    tipo_registo='ferias', registo_id=pedido.pk,
                    accao='ALTERADA',
                    estado_anterior=estado_anterior, estado_novo='Pendente',
                    colaborador=col, aprovador=col_log,
                )
                messages.success(request, 'Pedido de férias actualizado com sucesso.')
            else:
                pedido = PedidoFerias.objects.create(
                    colaborador=col,
                    data_inicio=request.POST.get('data_inicio'),
                    data_fim=request.POST.get('data_fim'),
                    motivo=request.POST.get('motivo', '').strip(),
                )
                _registrar_historico_presenca(
                    banca=banca, filial=col.filial,
                    tipo_registo='ferias', registo_id=pedido.pk,
                    accao='CRIADA',
                    estado_anterior='', estado_novo='Pendente',
                    colaborador=col, aprovador=col_log,
                )
                messages.success(request, 'Pedido de férias submetido com sucesso.')
                responsavel = _encontrar_responsavel_aprovacao(banca, col)
                if responsavel and (not col_log or responsavel.pk != col_log.pk):
                    notificar_ferias_pendente(pedido, banca, responsavel, request)
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                for field, messages_list in e.message_dict.items():
                    for msg in messages_list:
                        messages.error(request, msg)
            else:
                messages.error(request, str(e))
    next_url = request.POST.get('next') or 'rh_presencas'
    return redirect(next_url)


@_requer_sessao
def ferias_aprovar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    pedido = get_object_or_404(PedidoFerias, pk=pk, colaborador__banca=banca)
    if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, pedido.colaborador):
        messages.error(request, 'Sem permissão para gerir este pedido de férias.')
        return redirect('rh_presencas')
    if not pode_aprovar_presenca(request, banca, col_log, is_desp, pedido.colaborador):
        messages.error(request, 'Não tem autoridade para aprovar este pedido de férias.')
        return redirect('rh_presencas')
    if request.method == 'POST':
        try:
            estado_anterior = pedido.estado
            novo_estado = request.POST.get('estado', 'Aprovado')
            if novo_estado not in ('Aprovado', 'Rejeitado'):
                novo_estado = 'Aprovado'
            observacao = request.POST.get('observacao', '') if novo_estado == 'Rejeitado' else ''
            pedido.estado = novo_estado
            pedido.aprovado_por = col_log
            pedido.data_aprovacao = timezone.now()
            pedido.save()
            _registrar_historico_presenca(
                banca=banca, filial=pedido.colaborador.filial,
                tipo_registo='ferias', registo_id=pedido.pk,
                accao='APROVADA' if novo_estado == 'Aprovado' else 'REJEITADA',
                estado_anterior=estado_anterior, estado_novo=novo_estado,
                colaborador=pedido.colaborador, aprovador=col_log,
                observacao=observacao,
            )
            if novo_estado == 'Aprovado':
                marcar_ferias_no_registo(pedido)
                notificar_aprovado(pedido, banca, pedido.colaborador, 'ferias')
            else:
                notificar_rejeitado(pedido, banca, pedido.colaborador, 'ferias', motivo=observacao)
            messages.success(request, f'Pedido de férias de {pedido.colaborador.nome} {novo_estado.lower()}.')
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                for field, messages_list in e.message_dict.items():
                    for msg in messages_list:
                        messages.error(request, msg)
            else:
                messages.error(request, str(e))
    next_url = request.POST.get('next') or 'rh_presencas'
    return redirect(next_url)


@_requer_sessao
def presenca_apagar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    reg = get_object_or_404(RegistoPresenca, pk=pk, colaborador__banca=banca)
    if request.method == 'POST':
        if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, reg.colaborador):
            messages.error(request, 'Sem permissão para remover este registo.')
        elif not pode_aprovar_presenca(request, banca, col_log, is_desp, reg.colaborador):
            messages.error(request, 'Sem autoridade para remover este registo.')
        else:
            _registrar_historico_presenca(
                banca=banca, filial=reg.colaborador.filial,
                tipo_registo='presenca', registo_id=reg.pk,
                accao='REMOVIDA',
                estado_anterior=reg.estado, estado_novo='',
                colaborador=reg.colaborador, aprovador=col_log,
            )
            reg.delete()
            messages.success(request, 'Registo removido com sucesso.')
    return redirect('rh_presencas')


@_requer_sessao
def ferias_apagar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    pedido = get_object_or_404(PedidoFerias, pk=pk, colaborador__banca=banca)
    if request.method == 'POST':
        if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, pedido.colaborador):
            messages.error(request, 'Sem permissão para remover este pedido.')
        elif not pode_aprovar_presenca(request, banca, col_log, is_desp, pedido.colaborador):
            messages.error(request, 'Sem autoridade para remover este pedido.')
        else:
            _registrar_historico_presenca(
                banca=banca, filial=pedido.colaborador.filial,
                tipo_registo='ferias', registo_id=pedido.pk,
                accao='REMOVIDA',
                estado_anterior=pedido.estado, estado_novo='',
                colaborador=pedido.colaborador, aprovador=col_log,
            )
            pedido.delete()
            messages.success(request, 'Pedido de férias removido com sucesso.')
    return redirect('rh_ferias')


@_requer_sessao
def ferias_lista_view(request):
    from django.urls import reverse
    from django.utils import timezone
    hoje = timezone.now().date()
    url = reverse('rh_presencas')
    return redirect(f'{url}?tab=ferias&mes={hoje.month}&ano={hoje.year}')


# ══════════════════════════════════════════════════════════════════════════════
# AVALIAÇÃO DE DESEMPENHO
# ══════════════════════════════════════════════════════════════════════════════
@_requer_sessao
def avaliacoes_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca = acc[0]
    ciclos = banca.ciclos_avaliacao.annotate(
        num_avaliacoes=Count('avaliacoes')
    ).order_by('-id').all()
    paginator = Paginator(ciclos, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'rh/avaliacoes/lista.html',
                  _ctx(request, 'avaliacoes', {'banca': banca, 'ciclos': page_obj, 'page_obj': page_obj}))


@_requer_sessao
def ciclo_novo_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_avaliacoes')
    if bloqueio:
        return bloqueio
    banca = acc[0]
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if nome:
            try:
                ciclo = CicloAvaliacao.objects.create(
                    banca=banca, nome=nome,
                    periodo_inicio=request.POST.get('periodo_inicio'),
                    periodo_fim=request.POST.get('periodo_fim'),
                )
                metricas_nomes = request.POST.getlist('metrica_nome[]')
                metricas_desc = request.POST.getlist('metrica_descricao[]')
                for i, mnome in enumerate(metricas_nomes):
                    mnome = mnome.strip()
                    if mnome:
                        MetricaAvaliacao.objects.create(
                            ciclo=ciclo, nome=mnome,
                            descricao=(metricas_desc[i] if i < len(metricas_desc) else '').strip(),
                            ordem=i,
                        )
                return redirect('rh_avaliacoes')
            except ValidationError as e:
                if hasattr(e, 'message_dict'):
                    for field, messages_list in e.message_dict.items():
                        for msg in messages_list:
                            messages.error(request, msg)
                else:
                    messages.error(request, str(e))
        else:
            messages.error(request, 'O nome do ciclo é obrigatório.')
    return render(request, 'rh/avaliacoes/ciclo_form.html',
                  _ctx(request, 'avaliacoes', {'banca': banca}))


@_requer_sessao
def ciclo_editar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_avaliacoes')
    if bloqueio:
        return bloqueio
    banca = acc[0]
    ciclo = get_object_or_404(CicloAvaliacao, pk=pk, banca=banca)
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if nome:
            ciclo.nome = nome
            ciclo.periodo_inicio = request.POST.get('periodo_inicio')
            ciclo.periodo_fim = request.POST.get('periodo_fim')
            ciclo.save()
            return redirect('rh_avaliacoes')
        messages.error(request, 'O nome do ciclo é obrigatório.')
    return render(request, 'rh/avaliacoes/ciclo_form.html',
                  _ctx(request, 'avaliacoes', {'banca': banca, 'ciclo': ciclo}))


@_requer_sessao
def ciclo_apagar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_avaliacoes')
    if bloqueio:
        return bloqueio
    banca = acc[0]
    ciclo = get_object_or_404(CicloAvaliacao, pk=pk, banca=banca)
    if request.method == 'POST':
        ciclo.delete()
        messages.success(request, 'Ciclo de avaliação removido.')
    return redirect('rh_avaliacoes')


@_requer_sessao
def ciclo_detalhe_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    ciclo = get_object_or_404(CicloAvaliacao, pk=pk, banca=banca)
    metricas = ciclo.metricas.all()
    avaliacoes = ciclo.avaliacoes.select_related('colaborador').prefetch_related('notas_metricas__metrica').all()
    if not is_desp and gestor and gestor.filial_id:
        avaliacoes = avaliacoes.filter(
            colaborador__filial_id=gestor.filial_id,
        ).exclude(colaborador=col_log)
    # Construir mapa de notas por avaliação para template
    for a in avaliacoes:
        a.notas_map = {nm.metrica_id: nm.nota for nm in a.notas_metricas.all()}
    avaliados = {a.colaborador_id for a in avaliacoes}
    pendentes = escopo_colaboradores_ativos(
        banca, col_log, gestor, is_desp, request=request,
    ).exclude(pk__in=avaliados)
    if col_log:
        pendentes = pendentes.exclude(pk=col_log.pk)
    # Se não há métricas definidas, usar padrão
    if not metricas:
        metricas = [
            {'nome': 'Pontualidade', 'chave': 'pontualidade'},
            {'nome': 'Produtividade', 'chave': 'produtividade'},
            {'nome': 'Qualidade do Trabalho', 'chave': 'qualidade_trabalho'},
            {'nome': 'Trabalho em Equipa', 'chave': 'trabalho_equipa'},
            {'nome': 'Iniciativa', 'chave': 'iniciativa'},
        ]
    return render(request, 'rh/avaliacoes/ciclo_detalhe.html',
                  _ctx(request, 'avaliacoes', {
                      'banca': banca, 'ciclo': ciclo,
                      'avaliacoes': avaliacoes,
                      'metricas': metricas,
                      'funcs_pendentes': pendentes,
                      'cols_pendentes': pendentes,
                  }))


@_requer_sessao
def avaliacao_form_view(request, ciclo_pk, col_pk=None):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    ciclo = get_object_or_404(CicloAvaliacao, pk=ciclo_pk, banca=banca)
    aval = col = None

    if col_pk:
        col = get_object_or_404(Colaborador, pk=col_pk, banca=banca)
        if not pode_avaliar_colaborador(col_log, is_desp, col):
            messages.error(
                request,
                'Não pode avaliar o seu próprio desempenho. '
                'A avaliação do gestor é feita pelo despachante.',
            )
            return redirect('rh_ciclo_detalhe', pk=ciclo.pk)
        if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, col):
            messages.error(request, 'Sem permissão para avaliar este colaborador.')
            return redirect('rh_ciclo_detalhe', pk=ciclo.pk)
        aval = Avaliacao.objects.filter(ciclo=ciclo, colaborador=col).first()

    if request.method == 'POST':
        col_raw = request.POST.get('colaborador')
        col_id = col_pk or (int(col_raw) if col_raw else 0)
        col = get_object_or_404(Colaborador, pk=col_id, banca=banca)
        if not pode_avaliar_colaborador(col_log, is_desp, col):
            messages.error(
                request,
                'Não pode avaliar o seu próprio desempenho.',
            )
            return redirect('rh_ciclo_detalhe', pk=ciclo.pk)
        if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, col):
            messages.error(request, 'Sem permissão para avaliar este colaborador.')
            return redirect('rh_ciclo_detalhe', pk=ciclo.pk)
        if not col_pk and Avaliacao.objects.filter(ciclo=ciclo, colaborador=col).exists():
            messages.error(request, f'{col.nome} já foi avaliado neste ciclo.')
            return redirect('rh_ciclo_detalhe', pk=ciclo.pk)
        kpis = {}
        metricas = list(ciclo.metricas.all())
        for m in metricas:
            v = request.POST.get(f'metrica_{m.pk}')
            kpis[m.nome] = int(v) if v else 3
        if not metricas:
            for k in ['pontualidade', 'produtividade', 'qualidade_trabalho',
                      'trabalho_equipa', 'iniciativa']:
                v = request.POST.get(k)
                kpis[k] = int(v) if v else 3
        nota = round(sum(kpis.values()) / len(kpis), 1) if kpis else 3
        aval, created = Avaliacao.objects.update_or_create(
            ciclo=ciclo, colaborador=col,
            defaults={
                'nota_global': nota,
                'pontos_fortes': request.POST.get('pontos_fortes', '').strip(),
                'pontos_melhoria': request.POST.get('pontos_melhoria', '').strip(),
                'plano_desenvolvimento': request.POST.get('plano_desenvolvimento', '').strip(),
            }
        )
        # Guardar notas das métricas dinâmicas
        NotaMetrica.objects.filter(avaliacao=aval).delete()
        for m in metricas:
            v = request.POST.get(f'metrica_{m.pk}')
            if v:
                NotaMetrica.objects.create(avaliacao=aval, metrica=m, nota=int(v))

        # Backward compat: preencher campos antigos se as métricas forem as padrão
        if not metricas:
            aval.pontualidade = kpis.get('pontualidade', 3)
            aval.produtividade = kpis.get('produtividade', 3)
            aval.qualidade_trabalho = kpis.get('qualidade_trabalho', 3)
            aval.trabalho_equipa = kpis.get('trabalho_equipa', 3)
            aval.iniciativa = kpis.get('iniciativa', 3)
            aval.save(update_fields=['pontualidade', 'produtividade', 'qualidade_trabalho', 'trabalho_equipa', 'iniciativa'])
        return redirect('rh_ciclo_detalhe', pk=ciclo.pk)

    cols_avaliaveis = escopo_colaboradores_ativos(
        banca, col_log, gestor, is_desp, request=request,
    )
    if col_log:
        cols_avaliaveis = cols_avaliaveis.exclude(pk=col_log.pk)

    # Excluir colaboradores já avaliados neste ciclo (apenas na criação)
    if not col_pk:
        cols_avaliaveis = cols_avaliaveis.exclude(
            pk__in=Avaliacao.objects.filter(ciclo=ciclo).values_list('colaborador', flat=True)
        )

    metricas = ciclo.metricas.all()
    kpis_list = []
    if metricas:
        for m in metricas:
            nota = aval.notas_metricas.filter(metrica=m).first() if aval else None
            kpis_list.append((f'metrica_{m.pk}', m.nome, m.descricao, nota.nota if nota else 3))
    else:
        kpis_list = [
            ('pontualidade',      'Pontualidade',          '', aval.pontualidade if aval else 3),
            ('produtividade',     'Produtividade',         '', aval.produtividade if aval else 3),
            ('qualidade_trabalho','Qualidade do Trabalho', '', aval.qualidade_trabalho if aval else 3),
            ('trabalho_equipa',   'Trabalho em Equipa',    '', aval.trabalho_equipa if aval else 3),
            ('iniciativa',        'Iniciativa',            '', aval.iniciativa if aval else 3),
        ]

    return render(request, 'rh/avaliacoes/avaliacao_form.html',
                  _ctx(request, 'avaliacoes', {
                      'banca': banca, 'ciclo': ciclo, 'aval': aval, 'col': col,
                      'colaboradores': cols_avaliaveis,
                      'kpis_list': kpis_list,
                  }))


@_requer_sessao
def avaliacao_apagar_view(request, ciclo_pk, col_pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    if not is_desp and not ('gerir_rh' in _perm_set and col_log and not col_log.filial_id):
        messages.error(request, 'Apenas o despachante pode remover avaliações.')
        return redirect('rh_ciclo_detalhe', pk=ciclo_pk)
    if request.method == 'POST':
        ciclo = get_object_or_404(CicloAvaliacao, pk=ciclo_pk, banca=banca)
        aval = get_object_or_404(Avaliacao, ciclo=ciclo, colaborador__pk=col_pk)
        nome = aval.colaborador.nome
        aval.delete()
        messages.success(request, f'Avaliação de {nome} removida com sucesso.')
    return redirect('rh_ciclo_detalhe', pk=ciclo_pk)


@_requer_sessao
def avaliacao_detalhe_view(request, ciclo_pk, col_pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    ciclo = get_object_or_404(CicloAvaliacao, pk=ciclo_pk, banca=banca)
    col = get_object_or_404(Colaborador, pk=col_pk, banca=banca)
    aval = get_object_or_404(Avaliacao, ciclo=ciclo, colaborador=col)

    metricas = ciclo.metricas.all()
    kpis_list = []
    if metricas:
        for m in metricas:
            nota = aval.notas_metricas.filter(metrica=m).first()
            kpis_list.append((f'metrica_{m.pk}', m.nome, m.descricao, nota.nota if nota else 3, True))
    else:
        kpis_list = [
            ('pontualidade',      'Pontualidade',          '', getattr(aval, 'pontualidade', 3), True),
            ('produtividade',     'Produtividade',         '', getattr(aval, 'produtividade', 3), True),
            ('qualidade_trabalho','Qualidade do Trabalho', '', getattr(aval, 'qualidade_trabalho', 3), True),
            ('trabalho_equipa',   'Trabalho em Equipa',    '', getattr(aval, 'trabalho_equipa', 3), True),
            ('iniciativa',        'Iniciativa',            '', getattr(aval, 'iniciativa', 3), True),
        ]

    return render(request, 'rh/avaliacoes/avaliacao_form.html',
                  _ctx(request, 'avaliacoes', {
                      'banca': banca, 'ciclo': ciclo, 'aval': aval, 'col': col,
                      'colaboradores': [],
                      'kpis_list': kpis_list,
                      'readonly': True,
                  }))


# ─── Cargos da Banca (CRUD) ─────────────────────────────────────────────────────

@_requer_sessao
def cargos_lista_view(request):
    """Lista todos os cargos da banca. Gestor só vê cargos com permissões de filial."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    pode_gerir_cargos = (
        is_desp or gestor or
        ('gerir_rh' in _perm_set and not col_log.filial_id)
    )
    if not pode_gerir_cargos:
        return redirect_sem_acesso_rh(request)
    from django.db.models import Exists, OuterRef
    perm_fora = Permissao.objects.filter(
        cargos_banca=OuterRef('pk')
    ).exclude(codigo__in=PERMISSOES_GESTOR_CARGO)
    cargos = banca.cargos.annotate(
        tem_perm_fora=Exists(perm_fora),
        total_colab=models.Count('colaboradores'),
    )
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    if not is_desp and not ('gerir_rh' in _perm_set and col_log and not col_log.filial_id):
        cargos = cargos.filter(tem_perm_fora=False)
    return render(request, 'rh/cargos_lista.html',
                  _ctx(request, 'cargos', {
                      'banca': banca, 'cargos': cargos,
                  }))


@_requer_sessao
def _grupos_permissoes_banca(request, para_gestor=False):
    """Retorna a estrutura agrupada de permissões para o formulário de cargo.

    Se para_gestor=True, mostra apenas os grupos Aduaneiro/RH/Financeiro
    com permissões de âmbito filial.
    """
    if para_gestor:
        from users.permissoes import get_usuario_permissoes
        user_perm = get_usuario_permissoes(request)
        todas = Permissao.objects.filter(codigo__in=list(PERMISSOES_GESTOR_CARGO))
        perm_map = {p.codigo: p for p in todas}
        grupos = []
        # Grupo Aduaneiro — header: gerir_aduaneiro
        adu_header = perm_map.get('gerir_aduaneiro')
        adu_items = [p for p in [perm_map.get(c) for c in ['gerir_aduaneiro', 'criar_declaracao_unica', 'ver_pauta_aduaneira', 'gerir_clientes_filial']] if p]
        if adu_header or adu_items:
            grupos.append({'nome': 'Gestão Aduaneira', 'header': adu_header or adu_items[0], 'items': adu_items})
        # Grupo RH — header: gerir_rh
        rh_header = perm_map.get('gerir_rh')
        rh_codes = ['gerir_rh', 'ver_minha_banca', 'gerir_colaboradores_banca',
                    'gerir_processamento_salarial', 'gerir_recrutamento_banca',
                    'gerir_presencas_banca', 'gerir_avaliacoes_banca']
        rh_items = [p for p in [perm_map.get(c) for c in rh_codes] if p]
        if rh_header or rh_items:
            grupos.append({'nome': 'Recursos Humanos', 'header': rh_header or rh_items[0], 'items': rh_items})
        # Grupo Financeiro — header: gerir_financeiro_filial
        fin_header = perm_map.get('gerir_financeiro_filial')
        fin_codes = ['gerir_financeiro_filial', 'ver_requisicoes', 'ver_recibos', 'ver_notas_financeiro',
                     'ver_facturas', 'ver_conta_corrente', 'ver_relatorios_financeiros']
        fin_items = [p for p in [perm_map.get(c) for c in fin_codes] if p]
        if fin_header or fin_items:
            grupos.append({'nome': 'Gestão Financeira', 'header': fin_header or fin_items[0], 'items': fin_items})
        return grupos

    from users.permissoes import PERMISSOES_BANCA
    todas = Permissao.objects.filter(codigo__in=PERMISSOES_BANCA)
    perm_map = {p.codigo: p for p in todas}
    GRUPOS = [
        {
            'nome': 'Gestão Aduaneira',
            'header_codigo': 'gerir_aduaneiro',
            'items': ['gerir_aduaneiro', 'criar_declaracao_unica', 'ver_pauta_aduaneira', 'gerir_clientes', 'gerir_clientes_filial'],
        },
        {
            'nome': 'Recursos Humanos',
            'header_codigo': 'gerir_rh',
            'items': ['ver_minha_banca', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
                      'gerir_processamento_salarial', 'gerir_recrutamento_banca',
                      'gerir_presencas_banca', 'gerir_avaliacoes_banca'],
        },
        {
            'nome': 'Gestão Financeira',
            'header_codigo': 'gerir_financeiro',
            'items': ['ver_requisicoes', 'ver_recibos', 'ver_notas_financeiro',
                      'ver_facturas', 'ver_conta_corrente', 'ver_relatorios_financeiros',
                      'gerir_financeiro_filial'],
        },
        {
            'nome': 'Colaborador',
            'header_codigo': 'alterar_perfil',
            'items': ['alterar_perfil'],
        },
        {
            'nome': 'Administração',
            'header_codigo': 'ver_logs_banca',
            'items': ['ver_logs_banca'],
        },
        {
            'nome': 'Administrador da Banca',
            'header_codigo': 'admin_banca',
            'items': ['admin_banca'],
        },
    ]
    grupos = []
    for g in GRUPOS:
        header = perm_map.get(g['header_codigo'])
        if not header:
            continue
        items = []
        for cod in g['items']:
            p = perm_map.get(cod)
            if p:
                items.append(p)
        grupos.append({'nome': g['nome'], 'header': header, 'items': items})
    return grupos


def cargo_novo_view(request):
    """Cria um novo cargo na banca. Gestor só pode atribuir permissões de filial."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    pode_gerir_cargos = (
        is_desp or gestor or
        ('gerir_rh' in _perm_set and not col_log.filial_id)
    )
    if not pode_gerir_cargos:
        return redirect_sem_acesso_rh(request)
    para_gestor = bool(gestor and not is_desp)
    grupos = _grupos_permissoes_banca(request, para_gestor=para_gestor)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        descricao = request.POST.get('descricao', '').strip()
        codigos_perm = set(request.POST.getlist('permissoes'))
        erro_mistura = _validar_mistura_sede_filial(codigos_perm)
        if not nome:
            messages.error(request, 'O nome do cargo é obrigatório.')
        elif erro_mistura:
            messages.error(request, erro_mistura)
        elif banca.cargos.filter(nome__iexact=nome).exists():
            messages.error(request, f'Já existe um cargo com o nome "{nome}" nesta banca.')
        else:
            if para_gestor:
                codigos_perm &= PERMISSOES_GESTOR_CARGO
            cargo = CargoBanca.objects.create(
                banca=banca, nome=nome, descricao=descricao,
            )
            if codigos_perm:
                cargo.permissoes.set(Permissao.objects.filter(codigo__in=codigos_perm))
            messages.success(request, f'Cargo "{nome}" criado com sucesso.')
            return redirect('rh_cargos_lista')

    return render(request, 'rh/cargo_form.html',
                  _ctx(request, 'cargos', {
                      'banca': banca, 'grupos': grupos, 'cargo': None,
                  }))


@_requer_sessao
def cargo_editar_view(request, pk):
    """Edita um cargo existente da banca. Gestor só pode atribuir permissões de filial."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    pode_gerir_cargos = (
        is_desp or gestor or
        ('gerir_rh' in _perm_set and not col_log.filial_id)
    )
    if not pode_gerir_cargos:
        return redirect_sem_acesso_rh(request)
    para_gestor = bool(gestor and not is_desp)
    cargo = get_object_or_404(CargoBanca, pk=pk, banca=banca)

    # Gestor não pode editar cargos com permissões de banca (criados pelo despachante)
    tem_perm_banca = cargo.permissoes.exclude(codigo__in=PERMISSOES_GESTOR_CARGO).exists()
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    if not is_desp and not ('gerir_rh' in _perm_set and col_log and not col_log.filial_id) and tem_perm_banca:
        messages.error(request, 'Não pode editar cargos criados pelo despachante.')
        return redirect('rh_cargos_lista')
    if cargo.locked:
        messages.error(request, 'Este cargo é padrão do sistema e não pode ser alterado.')
        return redirect('rh_cargos_lista')
    grupos = _grupos_permissoes_banca(request, para_gestor=para_gestor)
    permissoes_ids = set(cargo.permissoes.values_list('pk', flat=True))

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        descricao = request.POST.get('descricao', '').strip()
        codigos_perm = set(request.POST.getlist('permissoes'))
        erro_mistura = _validar_mistura_sede_filial(codigos_perm)
        if not nome:
            messages.error(request, 'O nome do cargo é obrigatório.')
        elif erro_mistura:
            messages.error(request, erro_mistura)
        elif banca.cargos.filter(nome__iexact=nome).exclude(pk=cargo.pk).exists():
            messages.error(request, f'Já existe um cargo com o nome "{nome}" nesta banca.')
        else:
            cargo.nome = nome
            cargo.descricao = descricao
            cargo.save()
            if not cargo.locked:
                if para_gestor:
                    codigos_perm &= PERMISSOES_GESTOR_CARGO
                cargo.permissoes.set(Permissao.objects.filter(codigo__in=codigos_perm))
            messages.success(request, f'Cargo "{nome}" actualizado com sucesso.')
            return redirect('rh_cargos_lista')

    return render(request, 'rh/cargo_form.html',
                  _ctx(request, 'cargos', {
                      'banca': banca, 'grupos': grupos,
                      'cargo': cargo, 'permissoes_ids': permissoes_ids,
                  }))


@_requer_sessao
def cargo_eliminar_view(request, pk):
    """Elimina um cargo (apenas se nenhum colaborador o usar)."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    pode_gerir_cargos = (
        is_desp or gestor or
        ('gerir_rh' in _perm_set and not col_log.filial_id)
    )
    if not pode_gerir_cargos:
        return redirect_sem_acesso_rh(request)
    cargo = get_object_or_404(CargoBanca, pk=pk, banca=banca)

    # Impedir que despachante elimine cargos do gestor e vice-versa
    tem_perm_banca = cargo.permissoes.exclude(codigo__in=PERMISSOES_GESTOR_CARGO).exists()
    if is_desp and not tem_perm_banca:
        messages.error(request, 'Não pode eliminar cargos criados pelo gestor de filial.')
        return redirect('rh_cargos_lista')
    from users.permissoes import get_usuario_permissoes
    _perm_set = get_usuario_permissoes(request)
    if not is_desp and not ('gerir_rh' in _perm_set and col_log and not col_log.filial_id) and tem_perm_banca:
        messages.error(request, 'Não pode eliminar cargos criados pelo despachante.')
        return redirect('rh_cargos_lista')
    if cargo.locked:
        messages.error(request, 'Este cargo é padrão do sistema e não pode ser eliminado.')
        return redirect('rh_cargos_lista')

    if cargo.colaboradores.exists():
        messages.error(request, f'Não é possível eliminar o cargo "{cargo.nome}" porque está atribuído a {cargo.colaboradores.count()} colaborador(es).')
        return redirect('rh_cargos_lista')

    nome = cargo.nome
    cargo.delete()
    messages.success(request, f'Cargo "{nome}" eliminado com sucesso.')
    return redirect('rh_cargos_lista')


@_requer_sessao
def colaborador_cargo_view(request, pk):
    """Atribui ou remove o cargo_banca de um colaborador (inline na listagem)."""
    acc = obter_acesso_rh(request)
    if not acc:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'erro': 'Sem acesso.'}, status=403)
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc

    from .acesso import pode_aceder_colaborador
    col = get_object_or_404(Colaborador, pk=pk, banca=banca)
    if not pode_aceder_colaborador(banca, col_log, gestor, is_desp, col):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'erro': 'Não tem permissão para alterar este colaborador.'}, status=403)
        messages.error(request, 'Não tem permissão para alterar este colaborador.')
        return redirect('rh_colaboradores')

    perm_set = get_usuario_permissoes(request)
    if not _pode_gerir_cargo(col, col_log, gestor, is_desp, perm_set):
        msg = 'Não pode alterar o cargo deste colaborador.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'erro': msg}, status=403)
        messages.error(request, msg)
        return redirect('rh_colaboradores')

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        cargo_banca_pk = request.POST.get('cargo_banca', '').strip()
        if cargo_banca_pk:
            try:
                cargo = banca.cargos.get(pk=cargo_banca_pk)
                pode_banca = 'gerir_rh' in perm_set and not col_log.filial_id
                if cargo.nome == 'Gestor de Filial':
                    if is_ajax:
                        return JsonResponse({'ok': False, 'erro': 'Use o formulário de edição para atribuir "Gestor de Filial" com a filial correspondente.'}, status=400)
                    messages.warning(request, 'Use o formulário de edição para atribuir o cargo "Gestor de Filial" com a filial correspondente.')
                    return redirect('rh_colaborador_editar', pk=col.pk)
                if not is_desp and not pode_banca and (
                    cargo.permissoes.exclude(codigo__in=PERMISSOES_GESTOR_CARGO).exists()
                ):
                    if is_ajax:
                        return JsonResponse({'ok': False, 'erro': 'Não pode atribuir este cargo.'}, status=403)
                    messages.error(request, 'Não pode atribuir este cargo.')
                    return redirect('rh_colaboradores')
                col.cargo_banca = cargo
                col.save(update_fields=['cargo_banca'])
                if is_ajax:
                    return JsonResponse({'ok': True, 'cargo_nome': cargo.nome, 'cargo_pk': cargo.pk,
                                         'mensagem': f'Cargo "{cargo.nome}" atribuído a {col.nome}.'})
                messages.success(request, f'Cargo "{col.cargo_banca.nome}" atribuído a {col.nome}.')
            except CargoBanca.DoesNotExist:
                if is_ajax:
                    return JsonResponse({'ok': False, 'erro': 'Cargo inválido.'}, status=400)
                messages.error(request, 'Cargo inválido.')
        else:
            if col.cargo_banca and col.cargo_banca.nome == 'Gestor de Filial':
                if is_ajax:
                    return JsonResponse({'ok': False, 'erro': 'Use o formulário de edição para remover o cargo "Gestor de Filial".'}, status=400)
                messages.warning(request, 'Use o formulário de edição para remover o cargo "Gestor de Filial".')
                return redirect('rh_colaborador_editar', pk=col.pk)
            if not _pode_gerir_cargo(col, col_log, gestor, is_desp, perm_set):
                msg = 'Não pode remover o cargo deste colaborador.'
                if is_ajax:
                    return JsonResponse({'ok': False, 'erro': msg}, status=403)
                messages.error(request, msg)
                return redirect('rh_colaboradores')
            col.cargo_banca = None
            col.save(update_fields=['cargo_banca'])
            if is_ajax:
                return JsonResponse({'ok': True, 'cargo_nome': '', 'cargo_pk': None,
                                     'mensagem': f'Cargo removido de {col.nome}.'})
            messages.success(request, f'Cargo removido de {col.nome}.')

    return redirect('rh_colaboradores')
