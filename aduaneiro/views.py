"""Views do módulo aduaneiro — DU (Declaração Única)."""
import io
import json
import uuid

from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from clientes.models import Cliente
from users.models import Usuario
from users.permissoes import _is_admin_ou_acesso_total, get_usuario_permissoes
from users.auth_decorators import sessao_expirada, requer_sessao_ativa
from utils.validators import email_ja_existe
from django.core.paginator import Paginator
from rh.models import Colaborador, Banca
from .models import DeclaracaoUnica
from .acesso import escopo_du
import logging
from decimal import Decimal
from utils.format_kz import fmt_kz

logger = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sessao_ok(request):
    if not request.session.get('usuario_id'):
        return False
    if sessao_expirada(request):
        request.session.flush()
        return False
    request.session['login_time'] = timezone.now().isoformat()
    request.session.modified = True
    return True


def _usuario_id(request):
    return request.session.get('usuario_id')


def _papel(request):
    return request.session.get('usuario', {}).get('papel', '')


def _ctx_base(request):
    u = request.session.get('usuario', {})
    return {'usuario': u, 'nome': u.get('nome', ''), 'papel': u.get('papel', '')}


def _tem_permissao_ou_papel(request, *perm_codigos):
    """True se o user tem papel de acesso ou uma das permissões (para colaboradores)."""
    papel = _papel(request)
    if papel in ('Administrador', 'Despachante Oficial'):
        return True
    if _is_admin_ou_acesso_total(request):
        return True
    permissoes = get_usuario_permissoes(request)
    return any(p in permissoes for p in perm_codigos)


def _banca_owner(request):
    """
    Se o utilizador actual é um colaborador, devolve o Usuario dono da banca
    (o despachante) a quem este colaborador pertence.
    Caso contrário, devolve o próprio Usuario logado.
    Retorna (usuario_obj, usuario_id).
    """
    uid = _usuario_id(request)
    if request.session.get('tipo_usuario') == 'colaborador':
        colaborador_id = request.session.get('colaborador_id')
        if colaborador_id:
            try:
                colab = Colaborador.objects.select_related('banca').get(id=colaborador_id)
                if colab.banca and colab.banca.usuario_id:
                    dono = Usuario.objects.get(id=colab.banca.usuario_id)
                    return dono, dono.id
            except (Colaborador.DoesNotExist, Usuario.DoesNotExist):
                pass
        # Colaborador sem banca válida — negar acesso
        return None, 0
    # Fallback: o próprio utilizador
    try:
        u = Usuario.objects.get(id=uid)
        return u, u.id
    except Usuario.DoesNotExist:
        return None, uid


# ─── DU — Criar / Editar ─────────────────────────────────────────────────────

def du_view(request, du_uuid=None):
    """Formulário de criação ou edição de DU."""
    if not _sessao_ok(request):
        return redirect('login')

    # Apenas Despachante Oficial (ou quem tem permissão) pode criar nova DU
    if du_uuid is None and not _tem_permissao_ou_papel(request, 'criar_declaracao_unica'):
        return redirect('aduaneiro:du_lista')

    du = None
    dados_iniciais = '{}'
    dono_du = None          # dados do proprietário da DU (para o admin ver)
    is_admin_editando = False
    is_colaborador_operando = False

    # Se for colaborador, carregar dados do dono da banca para exibir no formulário
    if request.session.get('tipo_usuario') == 'colaborador':
        dono_banca, _ = _banca_owner(request)
        if dono_banca:
            dono_du = {
                'nome':    dono_banca.nome,
                'nif':     dono_banca.nif or '',
                'cedula':  dono_banca.cedula or '',
                'papel':   dono_banca.papel,
                'email':   dono_banca.email or '',
                'telefone': dono_banca.telefone or '',
            }
            is_colaborador_operando = True

    if du_uuid:
        du = get_object_or_404(escopo_du(request, DeclaracaoUnica.objects.all()), du_uuid=du_uuid)

        # Se for colaborador, comparar com o dono da banca
        _, uid_efetivo = _banca_owner(request)
        uid_atual = uid_efetivo if request.session.get('tipo_usuario') == 'colaborador' else _usuario_id(request)

        # Só o dono ou Administrador pode editar
        e_admin = _is_admin_ou_acesso_total(request)
        if du.usuario_id != uid_atual and not e_admin:
            return redirect('aduaneiro:du_lista')

        dados_iniciais = du.dados_json

        # Se é admin a editar uma DU de outro utilizador, buscar dados do dono
        if e_admin and du.usuario_id != uid_atual:
            is_admin_editando = True
            try:
                dono = Usuario.objects.get(id=du.usuario_id)
                dono_du = {
                    'nome':    dono.nome,
                    'nif':     dono.nif or '',
                    'cedula':  dono.cedula or '',
                    'papel':   dono.papel,
                    'email':   dono.email,
                    'telefone': dono.telefone or '',
                }
            except Usuario.DoesNotExist:
                # Fallback: usar dados guardados no dados_json
                dados_guardados = du.get_dados()
                dono_du = {
                    'nome':   dados_guardados.get('despachante_nome', du.nome_declarante or ''),
                    'nif':    dados_guardados.get('despachante_nif',  du.nif_declarante  or ''),
                    'cedula': dados_guardados.get('despachante_licenca', ''),
                    'papel':  'Despachante Oficial',
                    'email':  '',
                    'telefone': '',
                }

    ctx = _ctx_base(request)
    ctx.update({
        'active_menu': 'Gestão Aduaneira',
        'active_sub': 'du',
        'du': du,
        'dados_iniciais': dados_iniciais,
        'is_admin_editando': is_admin_editando,
        'is_colaborador_operando': is_colaborador_operando,
        'dono_du': dono_du,
    })
    return render(request, 'du.html', ctx)


# ─── DU — Guardar (rascunho ou submissão) ────────────────────────────────────

@require_POST
def du_guardar(request):
    """Guarda ou actualiza uma DU via AJAX (JSON body)."""
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    try:
        return _du_guardar_impl(request)
    except Exception as exc:
        logger.error(f"Erro ao guardar DU: {exc}\n{traceback.format_exc()}")
        return JsonResponse({'erro': f'Erro interno: {exc}'}, status=500)


