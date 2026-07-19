from django.db.models import prefetch_related_objects

from .models import Usuario, Permissao

# ── Permissões exclusivas do sistema institucional ──────────────────
# (nunca atribuíveis via cargo da banca)
# Estas permissões são apresentadas no form de criação/edição de Funções.

PERMISSOES_INSTITUCIONAIS = [
    # RH Institucional (módulos operacionais)
    'gerir_colaboradores_inst',
    'gerir_presencas_inst',
    'gerir_ferias_inst',
    'gerir_avaliacoes_inst',
    'processar_salarios_inst',
    'gerir_recrutamento_inst',
    'gerir_subsidios_inst',
    # Administração
    'gerir_utilizadores',
    # Super-Admin (nunca atribuível a Funções — apenas via papel)
    'admin',
]

# ── Permissões que NÃO podem ser atribuídas a Funções ───────────────
# Estas permissões são demasiado poderosas para delegação via Funcao.
# O acesso é concedido exclusivamente via papel do Utilizador.

PERMISSOES_NAO_ATRIBUIVEIS_FUNCAO = []

# ── Permissões exclusivas da Banca ─────────────────────────────────
# (só o Despachante concede via CargoBanca — NÃO alterar)

PERMISSOES_BANCA = [
    # Gestão Aduaneira
    'gerir_aduaneiro', 'criar_declaracao_unica', 'ver_pauta_aduaneira',
    'gerir_clientes', 'gerir_clientes_filial',
    'gerir_aduaneiro_filial',
    # Filial
    'gerir_filial',
    # RH
    'gerir_rh', 'gerir_rh_filial',
    'ver_minha_banca', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
    'gerir_processamento_salarial', 'gerir_recrutamento_banca',
    'gerir_presencas_banca', 'gerir_avaliacoes_banca',
    # Financeiro
    'gerir_financeiro', 'gerir_financeiro_filial',
    'ver_requisicoes', 'ver_recibos', 'ver_notas_financeiro',
    'ver_facturas', 'ver_conta_corrente', 'ver_relatorios_financeiros',
    # Governança
    'gerir_governanca',
    # Colaborador
    'alterar_perfil',
    # Administração
    'ver_logs_banca',
    # Super
    'admin_banca',
]

# ── Permissões que o Gestor de Filial pode atribuir ─────────────────
# Estas são as permissões que o gestor pode conceder aos
# colaboradores da sua filial para aceder a recursos do negócio.

PERMISSOES_FILIAL_GESTOR = [
    # Financeiro
    {'grupo': 'Financeiro', 'icone': 'fa-file-invoice-dollar', 'permissoes': [
        {'codigo': 'ver_requisicoes',           'nome': 'Ver Requisições de Fundos'},
        {'codigo': 'ver_recibos',               'nome': 'Ver Recibos'},
        {'codigo': 'ver_notas_financeiro',      'nome': 'Ver Notas (Crédito/Débito)'},
        {'codigo': 'ver_facturas',              'nome': 'Ver Facturas'},
        {'codigo': 'ver_conta_corrente',        'nome': 'Ver Conta Corrente'},
        {'codigo': 'ver_relatorios_financeiros','nome': 'Ver Relatórios Financeiros'},
    ]},
    # Aduaneiro
    {'grupo': 'Aduaneiro', 'icone': 'fa-file-alt', 'permissoes': [
        {'codigo': 'criar_declaracao_unica',    'nome': 'Criar Declaração Única'},
        {'codigo': 'ver_pauta_aduaneira',       'nome': 'Ver Pauta Aduaneira'},
        {'codigo': 'gerir_clientes',            'nome': 'Gerir Clientes'},
    ]},
    # RH
    {'grupo': 'Recursos Humanos', 'icone': 'fa-users-cog', 'permissoes': [
        {'codigo': 'gerir_presencas_banca',     'nome': 'Gerir Presenças'},
        {'codigo': 'gerir_avaliacoes_banca',    'nome': 'Gerir Avaliações'},
    ]},
]

# ── Permissões partilhadas (Institucional + Governance) ────────────
# Estas permissões estão no sistema de governance e podem ser
# atribuídas tanto a Despachantes (via CargoBanca) como a
# Colaboradores Institucionais (via Funcao).

PERMISSOES_GOVERNANCA = [
    'gerir_assembleia', 'gerir_atas', 'gerir_consultas',
    'gerir_votacoes', 'ser_membro_mesa', 'gerir_convocatorias',
    'ver_secretaria', 'gerir_documentos',
    'gerir_quotas', 'ver_quotas',
    'acesso_auditoria',
    'ver_relatorios_operacionais',
]

# ── Estrutura de menus para o form de Funções ──────────────────────
# Cada menu espelha a sidebar. O administrador decide qual submenu
# conceder a cada Colaborador Institucional.

