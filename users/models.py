from django.db import models


class Usuario(models.Model):
    PAPEIS = [
        ('Administrador', 'Administrador'),
        ('Gestor Financeiro', 'Gestor Financeiro'),
        ('Despachante Oficial', 'Despachante Oficial'),
        ('Operador', 'Operador'),
        ('Colaborador Institucional', 'Colaborador Institucional'),
        ('Visualizador', 'Visualizador'),
    ]

    STATUS_CHOICES = [
        ('Ativo', 'Ativo'),
        ('Inativo', 'Inativo'),
        ('Suspenso', 'Suspenso'),
    ]

    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255, null=True, blank=True)
    nome = models.CharField(max_length=100, db_index=True)
    email = models.EmailField(max_length=100, unique=True)
    foto = models.CharField(max_length=255, null=True, blank=True)
    telefone = models.CharField(max_length=20, null=True, blank=True)
    cedula = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    papel = models.CharField(max_length=50, choices=PAPEIS, default='Despachante Oficial', db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Ativo', db_index=True)
    is_staff = models.BooleanField(default=False, verbose_name='Acesso ao Admin')
    is_superuser = models.BooleanField(default=False, verbose_name='Superutilizador')
    categoria = models.ForeignKey('governanca.CategoriaMembro', on_delete=models.SET_NULL, null=True, blank=True)
    sso_portal_id = models.IntegerField(null=True, blank=True)
    ultimo_acesso = models.DateTimeField(null=True, blank=True)
    nif = models.TextField(blank=True, default='')
    is_secretario = models.BooleanField(default=False)
    is_vice_secretario = models.BooleanField(default=False)
    permissoes_diretas = models.ManyToManyField('Permissao', blank=True, related_name='usuarios_diretos')
    funcao = models.ForeignKey('Funcao', null=True, blank=True, on_delete=models.SET_NULL, related_name='usuarios')
    area_actuacao = models.CharField(max_length=100, blank=True, default='')
    cargo_personalizado = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'usuarios'
        managed = True
        verbose_name = 'Utilizador'
        verbose_name_plural = 'Utilizadores'
        indexes = [
            models.Index(fields=['papel', 'status'], name='idx_usuario_papel_status'),
        ]

    @property
    def is_active(self):
        return self.status == 'Ativo'

    def has_perm(self, perm, obj=None):
        if not self.is_staff:
            return False
        if self.is_superuser:
            return True
        if self.papel not in ('Administrador', 'Gestor Financeiro'):
            return False
        perms_ok = {
            'financeiro.view_requisicaofundo',
            'financeiro.change_requisicaofundo',
        }
        if self.papel == 'Administrador':
            perms_ok.add('financeiro.delete_requisicaofundo')
        return perm in perms_ok

    def has_module_perms(self, app_label):
        if not self.is_staff:
            return False
        if self.is_superuser:
            return True
        if self.papel not in ('Administrador', 'Gestor Financeiro'):
            return False
        return app_label == 'financeiro'

    def has_perms(self, perm_list, obj=None):
        return all(self.has_perm(p, obj) for p in perm_list)

    def get_group_permissions(self, obj=None):
        return set()

    def get_all_permissions(self, obj=None):
        if not self.is_staff:
            return set()
        if self.is_superuser:
            return {'financeiro.view_requisicaofundo', 'financeiro.change_requisicaofundo',
                    'financeiro.delete_requisicaofundo'}
        base = {'financeiro.view_requisicaofundo', 'financeiro.change_requisicaofundo',
                'financeiro.delete_requisicaofundo' if self.papel == 'Administrador' else '',
               }
        return {p for p in base if p}

    def get_user_permissions(self, obj=None):
        return set()

    def __str__(self):
        return f"{self.nome} ({self.papel})"


class Funcao(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True, default='')
    permissoes = models.ManyToManyField('Permissao', blank=True, related_name='funcoes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'funcoes'
        verbose_name = 'Função'
        verbose_name_plural = 'Funções'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Permissao(models.Model):
    codigo = models.SlugField(max_length=100, unique=True,
        help_text='Identificador único (ex: ver_secretaria, gerir_quotas)')
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True, default='')
    grupo = models.CharField(max_length=100, blank=True, default='',
        help_text='Agrupamento visual (ex: Secretaria, Financeiro)')
    icone = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'permissoes'
        verbose_name = 'Permissão'
        verbose_name_plural = 'Permissões'
        ordering = ['grupo', 'nome']

    def __str__(self):
        return self.nome


class LogAtividade(models.Model):
    """Registo cronológico de todas as acções dos utilizadores no sistema."""

    ACOES = [
        ('LOGIN', 'Login'),
        ('LOGIN_FALHA', 'Tentativa de login falhada'),
        ('LOGOUT', 'Logout'),
        ('SESSAO_EXPIRADA', 'Sessão expirada'),
        ('VIEW', 'Visualização'),
        ('CREATE', 'Criação'),
        ('EDIT', 'Edição'),
        ('DELETE', 'Eliminação'),
        ('CANCEL', 'Cancelamento'),
        ('APPROVE', 'Aprovação'),
        ('REJECT', 'Rejeição'),
        ('SEND_EMAIL', 'Envio de Email'),
        ('EXPORT', 'Exportação'),
        ('DOWNLOAD', 'Download'),
        ('OUTRO', 'Outro'),
    ]

    MODULOS = [
        ('users', 'Utilizadores'),
        ('clientes', 'Clientes'),
        ('financeiro', 'Financeiro'),
        ('governanca', 'Governança'),
        ('rh', 'Recursos Humanos'),
        ('aduaneiro', 'Aduaneiro'),
        ('sistema', 'Sistema'),
    ]

    usuario = models.ForeignKey('Usuario', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='logs_atividade', verbose_name='Utilizador')
    usuario_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Utilizador')
    email = models.EmailField(max_length=254, blank=True, default='', verbose_name='Email')
    accao = models.CharField(max_length=20, choices=ACOES, verbose_name='Ação')
    modulo = models.CharField(max_length=20, choices=MODULOS, verbose_name='Módulo')
    descricao = models.TextField(blank=True, default='', verbose_name='Descrição')
    modelo_alvo = models.CharField(max_length=100, blank=True, default='', verbose_name='Modelo Alvo')
    id_alvo = models.IntegerField(null=True, blank=True, verbose_name='ID do Registo')
    detalhes = models.JSONField(null=True, blank=True, verbose_name='Detalhes')
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='Endereço IP')
    user_agent = models.TextField(blank=True, default='', verbose_name='User-Agent')
    url = models.TextField(blank=True, default='', verbose_name='URL Acedido')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Data/Hora')

    class Meta:
        db_table = 'logs_atividade'
        verbose_name = 'Log de Atividade'
        verbose_name_plural = 'Logs de Atividade'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at:%d/%m/%Y %H:%M}] {self.usuario_nome} — {self.accao} ({self.modulo})"


