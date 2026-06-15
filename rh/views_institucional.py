"""
Views do RH Institucional — replicam a mesma lógica do RH dos Despachantes
mas para os colaboradores institucionais (equipa da instituição).
Acesso: Administrador ou utilizadores com permissões RH Institucionais.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Count, Prefetch, Q
from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
import bcrypt

from utils.format_kz import parse_kz
from utils.email_utils import gerar_senha_aleatoria, enviar_senha_colaborador
from utils.email_utils import enviar_resultado_candidatura, enviar_convocatoria_entrevista
from utils.validators import email_ja_existe
from .acesso import obter_acesso_inst, obter_acesso_inst_modulo
from users.models import (
    ColaboradorInstitucional, PresencaInstitucional, FeriasInstitucional,
    CicloAvaliacaoInstitucional, AvaliacaoInstitucional,
    ProcessamentoSalarialInstitucional, ReciboSalarialInstitucional,
    SubsidioInstitucional, SubsidioReciboInstitucional,
    VagaInstitucional, CandidaturaInstitucional, EntrevistaInstitucional,
    PlanoIntegracaoInstitucional, TarefaIntegracaoInstitucional,
    MetricaAvaliacaoInstitucional, NotaMetricaInstitucional,
)

MESES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
         'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']


# ─── Helpers ─────────────────────────────────────────────────────────────

def _requer_inst(fn):
    def wrapper(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            return redirect('login')
        if not obter_acesso_inst(request):
            messages.error(request, 'Acesso restrito ao RH Institucional.')
            return redirect('dashboard')
        return fn(request, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def _requer_inst_modulo(*modulos):
    def decorator(fn):
        def wrapper(request, *args, **kwargs):
            if not request.session.get('usuario_id'):
                return redirect('login')
            acesso = False
            for m in modulos:
                if obter_acesso_inst_modulo(request, m):
                    acesso = True
                    break
            if not acesso:
                messages.error(request, 'Não tem permissão para aceder a esta página.')
                return redirect('rh_inst_dashboard')
            return fn(request, *args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


def _ctx_inst(request, sub='', extra=None):
    u = request.session['usuario']
    from users.permissoes import get_usuario_permissoes
    user_permissoes = get_usuario_permissoes(request)
    ctx = {
        'usuario': u, 'nome': u['nome'], 'papel': u['papel'],
        'active_menu': 'RH_INST', 'active_sub': sub,
        'user_permissoes': user_permissoes,
    }
    if extra:
        ctx.update(extra)
    return ctx


def _dec(val, default=Decimal('0')):
    try:
        parsed = parse_kz(val)
        return Decimal(str(parsed)) if parsed else default
    except (InvalidOperation, ValueError, TypeError):
        return default


def _calcular_irt(salario: Decimal) -> Decimal:
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


def _hash_password(senha):
    if not senha:
        return None
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(senha.encode('utf-8'), salt)
    return hashed.decode('utf-8').replace('$2b$', '$2y$')


def marcar_ferias_no_registo_inst(pedido):
    from datetime import timedelta
    data = pedido.data_inicio
    while data <= pedido.data_fim:
        if data.weekday() < 5:
            PresencaInstitucional.objects.update_or_create(
                colaborador=pedido.colaborador, data=data,
                defaults={
                    'tipo': 'Ferias', 'estado': 'Aprovado',
                    'hora_entrada': None, 'hora_saida': None,
                    'horas_extras': 0, 'justificacao': '',
                },
            )
        data += timedelta(days=1)


def _gerar_pdf_processamento_inst(processamento, request):
    from django.conf import settings
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, white, black
    import os

    recibos = processamento.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()
    pdf_dir = os.path.join(settings.MEDIA_ROOT, 'processamentos_salariais_institucionais')
    os.makedirs(pdf_dir, exist_ok=True)
    filename = f"processamento_inst_{processamento.mes:02d}_{processamento.ano}_{processamento.pk}.pdf"
    filepath = os.path.join(pdf_dir, filename)

    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    margin_left, margin_right = 2 * cm, 2 * cm
    margin_top, margin_bottom = 2 * cm, 2 * cm

    # Cabeçalho CDOA
    cor_cdoa = HexColor('#1a3a5c')
    cor_cdoa_gold = HexColor('#c9a84c')
    estado_display = processamento.get_estado_display()
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

    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(cor_cdoa)
    title = "PROCESSAMENTO SALARIAL INSTITUCIONAL"
    tw = c.stringWidth(title, "Helvetica-Bold", 18)
    c.drawCentredString(width / 2, y_position, title)
    y_position -= 25
    c.setFont("Helvetica", 10)
    c.setFillColor(black)
    periodo = f"Período: {processamento.mes:02d}/{processamento.ano} | Estado: {estado_display}"
    tw = c.stringWidth(periodo, "Helvetica", 10)
    c.drawCentredString(width / 2, y_position, periodo)
    y_position -= 25

    c.line(margin_left, y_position, width - margin_right, y_position)
    y_position -= 25

    headers = ["Colaborador", "Salário Base", "Subsídios", "Bruto", "Faltas", "IRT", "INSS 3%", "Líquido"]
    col_widths = [6, 2, 2, 2, 1.5, 1.5, 1.5, 2]
    total_width = width - margin_left - margin_right

    c.setFont("Helvetica-Bold", 8)
    x = margin_left
    for i, h in enumerate(headers):
        cw = total_width * col_widths[i] / sum(col_widths)
        c.drawString(x, y_position, h)
        x += cw
    y_position -= 18
    c.setFont("Helvetica", 8)

    for recibo in recibos:
        if y_position < margin_bottom + 80:
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
            x = margin_left
            for i, h in enumerate(headers):
                cw = total_width * col_widths[i] / sum(col_widths)
                c.drawString(x, y_position, h)
                x += cw
            y_position -= 18
            c.setFont("Helvetica", 8)
        total_subs = sum(v.valor for v in recibo.subsidios_vinculados.all())
        dados = [
            recibo.colaborador.nome[:30],
            f"{recibo.salario_base:,.2f}",
            f"{total_subs:,.2f}",
            f"{recibo.bruto:,.2f}",
            f"{recibo.outros_descontos:,.2f}",
            f"{recibo.irt:,.2f}",
            f"{recibo.inss_trabalhador:,.2f}",
            f"{recibo.liquido:,.2f}",
        ]
        x = margin_left
        for i, d in enumerate(dados):
            cw = total_width * col_widths[i] / sum(col_widths)
            if i == 0:
                c.drawString(x, y_position, d)
            else:
                c.drawRightString(x + cw, y_position, d)
            x += cw
        y_position -= 15

    y_position -= 10
    c.line(margin_left, y_position, width - margin_right, y_position)
    y_position -= 15
    total_liquido = sum(r.liquido for r in recibos)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y_position, "Total Líquido Pago:")
    c.drawRightString(width - margin_right, y_position, f"{total_liquido:,.2f} KZ")
    y_position -= 60
    c.setFont("Helvetica", 8)
    footer = "Documento gerado automaticamente pelo Sistema de Gestão de Recursos Humanos"
    tw = c.stringWidth(footer, "Helvetica", 8)
    c.drawString((width - tw) / 2, y_position, footer)
    c.save()
    processamento.pdf_gerado = True
    processamento.save()


# ══════════════════════════════════════════════════════════════════════════
# DASHBOARD INSTITUCIONAL
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
def inst_dashboard_view(request):
    hoje = timezone.now().date()
    stats = {
        'total_colaboradores': ColaboradorInstitucional.objects.count(),
        'colaboradores_activos': ColaboradorInstitucional.objects.filter(estado='Ativo').count(),
        'presencas_hoje': PresencaInstitucional.objects.filter(data=hoje).count(),
        'presencas_pendentes': PresencaInstitucional.objects.filter(estado='Pendente').count(),
        'ferias_pendentes': FeriasInstitucional.objects.filter(estado='Pendente').count(),
        'vagas_abertas': VagaInstitucional.objects.filter(estado='Aberta').count(),
        'candidaturas_recentes': CandidaturaInstitucional.objects.filter(criado_em__date=hoje).count(),
        'ultimo_processamento': ProcessamentoSalarialInstitucional.objects.order_by('-ano', '-mes').first(),
        'ciclos_activos': CicloAvaliacaoInstitucional.objects.filter(estado__in=['Aberto', 'Em Curso']).count(),
        'colaboradores_recentes': ColaboradorInstitucional.objects.order_by('-criado_em')[:5],
    }
    return render(request, 'rh/institucional/dashboard.html',
                  _ctx_inst(request, 'dashboard_inst', {'stats': stats}))


# ══════════════════════════════════════════════════════════════════════════
# SUBSÍDIOS
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('subsidios')
def inst_subsidios_view(request):
    subsidios = SubsidioInstitucional.objects.all().order_by('codigo')
    paginator = Paginator(subsidios, 8)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'rh/institucional/subsidios_lista.html',
                  _ctx_inst(request, 'subsidios_inst', {
                      'subsidios': page, 'page_obj': page,
                  }))


@_requer_inst
@_requer_inst_modulo('subsidios')
def inst_subsidio_novo_view(request):
    def _render(extra=None):
        return render(request, 'rh/institucional/subsidio_form.html',
                      _ctx_inst(request, 'subsidios_inst', {
                          'subsidio': None, 'form': {},
                          'tipos_calculo': SubsidioInstitucional.TIPOS_CALCULO,
                          'colaboradores': ColaboradorInstitucional.objects.filter(estado='Ativo').order_by('nome'),
                          **(extra or {}),
                      }))

    if request.method == 'POST':
        apenas_especificos = request.POST.get('apenas_especificos') == 'on'
        dados = {
            'nome': request.POST.get('nome', '').strip(),
            'codigo': request.POST.get('codigo', '').strip().upper(),
            'tipo_calculo': request.POST.get('tipo_calculo', 'FIXO'),
            'valor_padrao': _dec(request.POST.get('valor_padrao', '0')),
            'percentual': _dec(request.POST.get('percentual')) if request.POST.get('percentual') else None,
            'ativo': request.POST.get('ativo') == 'on',
            'obrigatorio': request.POST.get('obrigatorio') == 'on',
            'apenas_especificos': apenas_especificos,
            'descricao': request.POST.get('descricao', '').strip(),
        }
        if not dados['nome']:
            return _render({'erro': 'Nome do subsídio é obrigatório.'})
        if not dados['codigo']:
            return _render({'erro': 'Código do subsídio é obrigatório.'})
        if dados['tipo_calculo'] == 'PERCENTUAL' and not dados['percentual']:
            return _render({'erro': 'Percentual é obrigatório para tipo Percentual.'})
        if apenas_especificos and not request.POST.getlist('colaboradores_ids'):
            return _render({'erro': 'Selecione pelo menos um colaborador.'})
        if dados['obrigatorio']:
            dados['apenas_especificos'] = False
        if SubsidioInstitucional.objects.filter(codigo=dados['codigo']).exists():
            return _render({'erro': 'Já existe um subsídio com este código.'})

        subsidio = SubsidioInstitucional.objects.create(**dados)
        if dados['apenas_especificos']:
            ids = request.POST.getlist('colaboradores_ids')
            subsidio.colaboradores_especificos.set(
                ColaboradorInstitucional.objects.filter(pk__in=ids)
            )
        return redirect('rh_inst_subsidios')

    return _render()


@_requer_inst
@_requer_inst_modulo('subsidios')
def inst_subsidio_editar_view(request, pk):
    subsidio = get_object_or_404(SubsidioInstitucional, pk=pk)

    def _render(extra=None):
        form_data = {
            'nome': subsidio.nome, 'codigo': subsidio.codigo,
            'tipo_calculo': subsidio.tipo_calculo,
            'valor_padrao': subsidio.valor_padrao, 'percentual': subsidio.percentual,
            'ativo': subsidio.ativo, 'obrigatorio': subsidio.obrigatorio,
            'apenas_especificos': subsidio.apenas_especificos,
            'descricao': subsidio.descricao,
        }
        return render(request, 'rh/institucional/subsidio_form.html',
                      _ctx_inst(request, 'subsidios_inst', {
                          'subsidio': subsidio, 'form': form_data,
                          'tipos_calculo': SubsidioInstitucional.TIPOS_CALCULO,
                          'colaboradores': ColaboradorInstitucional.objects.filter(estado='Ativo').order_by('nome'),
                          'colaboradores_selecionados': list(subsidio.colaboradores_especificos.values_list('pk', flat=True)),
                          **(extra or {}),
                      }))

    if request.method == 'POST':
        apenas_especificos = request.POST.get('apenas_especificos') == 'on'
        dados = {
            'nome': request.POST.get('nome', '').strip(),
            'codigo': request.POST.get('codigo', '').strip().upper(),
            'tipo_calculo': request.POST.get('tipo_calculo', 'FIXO'),
            'valor_padrao': _dec(request.POST.get('valor_padrao', '0')),
            'percentual': _dec(request.POST.get('percentual')) if request.POST.get('percentual') else None,
            'ativo': request.POST.get('ativo') == 'on',
            'obrigatorio': request.POST.get('obrigatorio') == 'on',
            'apenas_especificos': apenas_especificos,
            'descricao': request.POST.get('descricao', '').strip(),
        }
        if not dados['nome']:
            return _render({'erro': 'Nome do subsídio é obrigatório.'})
        if not dados['codigo']:
            return _render({'erro': 'Código do subsídio é obrigatório.'})
        if dados['tipo_calculo'] == 'PERCENTUAL' and not dados['percentual']:
            return _render({'erro': 'Percentual é obrigatório para tipo Percentual.'})
        if apenas_especificos and not request.POST.getlist('colaboradores_ids'):
            return _render({'erro': 'Selecione pelo menos um colaborador.'})
        if dados['obrigatorio']:
            dados['apenas_especificos'] = False
        if SubsidioInstitucional.objects.filter(codigo=dados['codigo']).exclude(pk=pk).exists():
            return _render({'erro': 'Já existe um subsídio com este código.'})

        for campo, valor in dados.items():
            setattr(subsidio, campo, valor)
        subsidio.save()
        if subsidio.apenas_especificos:
            ids = request.POST.getlist('colaboradores_ids')
            subsidio.colaboradores_especificos.set(ColaboradorInstitucional.objects.filter(pk__in=ids))
        else:
            subsidio.colaboradores_especificos.clear()
        return redirect('rh_inst_subsidios')

    return _render()


@_requer_inst
@_requer_inst_modulo('subsidios')
def inst_subsidio_apagar_view(request, pk):
    subsidio = get_object_or_404(SubsidioInstitucional, pk=pk)
    if request.method == 'POST':
        if subsidio.subsidioreciboinstitucional_set.exists():
            return render(request, 'rh/institucional/subsidio_erro.html',
                          _ctx_inst(request, 'subsidios_inst', {
                              'subsidio': subsidio,
                              'erro': 'Subsídio está vinculado a recibos salariais e não pode ser removido.',
                          }))
        subsidio.delete()
        messages.success(request, f'Subsídio "{subsidio.nome}" removido.')
        return redirect('rh_inst_subsidios')
    return render(request, 'rh/institucional/subsidio_apagar.html',
                  _ctx_inst(request, 'subsidios_inst', {'subsidio': subsidio}))


# ══════════════════════════════════════════════════════════════════════════
# PROCESSAMENTO SALARIAL
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salarios_view(request):
    processamentos = ProcessamentoSalarialInstitucional.objects.annotate(
        total_recibos=Count('recibos'),
    ).prefetch_related('recibos').order_by('-ano', '-mes')

    paginator = Paginator(processamentos, 8)
    pagina = paginator.get_page(request.GET.get('pagina', 1))

    return render(request, 'rh/institucional/salarios_lista.html',
                  _ctx_inst(request, 'salarios_inst', {
                      'processamentos': pagina, 'page_obj': pagina,
                      'total': processamentos.count(),
                  }))


@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salario_novo_view(request):
    if request.method == 'POST':
        mes = int(request.POST.get('mes') or 1)
        ano = int(request.POST.get('ano') or timezone.now().year)
        proc, criado = ProcessamentoSalarialInstitucional.objects.get_or_create(
            mes=mes, ano=ano, defaults={'estado': 'Rascunho'}
        )
        if not criado:
            return redirect('rh_inst_salario_detalhe', pk=proc.pk)

        subsidios_inst = list(SubsidioInstitucional.objects.filter(ativo=True))
        subsidio_colab_ids = {}
        for s in subsidios_inst:
            if s.apenas_especificos:
                subsidio_colab_ids[s.pk] = set(s.colaboradores_especificos.values_list('id', flat=True))

        colaboradores_ids = request.POST.getlist('colaboradores')
        colaboradores_qs = ColaboradorInstitucional.objects.filter(estado='Ativo')
        if colaboradores_ids:
            colaboradores_qs = colaboradores_qs.filter(pk__in=colaboradores_ids)
        for col in colaboradores_qs:
            salario = col.salario_base or Decimal('0')
            faltas = PresencaInstitucional.objects.filter(
                colaborador=col, data__month=mes, data__year=ano,
                tipo__in=['Falta', 'Falta_Justificada'], estado='Aprovado',
            ).count()
            dias_uteis = Decimal('22')
            desconto_faltas = (salario / dias_uteis * faltas).quantize(Decimal('0.01')) if faltas > 0 else Decimal('0')
            salario_apos_faltas = max(salario - desconto_faltas, Decimal('0'))
            irt = _calcular_irt(salario_apos_faltas)
            inss_trab = (salario_apos_faltas * Decimal('0.03')).quantize(Decimal('0.01'))
            inss_ent = (salario_apos_faltas * Decimal('0.08')).quantize(Decimal('0.01'))

            subsidios_aplicaveis = []
            for subsidio in subsidios_inst:
                if subsidio.apenas_especificos:
                    if col.id in subsidio_colab_ids.get(subsidio.pk, set()):
                        subsidios_aplicaveis.append(subsidio)
                else:
                    subsidios_aplicaveis.append(subsidio)

            total_subsidios = Decimal('0')
            for subsidio in subsidios_aplicaveis:
                if subsidio.tipo_calculo == 'PERCENTUAL':
                    if subsidio.percentual and salario:
                        total_subsidios += (salario * subsidio.percentual) / 100
                    else:
                        total_subsidios += subsidio.valor_padrao
                elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                    total_subsidios += subsidio.valor_padrao * 22
                elif subsidio.tipo_calculo == 'DEPENDENTES':
                    total_subsidios += subsidio.valor_padrao * 1
                else:
                    total_subsidios += subsidio.valor_padrao

            recibo, recibo_criado = ReciboSalarialInstitucional.objects.get_or_create(
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

            if recibo_criado:
                for subsidio in subsidios_aplicaveis:
                    if subsidio.tipo_calculo == 'PERCENTUAL':
                        v = (salario * subsidio.percentual) / 100 if subsidio.percentual and salario else subsidio.valor_padrao
                    elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                        v = subsidio.valor_padrao * 22
                    elif subsidio.tipo_calculo == 'DEPENDENTES':
                        v = subsidio.valor_padrao * 1
                    else:
                        v = subsidio.valor_padrao
                    SubsidioReciboInstitucional.objects.get_or_create(
                        recibo=recibo, subsidio=subsidio,
                        defaults={'valor': v, 'valor_padrao': subsidio.valor_padrao},
                    )

        if proc.total_liquido == 0:
            proc.delete()
            hoje = timezone.now().date()
            cols = ColaboradorInstitucional.objects.filter(estado='Ativo')
            anos = list(range(2023, hoje.year + 2))
            return render(request, 'rh/institucional/salario_novo.html',
                          _ctx_inst(request, 'salarios_inst', {
                              'colaboradores': cols, 'meses': list(enumerate(MESES, 1)),
                              'anos': anos, 'ano_atual': hoje.year,
                              'erro': 'Total líquido é 0,00 KZ. Verifique salários base e subsídios.',
                          }))
        return redirect('rh_inst_salario_detalhe', pk=proc.pk)

    hoje = timezone.now().date()
    cols = ColaboradorInstitucional.objects.filter(estado='Ativo')
    anos = list(range(2023, hoje.year + 2))
    return render(request, 'rh/institucional/salario_novo.html',
                  _ctx_inst(request, 'salarios_inst', {
                      'colaboradores': cols, 'meses': list(enumerate(MESES, 1)),
                      'anos': anos, 'ano_atual': hoje.year,
                  }))


@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salario_detalhe_view(request, pk):
    proc = get_object_or_404(ProcessamentoSalarialInstitucional, pk=pk)
    recibos = proc.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()

    if request.method == 'POST':
        if proc.estado == 'Pago':
            messages.error(request, 'Processamento Pago não pode ser alterado.')
            return redirect('rh_inst_salario_detalhe', pk=proc.pk)

        action = request.POST.get('accao', '')
        if action == 'salvar':
            subsidios_ativos = list(SubsidioInstitucional.objects.filter(ativo=True))
            for r in recibos:
                p = f'rec_{r.pk}_'
                total_subs = Decimal('0')
                subsidios_aplicaveis = []
                for subsidio in subsidios_ativos:
                    if subsidio.apenas_especificos:
                        if subsidio.colaboradores_especificos.filter(id=r.colaborador.id).exists():
                            subsidios_aplicaveis.append(subsidio)
                    else:
                        subsidios_aplicaveis.append(subsidio)

                for subsidio in subsidios_aplicaveis:
                    if subsidio.obrigatorio:
                        if subsidio.tipo_calculo == 'PERCENTUAL':
                            v = (r.salario_base * subsidio.percentual) / 100 if subsidio.percentual and r.salario_base else subsidio.valor_padrao
                        elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                            v = subsidio.valor_padrao * 22
                        elif subsidio.tipo_calculo == 'DEPENDENTES':
                            v = subsidio.valor_padrao * 1
                        else:
                            v = subsidio.valor_padrao
                    else:
                        v = _dec(request.POST.get(f'{p}subsidio_{subsidio.pk}', '0'))

                    vinculo, _ = SubsidioReciboInstitucional.objects.get_or_create(
                        recibo=r, subsidio=subsidio,
                        defaults={'valor': v, 'valor_padrao': subsidio.valor_padrao},
                    )
                    if not _:
                        vinculo.valor = v
                        vinculo.save()
                    total_subs += v

                SubsidioReciboInstitucional.objects.filter(recibo=r).exclude(
                    subsidio_id__in=[s.pk for s in subsidios_aplicaveis]
                ).delete()
                r.outros_subsidios = total_subs
                r.subsidio_alimentacao = Decimal('0')
                r.subsidio_transporte = Decimal('0')
                base_impostos = r.base_calculo_impostos
                r.irt = _calcular_irt(base_impostos)
                r.inss_trabalhador = (base_impostos * Decimal('0.03')).quantize(Decimal('0.01'))
                r.inss_entidade = (base_impostos * Decimal('0.08')).quantize(Decimal('0.01'))
                r.save()
            messages.success(request, 'Alterações guardadas.')

        elif action == 'processar':
            if proc.total_liquido == 0:
                messages.error(request, 'Total líquido é 0,00 KZ. Verifique os dados.')
                return redirect('rh_inst_salario_detalhe', pk=proc.pk)
            proc.estado = 'Processado'
            proc.processado_em = timezone.now()
            proc.save()
            messages.success(request, f'Processamento {proc.mes:02d}/{proc.ano} processado.')

        elif action == 'pagar':
            if proc.total_liquido == 0:
                messages.error(request, 'Total líquido é 0,00 KZ.')
                return redirect('rh_inst_salario_detalhe', pk=proc.pk)
            proc.estado = 'Pago'
            proc.save()
            _gerar_pdf_processamento_inst(proc, request)
            messages.success(request, f'Processamento {proc.mes:02d}/{proc.ano} pago.')

        elif action == 'reabrir':
            if proc.estado == 'Processado':
                proc.estado = 'Rascunho'
                proc.processado_em = None
                proc.save()
                messages.success(request, 'Processamento reaberto.')
            else:
                messages.error(request, 'Apenas processamentos "Processado" podem ser reabertos.')
        return redirect('rh_inst_salario_detalhe', pk=proc.pk)

    subsidios_ativos = SubsidioInstitucional.objects.filter(ativo=True)
    tem_faltantes = False
    for r in recibos:
        for subsidio in subsidios_ativos:
            if not subsidio.obrigatorio:
                continue
            if SubsidioReciboInstitucional.objects.filter(recibo=r, subsidio=subsidio).exists():
                continue
            tem_faltantes = True
            if subsidio.tipo_calculo == 'PERCENTUAL':
                v = (r.salario_base * subsidio.percentual) / 100 if subsidio.percentual and r.salario_base else subsidio.valor_padrao
            elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                v = subsidio.valor_padrao * 22
            elif subsidio.tipo_calculo == 'DEPENDENTES':
                v = subsidio.valor_padrao * 1
            else:
                v = subsidio.valor_padrao
            SubsidioReciboInstitucional.objects.get_or_create(
                recibo=r, subsidio=subsidio,
                defaults={'valor': v, 'valor_padrao': subsidio.valor_padrao},
            )
    if tem_faltantes:
        recibos = proc.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()

    return render(request, 'rh/institucional/salario_detalhe.html',
                  _ctx_inst(request, 'salarios_inst', {
                      'proc': proc, 'recibos': recibos, 'meses': MESES,
                      'subsidios_ativos': subsidios_ativos,
                  }))


@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salario_apagar_view(request, pk):
    proc = get_object_or_404(ProcessamentoSalarialInstitucional, pk=pk)
    if proc.estado == 'Pago':
        messages.error(request, 'Processamentos Pago são permanentes.')
        return redirect('rh_inst_salarios')
    if request.method == 'POST':
        label = f'{proc.mes:02d}/{proc.ano}'
        proc.delete()
        messages.success(request, f'Processamento {label} apagado.')
        return redirect('rh_inst_salarios')
    return render(request, 'rh/institucional/salario_apagar.html',
                  _ctx_inst(request, 'salarios_inst', {'proc': proc}))


@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salario_download_view(request, pk):
    proc = get_object_or_404(ProcessamentoSalarialInstitucional, pk=pk)
    if proc.estado != 'Pago':
        return render(request, 'rh/institucional/salario_erro_download.html',
                      _ctx_inst(request, 'salarios_inst', {
                          'proc': proc,
                          'erro': 'PDF disponível apenas para processamentos "Pago".',
                      }))
    if not proc.pdf_gerado:
        _gerar_pdf_processamento_inst(proc, request)

    from django.conf import settings
    import os
    pdf_dir = os.path.join(settings.MEDIA_ROOT, 'processamentos_salariais_institucionais')
    pdf_filename = f"processamento_inst_{proc.mes:02d}_{proc.ano}_{proc.pk}.pdf"
    pdf_filepath = os.path.join(pdf_dir, pdf_filename)
    if os.path.exists(pdf_filepath):
        with open(pdf_filepath, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="comprovante_pagamento_{proc.mes:02d}_{proc.ano}.pdf"'
            return response
    return render(request, 'rh/institucional/salario_erro_download.html',
                  _ctx_inst(request, 'salarios_inst', {
                      'proc': proc, 'erro': 'PDF não encontrado.',
                  }))


# ══════════════════════════════════════════════════════════════════════════
# RECRUTAMENTO
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_vagas_view(request):
    estado_filter = request.GET.get('estado', '')
    search_query = request.GET.get('search', '')
    vagas_qs = VagaInstitucional.objects.all()
    if estado_filter:
        vagas_qs = vagas_qs.filter(estado=estado_filter)
    if search_query:
        vagas_qs = vagas_qs.filter(
            Q(titulo__icontains=search_query) | Q(departamento__icontains=search_query)
        )
    vagas = vagas_qs.annotate(num_candidatos=Count('candidaturas')).order_by('-criado_em')
    paginator = Paginator(vagas, 8)
    page_obj = paginator.get_page(request.GET.get('page'))
    from django.utils import timezone
    stats = vagas_qs.aggregate(
        total_vagas=Count('id'),
        vagas_abertas=Count('id', filter=Q(estado='Aberta')),
        vagas_em_analise=Count('id', filter=Q(estado='Em Análise')),
        vagas_encerradas=Count('id', filter=Q(estado='Encerrada')),
        total_candidaturas=Count('candidaturas'),
    )
    stats['candidaturas_hoje'] = CandidaturaInstitucional.objects.filter(
        criado_em__date=timezone.now().date()
    ).count()
    from django.conf import settings
    return render(request, 'rh/institucional/recrutamento_vagas.html',
                  _ctx_inst(request, 'recrutamento_inst', {
                      'vagas': page_obj, 'stats': stats, 'page_obj': page_obj,
                      'estado_filter': estado_filter, 'search_query': search_query,
                      'site_url': settings.SITE_URL.rstrip('/'),
                  }))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_vaga_nova_view(request):
    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        if not titulo:
            return render(request, 'rh/institucional/recrutamento_vaga_form.html',
                          _ctx_inst(request, 'recrutamento_inst', {
                              'vaga': None, 'erro': 'O título é obrigatório.',
                          }))
        try:
            VagaInstitucional.objects.create(
                titulo=titulo,
                departamento=request.POST.get('departamento', '').strip(),
                descricao=request.POST.get('descricao', '').strip(),
                requisitos=request.POST.get('requisitos', '').strip(),
                salario_min=_dec(request.POST.get('salario_min')) or None,
                salario_max=_dec(request.POST.get('salario_max')) or None,
                vagas_numero=int(request.POST.get('vagas_numero') or 1),
                data_encerramento=request.POST.get('data_encerramento') or None,
            )
            return redirect('rh_inst_vagas')
        except ValidationError as e:
            messages.error(request, str(e))
    return render(request, 'rh/institucional/recrutamento_vaga_form.html',
                  _ctx_inst(request, 'recrutamento_inst', {'vaga': None}))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_vaga_editar_view(request, pk):
    vaga = get_object_or_404(VagaInstitucional, pk=pk)
    if request.method == 'POST':
        try:
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
            return redirect('rh_inst_vagas')
        except ValidationError as e:
            messages.error(request, str(e))
    return render(request, 'rh/institucional/recrutamento_vaga_form.html',
                  _ctx_inst(request, 'recrutamento_inst', {'vaga': vaga}))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_vaga_eliminar_view(request, pk):
    vaga = get_object_or_404(VagaInstitucional, pk=pk)
    if request.method == 'POST':
        vaga.delete()
        messages.success(request, f'Vaga "{vaga.titulo}" eliminada.')
        return redirect('rh_inst_vagas')
    return redirect('rh_inst_vagas')


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_candidaturas_view(request, vaga_pk):
    vaga = get_object_or_404(VagaInstitucional, pk=vaga_pk)
    candidaturas_qs = vaga.candidaturas.prefetch_related(
        'entrevistas',
        Prefetch('plano_integracao', queryset=PlanoIntegracaoInstitucional.objects.only('id', 'estado'))
    ).order_by('-criado_em')

    MAPA_ETAPA = {
        'Recebida': 'candidaturas', 'Em Análise': 'candidaturas',
        'Entrevista': 'entrevistas', 'Aprovado': 'integracao', 'Rejeitado': 'candidaturas',
    }
    candidaturas = []
    for c in candidaturas_qs:
        c.etapa_key = MAPA_ETAPA.get(c.estado, 'candidaturas')
        candidaturas.append(c)

    paginator = Paginator(candidaturas, 8)
    page_obj = paginator.get_page(request.GET.get('page'))
    etapas = [
        ('candidaturas', 'Candidaturas', 'gray', 'inbox'),
        ('entrevistas', 'Entrevistas', 'blue', 'event'),
        ('integracao', 'Integração', 'green', 'person_check'),
    ]
    return render(request, 'rh/institucional/recrutamento_candidaturas.html',
                  _ctx_inst(request, 'recrutamento_inst', {
                      'vaga': vaga, 'candidaturas': page_obj,
                      'etapas': etapas, 'page_obj': page_obj,
                  }))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_candidatura_detalhe_view(request, pk):
    cand = get_object_or_404(CandidaturaInstitucional, pk=pk)
    entrevistas = cand.entrevistas.all()
    plano = getattr(cand, 'plano_integracao', None)
    fluxo_etapas = [
        (1, 'Candidatura', ['Recebida', 'Em Análise']),
        (2, 'Entrevista', ['Entrevista']),
        (3, 'Aprovação', ['Aprovado', 'Rejeitado']),
        (4, 'Integração', []),
    ]
    etapa_map = {'Recebida': 1, 'Em Análise': 1, 'Entrevista': 2, 'Aprovado': 3, 'Rejeitado': 3}
    fluxo_atual = etapa_map.get(cand.estado, 1)
    if plano:
        fluxo_atual = 4
    return render(request, 'rh/institucional/recrutamento_candidatura_detalhe.html',
                  _ctx_inst(request, 'recrutamento_inst', {
                      'cand': cand, 'entrevistas': entrevistas, 'plano': plano,
                      'fluxo_etapas': fluxo_etapas, 'fluxo_etapa_atual': fluxo_atual,
                  }))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_candidatura_estado_view(request, pk):
    cand = get_object_or_404(CandidaturaInstitucional, pk=pk)
    if request.method == 'POST':
        estado_anterior = cand.estado
        cand.estado = request.POST.get('estado', cand.estado)
        cand.notas = request.POST.get('notas', '').strip()
        cand.save()
        if cand.estado in ('Aprovado', 'Rejeitado') and cand.estado != estado_anterior:
            sucesso, msg = enviar_resultado_candidatura(cand)
            if sucesso:
                messages.success(request, f'Email enviado para {cand.email}.')
            else:
                messages.warning(request, f'Estado atualizado, mas falhou envio de email.')
        else:
            messages.success(request, 'Estado atualizado.')
    return redirect('rh_inst_candidaturas', vaga_pk=cand.vaga.pk)


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_entrevista_nova_view(request, candidatura_pk):
    cand = get_object_or_404(CandidaturaInstitucional, pk=candidatura_pk)
    if request.method == 'POST':
        EntrevistaInstitucional.objects.create(
            candidatura=cand,
            data_hora=request.POST.get('data_hora'),
            tipo=request.POST.get('tipo', 'Presencial'),
            local_link=request.POST.get('local_link', '').strip(),
            entrevistador=request.POST.get('entrevistador', '').strip(),
            observacoes=request.POST.get('observacoes', '').strip(),
        )
        if cand.estado not in ('Aprovado', 'Rejeitado'):
            cand.estado = 'Entrevista'
            cand.save()
        entrevista = cand.entrevistas.order_by('-criado_em').first()
        if entrevista and cand.email:
            sucesso, msg = enviar_convocatoria_entrevista(entrevista)
            if sucesso:
                messages.success(request, f'Convocatória enviada para {cand.email}.')
            else:
                messages.warning(request, 'Entrevista agendada, mas falhou o envio de email.')
        else:
            messages.success(request, 'Entrevista agendada.')
        return redirect('rh_inst_candidatura_detalhe', pk=cand.pk)
    return render(request, 'rh/institucional/recrutamento_entrevista_form.html',
                  _ctx_inst(request, 'recrutamento_inst', {'cand': cand}))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_entrevista_resultado_view(request, pk):
    entrevista = get_object_or_404(EntrevistaInstitucional, pk=pk)
    if request.method == 'POST':
        entrevista.resultado = request.POST.get('resultado', 'Pendente')
        entrevista.nota = request.POST.get('nota') or None
        entrevista.observacoes = request.POST.get('observacoes', '').strip()
        entrevista.save()
        cand = entrevista.candidatura
        if entrevista.resultado == 'Aprovado':
            cand.estado = 'Aprovado'
            cand.save()
        elif entrevista.resultado == 'Reprovado':
            cand.estado = 'Rejeitado'
            cand.save()
        return redirect('rh_inst_candidatura_detalhe', pk=cand.pk)
    return redirect('rh_inst_candidatura_detalhe', pk=entrevista.candidatura.pk)


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_integracao_nova_view(request, candidatura_pk):
    cand = get_object_or_404(CandidaturaInstitucional, pk=candidatura_pk, estado='Aprovado')
    if hasattr(cand, 'plano_integracao'):
        return redirect('rh_inst_integracao_detalhe', pk=cand.plano_integracao.pk)

    if request.method == 'POST':
        plano = PlanoIntegracaoInstitucional.objects.create(
            candidatura=cand,
            data_inicio=request.POST.get('data_inicio'),
            data_fim_prevista=request.POST.get('data_fim_prevista') or None,
            responsavel=request.POST.get('responsavel', '').strip(),
            notas=request.POST.get('notas', '').strip(),
        )

        if request.POST.get('criar_colaborador') == '1':
            email_col = cand.email.strip() if cand.email else ''
            if email_col and email_ja_existe(email_col):
                messages.error(request, f'O email {email_col} já está registado.')
                return redirect('rh_inst_integracao_detalhe', pk=plano.pk)
            senha_gerada = None
            senha_hash = None
            if email_col:
                senha_gerada = gerar_senha_aleatoria()
                senha_hash = _hash_password(senha_gerada)
            col = ColaboradorInstitucional.objects.create(
                nome=cand.nome,
                email=email_col,
                telefone=cand.telefone,
                area_actuacao=request.POST.get('area_actuacao', 'Outro'),
                data_admissao=request.POST.get('data_inicio'),
                salario_base=_dec(request.POST.get('salario_base')) or None,
                estado='Ativo',
            )
            plano.colaborador = col
            plano.save()

            if email_col and senha_gerada:
                ok, msg = enviar_senha_colaborador(col, senha_gerada)
                if ok:
                    messages.success(request, f'Colaborador criado. Credenciais enviadas para {email_col}.')
                else:
                    messages.warning(request, f'Colaborador criado, mas falhou envio: {msg}')

        tarefas_padrao = [
            'Apresentação à equipa e instalações',
            'Entrega de equipamentos e acessos',
            'Formação inicial sobre processos internos',
            'Revisão de políticas e regulamentos',
            'Acompanhamento pelo responsável durante o período de integração',
        ]
        for t in tarefas_padrao:
            TarefaIntegracaoInstitucional.objects.create(
                plano=plano, titulo=t, prazo=request.POST.get('data_fim_prevista') or None,
            )
        return redirect('rh_inst_integracao_detalhe', pk=plano.pk)

    cargo_sugerido = cand.vaga.titulo
    departamento_sugerido = cand.vaga.departamento or ''
    responsavel_nome = request.session.get('usuario', {}).get('nome', '')
    return render(request, 'rh/institucional/recrutamento_integracao_form.html',
                  _ctx_inst(request, 'recrutamento_inst', {
                      'cand': cand,
                      'cargo_sugerido': cargo_sugerido,
                      'departamento_sugerido': departamento_sugerido,
                      'responsavel_nome': responsavel_nome,
                  }))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_integracao_detalhe_view(request, pk):
    plano = get_object_or_404(PlanoIntegracaoInstitucional, pk=pk)
    tarefas = plano.tarefas.all()
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'tarefa_toggle':
            tarefa = get_object_or_404(TarefaIntegracaoInstitucional, pk=request.POST.get('tarefa_pk'), plano=plano)
            tarefa.concluida = not tarefa.concluida
            tarefa.save()
        elif action == 'tarefa_nova':
            titulo = request.POST.get('titulo', '').strip()
            if titulo:
                TarefaIntegracaoInstitucional.objects.create(
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
        return redirect('rh_inst_integracao_detalhe', pk=plano.pk)
    return render(request, 'rh/institucional/recrutamento_integracao_detalhe.html',
                  _ctx_inst(request, 'recrutamento_inst', {'plano': plano, 'tarefas': tarefas}))


# ══════════════════════════════════════════════════════════════════════════
# CONTROLO DE PRESENÇAS
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('presencas')
def inst_presencas_view(request):
    hoje = timezone.now().date()
    mes = int(request.GET.get('mes') or hoje.month)
    ano = int(request.GET.get('ano') or hoje.year)
    from datetime import date
    primeiro_dia = date(ano, mes, 1)
    if mes == 12:
        ultimo_dia = date(ano, 12, 31)
    else:
        ultimo_dia = date(ano, mes + 1, 1) - timezone.timedelta(days=1)

    cols = ColaboradorInstitucional.objects.filter(estado='Ativo').only('id', 'nome', 'area_actuacao')
    registos = PresencaInstitucional.objects.filter(
        colaborador__in=cols, data__month=mes, data__year=ano,
    ).select_related('colaborador').order_by('-data')

    ferias_pendentes = FeriasInstitucional.objects.filter(
        colaborador__in=cols, estado='Pendente',
    ).select_related('colaborador')
    ferias_todas = FeriasInstitucional.objects.filter(
        colaborador__in=cols,
        data_inicio__lte=ultimo_dia, data_fim__gte=primeiro_dia,
    ).select_related('colaborador').order_by('-criado_em')

    paginator = Paginator(registos, 8)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'rh/institucional/presencas_lista.html',
                  _ctx_inst(request, 'presencas_inst', {
                    'colaboradores': cols, 'registos': page_obj,
                    'page_obj': page_obj, 'ferias_pendentes': ferias_pendentes,
                    'ferias_todas': ferias_todas,
                    'mes': mes, 'ano': ano, 'meses': list(enumerate(MESES, 1)), 'hoje': hoje,
                  }))


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_presenca_registar_view(request):
    if request.method == 'POST':
        col = get_object_or_404(ColaboradorInstitucional, pk=request.POST.get('colaborador'))
        try:
            data_str = request.POST.get('data')
            reg, _ = PresencaInstitucional.objects.get_or_create(colaborador=col, data=data_str)
            reg.tipo = request.POST.get('tipo', 'Entrada')
            reg.hora_entrada = request.POST.get('hora_entrada') or None
            reg.hora_saida = request.POST.get('hora_saida') or None
            reg.horas_extras = _dec(request.POST.get('horas_extras', '0'))
            reg.justificacao = request.POST.get('justificacao', '').strip()
            reg.estado = 'Pendente'
            reg.full_clean()
            reg.save()
            messages.success(request, 'Presença registada.')
        except ValidationError as e:
            messages.error(request, str(e))
        return redirect('rh_inst_presencas')
    cols = ColaboradorInstitucional.objects.filter(estado='Ativo')
    hoje = timezone.now().date()
    tipos_presenca = getattr(PresencaInstitucional, 'TIPOS', [])
    return render(request, 'rh/institucional/presenca_registar.html',
                  _ctx_inst(request, 'presencas_inst', {
                      'colaboradores': cols, 'tipos_presenca': tipos_presenca, 'hoje': hoje,
                  }))


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_presenca_aprovar_view(request, pk):
    reg = get_object_or_404(PresencaInstitucional, pk=pk)
    if request.method == 'POST':
        reg.estado = request.POST.get('estado', 'Aprovado')
        reg.save()
    return redirect('rh_inst_presencas')


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_presenca_apagar_view(request, pk):
    reg = get_object_or_404(PresencaInstitucional, pk=pk)
    if request.method == 'POST':
        reg.delete()
        messages.success(request, 'Registo removido.')
    return redirect('rh_inst_presencas')


@_requer_inst
@_requer_inst_modulo('presencas')
@_requer_inst
@_requer_inst_modulo('presencas')
def inst_ferias_pedir_view(request):
    if request.method == 'POST':
        col = get_object_or_404(ColaboradorInstitucional, pk=request.POST.get('colaborador'))
        try:
            FeriasInstitucional.objects.create(
                colaborador=col,
                data_inicio=request.POST.get('data_inicio'),
                data_fim=request.POST.get('data_fim'),
                motivo=request.POST.get('motivo', '').strip(),
            )
            messages.success(request, 'Pedido de férias submetido.')
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect('rh_inst_presencas')


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_ferias_aprovar_view(request, pk):
    pedido = get_object_or_404(FeriasInstitucional, pk=pk)
    if request.method == 'POST':
        try:
            pedido.estado = request.POST.get('estado', 'Aprovado')
            pedido.save()
            if pedido.estado == 'Aprovado':
                marcar_ferias_no_registo_inst(pedido)
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect('rh_inst_presencas')


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_ferias_apagar_view(request, pk):
    pedido = get_object_or_404(FeriasInstitucional, pk=pk)
    if request.method == 'POST':
        pedido.delete()
        messages.success(request, 'Pedido de férias removido.')
    return redirect('rh_inst_presencas')


# ══════════════════════════════════════════════════════════════════════════
# AVALIAÇÃO DE DESEMPENHO
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_avaliacoes_view(request):
    ciclos = CicloAvaliacaoInstitucional.objects.annotate(
        num_avaliacoes=Count('avaliacoes')
    ).all()
    paginator = Paginator(ciclos, 8)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'rh/institucional/avaliacoes_lista.html',
                  _ctx_inst(request, 'avaliacoes_inst', {
                      'ciclos': page_obj, 'page_obj': page_obj,
                  }))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_ciclo_novo_view(request):
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if nome:
            try:
                ciclo = CicloAvaliacaoInstitucional.objects.create(
                    nome=nome,
                    periodo_inicio=request.POST.get('periodo_inicio'),
                    periodo_fim=request.POST.get('periodo_fim'),
                )
                metricas_nomes = request.POST.getlist('metrica_nome[]')
                metricas_desc = request.POST.getlist('metrica_descricao[]')
                for i, mnome in enumerate(metricas_nomes):
                    mnome = mnome.strip()
                    if mnome:
                        MetricaAvaliacaoInstitucional.objects.create(
                            ciclo=ciclo, nome=mnome,
                            descricao=(metricas_desc[i] if i < len(metricas_desc) else '').strip(),
                            ordem=i,
                        )
                return redirect('rh_inst_avaliacoes')
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, 'Nome do ciclo é obrigatório.')
    return render(request, 'rh/institucional/avaliacao_ciclo_form.html',
                  _ctx_inst(request, 'avaliacoes_inst'))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_ciclo_detalhe_view(request, pk):
    ciclo = get_object_or_404(CicloAvaliacaoInstitucional, pk=pk)
    metricas = ciclo.metricas.all()
    avaliacoes = ciclo.avaliacoes.select_related('colaborador').prefetch_related('notas_metricas__metrica').all()
    for a in avaliacoes:
        a.notas_map = {nm.metrica_id: nm.nota for nm in a.notas_metricas.all()}
    avaliados = {a.colaborador_id for a in avaliacoes}
    pendentes = ColaboradorInstitucional.objects.filter(estado='Ativo').exclude(pk__in=avaliados)
    if not metricas:
        metricas = [
            {'nome': 'Pontualidade', 'chave': 'pontualidade'},
            {'nome': 'Produtividade', 'chave': 'produtividade'},
            {'nome': 'Qualidade do Trabalho', 'chave': 'qualidade_trabalho'},
            {'nome': 'Trabalho em Equipa', 'chave': 'trabalho_equipa'},
            {'nome': 'Iniciativa', 'chave': 'iniciativa'},
        ]
    return render(request, 'rh/institucional/avaliacao_ciclo_detalhe.html',
                  _ctx_inst(request, 'avaliacoes_inst', {
                      'ciclo': ciclo, 'avaliacoes': avaliacoes,
                      'metricas': metricas, 'cols_pendentes': pendentes,
                  }))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_avaliacao_form_view(request, ciclo_pk, col_pk=None):
    ciclo = get_object_or_404(CicloAvaliacaoInstitucional, pk=ciclo_pk)
    aval = col = None
    if col_pk:
        col = get_object_or_404(ColaboradorInstitucional, pk=col_pk)
        aval = AvaliacaoInstitucional.objects.filter(ciclo=ciclo, colaborador=col).first()

    if request.method == 'POST':
        col_id = col_pk or int(request.POST.get('colaborador', 0))
        col = get_object_or_404(ColaboradorInstitucional, pk=col_id)
        if not col_pk and AvaliacaoInstitucional.objects.filter(ciclo=ciclo, colaborador=col).exists():
            messages.error(request, f'{col.nome} já foi avaliado neste ciclo.')
            return redirect('rh_inst_ciclo_detalhe', pk=ciclo.pk)

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

        aval, created = AvaliacaoInstitucional.objects.update_or_create(
            ciclo=ciclo, colaborador=col,
            defaults={
                'nota_global': nota,
                'pontos_fortes': request.POST.get('pontos_fortes', '').strip(),
                'pontos_melhoria': request.POST.get('pontos_melhoria', '').strip(),
                'plano_desenvolvimento': request.POST.get('plano_desenvolvimento', '').strip(),
            }
        )
        if created:
            NotaMetricaInstitucional.objects.filter(avaliacao=aval).delete()
        for m in ciclo.metricas.all():
            v = request.POST.get(f'metrica_{m.pk}')
            if v:
                NotaMetricaInstitucional.objects.create(avaliacao=aval, metrica=m, nota=int(v))

        if not ciclo.metricas.exists():
            aval.pontualidade = kpis.get('pontualidade', 3)
            aval.produtividade = kpis.get('produtividade', 3)
            aval.qualidade_trabalho = kpis.get('qualidade_trabalho', 3)
            aval.trabalho_equipa = kpis.get('trabalho_equipa', 3)
            aval.iniciativa = kpis.get('iniciativa', 3)
            aval.save(update_fields=['pontualidade', 'produtividade', 'qualidade_trabalho', 'trabalho_equipa', 'iniciativa'])
        return redirect('rh_inst_ciclo_detalhe', pk=ciclo.pk)

    cols_avaliaveis = ColaboradorInstitucional.objects.filter(estado='Ativo')
    if not col_pk:
        cols_avaliaveis = cols_avaliaveis.exclude(
            pk__in=AvaliacaoInstitucional.objects.filter(ciclo=ciclo).values_list('colaborador', flat=True)
        )

    metricas = ciclo.metricas.all()
    kpis_list = []
    if metricas:
        for m in metricas:
            nota_obj = aval.notas_metricas.filter(metrica=m).first() if aval else None
            kpis_list.append((f'metrica_{m.pk}', m.nome, m.descricao, nota_obj.nota if nota_obj else 3))
    else:
        kpis_list = [
            ('pontualidade', 'Pontualidade', '', aval.pontualidade if aval else 3),
            ('produtividade', 'Produtividade', '', aval.produtividade if aval else 3),
            ('qualidade_trabalho', 'Qualidade do Trabalho', '', aval.qualidade_trabalho if aval else 3),
            ('trabalho_equipa', 'Trabalho em Equipa', '', aval.trabalho_equipa if aval else 3),
            ('iniciativa', 'Iniciativa', '', aval.iniciativa if aval else 3),
        ]

    return render(request, 'rh/institucional/avaliacao_form.html',
                  _ctx_inst(request, 'avaliacoes_inst', {
                      'ciclo': ciclo, 'aval': aval, 'col': col,
                      'colaboradores': cols_avaliaveis, 'kpis_list': kpis_list,
                  }))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_avaliacao_detalhe_view(request, ciclo_pk, col_pk):
    ciclo = get_object_or_404(CicloAvaliacaoInstitucional, pk=ciclo_pk)
    col = get_object_or_404(ColaboradorInstitucional, pk=col_pk)
    aval = get_object_or_404(AvaliacaoInstitucional, ciclo=ciclo, colaborador=col)

    metricas = ciclo.metricas.all()
    kpis_list = []
    if metricas:
        for m in metricas:
            nota_obj = aval.notas_metricas.filter(metrica=m).first()
            kpis_list.append((f'metrica_{m.pk}', m.nome, m.descricao, nota_obj.nota if nota_obj else 3, True))
    else:
        kpis_list = [
            ('pontualidade', 'Pontualidade', '', getattr(aval, 'pontualidade', 3), True),
            ('produtividade', 'Produtividade', '', getattr(aval, 'produtividade', 3), True),
            ('qualidade_trabalho', 'Qualidade do Trabalho', '', getattr(aval, 'qualidade_trabalho', 3), True),
            ('trabalho_equipa', 'Trabalho em Equipa', '', getattr(aval, 'trabalho_equipa', 3), True),
            ('iniciativa', 'Iniciativa', '', getattr(aval, 'iniciativa', 3), True),
        ]

    return render(request, 'rh/institucional/avaliacao_form.html',
                  _ctx_inst(request, 'avaliacoes_inst', {
                      'ciclo': ciclo, 'aval': aval, 'col': col,
                      'colaboradores': [], 'kpis_list': kpis_list, 'readonly': True,
                  }))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_avaliacao_apagar_view(request, ciclo_pk, col_pk):
    if request.method == 'POST':
        ciclo = get_object_or_404(CicloAvaliacaoInstitucional, pk=ciclo_pk)
        aval = get_object_or_404(AvaliacaoInstitucional, ciclo=ciclo, colaborador__pk=col_pk)
        nome = aval.colaborador.nome
        aval.delete()
        messages.success(request, f'Avaliação de {nome} removida.')
    return redirect('rh_inst_ciclo_detalhe', pk=ciclo_pk)


# ══════════════════════════════════════════════════════════════════════════
# PÁGINAS PÚBLICAS (candidaturas externas)
# ══════════════════════════════════════════════════════════════════════════

def inst_vaga_publica_view(request, link_uuid):
    vaga = get_object_or_404(VagaInstitucional, link_externo=link_uuid, estado__in=['Aberta', 'Em Análise'])
    return render(request, 'rh/institucional/public/vaga_detalhe.html', {
        'vaga': vaga,
    })


def inst_candidatura_externa_view(request, link_uuid):
    vaga = get_object_or_404(VagaInstitucional, link_externo=link_uuid, estado__in=['Aberta', 'Em Análise'])
    form_data = {}
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        form_data = {'nome': nome, 'email': email, 'telefone': telefone}
        if not nome or not email:
            return render(request, 'rh/institucional/public/candidatura_form.html', {
                'vaga': vaga, 'erro': 'Nome e email são obrigatórios.', 'form_data': form_data,
            })
        cv = request.FILES.get('curriculo')
        candidatura = CandidaturaInstitucional.objects.create(
            vaga=vaga, nome=nome, email=email, telefone=telefone, cv=cv,
        )
        return render(request, 'rh/institucional/public/candidatura_sucesso.html', {'vaga': vaga, 'candidatura': candidatura})
    return render(request, 'rh/institucional/public/candidatura_form.html', {'vaga': vaga, 'form_data': form_data})