def _du_guardar_impl(request):
    """Implementação real do guardar DU."""
    logger = logging.getLogger(__name__)
    
    logger.info(f"=== DEBUG du_guardar ===")
    logger.info(f"Session keys: {list(request.session.keys())}")
    logger.info(f"usuario_id: {request.session.get('usuario_id')}")
    logger.info(f"Session cookie: {request.COOKIES.get('sessionid', 'NONE')}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    if not _sessao_ok(request):
        logger.warning("Sessão não OK - retornando 401")
        return JsonResponse({'erro': 'Não autorizado'}, status=401)

    try:
        payload = json.loads(request.body)
        logger.info(f"Payload recebido: {json.dumps(payload, indent=2, ensure_ascii=False)[:1000]}...")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    du_uuid = payload.get('uuid')

    # Apenas Despachante Oficial ou quem tem permissão pode criar nova DU
    if not du_uuid:
        papel = _papel(request)
        if papel != 'Despachante Oficial' and not _tem_permissao_ou_papel(request, 'criar_declaracao_unica'):
            logger.warning(f"Papel {papel} sem permissão para criar DU")
            return JsonResponse({'erro': 'Sem permissão para criar DU'}, status=403)
    submeter  = payload.get('submeter', False)
    dados     = payload.get('dados', {})
    totais    = payload.get('totais', {})

    # Se for colaborador, a DU deve ficar em nome do dono da banca
    dono_banca, uid = _banca_owner(request)

    # ── Normalizar e validar totais recebidos ─────────────────────────────
    def _safe_float(v, default=0.0):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return default

    t_derimp = _safe_float(totais.get('derimp', 0))
    t_iec    = _safe_float(totais.get('iec',    0))
    t_emgead = _safe_float(totais.get('emgead', 0))
    t_direxp = _safe_float(totais.get('direxp', 0))
    t_iva    = _safe_float(totais.get('iva',    0))
    # Recalcular total server-side para garantir consistência
    t_total  = t_derimp + t_iec + t_emgead + t_direxp + t_iva

    # ── Normalizar impostos por adição ────────────────────────────────────
    adicoes = dados.get('adicoes', [])
    for ad in adicoes:
        # Se o frontend enviou impostos como objecto, garantir que está bem formado
        imp = ad.get('impostos')
        if isinstance(imp, dict):
            for cod, info in imp.items():
                if isinstance(info, dict):
                    info['valor'] = _safe_float(info.get('valor', 0))
                    info['taxa']  = _safe_float(info.get('taxa',  0))
                    info['base']  = _safe_float(info.get('base',  0))
        # Garantir que montante_kz e fob_kz são numéricos
        for campo in ('montante_kz', 'fob_kz', 'seguro_kz', 'frete_kz',
                      'valor_fob', 'valor_seguro', 'valor_frete',
                      'valor_fob_kz', 'valor_seguro_kz', 'valor_frete_kz',
                      'reparticao_seguro', 'reparticao_frete'):
            if campo in ad and ad[campo] == '':
                ad[campo] = '0'
    dados['adicoes'] = adicoes

    # ── Validação server-side dos campos obrigatórios ─────────────────────
    erros = []

    # Validações básicas apenas para submissão final
    if submeter:
        regime = (dados.get('regime_aduaneiro', '') or '').strip()
        if not regime:
            erros.append('Regime Aduaneiro é obrigatório.')

        ref = (dados.get('ref_despachante', '') or '').strip()
        if not ref:
            erros.append('Referência Interna é obrigatória.')

        if not (dados.get('exportador_nome', '') or '').strip() and \
           not (dados.get('exportador_codigo', '') or '').strip():
            erros.append('Dados do Exportador (nome ou NIF) são obrigatórios.')

        adicoes = dados.get('adicoes', [])
        if not adicoes:
            erros.append('A DU deve ter pelo menos uma adição.')
        else:
            for i, ad in enumerate(adicoes, 1):
                if not (ad.get('codigo_pautal', '') or '').strip():
                    erros.append(f'Adição {i}: Código Pautal é obrigatório.')
                if not (ad.get('pais_origem', '') or '').strip():
                    erros.append(f'Adição {i}: País de Origem é obrigatório.')

        forma_pag = (dados.get('forma_pagamento', '') or '').strip()
        if not forma_pag:
            erros.append('Forma de Pagamento é obrigatória.')
    else:
        # Para rascunhos, apenas validações mínimas
        regime = (dados.get('regime_aduaneiro', '') or '').strip()
        if not regime:
            erros.append('Regime Aduaneiro é obrigatório.')

        ref = (dados.get('ref_despachante', '') or '').strip()
        if not ref:
            erros.append('Referência Interna é obrigatória.')

    # ── Validação de totais: Step 1 vs Adições (só na submissão final) ───────
    if submeter:
        fob_step1 = _safe_float(dados.get('valor_fob_kz', 0))
        frete_step1 = _safe_float(dados.get('valor_frete_kz', 0))
        seguro_step1 = _safe_float(dados.get('valor_seguro_kz', 0))

        fob_total = sum(_safe_float(ad.get('fob_kz', 0)) for ad in dados.get('adicoes', []))
        frete_total = sum(_safe_float(ad.get('frete_kz', 0)) for ad in dados.get('adicoes', []))
        seguro_total = sum(_safe_float(ad.get('seguro_kz', 0)) for ad in dados.get('adicoes', []))

        # Margem de 1 KZ para arredondamentos de câmbio
        margem = 1.0

        logger.info(f"Validação de totais (submissão):")
        logger.info(f"  FOB Step1: {fob_step1:.2f} | Adições: {fob_total:.2f} | Diff: {abs(fob_step1 - fob_total):.2f}")
        logger.info(f"  Frete Step1: {frete_step1:.2f} | Adições: {frete_total:.2f} | Diff: {abs(frete_step1 - frete_total):.2f}")
        logger.info(f"  Seguro Step1: {seguro_step1:.2f} | Adições: {seguro_total:.2f} | Diff: {abs(seguro_step1 - seguro_total):.2f}")

        if fob_step1 > 0 and fob_total > 0 and abs(fob_step1 - fob_total) > margem:
            erros.append(f'FOB do Step 1 ({fmt_kz(fob_step1)}) não corresponde ao total das adições ({fmt_kz(fob_total)}). Diferença: {fmt_kz(abs(fob_step1 - fob_total))}')

        if frete_step1 > 0 and frete_total > 0 and abs(frete_step1 - frete_total) > margem:
            erros.append(f'Frete do Step 1 ({fmt_kz(frete_step1)}) não corresponde ao total das adições ({fmt_kz(frete_total)}). Diferença: {fmt_kz(abs(frete_step1 - frete_total))}')

        if seguro_step1 > 0 and seguro_total > 0 and abs(seguro_step1 - seguro_total) > margem:
            erros.append(f'Seguro do Step 1 ({fmt_kz(seguro_step1)}) não corresponde ao total das adições ({fmt_kz(seguro_total)}). Diferença: {fmt_kz(abs(seguro_step1 - seguro_total))}')
    else:
        logger.info("Rascunho: validação de totais ignorada")

    if erros:
        logger.warning(f"Erros de validação: {erros}")
        return JsonResponse({'erro': ' | '.join(erros), 'erros': erros}, status=400)

    banca_id = request.session.get('banca_id')
    if not banca_id:
        # Fallback: lookup banca by usuario_id
        banca_obj = Banca.objects.filter(usuario_id=uid).first()
        banca_id = banca_obj.id if banca_obj else None

    filial_id = request.session.get('colaborador_filial_id') if request.session.get('tipo_usuario') == 'colaborador' else None

    if du_uuid:
        try:
            du = DeclaracaoUnica.objects.get(du_uuid=du_uuid)
            if du.usuario_id != uid and not _is_admin_ou_acesso_total(request):
                return JsonResponse({'erro': 'Sem permissão'}, status=403)
            if not escopo_du(request, DeclaracaoUnica.objects.filter(pk=du.pk)).exists():
                return JsonResponse({'erro': 'Sem permissão'}, status=403)
        except DeclaracaoUnica.DoesNotExist:
            du = DeclaracaoUnica(usuario_id=uid, processo_id=None, banca_id=banca_id, filial_id=filial_id)
    else:
        du = DeclaracaoUnica(usuario_id=uid, processo_id=None, banca_id=banca_id, filial_id=filial_id)

    # Preencher campos desnormalizados
    du.regime_aduaneiro   = (dados.get('regime_aduaneiro', '') or '')[:100]
    du.ref_despachante    = (dados.get('ref_despachante',  '') or '')[:100]
    du.exportador_nome    = (dados.get('exportador_nome',  '') or '')[:200]
    du.destinatario_nome  = (dados.get('destinatario_nome','') or '')[:200]
    du.nome_declarante    = (dados.get('exportador_nome',  '') or '')[:200]
    du.nif_declarante     = (dados.get('exportador_codigo','') or '')[:50]
    du.nome_banco         = (dados.get('nome_banco',      '') or '')[:50]
    du.termo_pagamento    = (dados.get('termo_pagamento', '') or '')[:5]
    du.codigo_pautal      = ''   # campo obrigatório na tabela — deixar vazio
    
    # Extrair dados de carga das adições para campos desnormalizados
    adicoes_lista = dados.get('adicoes') or []
    if adicoes_lista:
        descs = [a.get('descricao_mercadoria', '').strip() for a in adicoes_lista if a.get('descricao_mercadoria', '').strip()]
        du.descricao_mercadoria = ' | '.join(descs)[:500] if descs else ''
        du.peso_bruto = sum(float(a.get('peso_bruto', 0) or 0) for a in adicoes_lista)
        du.peso_liquido = sum(float(a.get('peso_liquido', 0) or 0) for a in adicoes_lista)
        du.quantidade = sum(int(a.get('quantidade', 0) or 0) for a in adicoes_lista)
    else:
        du.descricao_mercadoria = ''
        du.quantidade = 0
        du.peso_bruto = 0
        du.peso_liquido = 0
    
    # Extrair campos de transporte/origem/destino
    du.meio_transporte = (dados.get('transporte_identidade', '') or '')[:50]
    du.porto_embarque = (dados.get('porto_embarque', '') or '')[:100]
    du.porto_desembarque = (dados.get('porto_desembarque', '') or '')[:100]
    # País de origem: da primeira adição ou do campo directo
    pais_origem = ''
    if adicoes_lista:
        pais_origem = adicoes_lista[0].get('pais_origem', '') or ''
    if not pais_origem:
        pais_origem = dados.get('pais_origem', '') or ''
    du.pais_origem = pais_origem[:100]

    # Totais por imposto
    du.total_derimp  = t_derimp
    du.total_iec     = t_iec
    du.total_emgead  = t_emgead
    du.total_direxp  = t_direxp
    du.total_iva     = t_iva
    du.total_geral   = t_total

    # Totais nos campos originais da tabela
    du.direitos_aduaneiros = du.total_derimp
    du.imposto_consumo     = du.total_iec
    du.emolumentos         = du.total_emgead
    du.iva                 = du.total_iva
    du.total_impostos      = du.total_geral

    # Valores financeiros
    try:
        du.valor_fob    = float(dados.get('valor_fob_kz',    0) or 0)
        du.valor_frete  = float(dados.get('valor_frete_kz',  0) or 0)
        du.valor_seguro = float(dados.get('valor_seguro_kz', 0) or 0)
    except (TypeError, ValueError):
        du.valor_fob = du.valor_frete = du.valor_seguro = 0
    du.valor_cif = du.valor_fob + du.valor_frete + du.valor_seguro

    # Se um colaborador está a agir em nome do dono da banca, registar quem operou
    if request.session.get('tipo_usuario') == 'colaborador':
        colaborador_id = request.session.get('colaborador_id')
        if colaborador_id:
            try:
                colab = Colaborador.objects.get(id=colaborador_id)
                dados['_operado_por'] = {
                    'tipo': 'colaborador',
                    'colaborador_id': colab.id,
                    'nome': colab.nome,
                }
            except Colaborador.DoesNotExist:
                pass

    # Capturar estado anterior para versionamento
    campos_alterados = {}
    if du.pk:
        old = DeclaracaoUnica.objects.get(pk=du.pk)
        for campo in ('status', 'regime_aduaneiro', 'ref_despachante', 'exportador_nome',
                      'destinatario_nome', 'total_geral', 'valor_fob', 'valor_frete', 'valor_seguro'):
            old_val = str(getattr(old, campo, '') or '')
            new_val = str(getattr(du, campo, '') or '')
            if old_val != new_val:
                campos_alterados[campo] = {'de': old_val, 'para': new_val}
        old_dados = old.get_dados()
        if old_dados != dados:
            campos_alterados['dados_json'] = 'Dados do formulário alterados'
    else:
        campos_alterados['_criado'] = 'Nova Declaração Única criada'

    du.set_dados(dados)

    # Gerar UUID e código de processo se novo registo
    if not du.du_uuid:
        du.du_uuid = str(uuid.uuid4())
    if not du.codigo_processo:
        du.codigo_processo = DeclaracaoUnica.gerar_codigo_processo()

    if submeter:
        du.status = 'Submetida'
        if not du.numero_du:
            du.numero_du = du.gerar_numero()
        du.data_submissao = timezone.now()
    else:
        du.status = 'Rascunho'
        # Rascunho não tem número — fica NULL até submeter
        if not du.numero_du:
            du.numero_du = None

    du.save()

    # Registar versão no histórico
    if du.pk and campos_alterados:
        from aduaneiro.signals import registrar_versao_du
        registrar_versao_du(du, campos_alterados, request)

    return JsonResponse({
        'sucesso': True,
        'uuid': du.du_uuid,
        'codigo_processo': du.codigo_processo or '',
        'numero_du': du.numero_du or '',
        'status': du.status,
    })


# ─── DU — Listar ─────────────────────────────────────────────────────────────

def du_lista(request):
    """Lista de DUs — filtrada por papel."""
    if not _sessao_ok(request):
        return redirect('login')

    papel = _papel(request)
    _, uid = _banca_owner(request)

    dus = escopo_du(request, DeclaracaoUnica.objects.all())

    # Excluir DUs sem du_uuid (não editáveis via interface) — registo legado
    dus = dus.exclude(du_uuid='').exclude(du_uuid__isnull=True)

    # Filtros opcionais
    q      = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    if q:
        dus = dus.filter(
            Q(numero_du__icontains=q) |
            Q(codigo_processo__icontains=q) |
            Q(ref_despachante__icontains=q) |
            Q(exportador_nome__icontains=q) |
            Q(destinatario_nome__icontains=q) |
            Q(nome_declarante__icontains=q)
        )
    if status:
        dus = dus.filter(status=status)

    paginator = Paginator(dus, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    pode_criar = _tem_permissao_ou_papel(request, 'criar_declaracao_unica') and _papel(request) not in ('Administrador', 'Colaborador Institucional')
    e_admin = _is_admin_ou_acesso_total(request)

    ctx = _ctx_base(request)
    ctx.update({
        'active_menu': 'Gestão Aduaneira',
        'active_sub': 'du',
        'page_obj': page_obj,
        'q': q,
        'status_filtro': status,
        'is_admin': e_admin,
        'total_dus': dus.count(),
        'pode_criar': pode_criar,
    })
    return render(request, 'du_lista.html', ctx)


# ─── DU — Detalhe ────────────────────────────────────────────────────────────

def du_detalhe(request, du_uuid):
    """Detalhe de uma DU."""
    if not _sessao_ok(request):
        return redirect('login')

    du = get_object_or_404(escopo_du(request, DeclaracaoUnica.objects.all()), du_uuid=du_uuid)
    papel = _papel(request)
    _, uid = _banca_owner(request)

    e_admin = _is_admin_ou_acesso_total(request)
    if du.usuario_id != uid and not e_admin:
        return redirect('aduaneiro:du_lista')

    ctx = _ctx_base(request)
    ctx.update({
        'active_menu': 'Gestão Aduaneira',
        'active_sub': 'du',
        'du': du,
        'dados': du.get_dados(),
        'is_admin': e_admin,
        'pode_editar': e_admin or du.usuario_id == uid,
    })
    return render(request, 'du_detalhe.html', ctx)


# ─── DU — Apagar (só Administrador) ─────────────────────────────────────────

@require_POST
def du_apagar(request, du_uuid):
    if not _sessao_ok(request):
        return JsonResponse({'erro': 'Não autorizado'}, status=401)

    du = get_object_or_404(escopo_du(request, DeclaracaoUnica.objects.all()), du_uuid=du_uuid)

    if du.status != 'Rascunho':
        return JsonResponse({'erro': 'Apenas DUs em rascunho podem ser apagadas.'}, status=403)

    du.delete()
    return JsonResponse({'sucesso': True})


# ─── DU — Alterar status (só Administrador) ──────────────────────────────────

@require_POST
def du_alterar_status(request, du_uuid):
    if not _sessao_ok(request):
        return JsonResponse({'erro': 'Não autorizado'}, status=401)
    if not _is_admin_ou_acesso_total(request):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)

    try:
        payload = json.loads(request.body)
        novo_status = payload.get('status', '')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    status_validos = [s[0] for s in DeclaracaoUnica.STATUS_CHOICES]
    if novo_status not in status_validos:
        return JsonResponse({'erro': 'Status inválido'}, status=400)

    du = get_object_or_404(escopo_du(request, DeclaracaoUnica.objects.all()), du_uuid=du_uuid)

    # Transições automáticas
    if novo_status == 'Aprovada' and du.status in ('Submetida', 'Em Análise'):
        du.data_aprovacao = timezone.now()
        if not du.numero_du:
            du.numero_du = du.gerar_numero()
    if novo_status == 'Submetida':
        du.data_submissao = timezone.now()

    du.status = novo_status
    du.save(update_fields=['status', 'data_aprovacao', 'data_submissao', 'numero_du', 'updated_at'])
    return JsonResponse({'sucesso': True, 'status': du.status})


# ─── DU — Download PDF ───────────────────────────────────────────────────────

def du_download_pdf(request, du_uuid):
    """Gera PDF da DU com layout profissional (padrão Requisição de Fundos)."""
    if not _sessao_ok(request):
        return redirect('login')

    du = get_object_or_404(escopo_du(request, DeclaracaoUnica.objects.all()), du_uuid=du_uuid)
    _, uid = _banca_owner(request)

    if du.usuario_id != uid and not _is_admin_ou_acesso_total(request):
        return redirect('aduaneiro:du_lista')

    import html as _html_mod
    def _safe(text):
        if not text:
            return ''
        return _html_mod.escape(str(text))

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate,
            Spacer, Table, TableStyle,
        )
        import qrcode as _qr

        # ── Dados do despachante ──────────────────────────────────────────
        dono = None
        try:
            dono = Usuario.objects.get(id=du.usuario_id)
            desp_nome     = _safe(dono.nome)
            desp_nif      = _safe(dono.nif) or '—'
            desp_cedula   = _safe(dono.cedula) or '—'
            desp_papel    = _safe(dono.papel) or 'Despachante Oficial'
            desp_email    = _safe(dono.email) or '—'
            desp_telefone = _safe(dono.telefone) or '—'
        except Usuario.DoesNotExist:
            dados_j = du.get_dados()
            desp_nome     = _safe(dados_j.get('despachante_nome', du.nome_declarante or 'N/D'))
            desp_nif      = _safe(dados_j.get('despachante_nif', du.nif_declarante or 'N/D'))
            desp_cedula   = _safe(dados_j.get('despachante_licenca', 'N/D'))
            desp_papel    = 'Despachante Oficial'
            desp_email    = '—'
            desp_telefone = '—'

        # ── Banca ─────────────────────────────────────────────────────────
        banca = du.banca
        nome_banco_txt = _safe(banca.nome) if banca else 'CDOA'
        nif_banco      = _safe(banca.nif) if banca else 'N/D'
        cdoa_txt       = _safe(banca.licenca_cdoa) if banca else '—'
        endereco_banco = _safe(banca.endereco) if banca else '—'
        tel_banco      = _safe(banca.telefone) if banca else '—'
        email_banco    = _safe(banca.email) if banca else '—'

        agora = timezone.now()
        dados = du.get_dados()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=0.7*cm, rightMargin=0.7*cm,
            topMargin=0.5*cm, bottomMargin=1.0*cm,
            title=f'DU {du.numero_du or du.du_uuid}',
        )
        PAGE_W, PAGE_H = A4
        W = PAGE_W - 1.4*cm

        # ── Cores (padrão requisição) ────────────────────────────────────
        COR_PRIMARIO    = colors.HexColor('#0f172a')
        COR_SECUNDARIO  = colors.white
        COR_CINZA       = colors.HexColor('#64748b')
        COR_CINZA_CLARO = colors.HexColor('#f1f5f9')
        COR_BORDA       = colors.HexColor('#cbd5e1')
        COR_BRANCO      = colors.white
        COR_HEADER      = colors.white
        COR_CDOA        = colors.HexColor('#1a3a5c')
        COR_GOLD        = colors.HexColor('#c9a84c')
        COR_PRIMAZUL    = colors.HexColor('#137fec')

        def st(name, **kw):
            defaults = dict(fontName='Helvetica', fontSize=9, textColor=COR_PRIMARIO, leading=11)
            defaults.update(kw)
            return ParagraphStyle(name, **defaults)

        s_small = st('small', fontSize=7, textColor=COR_CINZA, leading=9)
        s_bold7 = st('bold7', fontSize=7, fontName='Helvetica-Bold', textColor=COR_PRIMARIO, leading=9)
        s_bold7_r = st('bold7r', fontSize=7, fontName='Helvetica-Bold', textColor=COR_PRIMARIO, leading=9, alignment=TA_RIGHT)
        s_kv_label = st('kv_label', fontSize=7, fontName='Helvetica', textColor=COR_CINZA, leading=9)
        s_kv_value = st('kv_value', fontSize=7.5, fontName='Helvetica', textColor=COR_PRIMARIO, leading=10)
        s_kv_value_r = st('kv_value_r', fontSize=7.5, fontName='Helvetica', textColor=COR_PRIMARIO, leading=10, alignment=TA_RIGHT)

        story = []

        # ════════════════════════════════════════════════════════════════
        # LOGO (esquerda) + QR CODE (direita)
        # ════════════════════════════════════════════════════════════════
        logo_path = None
        if banca and hasattr(banca, 'logo') and banca.logo:
            try:
                logo_path = banca.logo.path
            except Exception:
                logo_path = None

        col_logo = Paragraph('', st('empty', fontSize=1))
        if logo_path:
            try:
                col_logo = RLImage(logo_path, width=2.4*cm, height=1.7*cm)
            except Exception:
                col_logo = Paragraph('', st('empty', fontSize=1))

        nr_du = _safe(du.numero_du) or 'Rascunho'
        ref = _safe(du.ref_despachante) or '—'
        merc = _safe(dados.get('exportador_nome', du.exportador_nome)) or '—'

        qr_data = (
            f"=== DECLARACAO UNICA (DU) ===\n"
            f"DU: {nr_du}\n"
            f"Processo: {du.codigo_processo or 'N/D'}\n"
            f"Ref: {ref}\n"
            f"Data: {du.created_at.strftime('%d/%m/%Y %H:%M')}\n"
            f"Estado: {du.status}\n"
            f"\n--- EXPORTADOR ---\n"
            f"Nome: {merc}\n"
            f"NIF: {du.nif_declarante or 'N/D'}\n"
            f"\n--- DESPACHANTE ---\n"
            f"Nome: {desp_nome}\n"
            f"NIF: {desp_nif}\n"
            f"Cedula: {desp_cedula}\n"
            f"\n--- VALORES ---\n"
            f"FOB: {fmt_kz(du.valor_fob)} KZ\n"
            f"Frete: {fmt_kz(du.valor_frete or 0)} KZ\n"
            f"Seguro: {fmt_kz(du.valor_seguro or 0)} KZ\n"
            f"CIF: {fmt_kz(du.valor_cif)} KZ\n"
            f"TOTAL: {fmt_kz(du.total_geral)} KZ\n"
        )
        _qr_buf = io.BytesIO()
        _qr_obj = _qr.QRCode(version=1, box_size=10, border=2)
        _qr_obj.add_data(qr_data)
        _qr_obj.make(fit=True)
        _qr_obj.make_image(fill_color="black", back_color="white").save(_qr_buf, format='PNG')
        _qr_buf.seek(0)
        qr_flowable = RLImage(_qr_buf, width=1.9*cm, height=1.9*cm)

        top_line = Table([[col_logo, qr_flowable]], colWidths=[W - 1.9*cm, 1.9*cm])
        top_line.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(top_line)
        story.append(Spacer(1, 0.15*cm))

        # ════════════════════════════════════════════════════════════════
        # BLOCO DESPACHANTE (esquerda) + BLOCO EXPORTADOR (direita)
        # ════════════════════════════════════════════════════════════════
        empresa_info = (
            f'<font size="9"><b>{nome_banco_txt}</b></font><br/>'
            f'<font size="7.5" color="#334155">Residência: {endereco_banco}</font><br/>'
            f'<font size="7.5" color="#334155">Tel: {tel_banco}</font><br/>'
            f'<font size="7.5" color="#334155">Email: {email_banco}</font><br/>'
            f'<font size="7.5" color="#334155">NIF: {nif_banco} &nbsp;|&nbsp; Licença CDOA: {cdoa_txt}</font>'
        )
        exp_nome = _safe(dados.get('exportador_nome', du.exportador_nome)) or '—'
        exp_nif  = _safe(du.nif_declarante) or '—'
        exp_end  = _safe(dados.get('exportador_endereco', '')) or '—'
        cli_info = (
            f'<font size="7.5">Exportador / Remetente</font><br/>'
            f'<font size="9"><b>{exp_nome}</b></font><br/>'
            f'<font size="7.5" color="#334155">{exp_end}</font><br/>'
            f'<font size="7.5" color="#334155">NIF: {exp_nif}</font>'
        )
        header_body = Table([[
            Paragraph(empresa_info, st('empresa_info', fontSize=7.5, leading=10)),
            Paragraph(cli_info, st('cli_info', fontSize=7.5, leading=10)),
        ]], colWidths=[W*0.55, W*0.45])
        header_body.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(header_body)
        story.append(Spacer(1, 0.35*cm))

        # ════════════════════════════════════════════════════════════════
        # TÍTULO DO DOCUMENTO
        # ════════════════════════════════════════════════════════════════
        story.append(Paragraph('<font size="7.5">Original</font>', st('original', fontSize=7.5)))
        story.append(Paragraph(
            f'<font size="12"><b>DECLARAÇÃO ÚNICA (DU) n.º {nr_du}</b></font>',
            st('titulo', fontSize=12)
        ))
        story.append(Spacer(1, 0.15*cm))

        # ════════════════════════════════════════════════════════════════
        # DADOS DO DOCUMENTO (5 colunas)
        # ════════════════════════════════════════════════════════════════
        data_sub = du.created_at.strftime('%d/%m/%Y') if du.created_at else '—'
        hora_sub = du.created_at.strftime('%H:%M') if du.created_at else '—'

        dados_doc_header = [
            Paragraph('<b>Nº DU</b>', st('ddh', fontSize=7.5)),
            Paragraph('<b>Processo</b>', st('ddh', fontSize=7.5)),
            Paragraph('<b>Ref. Despachante</b>', st('ddh', fontSize=7.5)),
            Paragraph('<b>Data Submissão</b>', st('ddh', fontSize=7.5)),
            Paragraph('<b>Estado</b>', st('ddh', fontSize=7.5)),
        ]
        dados_doc_valores = [
            Paragraph(nr_du, st('ddv', fontSize=7.5)),
            Paragraph(du.codigo_processo or 'N/D', st('ddv', fontSize=7.5)),
            Paragraph(ref, st('ddv', fontSize=7.5)),
            Paragraph(f'{data_sub} {hora_sub}', st('ddv', fontSize=7.5)),
            Paragraph(du.status or 'Rascunho', st('ddv', fontSize=7.5)),
        ]
        t_dados_doc = Table([dados_doc_header, dados_doc_valores], colWidths=[W/5]*5)
        t_dados_doc.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, COR_CINZA),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_CINZA),
            ('LINEBELOW', (0, 1), (-1, 1), 0.5, COR_CINZA),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_dados_doc)
        story.append(Spacer(1, 0.25*cm))

        # ════════════════════════════════════════════════════════════════
        # SECCÕES 1-4: IDENTIFICAÇÃO + EXPORTADOR + DESTINATÁRIO + DESPACHANTE
        # ════════════════════════════════════════════════════════════════
        def tabela_kvCompacta(linhas, col_label=4.5*cm):
            rows = []
            for k, v in linhas:
                rows.append([
                    Paragraph(str(k), s_kv_label),
                    Paragraph(str(v) if v else 'N/D', s_kv_value),
                ])
            if not rows:
                return None
            t = Table(rows, colWidths=[col_label, W - col_label])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), COR_CINZA_CLARO),
                ('GRID', (0, 0), (-1, -1), 0.3, COR_BORDA),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ('ROWBACKGROUNDS', (1, 0), (1, -1), [COR_BRANCO, colors.HexColor('#f8fafc')]),
            ]))
            return t

        def sec_titulo(txt):
            story.append(Spacer(1, 0.15*cm))
            story.append(Paragraph(f'<b>{txt}</b>', st('sec', fontSize=8, fontName='Helvetica-Bold',
                                                       textColor=COR_PRIMARIO, spaceBefore=4, spaceAfter=2)))

        # 1. IDENTIFICAÇÃO
        sec_titulo('1. Identificação da Declaração')
        t = tabela_kvCompacta([
            ('Regime Aduaneiro',     dados.get('regime_aduaneiro', du.regime_aduaneiro)),
            ('Ref. Interna',          dados.get('ref_despachante', du.ref_despachante)),
            ('Estância',              dados.get('estancia', '')),
            ('Vinheta',               dados.get('vinheta_selecionada', dados.get('vinheta', ''))),
            ('INCOTERM',              dados.get('incoterm', '')),
            ('Natureza da Transação', dados.get('natureza_transacao', '')),
            ('Conta de Crédito',      dados.get('conta_credito', '')),
            ('Conta de Garantia',     dados.get('conta_garantias', '')),
        ])
        if t: story.append(t)

        # 2. EXPORTADOR
        sec_titulo('2. Exportador / Remetente')
        t = tabela_kvCompacta([
            ('Nome / Razão Social', dados.get('exportador_nome', du.exportador_nome)),
            ('NIF',                 dados.get('exportador_codigo', du.nif_declarante)),
            ('Endereço',            dados.get('exportador_endereco', '')),
        ])
        if t: story.append(t)

        # 3. DESTINATÁRIO
        sec_titulo('3. Destinatário / Consignatário')
        t = tabela_kvCompacta([
            ('Nome / Razão Social', dados.get('destinatario_nome', du.destinatario_nome)),
            ('NIF',                 dados.get('destinatario_nif', '')),
            ('Telefone',            dados.get('destinatario_telefone', '')),
            ('Endereço',            dados.get('destinatario_endereco', '')),
        ])
        if t: story.append(t)

        # 4. DESPACHANTE
        sec_titulo('4. Despachante / Declarante')
        t = tabela_kvCompacta([
            ('Nome Completo',      desp_nome),
            ('Papel / Função',     desp_papel),
            ('NIF',                desp_nif),
            ('Nº Cédula / Licença', desp_cedula),
        ])
        if t: story.append(t)

        # ════════════════════════════════════════════════════════════════
        # SECCÃO 5: INFORMAÇÕES COMERCIAIS
        # ════════════════════════════════════════════════════════════════
        sec_titulo('5. Informações Comerciais e Financeiras')
        t = tabela_kvCompacta([
            ('Valor FOB',          f"{dados.get('valor_fob', '0')} {dados.get('moeda_fob', '')}"),
            ('Câmbio FOB',         dados.get('cambio_fob', '')),
            ('Valor Seguro',       f"{dados.get('valor_seguro', '0')} {dados.get('moeda_seguro', '')}"),
            ('Câmbio Seguro',      dados.get('cambio_seguro', '')),
            ('Valor Frete',        f"{dados.get('valor_frete', '0')} {dados.get('moeda_frete', '')}"),
            ('Câmbio Frete',       dados.get('cambio_frete', '')),
            ('Forma de Pagamento', dados.get('forma_pagamento', '')),
            ('Banco',              dados.get('nome_banco', '')),
            ('Termo de Pagamento', dados.get('termo_pagamento', '')),
        ])
        if t: story.append(t)

        # ════════════════════════════════════════════════════════════════
        # SECCÃO 6: TRANSPORTE
        # ════════════════════════════════════════════════════════════════
        sec_titulo('6. Transporte')
        t = tabela_kvCompacta([
            ('Modo de Transporte',   dados.get('modo_transporte', du.meio_transporte or '')),
            ('Nº Conhecimento',      dados.get('numero_conhecimento', '')),
            ('Porto de Embarque',    dados.get('porto_embarque', du.porto_embarque or '')),
            ('Porto de Desembarque', dados.get('porto_desembarque', du.porto_desembarque or '')),
            ('País de Expedição',    dados.get('pais_expedicao', '')),
        ])
        if t: story.append(t)

        contentores = dados.get('contentores', [])
        if contentores:
            story.append(Spacer(1, 0.1*cm))
            cont_header = [
                Paragraph('<b>Nº</b>', s_bold7),
                Paragraph('<b>Identificação</b>', s_bold7),
                Paragraph('<b>Tipo</b>', s_bold7),
                Paragraph('<b>Peso Bruto</b>', s_bold7),
                Paragraph('<b>Qtd. Volumes</b>', s_bold7),
            ]
            cont_rows = [cont_header]
            for i, c in enumerate(contentores, 1):
                cont_rows.append([
                    Paragraph(str(i), s_kv_value),
                    Paragraph(str(c.get('identificacao', 'N/D')), s_kv_value),
                    Paragraph(str(c.get('tipo', 'N/D')), s_kv_value),
                    Paragraph(str(c.get('peso_bruto', 'N/D')), s_kv_value),
                    Paragraph(str(c.get('qtd_volumes', 'N/D')), s_kv_value),
                ])
            t_cont = Table(cont_rows, colWidths=[0.8*cm, 5*cm, 3*cm, 3*cm, 3*cm])
            t_cont.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_PRIMARIO),
                ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#e2e2e2')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_cont)

        # ════════════════════════════════════════════════════════════════
        # SECCÃO 7: ADIÇÕES (tabela de itens)
        # ════════════════════════════════════════════════════════════════
        adicoes = dados.get('adicoes', [])
        if adicoes:
            sec_titulo(f'7. Adições ({len(adicoes)})')
            ad_header = [
                Paragraph('<b>Cód. Pautal</b>', s_bold7),
                Paragraph('<b>Descrição</b>', s_bold7),
                Paragraph('<b>Qtd</b>', s_bold7_r),
                Paragraph('<b>Peso (kg)</b>', s_bold7_r),
                Paragraph('<b>Valor FOB</b>', s_bold7_r),
                Paragraph('<b>Valor CIF</b>', s_bold7_r),
            ]
            ad_rows = [ad_header]
            total_fob_ad = Decimal('0')
            total_cif_ad = Decimal('0')
            for ad in adicoes:
                fob_val = Decimal(str(ad.get('valor_fob_kz', 0) or 0))
                cif_val = Decimal(str(ad.get('montante_kz', 0) or 0))
                total_fob_ad += fob_val
                total_cif_ad += cif_val
                ad_rows.append([
                    Paragraph(_safe(ad.get('codigo_pautal', '')), s_kv_value),
                    Paragraph(_safe(ad.get('descricao_mercadoria', ''))[:60], s_kv_value),
                    Paragraph(str(ad.get('quantidade', '')), s_kv_value_r),
                    Paragraph(str(ad.get('peso_bruto', '')), s_kv_value_r),
                    Paragraph(fmt_kz(fob_val), s_kv_value_r),
                    Paragraph(fmt_kz(cif_val), s_kv_value_r),
                ])
            t_ad = Table(ad_rows, colWidths=[W*0.12, W*0.33, W*0.09, W*0.11, W*0.17, W*0.18])
            t_ad.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_BORDA),
                ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#e2e2e2')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_ad)
            story.append(Spacer(1, 0.1*cm))

            # Impostos por adição (se existirem)
            for i, ad in enumerate(adicoes, 1):
                impostos = ad.get('impostos', {})
                if impostos:
                    imp_rows = [[
                        Paragraph('<b>Imposto</b>', s_bold7),
                        Paragraph('<b>Base (KZ)</b>', s_bold7_r),
                        Paragraph('<b>Taxa</b>', s_bold7_r),
                        Paragraph('<b>Valor (KZ)</b>', s_bold7_r),
                        Paragraph('<b>Accão</b>', s_bold7),
                    ]]
                    for cod, info in impostos.items():
                        if isinstance(info, dict) and info.get('valor', 0):
                            imp_rows.append([
                                Paragraph(str(cod), s_kv_value),
                                Paragraph(fmt_kz(info.get('base', 0)), s_kv_value_r),
                                Paragraph(f"{info.get('taxa', 0)}%", s_kv_value_r),
                                Paragraph(fmt_kz(info.get('valor', 0)), s_kv_value_r),
                                Paragraph(str(info.get('acao', '')), s_kv_value),
                            ])
                    if len(imp_rows) > 1:
                        story.append(Spacer(1, 0.08*cm))
                        t_imp = Table(imp_rows, colWidths=[W*0.22, W*0.22, W*0.12, W*0.22, W*0.22])
                        t_imp.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
                            ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_PRIMARIO),
                            ('LINEBELOW', (0, 1), (-1, -1), 0.3, COR_BORDA),
                            ('TOPPADDING', (0, 0), (-1, -1), 3),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                            ('LEFTPADDING', (0, 0), (-1, -1), 4),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COR_BRANCO, COR_CINZA_CLARO]),
                        ]))
                        story.append(t_imp)

        # ════════════════════════════════════════════════════════════════
        # SECCÃO 8: RESUMO DE TAXAÇÃO + VALORES (esquerda) | SUMÁRIO (direita)
        # ════════════════════════════════════════════════════════════════
        imposto_rows = [
            [Paragraph('<b>Imposto</b>', st('imh', fontSize=7, textColor=COR_PRIMARIO)),
             Paragraph('<b>Incidência</b>', st('imh', fontSize=7, textColor=COR_PRIMARIO)),
             Paragraph('<b>Valor (KZ)</b>', st('imh', fontSize=7, textColor=COR_PRIMARIO, alignment=TA_RIGHT))],
            [Paragraph('DERIMP - Direitos de Importação', st('imc', fontSize=7)),
             Paragraph('Sobre CIF', st('imc', fontSize=7)),
             Paragraph(fmt_kz(du.total_derimp), st('imc', fontSize=7, alignment=TA_RIGHT))],
            [Paragraph('IEC - Imposto Especial de Consumo', st('imc', fontSize=7)),
             Paragraph('Sobre CIF', st('imc', fontSize=7)),
             Paragraph(fmt_kz(du.total_iec), st('imc', fontSize=7, alignment=TA_RIGHT))],
            [Paragraph('EMGEAD - Emolumentos Gerais', st('imc', fontSize=7)),
             Paragraph('Sobre CIF', st('imc', fontSize=7)),
             Paragraph(fmt_kz(du.total_emgead), st('imc', fontSize=7, alignment=TA_RIGHT))],
            [Paragraph('DIREXP - Direitos de Exportação', st('imc', fontSize=7)),
             Paragraph('Sobre CIF', st('imc', fontSize=7)),
             Paragraph(fmt_kz(du.total_direxp), st('imc', fontSize=7, alignment=TA_RIGHT))],
            [Paragraph('IVA', st('imc', fontSize=7)),
             Paragraph('Sobre CIF', st('imc', fontSize=7)),
             Paragraph(fmt_kz(du.total_iva), st('imc', fontSize=7, alignment=TA_RIGHT))],
        ]
        t_imposto = Table(imposto_rows, colWidths=[W*0.55*0.50, W*0.55*0.20, W*0.55*0.30])
        t_imposto.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, COR_CINZA),
            ('LINEBELOW', (0, 0), (-1, 0), 1.0, COR_CINZA),
            ('LINEBELOW', (0, 1), (-1, -1), 0.3, COR_BORDA),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COR_BRANCO, COR_CINZA_CLARO]),
        ]))

        # Valores aduaneiros
        val_texto = (
            f'<font size="7.5"><b>Valores Aduaneiros</b></font><br/>'
            f'<font size="7" color="#334155">FOB: {fmt_kz(du.valor_fob)} KZ</font><br/>'
            f'<font size="7" color="#334155">Frete: {fmt_kz(du.valor_frete or 0)} KZ</font><br/>'
            f'<font size="7" color="#334155">Seguro: {fmt_kz(du.valor_seguro or 0)} KZ</font><br/>'
            f'<font size="7" color="#334155">CIF: {fmt_kz(du.valor_cif)} KZ</font>'
        )
        bloco_esquerdo = [
            [t_imposto],
            [Spacer(1, 0.15*cm)],
            [Paragraph(val_texto, st('val_ad', fontSize=7, leading=10))],
        ]
        t_bloco_esquerdo = Table(bloco_esquerdo, colWidths=[W*0.55])
        t_bloco_esquerdo.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        total_geral = du.total_geral or Decimal('0')
        sumario_rows = [
            [Paragraph('<b>Sumário</b>', st('sum_h', fontSize=8, fontName='Helvetica-Bold', textColor=COR_PRIMARIO))],
            [Spacer(1, 0.15*cm)],
            [Paragraph(f'<font size="7">FOB: <b>{fmt_kz(du.valor_fob)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Paragraph(f'<font size="7">Frete: <b>{fmt_kz(du.valor_frete or 0)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Paragraph(f'<font size="7">Seguro: <b>{fmt_kz(du.valor_seguro or 0)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Paragraph(f'<font size="7">CIF: <b>{fmt_kz(du.valor_cif)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Spacer(1, 0.1*cm)],
            [Paragraph(f'<font size="7">DERIMP: <b>{fmt_kz(du.total_derimp)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Paragraph(f'<font size="7">IEC: <b>{fmt_kz(du.total_iec)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Paragraph(f'<font size="7">EMGEAD: <b>{fmt_kz(du.total_emgead)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Paragraph(f'<font size="7">IVA: <b>{fmt_kz(du.total_iva)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Spacer(1, 0.15*cm)],
            [Paragraph(f'<font size="10" color="#0f172a"><b>Total: {fmt_kz(total_geral)} KZ</b></font>',
                       st('sum_total', fontSize=10, leading=12))],
        ]
        t_sumario = Table(sumario_rows, colWidths=[W*0.35])
        t_sumario.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), COR_HEADER),
            ('TOPPADDING', (0, 0), (0, 0), 5),
            ('BOTTOMPADDING', (0, 0), (0, 0), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
        ]))

        t_resumo = Table([[t_bloco_esquerdo, '', '', t_sumario]], colWidths=[W*0.60, W*0.02, W*0.03, W*0.35])
        t_resumo.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(Spacer(1, 0.2*cm))
        story.append(t_resumo)
        story.append(Spacer(1, 0.2*cm))

        # ════════════════════════════════════════════════════════════════
        # DESPACHANTE RESPONSÁVEL
        # ════════════════════════════════════════════════════════════════
        story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
        story.append(Spacer(1, 0.15*cm))
        desp_box = Table([[
            Paragraph('<b>Despachante Responsável</b>', st('desp_h', fontSize=7.5, textColor=COR_PRIMARIO)),
        ]], colWidths=[W])
        desp_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('LEFTPADDING', (0, 0), (-1, 0), 6),
        ]))
        story.append(desp_box)
        story.append(Spacer(1, 0.1*cm))
        story.append(Paragraph(
            f'{desp_nome} &nbsp;|&nbsp; NIF: {desp_nif} &nbsp;|&nbsp; '
            f'Cédula CDOA: {desp_cedula}',
            st('desp_l1', fontSize=7.5, textColor=COR_PRIMARIO)
        ))
        story.append(Paragraph(
            f'Tel: {desp_telefone} &nbsp;|&nbsp; Email: {desp_email}',
            st('desp_l2', fontSize=7, textColor=COR_CINZA)
        ))
        story.append(Spacer(1, 0.15*cm))

        # Declaração
        story.append(Paragraph(
            f'Eu, <b>{desp_nome}</b>, portador do NIF <b>{desp_nif}</b>, '
            f'Nº de Cédula/Licença <b>{desp_cedula}</b>, na qualidade de <b>{desp_papel}</b>, '
            f'declaro que as informações constantes nesta Declaração Única são verdadeiras e '
            f'conformes com os documentos que as suportam, assumindo total responsabilidade '
            f'pelo seu conteúdo.',
            st('declaracao', fontSize=7.5, textColor=COR_PRIMARIO, leading=11, spaceAfter=8)
        ))

        # ════════════════════════════════════════════════════════════════
        # ASSINATURA
        # ════════════════════════════════════════════════════════════════
        story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
        story.append(Spacer(1, 0.1*cm))

        # Assinatura digital do despachante (se existir)
        _assinatura_img = None
        try:
            _assinatura_raw = getattr(dono, 'assinatura', '') or ''
            if _assinatura_raw.startswith('data:image/png;base64,'):
                import base64 as _b64
                from io import BytesIO
                _img_data = _b64.b64decode(_assinatura_raw.split(',', 1)[1])
                _assinatura_img = BytesIO(_img_data)
        except Exception:
            _assinatura_img = None

        if _assinatura_img:
            from reportlab.platypus import Image as RLImage
            _assinatura_rl = RLImage(_assinatura_img, width=5*cm, height=1*cm)
            ass_data = [
                [Paragraph('<b>Assinatura do Despachante:</b>', st('ass_lab', fontSize=8)),
                 Paragraph('', st('ass_spc', fontSize=8))],
                [Spacer(1, 0.15*cm), Spacer(1, 0.15*cm)],
                [_assinatura_rl, HRFlowable(width=5.5*cm, thickness=0.8, color=COR_CINZA)],
                [Paragraph(f'<font size="7.5"><b>Data:</b> {timezone.now().strftime("%d/%m/%Y")}</font>', st('ass_data', fontSize=7.5)),
                 Paragraph(f'<font size="7.5"><b>{desp_nome}</b></font>',
                           st('ass_cli', fontSize=7.5, alignment=TA_CENTER))],
                [Paragraph('', st('ass_spc', fontSize=3)),
                 Paragraph(f'<font size="7">{desp_papel}</font>',
                           st('ass_papel', fontSize=7, alignment=TA_CENTER))],
            ]
            assinatura = Table(ass_data, colWidths=[W/2, W/2])
            assinatura.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
        else:
            ass_data = [
                [Paragraph('<b>Assinatura do Despachante:</b>', st('ass_lab', fontSize=8)),
                 Paragraph('', st('ass_spc', fontSize=8))],
                [Spacer(1, 0.2*cm), Spacer(1, 0.2*cm)],
                [HRFlowable(width=5.5*cm, thickness=0.8, color=COR_CINZA),
                 HRFlowable(width=5.5*cm, thickness=0.8, color=COR_CINZA)],
                [Paragraph(f'<font size="7.5"><b>Data:</b> _____/_____/______</font>', st('ass_data', fontSize=7.5)),
                 Paragraph(f'<font size="7.5"><b>{desp_nome}</b></font>',
                           st('ass_cli', fontSize=7.5, alignment=TA_CENTER))],
                [Paragraph('', st('ass_spc', fontSize=3)),
                 Paragraph(f'<font size="7">{desp_papel}</font>',
                           st('ass_papel', fontSize=7, alignment=TA_CENTER))],
            ]
            assinatura = Table(ass_data, colWidths=[W/2, W/2])
            assinatura.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))
        story.append(assinatura)
        story.append(Spacer(1, 0.15*cm))

        # ════════════════════════════════════════════════════════════════
        # RODAPÉ: HASH + PÁGINA/DATA (via NumberedCanvas)
        # ════════════════════════════════════════════════════════════════
        from reportlab.pdfgen import canvas as _pdf_canvas

        class _NumberedCanvas(_pdf_canvas.Canvas):
            def __init__(self, *args, **kwargs):
                _pdf_canvas.Canvas.__init__(self, *args, **kwargs)
                self._saved_page_states = []

            def showPage(self):
                self._saved_page_states.append(dict(self.__dict__))
                _pdf_canvas.Canvas.showPage(self)

            def save(self):
                num_pages = len(self._saved_page_states)
                for i, state in enumerate(self._saved_page_states):
                    self.__dict__.update(state)
                    self._draw_footer(i + 1, num_pages)
                    _pdf_canvas.Canvas.showPage(self)
                _pdf_canvas.Canvas.save(self)

            def _draw_footer(self, page_num, total_pages):
                self.saveState()
                self.setStrokeColor(colors.HexColor('#e2e2e2'))
                self.setLineWidth(0.5)
                self.line(0.7 * cm, 50, PAGE_W - 0.7 * cm, 50)
                self.setFont('Helvetica', 6)
                self.setFillColor(colors.HexColor('#94a3b8'))
                self.drawString(
                    0.7 * cm, 38,
                    f'{nome_banco_txt} - HASH  |  '
                    f'Processado por programa válido nº35/AGT/2019',
                )
                self.drawCentredString(
                    PAGE_W / 2, 25,
                    f'Pág. {page_num} / {total_pages}     '
                    f'{agora.strftime("%H:%M:%S")}     '
                    f'{agora.strftime("%d/%m/%Y")}',
                )
                self.restoreState()

        doc.build(story, canvasmaker=_NumberedCanvas)
        buffer.seek(0)

        nome_ficheiro = f'DU_{du.numero_du or du.du_uuid}.pdf'
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{nome_ficheiro}"'
        return response

    except ImportError:
        return HttpResponse(
            'ReportLab não instalado. Execute: pip install reportlab',
            status=500
        )
    except Exception:
        logger.exception("Erro ao gerar PDF da DU")
        return HttpResponse('Erro ao gerar PDF.', status=500)