def registrar_log(request, accao, modulo='sistema', descricao='',
                  modelo_alvo='', id_alvo=None, detalhes=None, email_forcado=''):
    """Regista uma atividade no log."""
    from django.utils import timezone
    uid = request.session.get('usuario_id') if request else None
    if uid is not None and not Usuario.objects.filter(pk=uid).exists():
        uid = None
    LogAtividade.objects.create(
        usuario_id=uid,
        usuario_nome=request.session.get('usuario', {}).get('nome', '') if request else '',
        email=email_forcado or (request.session.get('usuario', {}).get('email', '') if request else ''),
        accao=accao,
        modulo=modulo,
        descricao=descricao,
        modelo_alvo=modelo_alvo,
        id_alvo=id_alvo,
        detalhes=detalhes,
        ip=request.META.get('REMOTE_ADDR', '') if request else '',
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500] if request else '',
        url=request.build_absolute_uri() if request else '',
        created_at=timezone.now(),
    )


# ─── Colaborador Institucional ─────────────────────────────────────────────

class ColaboradorInstitucional(models.Model):
    AREAS = [
        ('Informática', 'Informática'),
        ('Limpeza', 'Limpeza'),
        ('Administrativo', 'Administrativo'),
        ('Financeiro', 'Financeiro'),
        ('Jurídico', 'Jurídico'),
        ('Recursos Humanos', 'Recursos Humanos'),
        ('Comunicação', 'Comunicação'),
        ('Outro', 'Outro'),
    ]
    ESTADOS = [
        ('Ativo', 'Ativo'),
        ('Inativo', 'Inativo'),
        ('Suspenso', 'Suspenso'),
        ('Ferias', 'De Férias'),
    ]

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='colaborador_institucional')
    nome = models.CharField(max_length=255, db_index=True)
    email = models.EmailField(blank=True, default='')
    telefone = models.CharField(max_length=30, blank=True, default='')
    area_actuacao = models.CharField(max_length=100, blank=True, default='', db_index=True)
    data_admissao = models.DateField(null=True, blank=True)
    salario_base = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default='Ativo', db_index=True)
    foto = models.ImageField(upload_to='colaboradores_institucionais/fotos/', null=True, blank=True)
    observacoes = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'colaboradores_institucionais'
        verbose_name = 'Colaborador Institucional'
        verbose_name_plural = 'Colaboradores Institucionais'
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.area_actuacao})"