PERMISSOES_POR_MENU_INST = [
    {
        'nome': 'Administração do Sistema',
        'icone': 'fa-shield-alt',
        'permissoes': [
            {'nome': 'Administrador do Sistema', 'descricao': 'Acesso total a todos os módulos e funcionalidades. Indicado para Presidente e Vice-Presidente.', 'codigo': 'admin'},
        ],
    },
    {
        'nome': 'Gestão de Utilizadores',
        'icone': 'fa-user-cog',
        'permissoes': [
            {'nome': 'Utilizadores', 'descricao': 'Criar, editar e gerir todos os utilizadores do sistema', 'codigo': 'gerir_utilizadores'},
        ],
    },
    {
        'nome': 'RH Institucional',
        'icone': 'fa-building',
        'permissoes': [
            {'nome': 'Colaboradores', 'descricao': 'Gerir colaboradores da equipa administrativa', 'codigo': 'gerir_colaboradores_inst'},
            {'nome': 'Processamento Salarial', 'descricao': 'Processar salários e gerar recibos', 'codigo': 'processar_salarios_inst'},
            {'nome': 'Recrutamento', 'descricao': 'Gerir vagas, candidaturas e entrevistas', 'codigo': 'gerir_recrutamento_inst'},
            {'nome': 'Presenças', 'descricao': 'Registar e aprovar presenças dos colaboradores', 'codigo': 'gerir_presencas_inst'},
            {'nome': 'Férias', 'descricao': 'Aprovar ou rejeitar pedidos de férias', 'codigo': 'gerir_ferias_inst'},
            {'nome': 'Avaliação de Desempenho', 'descricao': 'Criar ciclos e avaliar colaboradores', 'codigo': 'gerir_avaliacoes_inst'},
            {'nome': 'Subsídios', 'descricao': 'Configurar subsídios salariais', 'codigo': 'gerir_subsidios_inst'},
        ],
    },
    {
        'nome': 'CDOA Governança',
        'icone': 'fa-vote-yea',
        'permissoes': [
            {'nome': 'Assembleias / Votações', 'descricao': 'Gerir assembleias, votações e convocatórias', 'codigo': 'gerir_assembleia'},
            {'nome': 'Atas & Decretos', 'descricao': 'Assinar e publicar atas e decretos', 'codigo': 'gerir_atas'},
            {'nome': 'Secretaria - Documentos', 'descricao': 'Acesso à secretaria e gestão de documentos', 'codigo': 'ver_secretaria'},
            {'nome': 'Gestão de Quotas', 'descricao': 'Atribuir, definir e gerir quotas anuais', 'codigo': 'gerir_quotas'},
            {'nome': 'Escuta Activa', 'descricao': 'Gerir consultas públicas', 'codigo': 'gerir_consultas'},
            {'nome': 'Membros da Mesa', 'descricao': 'Pertencer à mesa da assembleia', 'codigo': 'ser_membro_mesa'},
        ],
    },
    {
        'nome': 'Gestão Financeira',
        'icone': 'fa-credit-card',
        'permissoes': [
            {'nome': 'Relatórios Operacionais', 'descricao': 'Visualizar relatórios com dados de todos os despachantes', 'codigo': 'ver_relatorios_operacionais'},
            {'nome': 'Acesso de Auditoria', 'descricao': 'Acesso de leitura a todos os módulos do sistema', 'codigo': 'acesso_auditoria'},
        ],
    },
    {
        'nome': 'Logs de Atividade',
        'icone': 'fa-history',
        'permissoes': [
            {'nome': 'Ver Logs de Atividade', 'descricao': 'Consultar registo de atividades de todos os utilizadores', 'codigo': 'acesso_auditoria'},
        ],
    },
]

PERMISSOES_AUTO_DESPACHANTE = ['alterar_perfil']


def _is_admin_ou_acesso_total(request):
    """True se papel=Administrador ou tiver permissão 'admin' (direta, via função, ou via cargo_banca)."""
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Administrador':
        return True
    usuario_id = request.session.get('usuario_id')
    if not usuario_id:
        return False
    if Usuario.objects.filter(
        pk=usuario_id, permissoes_diretas__codigo='admin'
    ).exists():
        return True
    if Usuario.objects.filter(
        pk=usuario_id, papel='Colaborador Institucional', funcao__permissoes__codigo='admin'
    ).exists():
        return True
    # Colaborador da Banca: verificar cargo_banca (admin_banca não concede acesso total ao sistema)
    if request.session.get('tipo_usuario') == 'colaborador':
        colaborador_id = request.session.get('colaborador_id')
        if colaborador_id:
            from rh.models import Colaborador
            if Colaborador.objects.filter(
                pk=colaborador_id, estado='Ativo', cargo_banca__permissoes__codigo='admin'
            ).exists():
                return True
    return False


def _get_usuario_funcao_permissoes(usuario):
    """Retorna set de códigos de permissão vindos da função do usuário."""
    if not usuario or not usuario.funcao_id:
        return set()
    return set(usuario.funcao.permissoes.values_list('codigo', flat=True))