def du_pesquisar(request):
    """API JSON — pesquisa DUs por código_processo (4+ dígitos) ou nome do cliente."""
    if not _sessao_ok(request):
        return JsonResponse({'resultados': []})
    if not _tem_permissao_ou_papel(request, 'gerir_aduaneiro', 'criar_declaracao_unica'):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)

    q     = request.GET.get('q', '').strip()
    papel = _papel(request)
    _, uid = _banca_owner(request)

    if len(q) < 2:
        return JsonResponse({'resultados': []})

    qs = escopo_du(request, DeclaracaoUnica.objects.all())

    qs = qs.filter(
        Q(codigo_processo__icontains=q) |
        Q(numero_du__icontains=q) |
        Q(exportador_nome__icontains=q) |
        Q(destinatario_nome__icontains=q) |
        Q(nome_declarante__icontains=q) |
        Q(ref_despachante__icontains=q)
    ).order_by('-created_at')[:10]

    resultados = [
        {
            'codigo_processo': du.codigo_processo or '',
            'numero_du':       du.numero_du or 'Rascunho',
            'cliente':         du.exportador_nome or du.nome_declarante or '—',
            'regime':          du.regime_aduaneiro or '—',
            'status':          du.status,
            'url':             f'/du/{du.du_uuid}/ver/',
        }
        for du in qs
    ]
    return JsonResponse({'resultados': resultados})


