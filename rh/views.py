from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.cache import cache
from django.db import models
from django.db.models import Count, Prefetch, Q
from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
from utils.format_kz import parse_kz
import bcrypt
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
    filial_id_obrigatoria_gestor,
    redirect_sem_acesso_rh,
)
from .models import (
    Banca, FilialBanca, Colaborador, GestorFilial, DocumentoColaborador,
    ProcessamentoSalarial, ReciboSalarial, Subsidio, SubsidioRecibo, Fatura,
    Vaga, Candidatura, Entrevista, PlanoIntegracao, TarefaIntegracao,
    RegistoPresenca, PedidoFerias,
    CicloAvaliacao, Avaliacao, MetricaAvaliacao, NotaMetrica,
)

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
MESES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
         'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _requer_sessao(fn):
    def wrapper(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            return redirect('login')
        return fn(request, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def _ctx(request, sub='', extra=None):
    u = request.session['usuario']
    ctx = {'usuario': u, 'nome': u['nome'], 'papel': u['papel'],
           'active_menu': 'RH', 'active_sub': sub}
    acc = obter_acesso_rh(request)
    if acc:
        banca, col_log, gestor, is_desp = acc
        ctx['is_despachante'] = is_desp
        ctx['e_gestor_filial'] = bool(gestor and not is_desp)
        ctx['e_responsavel'] = ctx['e_gestor_filial']
        ctx['filial_gestor'] = gestor.filial if gestor else None
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
    """Bloqueia gestores de filial em acções reservadas ao despachante."""
    if acc and not acc[3]:
        messages.error(request, 'Apenas o despachante pode realizar esta acção.')
        return redirect(destino)
    return None


# ─── Helpers de Presenças / Férias ─────────────────────────────────────────────

def marcar_ferias_no_registo(pedido):
    """Quando férias são aprovadas, marca todos os dias úteis como 'Ferias' e remove faltas."""
    from datetime import timedelta
    data = pedido.data_inicio
    while data <= pedido.data_fim:
        if data.weekday() < 5:
            RegistoPresenca.objects.update_or_create(
                colaborador=pedido.colaborador, data=data,
                defaults={
                    'tipo': 'Ferias', 'estado': 'Aprovado',
                    'hora_entrada': None, 'hora_saida': None,
                    'horas_extras': 0, 'justificacao': '',
                },
            )
        data += timedelta(days=1)


def auto_marcar_faltas(banca, data_alvo=None):
    """Marca 'Falta' para colaboradores activos sem registo de presença num dia útil."""
    from datetime import date
    data_alvo = data_alvo or date.today()
    if data_alvo.weekday() >= 5:
        return
    cols = banca.colaboradores.filter(estado='Ativo').only('id', 'nome')
    for col in cols:
        if not RegistoPresenca.objects.filter(colaborador=col, data=data_alvo).exists():
            reg = RegistoPresenca(colaborador=col, data=data_alvo)
            reg.tipo = 'Falta'
            reg.estado = 'Pendente'
            reg.justificacao = 'Falta automática — não registou presença'
            reg.full_clean()
            reg.save()


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


def _dec(val, default=Decimal('0')):
    try:
        parsed = parse_kz(val)
        return Decimal(str(parsed)) if parsed else default
    except (InvalidOperation, ValueError, TypeError):
        return default


def _hash_password(senha):
    """Gera hash bcrypt para a senha (compatível com formato PHP)"""
    if not senha:
        return None
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(senha.encode('utf-8'), salt)
    # Converter de $2b$ (Python) para $2y$ (PHP) para compatibilidade
    return hashed.decode('utf-8').replace('$2b$', '$2y$')


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
    from django.conf import settings
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import black, gray, green
    from decimal import Decimal
    import os

    recibos = processamento.recibos.select_related('colaborador').all()
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

    y_position = height - margin_top

    # Cabeçalho
    c.setFont("Helvetica-Bold", 16)
    title_text = "PROCESSAMENTO SALARIAL - COMPROVANTE DE PAGAMENTO"
    text_width = c.stringWidth(title_text, "Helvetica-Bold", 16)
    c.drawString((width - text_width) / 2, y_position, title_text)
    y_position -= 30

    c.setFont("Helvetica-Bold", 12)
    banca_text = banca.nome
    text_width = c.stringWidth(banca_text, "Helvetica-Bold", 12)
    c.drawString((width - text_width) / 2, y_position, banca_text)
    y_position -= 20

    c.setFont("Helvetica", 10)
    periodo_text = f"Período: {processamento.mes:02d}/{processamento.ano} | Status: {estado_display}"
    text_width = c.stringWidth(periodo_text, "Helvetica", 10)
    c.drawString((width - text_width) / 2, y_position, periodo_text)
    y_position -= 15

    from django.utils import timezone
    data_text = f"Data de pagamento: {timezone.now().strftime('%d/%m/%Y %H:%M')}"
    text_width = c.stringWidth(data_text, "Helvetica", 10)
    c.drawString((width - text_width) / 2, y_position, data_text)
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
            y_position = height - margin_top

            # Repetir cabeçalho na nova página
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
            f"{recibo.salario_base:,.2f}",
            f"{total_subsidios:,.2f}",
            f"{recibo.bruto:,.2f}",
            f"{recibo.outros_descontos:,.2f}",
            f"{recibo.irt:,.2f}",
            f"{recibo.inss_trabalhador:,.2f}",
            f"{recibo.liquido:,.2f}"
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
    c.drawRightString(width - margin_right, y_position, f"{total_liquido:,.2f} KZ")
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


def _gerar_faturas_processamento(processamento, request):
    """Gera faturas para despachante e colaboradores quando o processamento é marcado como pago."""
    from .models import Fatura

    # Verificar se já existem faturas para este processamento
    if processamento.faturas.exists():
        return  # Já foram geradas

    # Calcular valor total do processamento
    valor_total = sum(r.liquido for r in processamento.recibos.all())

    # Gerar fatura para o despachante (serviço de processamento salarial)
    taxa_servico = valor_total * Decimal('0.05')  # 5% de taxa de serviço
    codigo_despachante = f"FAT-DESP-{timezone.now().year}-{str(processamento.pk).zfill(4)}"

    Fatura.objects.create(
        codigo=codigo_despachante,
        tipo='SALARIO_DESPACHANTE',
        processamento_salarial=processamento,
        banca=processamento.banca,
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
            colaborador=recibo.colaborador,
            valor_bruto=recibo.bruto,
            valor_liquido=recibo.liquido,
            valor_imposto=recibo.irt + recibo.inss_trabalhador,
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


# Tabela IRT Angola (Imposto sobre Rendimento do Trabalho) - 2024
# Base: salário bruto mensal em KZ
def _calcular_irt(salario: Decimal) -> Decimal:
    """
    Calcula o IRT segundo a tabela angolana vigente.
    Escalões sobre o salário bruto mensal (KZ).
    """
    s = float(salario)
    if s <= 150000:
        irt = 0.0
    elif s <= 200000:
        irt = (s - 150000) * 0.16
    elif s <= 300000:
        irt = 8000 + (s - 200000) * 0.18
    elif s <= 500000:
        irt = 26000 + (s - 300000) * 0.19
    elif s <= 1000000:
        irt = 64000 + (s - 500000) * 0.20
    elif s <= 1500000:
        irt = 164000 + (s - 1000000) * 0.21
    elif s <= 2000000:
        irt = 269000 + (s - 1500000) * 0.22
    elif s <= 5000000:
        irt = 379000 + (s - 2000000) * 0.23
    elif s <= 10000000:
        irt = 1069000 + (s - 5000000) * 0.24
    else:
        irt = 2269000 + (s - 10000000) * 0.25
    return Decimal(str(round(irt, 2)))


# ══════════════════════════════════════════════════════════════════════════════
# BANCA
# ══════════════════════════════════════════════════════════════════════════════
@_requer_sessao
def banca_view(request):
    """Dashboard da banca com visão geral das filiais, colaboradores e recrutamento."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    if not is_desp:
        return redirect('rh_presencas')

    uid = request.session['usuario_id']
    banca = Banca.objects.filter(usuario_id=uid, ativa=True).first()
    if not banca:
        return redirect('rh_banca_criar')

    filiais = list(banca.filiais.filter(ativa=True).order_by('provincia'))
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
def banca_criar_view(request):
    """Criação da banca (apenas se não existir)."""
    uid = request.session['usuario_id']

    # Verificar se já existe banca
    if Banca.objects.filter(usuario_id=uid, ativa=True).exists():
        return redirect('rh_banca')

    def _render(extra=None):
        return render(request, 'rh/banca/criar.html', _ctx(request, 'banca', {
            'banca_tipos': BANCA_TIPOS, 'provincias': PROVINCIAS,
            **(extra or {}),
        }))

    if request.method == 'POST':
        dados = {k: request.POST.get(k, '').strip() for k in
                 ['nome', 'nif', 'tipo', 'email', 'telefone',
                  'endereco', 'provincia', 'municipio', 'licenca_cdoa']}
        if not dados['nome'] or not dados['nif']:
            return _render({'erro': 'Nome e NIF são obrigatórios.'})

        # Verificar se NIF já existe
        if Banca.objects.filter(nif=dados['nif']).exists():
            return _render({'erro': 'Já existe uma banca com este NIF.'})

        # Verificar se email já existe no sistema
        if dados['email'] and email_ja_existe(dados['email']):
            return _render({'erro': 'Este email já está registado no sistema.'})

        banca = Banca(usuario_id=uid, **dados)
        if 'logo' in request.FILES:
            banca.logo = request.FILES['logo']
        banca.save()

        return redirect('rh_banca')

    return _render()


@_requer_sessao
def banca_editar_view(request):
    """Edição dos dados da banca."""
    uid = request.session['usuario_id']
    banca = get_object_or_404(Banca, usuario_id=uid, ativa=True)

    def _render(extra=None):
        form_data = {
            'nome': banca.nome, 'nif': banca.nif, 'tipo': banca.tipo,
            'email': banca.email, 'telefone': banca.telefone,
            'endereco': banca.endereco, 'provincia': banca.provincia,
            'municipio': banca.municipio, 'licenca_cdoa': banca.licenca_cdoa,
        }
        return render(request, 'rh/banca/editar.html', _ctx(request, 'banca', {
            'banca': banca, 'banca_tipos': BANCA_TIPOS,
            'provincias': PROVINCIAS, 'form': form_data, **(extra or {}),
        }))

    if request.method == 'POST':
        dados = {k: request.POST.get(k, '').strip() for k in
                 ['nome', 'nif', 'tipo', 'email', 'telefone',
                  'endereco', 'provincia', 'municipio', 'licenca_cdoa']}
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
        if 'logo' in request.FILES:
            banca.logo = request.FILES['logo']
        banca.save()

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
    """Visualização detalhada da filial com colaboradores e estatísticas."""
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    bloqueio = _redirect_se_nao_despachante(request, acc, 'rh_banca')
    if bloqueio:
        return bloqueio
    banca = acc[0]

    try:
        filial = FilialBanca.objects.get(pk=pk, banca=banca)
    except FilialBanca.DoesNotExist:
        messages.error(request, 'A filial que tentou aceder não existe ou foi removida.')
        return redirect('rh_banca')

    colaboradores = filial.colaboradores.select_related('filial').all()

    # Verificar se há gestor para esta filial — prefetch evita query extra
    gestor = None
    if hasattr(filial, 'gestores'):
        gestor_ativo = filial.gestores.select_related('colaborador').filter(ativo=True).first()
        if gestor_ativo:
            gestor = gestor_ativo.colaborador

    return render(request, 'rh/filiais/detalhe.html', _ctx(request, 'filiais', {
        'banca': banca, 'filial': filial, 'colaboradores': colaboradores,
        'total_colaboradores': colaboradores.count(),
        'colaboradores_ativos': colaboradores.filter(estado='Ativo'),
        'gestor': gestor,
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
@_requer_sessao
def colaboradores_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    cols = escopo_colaboradores(
        banca, col_log, gestor, is_desp,
    ).select_related('filial').prefetch_related('documentos')
    filiais = (
        list(banca.filiais.all()) if is_desp
        else [gestor.filial]
    )
    paginator = Paginator(cols, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'rh/colaboradores/lista.html',
                  _ctx(request, 'colaboradores', {
                      'banca': banca, 'colaboradores': page_obj, 'filiais': filiais,
                      'page_obj': page_obj,
                  }))


@_requer_sessao
def colaborador_novo_view(request):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    filiais = (
        list(banca.filiais.all()) if is_desp
        else [gestor.filial]
    )

    def _render(extra=None):
        return render(request, 'rh/colaboradores/form.html',
                      _ctx(request, 'colaboradores', {
                          'banca': banca, 'filiais': filiais,
                          'cargos': CARGOS, 'estados': ESTADOS_COL,
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
            gestor, is_desp, request.POST.get('filial') or None,
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
        )
        if 'foto' in request.FILES:
            col.foto = request.FILES['foto']
        col.save()
        
        # Enviar email com senha se tiver email
        if email_colaborador and senha_gerada:
            sucesso_email, msg_email = enviar_senha_colaborador(col, senha_gerada)
            if sucesso_email:
                messages.success(request, f'Colaborador {nome} criado! Credenciais enviadas para {email_colaborador}.')
            else:
                messages.success(request, f'Colaborador {nome} criado com sucesso!')
                messages.warning(request, f'Não foi possível enviar o email de credenciais: {msg_email}. Use o botão "Reenviar" na lista.')
        else:
            messages.success(request, f'Colaborador {nome} criado com sucesso!')
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
    banca = _banca(request)
    if not banca:
        return JsonResponse({'erro': 'Sem permissão'}, status=403)
    col = get_object_or_404(Colaborador, pk=pk, banca=banca)
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
    filiais = (
        list(banca.filiais.prefetch_related('gestores').all()) if is_desp
        else [gestor.filial]
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

    def _render(extra=None):
        return render(request, 'rh/colaboradores/form.html',
                      _ctx(request, 'colaboradores', {
                          'banca': banca, 'col': col, 'filiais': filiais,
                          'cargos': CARGOS, 'estados': ESTADOS_COL,
                          'gestor_filial': gestor_filial,
                          'filiais_sem_gestor': filiais_sem_gestor,
                          **(extra or {}),
                      }))

    if request.method == 'POST':
        acao_gestor = request.POST.get('acao_gestor', '').strip()

        if acao_gestor == 'remover_gestor':
            if not is_desp:
                messages.error(
                    request,
                    'Apenas o despachante pode remover responsabilidade de filial.',
                )
                return redirect('rh_colaborador_editar', pk=col.pk)
            if _remover_gestor_filial(col):
                messages.success(
                    request,
                    'Responsabilidade de gestão de filial removida com sucesso.',
                )
            else:
                messages.info(request, 'Este colaborador não é gestor de filial.')
            return redirect('rh_colaborador_editar', pk=col.pk)

        if acao_gestor == 'atribuir_gestor' and is_desp:
            filial_pk = request.POST.get('filial_gestor', '').strip()
            if not filial_pk:
                messages.error(request, 'Seleccione a filial para atribuir gestão.')
                return _render()
            filial = get_object_or_404(FilialBanca, pk=filial_pk, banca=banca)
            gestor_ativo = filial.gestores.filter(ativo=True).exclude(
                colaborador=col,
            ).first()
            if gestor_ativo:
                messages.error(
                    request,
                    f'A filial {filial.provincia} já tem gestor: '
                    f'{gestor_ativo.colaborador.nome}.',
                )
                return _render()
            elegiveis = _colaboradores_elegiveis_gestor(banca, filial=filial)
            if not elegiveis.filter(pk=col.pk).exists() and not (
                gestor_filial and gestor_filial.filial_id == filial.pk
            ):
                messages.error(
                    request,
                    'Este colaborador já gere outra filial.',
                )
                return _render()
            _atribuir_gestor_filial(col, filial)
            messages.success(
                request,
                f'{col.nome} foi designado gestor da filial {filial.provincia}.',
            )
            return redirect('rh_colaborador_editar', pk=col.pk)

        col.filial_id = filial_id_obrigatoria_gestor(
            gestor, is_desp, request.POST.get('filial') or None,
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
        if 'foto' in request.FILES:
            col.foto = request.FILES['foto']
        col.save()

        _processar_documentos_colaborador(col, request)

        return redirect('rh_colaboradores')
    return _render()


@_requer_sessao
def colaborador_apagar_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    if not is_desp:
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
    if not acc[3]:
        messages.error(request, 'Apenas o despachante pode gerir subsídios.')
        return redirect('dashboard_colaborador')
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
    if not acc[3]:
        messages.info(
            request,
            'Consulte o seu recibo em Processo Salarial no menu pessoal.',
        )
        return redirect('colaborador_salario')
    banca = acc[0]

    from django.db.models import Sum
    todos = banca.processamentos.annotate(
        total_recibos=Count('recibos'),
        total_liquido_annotated=Sum('recibos__liquido'),
    ).order_by('-ano', '-mes')

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
    if request.method == 'POST':
        mes = int(request.POST.get('mes') or 1)
        ano = int(request.POST.get('ano') or timezone.now().year)
        proc, criado = ProcessamentoSalarial.objects.get_or_create(
            banca=banca, mes=mes, ano=ano, defaults={'estado': 'Rascunho'}
        )
        if not criado:
            return render(request, 'rh/salarios/novo.html',
                          _ctx(request, 'salarios', {
                              'banca': banca, 'meses': MESES,
                              'ano_atual': timezone.now().year,
                              'erro': f'Já existe processamento para {MESES[mes-1]}/{ano}.',
                          }))
        # Obter todos os subsídios ativos da banca (excluindo ALIM e TRANS)
        subsidios_banca = list(banca.subsidios.filter(ativo=True).exclude(codigo__in=['ALIM', 'TRANS']))

        # Pré-carregar M2M de subsídios específicos (bulk, 1 query por subsídio)
        subsidio_colab_ids = {}
        for s in subsidios_banca:
            if s.apenas_especificos:
                subsidio_colab_ids[s.pk] = set(
                    s.colaboradores_especificos.values_list('id', flat=True)
                )

        for col in banca.colaboradores.filter(estado='Ativo'):
            salario = col.salario_efetivo
            # Calcular faltas do mês
            faltas = RegistoPresenca.objects.filter(
                colaborador=col,
                data__month=mes, data__year=ano,
                tipo__in=['Falta', 'Falta_Justificada'],
                estado='Aprovado'
            ).count()
            # Dias úteis no mês ≈ 22; desconto proporcional por falta
            dias_uteis = Decimal('22')
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
                              'banca': banca, 'meses': MESES,
                              'ano_atual': timezone.now().year,
                              'erro': 'Não é possível gerar o processamento porque o total líquido é 0,00 KZ. Verifique os salários base e subsídios dos colaboradores ativos.',
                          }))
        return redirect('rh_salario_detalhe', pk=proc.pk)
    return render(request, 'rh/salarios/novo.html',
                  _ctx(request, 'salarios', {
                      'banca': banca, 'meses': MESES, 'ano_atual': timezone.now().year,
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
            subsidios_ativos = list(banca.subsidios.filter(ativo=True).exclude(codigo__in=['ALIM', 'TRANS']))

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
                    if subsidio.obrigatorio:
                        # Subsídios obrigatórios - recalcular valor automaticamente
                        if subsidio.tipo_calculo == 'PERCENTUAL':
                            if subsidio.percentual and r.salario_base:
                                valor_subsidio = (r.salario_base * subsidio.percentual) / 100
                            else:
                                valor_subsidio = subsidio.valor_padrao
                        elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                            dias_trabalho = 22  # Padrão
                            valor_subsidio = subsidio.valor_padrao * dias_trabalho
                        elif subsidio.tipo_calculo == 'DEPENDENTES':
                            dependentes = 1  # Padrão
                            valor_subsidio = subsidio.valor_padrao * dependentes
                        else:
                            # FIXO
                            valor_subsidio = subsidio.valor_padrao
                    else:
                        # Subsídios não obrigatórios - usar valor do formulário
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
            proc.estado = 'Pago'
            proc.save()
            # Gerar faturas para o despachante e colaboradores
            _gerar_faturas_processamento(proc, request)
            # Gerar PDF automaticamente quando marcado como pago
            _gerar_pdf_processamento(proc, request)
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
        return redirect('rh_salario_detalhe', pk=proc.pk)
    # Obter subsídios ativos para o template (excluindo ALIM e TRANS)
    subsidios_ativos = banca.subsidios.filter(ativo=True).exclude(codigo__in=['ALIM', 'TRANS'])

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

    return render(request, 'rh/salarios/detalhe.html',
                  _ctx(request, 'salarios', {
                      'banca': banca, 'proc': proc, 'recibos': recibos, 'meses': MESES,
                      'subsidios_ativos': subsidios_ativos,
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

    vagas_base = escopo_vagas(banca, gestor, is_desp)
    filiais = (
        list(banca.filiais.all()) if is_desp
        else [gestor.filial]
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
        else [gestor.filial]
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
                    gestor, is_desp, request.POST.get('filial') or None,
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
        else [gestor.filial]
    )
    if request.method == 'POST':
        try:
            vaga.filial_id = filial_id_obrigatoria_gestor(
                gestor, is_desp, request.POST.get('filial') or None,
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
        else [gestor.filial]
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
            col = Colaborador.objects.create(
                banca=banca,
                filial_id=request.POST.get('filial') or None,
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
    mes  = int(request.GET.get('mes') or hoje.month)
    ano  = int(request.GET.get('ano') or hoje.year)
    from datetime import date
    primeiro_dia = date(ano, mes, 1)
    if mes == 12:
        ultimo_dia = date(ano, 12, 31)
    else:
        ultimo_dia = date(ano, mes + 1, 1) - timezone.timedelta(days=1)
    cols = escopo_colaboradores_ativos(banca, col_log, gestor, is_desp).only(
        'id', 'nome', 'cargo', 'cargo_personalizado', 'filial_id'
    )

    registos = RegistoPresenca.objects.filter(
        colaborador__in=cols, data__month=mes, data__year=ano,
    ).select_related('colaborador').order_by('-data')
    pedidos_pendentes = PedidoFerias.objects.filter(
        colaborador__in=cols, estado='Pendente',
    ).select_related('colaborador').only(
        'id', 'colaborador_id', 'data_inicio', 'data_fim', 'motivo', 'estado', 'criado_em'
    )
    pedidos_todos = PedidoFerias.objects.filter(
        colaborador__in=cols,
        data_inicio__lte=ultimo_dia, data_fim__gte=primeiro_dia,
    ).select_related('colaborador').order_by('-criado_em')
    paginator = Paginator(registos, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'rh/presencas/lista.html',
                  _ctx(request, 'presencas', {
                      'banca': banca, 'colaboradores': cols,
                      'registos': page_obj, 'pedidos': pedidos_pendentes,
                      'page_obj': page_obj,
                      'pedidos_todos': pedidos_todos,
                      'mes': mes, 'ano': ano, 'meses': MESES, 'hoje': hoje,
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
        try:
            # Criar ou actualizar registo de presença
            data_str = request.POST.get('data')
            reg, created = RegistoPresenca.objects.get_or_create(
                colaborador=col,
                data=data_str,
            )
            reg.tipo = request.POST.get('tipo', 'Entrada')
            reg.hora_entrada = request.POST.get('hora_entrada') or None
            reg.hora_saida = request.POST.get('hora_saida') or None
            reg.horas_extras = _dec(request.POST.get('horas_extras', '0'))
            reg.justificacao = request.POST.get('justificacao', '').strip()
            reg.estado = 'Pendente'
            reg.full_clean()
            reg.save()
            messages.success(request, 'Registo de presença salvo com sucesso.')
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
        messages.error(request, 'Sem permissão para aprovar esta presença.')
        return redirect('rh_presencas')
    if request.method == 'POST':
        reg.estado = request.POST.get('estado', 'Aprovado')
        reg.save()
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
            messages.error(request, 'Sem permissão para criar pedido para este colaborador.')
            return redirect('rh_presencas')
        try:
            PedidoFerias.objects.create(
                colaborador=col,
                data_inicio=request.POST.get('data_inicio'),
                data_fim=request.POST.get('data_fim'),
                motivo=request.POST.get('motivo', '').strip(),
            )
            messages.success(request, 'Pedido de férias submetido com sucesso.')
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
    if request.method == 'POST':
        try:
            pedido.estado = request.POST.get('estado', 'Aprovado')
            pedido.save()
            if pedido.estado == 'Aprovado':
                marcar_ferias_no_registo(pedido)
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
        else:
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
        else:
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
    ciclos = banca.ciclos_avaliacao.all()
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
    if not acc[3]:
        messages.error(request, 'Apenas o despachante pode criar ciclos de avaliação.')
        return redirect('rh_avaliacoes')
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
                # Guardar métricas do ciclo
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
def ciclo_detalhe_view(request, pk):
    acc = obter_acesso_rh(request)
    if not acc:
        return redirect_sem_acesso_rh(request)
    banca, col_log, gestor, is_desp = acc
    ciclo = get_object_or_404(CicloAvaliacao, pk=pk, banca=banca)
    metricas = ciclo.metricas.all()
    avaliacoes = ciclo.avaliacoes.select_related('colaborador').prefetch_related('notas_metricas__metrica').all()
    if not is_desp:
        avaliacoes = avaliacoes.filter(
            colaborador__filial=gestor.filial,
        ).exclude(colaborador=col_log)
    # Construir mapa de notas por avaliação para template
    for a in avaliacoes:
        a.notas_map = {nm.metrica_id: nm.nota for nm in a.notas_metricas.all()}
    avaliados = {a.colaborador_id for a in avaliacoes}
    pendentes = escopo_colaboradores_ativos(
        banca, col_log, gestor, is_desp,
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
        for m in ciclo.metricas.all():
            v = request.POST.get(f'metrica_{m.pk}')
            kpis[m.nome] = int(v) if v else 3
        if not ciclo.metricas.exists():
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
        for m in ciclo.metricas.all():
            v = request.POST.get(f'metrica_{m.pk}')
            if v:
                NotaMetrica.objects.create(avaliacao=aval, metrica=m, nota=int(v))

        # Backward compat: preencher campos antigos se as métricas forem as padrão
        if not ciclo.metricas.exists():
            aval.pontualidade = kpis.get('pontualidade', 3)
            aval.produtividade = kpis.get('produtividade', 3)
            aval.qualidade_trabalho = kpis.get('qualidade_trabalho', 3)
            aval.trabalho_equipa = kpis.get('trabalho_equipa', 3)
            aval.iniciativa = kpis.get('iniciativa', 3)
            aval.save(update_fields=['pontualidade', 'produtividade', 'qualidade_trabalho', 'trabalho_equipa', 'iniciativa'])
        return redirect('rh_ciclo_detalhe', pk=ciclo.pk)

    cols_avaliaveis = escopo_colaboradores_ativos(
        banca, col_log, gestor, is_desp,
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
    if not is_desp:
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