def get_usuario_permissoes(request):
    """Retorna set de códigos de permissão do usuário logado (diretas + função + cargo banca)."""
    if not request.session.get('usuario_id'):
        return set()
    if _is_admin_ou_acesso_total(request):
        return set(Permissao.objects.values_list('codigo', flat=True))
    # Colaboradores: as permissões vêm do cargo_banca (consulta à BD em tempo real)
    if request.session.get('tipo_usuario') == 'colaborador':
        colaborador_id = request.session.get('colaborador_id')
        if colaborador_id:
            from rh.models import Colaborador
            try:
                col = Colaborador.objects.select_related('cargo_banca').prefetch_related(
                    'cargo_banca__permissoes', 'permissoes_filiais'
                ).get(pk=colaborador_id, estado='Ativo')
                permissoes = set()
                if col.cargo_banca_id:
                    permissoes = set(col.cargo_banca.permissoes.values_list('codigo', flat=True))
                # Permissões adicionais atribuídas pelo gestor de filial
                permissoes.update(col.permissoes_filiais.values_list('codigo', flat=True))
                if 'admin' in permissoes:
                    return set(Permissao.objects.values_list('codigo', flat=True))
                if 'admin_banca' in permissoes:
                    return set(Permissao.objects.filter(
                        codigo__in=PERMISSOES_BANCA
                    ).values_list('codigo', flat=True))
                if 'acesso_auditoria' in permissoes:
                    ver_codigos = set(Permissao.objects.filter(codigo__startswith='ver_').values_list('codigo', flat=True))
                    permissoes.update(ver_codigos)
                return permissoes
            except Colaborador.DoesNotExist:
                pass
        # Institucional sem Colaborador RH (tipo_usuario='colaborador' mas sem registro rh)
        # → resolver permissões via tabela usuarios (funcao + permissoes_diretas)
        usuario_id = request.session['usuario_id']
        usuario = Usuario.objects.filter(pk=usuario_id).select_related('funcao').prefetch_related(
            'permissoes_diretas'
        ).first()
        if usuario:
            permissoes = set(usuario.permissoes_diretas.values_list('codigo', flat=True))
            if usuario.papel == 'Colaborador Institucional':
                permissoes.update(_get_usuario_funcao_permissoes(usuario))
            if 'acesso_auditoria' in permissoes:
                ver_codigos = set(Permissao.objects.filter(codigo__startswith='ver_').values_list('codigo', flat=True))
                permissoes.update(ver_codigos)
            return permissoes
        return set()
    usuario_id = request.session['usuario_id']
    usuario = Usuario.objects.filter(pk=usuario_id).select_related('funcao').prefetch_related(
        'permissoes_diretas'
    ).first()
    if not usuario:
        return set()
    permissoes = set(usuario.permissoes_diretas.values_list('codigo', flat=True))
    if usuario.papel == 'Despachante Oficial':
        permissoes.update(PERMISSOES_AUTO_DESPACHANTE)
    if usuario.papel == 'Colaborador Institucional':
        permissoes.update(_get_usuario_funcao_permissoes(usuario))
    if 'acesso_auditoria' in permissoes:
        ver_codigos = set(Permissao.objects.filter(codigo__startswith='ver_').values_list('codigo', flat=True))
        permissoes.update(ver_codigos)
    return permissoes


def usuario_tem_permissao(request, codigo):
    """Verifica se o usuário logado tem uma permissão específica."""
    if not request.session.get('usuario_id'):
        return False
    if _is_admin_ou_acesso_total(request):
        return True
    # Colaborador: verificar permissões do cargo_banca na BD em tempo real
    if request.session.get('tipo_usuario') == 'colaborador':
        return codigo in get_usuario_permissoes(request)
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Despachante Oficial' and codigo in PERMISSOES_AUTO_DESPACHANTE:
        return True
    usuario_id = request.session['usuario_id']
    if codigo.startswith('ver_'):
        if Usuario.objects.filter(pk=usuario_id, permissoes_diretas__codigo='acesso_auditoria').exists():
            return True
    return Usuario.objects.filter(
        pk=usuario_id, permissoes_diretas__codigo=codigo
    ).exists() or Usuario.objects.filter(
        pk=usuario_id, papel='Colaborador Institucional', funcao__permissoes__codigo=codigo
    ).exists()


def usuario_obj_tem_permissao(usuario, codigo):
    """Verifica se um objecto Usuario tem uma permissão específica."""
    if not usuario:
        return False
    if usuario.papel == 'Administrador':
        return True
    if usuario.permissoes_diretas.filter(codigo='admin').exists():
        return True
    if usuario.papel == 'Colaborador Institucional':
        if usuario.funcao and usuario.funcao.permissoes.filter(codigo=codigo).exists():
            return True
    return Usuario.objects.filter(
        pk=usuario.pk, permissoes_diretas__codigo=codigo
    ).exists()