# ─── APIs de clientes (mantidas) ─────────────────────────────────────────────

def consultar_nif_cliente(request):
    """API para consultar NIF de clientes/exportadores dinamicamente."""
    if not _sessao_ok(request):
        return JsonResponse({'error': 'Não autorizado'}, status=401)
    if not _tem_permissao_ou_papel(request, 'criar_declaracao_unica'):
        return JsonResponse({'error': 'Sem permissão'}, status=403)

    nif = request.GET.get('nif', '').strip()
    if not nif:
        return JsonResponse({'error': 'NIF não fornecido'}, status=400)

    try:
        # Se for colaborador, usar o ID do dono da banca para filtrar clientes
        _, uid = _banca_owner(request)

        # 1. Procura exacta no próprio utilizador
        if len(nif) >= 4:
            cliente = Cliente.objects.filter(
                Q(nif__iexact=nif) & Q(usuario_id=uid) & Q(ativo=True)
            ).first()
            if cliente:
                return JsonResponse({'encontrado': True, 'dados': {
                    'nome': cliente.nome, 'nif': cliente.nif,
                    'endereco': cliente.localizacao,
                    'telefone': cliente.telefone or '',
                    'email': cliente.email or '',
                }})

        # 2. Procura exacta em todos os clientes (qualquer utilizador)
        if len(nif) >= 4:
            cliente = Cliente.objects.filter(
                Q(nif__iexact=nif) & Q(ativo=True)
            ).first()
            if cliente:
                return JsonResponse({'encontrado': True, 'dados': {
                    'nome': cliente.nome, 'nif': cliente.nif,
                    'endereco': cliente.localizacao,
                    'telefone': cliente.telefone or '',
                    'email': cliente.email or '',
                }})

        # 3. Sugestões parciais no próprio utilizador
        if len(nif) >= 3:
            sugestoes = Cliente.objects.filter(
                Q(nif__icontains=nif) & Q(usuario_id=uid) & Q(ativo=True)
            ).values('id', 'nome', 'nif', 'localizacao', 'telefone', 'email')[:8]
            if sugestoes:
                return JsonResponse({
                    'encontrado': False,
                    'sugestoes': list(sugestoes),
                    'mensagem': f'NIF {nif} não encontrado. Sugestões:',
                })

        # 4. Não encontrado — retornar erro sem permitir criação
        return JsonResponse({
            'encontrado': False,
            'sugestoes': [],
            'mensagem': f'Nenhum cliente encontrado com o NIF {nif}. Por favor, verifique o NIF ou crie o cliente na seção de Clientes.',
            'mostrar_formulario': False,
        })

    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