class PresencaInstitucional(models.Model):
    TIPOS = [
        ('Entrada', 'Entrada'),
        ('Saida', 'Saída'),
        ('Hora_Extra', 'Hora Extra'),
        ('Falta', 'Falta'),
        ('Falta_Justificada', 'Falta Justificada'),
        ('Ferias', 'Férias'),
        ('Feriado', 'Feriado'),
    ]
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Aprovado', 'Aprovado'),
        ('Rejeitado', 'Rejeitado'),
    ]
    colaborador = models.ForeignKey(ColaboradorInstitucional, on_delete=models.CASCADE, related_name='presencas')
    data = models.DateField()
    tipo = models.CharField(max_length=20, choices=TIPOS, default='Entrada')
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_saida = models.TimeField(null=True, blank=True)
    horas_extras = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    justificacao = models.TextField(blank=True, default='')
    estado = models.CharField(max_length=10, choices=ESTADOS, default='Pendente', db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'presencas_institucionais'
        unique_together = ('colaborador', 'data')
        ordering = ['-data']
        verbose_name = 'Presença Institucional'
        verbose_name_plural = 'Presenças Institucionais'


class FeriasInstitucional(models.Model):
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Aprovado', 'Aprovado'),
        ('Rejeitado', 'Rejeitado'),
    ]
    colaborador = models.ForeignKey(ColaboradorInstitucional, on_delete=models.CASCADE, related_name='pedidos_ferias')
    data_inicio = models.DateField()
    data_fim = models.DateField()
    motivo = models.TextField(blank=True, default='')
    estado = models.CharField(max_length=10, choices=ESTADOS, default='Pendente', db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ferias_institucionais'
        ordering = ['-criado_em']
        verbose_name = 'Férias Institucional'
        verbose_name_plural = 'Férias Institucionais'

    @property
    def dias(self):
        return (self.data_fim - self.data_inicio).days + 1


class CicloAvaliacaoInstitucional(models.Model):
    ESTADOS = [
        ('Aberto', 'Aberto'),
        ('Em Curso', 'Em Curso'),
        ('Encerrado', 'Encerrado'),
    ]
    nome = models.CharField(max_length=200)
    periodo_inicio = models.DateField()
    periodo_fim = models.DateField()
    estado = models.CharField(max_length=10, choices=ESTADOS, default='Aberto', db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ciclos_avaliacao_institucionais'
        ordering = ['-periodo_inicio']
        verbose_name = 'Ciclo de Avaliação Institucional'
        verbose_name_plural = 'Ciclos de Avaliação Institucionais'


class AvaliacaoInstitucional(models.Model):
    ciclo = models.ForeignKey(CicloAvaliacaoInstitucional, on_delete=models.CASCADE, related_name='avaliacoes')
    colaborador = models.ForeignKey(ColaboradorInstitucional, on_delete=models.CASCADE, related_name='avaliacoes')
    pontualidade = models.PositiveSmallIntegerField(default=3)
    produtividade = models.PositiveSmallIntegerField(default=3)
    qualidade_trabalho = models.PositiveSmallIntegerField(default=3)
    trabalho_equipa = models.PositiveSmallIntegerField(default=3)
    iniciativa = models.PositiveSmallIntegerField(default=3)
    nota_global = models.DecimalField(max_digits=3, decimal_places=1, default=3)
    pontos_fortes = models.TextField(blank=True, default='')
    pontos_melhoria = models.TextField(blank=True, default='')
    plano_desenvolvimento = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'avaliacoes_institucionais'
        unique_together = ('ciclo', 'colaborador')
        verbose_name = 'Avaliação Institucional'
        verbose_name_plural = 'Avaliações Institucionais'

    @property
    def classificacao(self):
        n = float(self.nota_global)
        if n >= 4.5: return ('Excelente', 'green')
        if n >= 3.5: return ('Bom', 'blue')
        if n >= 2.5: return ('Satisfatório', 'amber')
        return ('Necessita Melhoria', 'red')


class ProcessamentoSalarialInstitucional(models.Model):
    ESTADOS = [
        ('Rascunho', 'Rascunho'),
        ('Processado', 'Processado'),
        ('Pago', 'Pago'),
    ]
    mes = models.PositiveSmallIntegerField()
    ano = models.PositiveSmallIntegerField()
    estado = models.CharField(max_length=15, choices=ESTADOS, default='Rascunho', db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    pdf_gerado = models.BooleanField(default=False)

    class Meta:
        db_table = 'processamentos_salariais_institucionais'
        unique_together = ('mes', 'ano')
        ordering = ['-ano', '-mes']
        verbose_name = 'Processamento Salarial Institucional'
        verbose_name_plural = 'Processamentos Salariais Institucionais'


class ReciboSalarialInstitucional(models.Model):
    processamento = models.ForeignKey(ProcessamentoSalarialInstitucional, on_delete=models.CASCADE, related_name='recibos')
    colaborador = models.ForeignKey(ColaboradorInstitucional, on_delete=models.CASCADE, related_name='recibos')
    salario_base = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subsidio_alimentacao = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subsidio_transporte = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    outros_subsidios = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    horas_extras_valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    irt = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    inss_trabalhador = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    outros_descontos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observacoes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'recibos_salariais_institucionais'
        unique_together = ('processamento', 'colaborador')
        verbose_name = 'Recibo Salarial Institucional'
        verbose_name_plural = 'Recibos Salariais Institucionais'

    @property
    def bruto(self):
        return (self.salario_base + self.subsidio_alimentacao + self.subsidio_transporte
                + self.outros_subsidios + self.horas_extras_valor)

    @property
    def total_descontos(self):
        return self.irt + self.inss_trabalhador + self.outros_descontos

    @property
    def liquido(self):
        return self.bruto - self.total_descontos