def criar_cliente_rapido(request):
    """API para criar cliente rapidamente via AJAX."""
    if not _sessao_ok(request):
        return JsonResponse({'error': 'Não autorizado'}, status=401)
    if not _tem_permissao_ou_papel(request, 'criar_declaracao_unica', 'gerir_clientes'):
        return JsonResponse({'error': 'Sem permissão'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)

    try:
        _, uid = _banca_owner(request)
        banca_id = request.session.get('banca_id')
        if not banca_id:
            from rh.models import Banca
            banca_obj = Banca.objects.filter(usuario_id=uid).first()
            banca_id = banca_obj.id if banca_obj else None
        filial_id = request.session.get('colaborador_filial_id') if request.session.get('tipo_usuario') == 'colaborador' else None
        nome       = request.POST.get('nome', '').strip()
        nif        = request.POST.get('nif', '').strip()
        localizacao = request.POST.get('localizacao', '').strip()
        telefone   = request.POST.get('telefone', '').strip()
        email      = request.POST.get('email', '').strip()
        observacoes = request.POST.get('observacoes', '').strip()

        if not nome or not nif or not localizacao:
            return JsonResponse({'error': 'Nome, NIF e Localização são obrigatórios'}, status=400)

        if Cliente.objects.filter(nif=nif, usuario_id=uid, ativo=True).exists():
            return JsonResponse({'error': 'Já existe um cliente com este NIF'}, status=400)

        if email and email_ja_existe(email):
            return JsonResponse({'error': 'Este email já está registado no sistema.'}, status=400)

        cliente = Cliente.objects.create(
            nome=nome, nif=nif, localizacao=localizacao,
            telefone=telefone, email=email, observacoes=observacoes,
            usuario_id=uid, banca_id=banca_id, filial_id=filial_id, ativo=True,
        )
        return JsonResponse({'sucesso': True, 'cliente': {
            'nome': cliente.nome, 'nif': cliente.nif,
            'endereco': cliente.localizacao,
            'telefone': cliente.telefone or '',
            'email': cliente.email or '',
        }, 'mensagem': f'Cliente "{nome}" criado com sucesso!'})

    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


# ─── Pauta Aduaneira ────────────────────────────────────────────────────────

def pauta_aduaneira_view(request):
    """Página de consulta da pauta aduaneira."""
    if not _sessao_ok(request):
        return redirect('login')
    if not _tem_permissao_ou_papel(request, 'ver_pauta_aduaneira'):
        return redirect('aduaneiro:du_lista')

    ctx = _ctx_base(request)
    ctx.update({
        'active_menu': 'Gestão Aduaneira',
        'active_sub': 'pauta_aduaneira',
    })
    return render(request, 'pauta_aduaneira.html', ctx)


# Dados base da Pauta Aduaneira de Angola (Sistema Harmonizado)
_PAUTA_BASE = [
    # Cap 01 — Animais vivos
    ('01011000', 'Cavalos reprodutores de raça pura', 0, 0, 'UN'),
    ('01012100', 'Cavalos para reprodução', 2, 0, 'UN'),
    ('01012900', 'Outros cavalos', 5, 0, 'UN'),
    ('01013000', 'Asininos (burros)', 5, 0, 'UN'),
    ('01022100', 'Bovinos reprodutores de raça pura', 0, 0, 'UN'),
    ('01022900', 'Outros bovinos vivos', 10, 0, 'UN'),
    ('01031000', 'Suínos reprodutores de raça pura', 0, 0, 'UN'),
    ('01039100', 'Suínos com peso inferior a 50 kg', 15, 0, 'UN'),
    ('01039200', 'Suínos com peso igual ou superior a 50 kg', 15, 0, 'UN'),
    ('01041000', 'Ovinos vivos', 5, 0, 'UN'),
    ('01042000', 'Caprinos vivos', 5, 0, 'UN'),
    ('01051100', 'Galinhas e galos domésticos', 2, 0, 'UN'),
    ('01051200', 'Perus e peruas', 2, 0, 'UN'),
    ('01051300', 'Patos', 2, 0, 'UN'),
    ('01051400', 'Gansos', 2, 0, 'UN'),
    ('01051900', 'Outras aves domésticas vivas', 5, 0, 'UN'),
    ('01061100', 'Primatas vivos', 0, 0, 'UN'),
    ('01061300', 'Camelos e outros camelídeos', 5, 0, 'UN'),
    ('01061400', 'Coelhos e lebres', 5, 0, 'UN'),
    # Cap 02 — Carnes e miudezas
    ('02011000', 'Carcaças e meias-carcaças de bovino, frescas ou refrigeradas', 20, 0, 'KG'),
    ('02012000', 'Outros cortes não desossados de bovino, frescos ou refrigerados', 20, 0, 'KG'),
    ('02013000', 'Carnes desossadas de bovino, frescas ou refrigeradas', 20, 0, 'KG'),
    ('02021000', 'Carcaças e meias-carcaças de bovino, congeladas', 20, 0, 'KG'),
    ('02022000', 'Outros cortes não desossados de bovino, congelados', 20, 0, 'KG'),
    ('02023000', 'Carnes desossadas de bovino, congeladas', 20, 0, 'KG'),
    ('02031100', 'Carcaças e meias-carcaças de suíno, frescas ou refrigeradas', 20, 0, 'KG'),
    ('02031200', 'Pernas, pás e pedaços de suíno, frescos ou refrigerados', 20, 0, 'KG'),
    ('02031900', 'Outras carnes de suíno, frescas ou refrigeradas', 20, 0, 'KG'),
    ('02032100', 'Carcaças e meias-carcaças de suíno, congeladas', 20, 0, 'KG'),
    ('02032200', 'Pernas, pás e pedaços de suíno, congelados', 20, 0, 'KG'),
    ('02032900', 'Outras carnes de suíno, congeladas', 20, 0, 'KG'),
    ('02071100', 'Frangos inteiros, frescos ou refrigerados', 30, 0, 'KG'),
    ('02071200', 'Frangos inteiros, congelados', 30, 0, 'KG'),
    ('02071300', 'Pedaços e miudezas de frango, frescos ou refrigerados', 30, 0, 'KG'),
    ('02071400', 'Pedaços e miudezas de frango, congelados', 30, 0, 'KG'),
    # Cap 03 — Peixes e crustáceos
    ('03011100', 'Trutas vivas', 5, 0, 'KG'),
    ('03011900', 'Outros peixes de água doce vivos', 5, 0, 'KG'),
    ('03024100', 'Atuns de barbatana amarela, frescos ou refrigerados', 10, 0, 'KG'),
    ('03025100', 'Arenques frescos ou refrigerados', 10, 0, 'KG'),
    ('03026100', 'Sardinhas frescas ou refrigeradas', 10, 0, 'KG'),
    ('03036300', 'Sardinhas congeladas', 10, 0, 'KG'),
    ('03037100', 'Atuns de barbatana amarela, congelados', 10, 0, 'KG'),
    ('03061100', 'Lagostas congeladas', 5, 0, 'KG'),
    ('03061700', 'Camarões congelados', 5, 0, 'KG'),
    # Cap 04 — Lacticínios
    ('04011000', 'Leite e nata, não concentrados, teor de gordura <= 1%', 5, 0, 'LT'),
    ('04012000', 'Leite e nata, não concentrados, teor de gordura > 1% e <= 6%', 5, 0, 'LT'),
    ('04021000', 'Leite em pó, teor de gordura <= 1,5%', 5, 0, 'KG'),
    ('04022100', 'Leite em pó, teor de gordura > 1,5%, sem adição de açúcar', 5, 0, 'KG'),
    ('04031000', 'Iogurte', 20, 0, 'KG'),
    ('04051000', 'Manteiga', 20, 0, 'KG'),
    ('04061000', 'Queijo fresco (não curado)', 20, 0, 'KG'),
    ('04062000', 'Queijo ralado ou em pó', 20, 0, 'KG'),
    ('04063000', 'Queijo fundido', 20, 0, 'KG'),
    ('04069000', 'Outros queijos', 20, 0, 'KG'),
    # Cap 09 — Café, chá, especiarias
    ('09011100', 'Café não torrado, não descafeinado', 0, 0, 'KG'),
    ('09011200', 'Café não torrado, descafeinado', 0, 0, 'KG'),
    ('09012100', 'Café torrado, não descafeinado', 20, 0, 'KG'),
    ('09012200', 'Café torrado, descafeinado', 20, 0, 'KG'),
    ('09021000', 'Chá verde (não fermentado), em embalagens <= 3 kg', 20, 0, 'KG'),
    ('09023000', 'Chá preto (fermentado), em embalagens <= 3 kg', 20, 0, 'KG'),
    ('09030000', 'Mate', 10, 0, 'KG'),
    ('09041100', 'Pimenta do género Piper, não triturada nem em pó', 20, 0, 'KG'),
    ('09041200', 'Pimenta do género Piper, triturada ou em pó', 20, 0, 'KG'),
    ('09051000', 'Baunilha, não triturada nem em pó', 10, 0, 'KG'),
    ('09061100', 'Canela e flores de caneleira, não trituradas nem em pó', 20, 0, 'KG'),
    ('09070000', 'Cravinho (frutos e pedúnculos)', 20, 0, 'KG'),
    ('09081100', 'Noz-moscada, não triturada nem em pó', 20, 0, 'KG'),
    ('09101100', 'Gengibre, não triturado nem em pó', 20, 0, 'KG'),
    ('09102000', 'Açafrão', 20, 0, 'KG'),
    ('09103000', 'Cúrcuma (açafrão-da-terra)', 20, 0, 'KG'),
    # Cap 10 — Cereais
    ('10011100', 'Trigo duro para sementeira', 2, 0, 'KG'),
    ('10011900', 'Outro trigo duro', 5, 0, 'KG'),
    ('10019900', 'Outro trigo mole e mistura de trigo e centeio', 5, 0, 'KG'),
    ('10030000', 'Cevada', 5, 0, 'KG'),
    ('10040000', 'Aveia', 5, 0, 'KG'),
    ('10051000', 'Milho para sementeira', 2, 0, 'KG'),
    ('10059000', 'Outro milho', 5, 0, 'KG'),
    ('10061000', 'Arroz em casca (arroz paddy)', 5, 0, 'KG'),
    ('10062000', 'Arroz descascado (arroz cargo ou castanho)', 5, 0, 'KG'),
    ('10063000', 'Arroz semibranqueado ou branqueado', 10, 0, 'KG'),
    ('10064000', 'Arroz partido', 10, 0, 'KG'),
    ('10070000', 'Sorgo de grão', 5, 0, 'KG'),
    ('10082900', 'Milho-miúdo', 5, 0, 'KG'),
    # Cap 22 — Bebidas
    ('22011000', 'Águas minerais e águas gaseificadas', 5, 0, 'LT'),
    ('22019000', 'Outras águas e gelo', 5, 0, 'LT'),
    ('22021000', 'Água, incluindo a mineral e a gaseificada, adicionada de açúcar', 20, 0, 'LT'),
    ('22029000', 'Outras bebidas não alcoólicas', 20, 0, 'LT'),
    ('22030000', 'Cerveja de malte', 30, 30, 'LT'),
    ('22041000', 'Champanhe e outros vinhos espumantes', 30, 30, 'LT'),
    ('22042100', 'Outros vinhos em recipientes <= 2 litros', 30, 30, 'LT'),
    ('22071000', 'Álcool etílico não desnaturado, teor alcoólico >= 80%', 30, 50, 'LT'),
    ('22082000', 'Aguardentes de vinho ou de bagaço de uvas', 30, 50, 'LT'),
    ('22083000', 'Uísque', 30, 50, 'LT'),
    ('22084000', 'Rum e tafia', 30, 50, 'LT'),
    ('22085000', 'Gin e genebra', 30, 50, 'LT'),
    ('22086000', 'Vodca', 30, 50, 'LT'),
    ('22089000', 'Outras bebidas espirituosas', 30, 50, 'LT'),
    # Cap 24 — Tabaco
    ('24011000', 'Tabaco não destalado', 30, 0, 'KG'),
    ('24012000', 'Tabaco total ou parcialmente destalado', 30, 0, 'KG'),
    ('24021000', 'Charutos e cigarrilhas, contendo tabaco', 30, 150, 'UN'),
    ('24022000', 'Cigarros contendo tabaco', 30, 150, 'UN'),
    ('24031100', 'Tabaco para cachimbo de água', 30, 100, 'KG'),
    # Cap 27 — Combustíveis minerais
    ('27090000', 'Óleos brutos de petróleo ou de minerais betuminosos', 0, 0, 'LT'),
    ('27101200', 'Gasolinas para motores', 5, 0, 'LT'),
    ('27101900', 'Outros óleos de petróleo leves', 5, 0, 'LT'),
    ('27102000', 'Óleos de petróleo contendo biodiesel', 5, 0, 'LT'),
    ('27111100', 'Gás natural liquefeito', 5, 0, 'KG'),
    ('27112100', 'Gás natural em estado gasoso', 5, 0, 'KG'),
    # Cap 30 — Produtos farmacêuticos
    ('30021000', 'Antissoros e outros componentes do sangue', 0, 0, 'KG'),
    ('30022000', 'Vacinas para medicina humana', 0, 0, 'KG'),
    ('30023000', 'Vacinas para medicina veterinária', 0, 0, 'KG'),
    ('30031000', 'Medicamentos contendo penicilinas ou estreptomicinas', 0, 0, 'KG'),
    ('30032000', 'Medicamentos contendo antibióticos', 0, 0, 'KG'),
    ('30039000', 'Outros medicamentos', 0, 0, 'KG'),
    ('30041000', 'Medicamentos contendo penicilinas, em doses', 0, 0, 'KG'),
    ('30049000', 'Outros medicamentos em doses', 0, 0, 'KG'),
    # Cap 84 — Máquinas e aparelhos mecânicos
    ('84071000', 'Motores de pistão para aviação', 5, 0, 'UN'),
    ('84072100', 'Motores fora de borda para embarcações', 10, 0, 'UN'),
    ('84073100', 'Motores de pistão para veículos, cilindrada <= 50 cm3', 10, 0, 'UN'),
    ('84073200', 'Motores de pistão para veículos, cilindrada > 50 cm3 e <= 250 cm3', 10, 0, 'UN'),
    ('84073300', 'Motores de pistão para veículos, cilindrada > 250 cm3 e <= 1000 cm3', 10, 0, 'UN'),
    ('84073400', 'Motores de pistão para veículos, cilindrada > 1000 cm3', 10, 0, 'UN'),
    ('84081000', 'Motores diesel para aviação', 5, 0, 'UN'),
    ('84082000', 'Motores diesel para veículos', 10, 0, 'UN'),
    ('84431100', 'Máquinas de impressão offset, de alimentação em bobinas', 5, 0, 'UN'),
    ('84713000', 'Máquinas de processamento de dados portáteis (laptops)', 5, 0, 'UN'),
    ('84714100', 'Outras máquinas de processamento de dados, com unidade central', 5, 0, 'UN'),
    ('84716000', 'Unidades de entrada ou saída de dados', 5, 0, 'UN'),
    # Cap 85 — Máquinas e aparelhos elétricos
    ('85011000', 'Motores de potência <= 37,5 W', 5, 0, 'UN'),
    ('85012000', 'Motores universais de potência > 37,5 W', 5, 0, 'UN'),
    ('85044000', 'Conversores estáticos (carregadores, inversores)', 10, 0, 'UN'),
    ('85176200', 'Aparelhos para recepção, conversão e transmissão de voz/dados', 10, 0, 'UN'),
    ('85177000', 'Partes de aparelhos de telefonia', 10, 0, 'UN'),
    ('85211000', 'Aparelhos de gravação ou reprodução de vídeo', 20, 0, 'UN'),
    ('85258000', 'Câmaras de televisão, câmaras digitais e câmaras de vídeo', 20, 0, 'UN'),
    ('85271200', 'Rádios para veículos automóveis', 20, 0, 'UN'),
    ('85272100', 'Rádios portáteis', 20, 0, 'UN'),
    ('85281200', 'Monitores de televisão a cores', 20, 0, 'UN'),
    ('85287200', 'Outros aparelhos receptores de televisão a cores', 20, 0, 'UN'),
    # Cap 87 — Veículos automóveis
    ('87011000', 'Motocultores', 5, 0, 'UN'),
    ('87012000', 'Tractores rodoviários para semi-reboques', 5, 0, 'UN'),
    ('87019000', 'Outros tractores', 5, 0, 'UN'),
    ('87021000', 'Veículos para transporte de 10 ou mais pessoas, motor diesel', 5, 0, 'UN'),
    ('87029000', 'Outros veículos para transporte de 10 ou mais pessoas', 5, 0, 'UN'),
    ('87031000', 'Veículos especialmente concebidos para deslocação na neve', 10, 0, 'UN'),
    ('87032100', 'Automóveis de cilindrada <= 1000 cm3', 30, 0, 'UN'),
    ('87032200', 'Automóveis de cilindrada > 1000 cm3 e <= 1500 cm3', 30, 0, 'UN'),
    ('87032300', 'Automóveis de cilindrada > 1500 cm3 e <= 3000 cm3', 30, 0, 'UN'),
    ('87032400', 'Automóveis de cilindrada > 3000 cm3', 30, 0, 'UN'),
    ('87033100', 'Automóveis diesel de cilindrada <= 1500 cm3', 30, 0, 'UN'),
    ('87033200', 'Automóveis diesel de cilindrada > 1500 cm3 e <= 2500 cm3', 30, 0, 'UN'),
    ('87033300', 'Automóveis diesel de cilindrada > 2500 cm3', 30, 0, 'UN'),
    ('87042100', 'Veículos para transporte de mercadorias, diesel, <= 5 ton', 10, 0, 'UN'),
    ('87042200', 'Veículos para transporte de mercadorias, diesel, > 5 ton', 10, 0, 'UN'),
    ('87051000', 'Veículos-grua', 5, 0, 'UN'),
    ('87060000', 'Chassis com motor para veículos automóveis', 10, 0, 'UN'),
    ('87089900', 'Outras partes e acessórios de veículos automóveis', 20, 0, 'UN'),
    # Cap 90 — Instrumentos e aparelhos de óptica
    ('90181100', 'Electrocardiógrafos', 0, 0, 'UN'),
    ('90181200', 'Aparelhos de diagnóstico por ultrassom', 0, 0, 'UN'),
    ('90181300', 'Aparelhos de diagnóstico por ressonância magnética', 0, 0, 'UN'),
    ('90181400', 'Aparelhos de cintilografia', 0, 0, 'UN'),
    ('90181900', 'Outros aparelhos de electro-diagnóstico', 0, 0, 'UN'),
    ('90192000', 'Aparelhos de ozonioterapia, oxigenoterapia, aerossolterapia', 0, 0, 'UN'),
    ('90211000', 'Artigos e aparelhos de ortopedia', 0, 0, 'UN'),
    ('90213100', 'Articulações artificiais', 0, 0, 'UN'),
    ('90214000', 'Aparelhos para facilitar a audição dos surdos', 0, 0, 'UN'),
]


def pauta_aduaneira_api(request):
    """API de pesquisa da pauta aduaneira — busca dados reais da API externa."""
    if not _sessao_ok(request):
        return JsonResponse({'erro': 'Não autorizado'}, status=401)
    if not _tem_permissao_ou_papel(request, 'ver_pauta_aduaneira'):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)

    q_codigo    = request.GET.get('codigo',    '').strip().upper()
    q_descricao = request.GET.get('descricao', '').strip().lower()
    q_capitulo  = request.GET.get('capitulo',  '').strip()

    try:
        import ssl
        import urllib.request as _urllib
        from utils.ssl_utils import ssl_context_relaxado
        api_url = 'https://api-sic-fields.netsulwel.tech/pautas'

        req = _urllib.Request(
            api_url,
            headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
            }
        )
        with _urllib.urlopen(req, timeout=15, context=ssl_context_relaxado()) as resp:
            dados_api = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Erro ao carregar pauta aduaneira: {e}')
        dados_api = []

    # Filtrar e normalizar
    resultados = []
    for item in dados_api:
        # Ignorar itens inactivos
        if not item.get('ativo', True):
            continue

        codigo    = str(item.get('codigo_sh', '') or '').strip()
        descricao = str(item.get('descricao_mercadoria', '') or '').strip()
        aliquota  = item.get('direito_importacao', 0) or 0
        iec       = item.get('direito_consumo', 0) or 0
        iva       = item.get('iva', 0) or 0
        unidade   = str(item.get('unidade_medida', 'UN') or 'UN').strip()
        cap_num   = item.get('capitulo', '')
        cap_str   = str(cap_num).zfill(2) if cap_num else ''
        fonte     = str(item.get('fonte', '') or '').strip()
        obs       = str(item.get('observacoes', '') or '').strip()

        # Aplicar filtros
        if q_codigo and q_codigo not in codigo.upper():
            continue
        if q_descricao and q_descricao not in descricao.lower():
            continue
        if q_capitulo and cap_str != q_capitulo.zfill(2):
            continue

        resultados.append({
            'codigo':    codigo,
            'descricao': descricao,
            'aliquota':  aliquota,
            'iec':       iec,
            'iva':       iva,
            'unidade':   unidade,
            'capitulo':  cap_str,
            'fonte':     fonte,
            'obs':       obs,
        })

    # Ordenar por código
    resultados.sort(key=lambda x: x['codigo'])

    tem_filtro = bool(q_codigo or q_descricao or q_capitulo)

    # Sem filtros — devolver apenas os primeiros 5
    if not tem_filtro:
        resultados = resultados[:5]

    return JsonResponse({'resultados': resultados, 'total': len(resultados)})


# ─── API de Vinhetas (proxy ao portal CDOA) ──────────────────────────────────

def api_vinhetas(request):
    """
    Proxy ao endpoint do portal CDOA para buscar as vinhetas do utilizador autenticado.
    Usa a cédula guardada na sessão para filtrar as vinhetas desse utilizador.
    Devolve apenas vinhetas com status_utilizacao == 'NAO_UTILIZADO'.
    """
    if not _sessao_ok(request):
        return JsonResponse({'erro': 'Não autorizado'}, status=401)
    if not _tem_permissao_ou_papel(request, 'criar_declaracao_unica'):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)

    # Se for colaborador, usar a cédula do dono da banca
    if request.session.get('tipo_usuario') == 'colaborador':
        dono, _ = _banca_owner(request)
        if dono:
            usuario_sessao = {'cedula': dono.cedula or ''}
        else:
            usuario_sessao = request.session.get('usuario', {})
    else:
        usuario_sessao = request.session.get('usuario', {})

    cedula = usuario_sessao.get('cedula', '').strip()

    if not cedula:
        # Tentar buscar directamente da base de dados
        try:
            uid = _usuario_id(request)
            u = Usuario.objects.get(id=uid)
            cedula = (u.cedula or '').strip()
        except Usuario.DoesNotExist:
            pass

    if not cedula:
        return JsonResponse({
            'erro': 'Cédula não configurada no perfil. Por favor, actualize o seu perfil.',
            'vinhetas': [],
        }, status=400)

    import urllib.request as _urllib_req
    import urllib.error as _urllib_err
    from utils.ssl_utils import ssl_context_relaxado

    portal_url = 'https://portal.cdoangola.co.ao/controllers/sicdoa-vinhetas.php'
    payload = json.dumps({'cedula': cedula}).encode('utf-8')

    try:
        req = _urllib_req.Request(
            portal_url,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'SICDOA/1.0',
            },
            method='POST',
        )
        with _urllib_req.urlopen(req, timeout=15, context=ssl_context_relaxado()) as resp:
            dados = json.loads(resp.read().decode('utf-8'))

    except _urllib_err.HTTPError as exc:
        # 404 ou qualquer HTTP error — mensagem amigável
        if exc.code == 404:
            return JsonResponse({
                'sem_vinhetas': True,
                'mensagem': 'Nenhuma vinheta disponível para a sua cédula.',
                'vinhetas': [],
            })
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Nenhuma vinheta disponível.',
            'vinhetas': [],
        })
    except _urllib_err.URLError:
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Não foi possível contactar o portal CDOA. Verifique a sua ligação.',
            'vinhetas': [],
        })
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Nenhuma vinheta disponível.',
            'vinhetas': [],
        })
    except Exception:
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Nenhuma vinheta disponível.',
            'vinhetas': [],
        })

    # Verificar status da resposta do portal (404 lógico ou utilizador não encontrado)
    if dados.get('status') != 200:
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Nenhuma vinheta disponível para a sua cédula.',
            'vinhetas': [],
        })

    # Filtrar apenas vinhetas não utilizadas
    todas_vinhetas = dados.get('vinhetas', [])
    vinhetas_disponiveis = [
        v for v in todas_vinhetas
        if v.get('status_utilizacao') == 'NAO_UTILIZADO' and v.get('estado') == '1'
    ]

    despachante = dados.get('despachante', {})

    return JsonResponse({
        'sucesso': True,
        'cedula': cedula,
        'despachante': {
            'nome': f"{despachante.get('nome', '')} {despachante.get('apelido', '')}".strip(),
            'nif': despachante.get('nif', ''),
        },
        'total_vinhetas': dados.get('total_vinhetas', 0),
        'total_disponiveis': len(vinhetas_disponiveis),
        'vinhetas': [
            {
                'id': v.get('id'),
                'vinheta': v.get('vinheta', ''),
                'valor': v.get('valor', 0),
                'created_at': v.get('created_at', ''),
            }
            for v in vinhetas_disponiveis
        ],
    })


# ─── DU — Histórico de Versões ─────────────────────────────────────────


@requer_sessao_ativa
def du_historico(request, du_uuid):
    try:
        du = DeclaracaoUnica.objects.get(du_uuid=du_uuid)
    except DeclaracaoUnica.DoesNotExist:
        messages.error(request, 'Declaração Única não encontrada.')
        return redirect('aduaneiro:du_lista')

    historicos = du.historico_versoes.all().order_by('-criado_em')

    ctx = _ctx_base(request)
    ctx['active_menu'] = 'Aduaneiro'
    ctx['active_sub'] = 'du'
    ctx['du'] = du
    # Parse campos_alterados de JSON string para dict
    for h in historicos:
        h.campos_alterados_dict = h.get_campos_alterados_dict()
    ctx['historicos'] = historicos
    ctx['total_versoes'] = historicos.count()

    return render(request, 'aduaneiro/du_historico.html', ctx)
