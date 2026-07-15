import uuid
from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class Usuario(models.Model):
    PAPEIS = [
        ('Administrador', 'Administrador'),
        ('Despachante Oficial', 'Despachante Oficial'),
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
    telefone = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    cedula = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    papel = models.CharField(max_length=50, choices=PAPEIS, default='Despachante Oficial', db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Ativo', db_index=True)
    is_staff = models.BooleanField(default=False, verbose_name='Acesso ao Admin')
    is_superuser = models.BooleanField(default=False, verbose_name='Superutilizador')
    categoria = models.ForeignKey('governanca.CategoriaMembro', on_delete=models.SET_NULL, null=True, blank=True)
    sso_portal_id = models.IntegerField(null=True, blank=True)
    ultimo_acesso = models.DateTimeField(null=True, blank=True)
    nif = models.TextField(blank=True, default='', db_index=True)
    is_secretario = models.BooleanField(default=False)
    is_vice_secretario = models.BooleanField(default=False)
    permissoes_diretas = models.ManyToManyField('Permissao', blank=True, related_name='usuarios_diretos')
    funcao = models.ForeignKey('Funcao', null=True, blank=True, on_delete=models.SET_NULL, related_name='usuarios')
    area_actuacao = models.CharField(max_length=100, blank=True, default='')
    cargo_personalizado = models.CharField(max_length=100, blank=True, default='')
    assinatura = models.TextField(blank=True, default='', verbose_name='Assinatura Digital (Base64 PNG)')
    assinatura_data = models.DateTimeField(null=True, blank=True, verbose_name='Data da Assinatura')
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
        if self.papel != 'Administrador':
            return False
        perms_ok = {
            'financeiro.view_requisicaofundo',
            'financeiro.change_requisicaofundo',
            'financeiro.delete_requisicaofundo',
        }
        return perm in perms_ok

    def has_module_perms(self, app_label):
        if not self.is_staff:
            return False
        if self.is_superuser:
            return True
        if self.papel != 'Administrador':
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
        if self.papel == 'Administrador':
            return {'financeiro.view_requisicaofundo', 'financeiro.change_requisicaofundo',
                    'financeiro.delete_requisicaofundo'}
        return set()

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
    grupo = models.CharField(max_length=100, blank=True, default='', db_index=True,
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
    banca = models.ForeignKey('rh.Banca', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='logs_atividade', verbose_name='Banca')
    filial = models.ForeignKey('rh.FilialBanca', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='logs_atividade', verbose_name='Filial')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Data/Hora')

    class Meta:
        db_table = 'logs_atividade'
        verbose_name = 'Log de Atividade'
        verbose_name_plural = 'Logs de Atividade'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['usuario', '-created_at'], name='idx_log_usuario_data'),
            models.Index(fields=['modulo', '-created_at'], name='idx_log_modulo'),
        ]

    def __str__(self):
        return f"[{self.created_at:%d/%m/%Y %H:%M}] {self.usuario_nome} — {self.accao} ({self.modulo})"


def _get_client_ip(request):
    """Obtém o IP real do cliente, verificando HTTP_X_FORWARDED_FOR primeiro."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '-')


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
        banca_id=request.session.get('banca_id') if request else None,
        filial_id=request.session.get('colaborador_filial_id') if request else None,
        ip=_get_client_ip(request) if request else '',
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
    email = models.EmailField(blank=True, default='', db_index=True)
    telefone = models.CharField(max_length=30, blank=True, default='', db_index=True)
    area_actuacao = models.CharField(max_length=100, blank=True, default='', db_index=True)
    data_admissao = models.DateField(null=True, blank=True)
    salario_base = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default='Ativo', db_index=True)
    foto = models.ImageField(upload_to='colaboradores_institucionais/fotos/', null=True, blank=True)
    observacoes = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
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
    data = models.DateField(db_index=True)
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

    def clean(self):
        if self.data and self.data > timezone.now().date():
            raise ValidationError({'data': 'A data não pode estar no futuro.'})


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
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'ferias_institucionais'
        ordering = ['-criado_em']
        verbose_name = 'Férias Institucional'
        verbose_name_plural = 'Férias Institucionais'

    def clean(self):
        if self.data_inicio and self.data_fim:
            if self.data_fim < self.data_inicio:
                raise ValidationError({'data_fim': 'A data de fim não pode ser anterior à data de início.'})
            if self.data_inicio > timezone.now().date():
                raise ValidationError({'data_inicio': 'A data de início não pode estar no futuro.'})

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
    periodo_inicio = models.DateField(db_index=True)
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

class ProcessamentoSalarialInstitucional(models.Model):
    ESTADOS = [
        ('Rascunho', 'Rascunho'),
        ('Processado', 'Processado'),
        ('Pago', 'Pago'),
    ]
    mes = models.PositiveSmallIntegerField(db_index=True)
    ano = models.PositiveSmallIntegerField(db_index=True)
    estado = models.CharField(max_length=15, choices=ESTADOS, default='Rascunho', db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    pdf_gerado = models.BooleanField(default=False)

    @property
    def total_bruto(self):
        return sum(r.bruto for r in self.recibos.all())

    @property
    def total_descontos(self):
        return sum(r.total_descontos for r in self.recibos.all())

    @property
    def total_liquido(self):
        return sum(r.liquido for r in self.recibos.all())

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
    inss_entidade = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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

    @property
    def base_calculo_impostos(self):
        return max(Decimal('0'), self.salario_base - self.outros_descontos)

    @property
    def faltas_count(self):
        if self.outros_descontos and self.salario_base:
            return round(float(self.outros_descontos) / float(self.salario_base) * 22)
        return 0


# ─── Subsídios Institucionais ────────────────────────────────────────────

class SubsidioInstitucional(models.Model):
    TIPOS_CALCULO = [
        ('FIXO', 'Valor Fixo'),
        ('PERCENTUAL', 'Percentual do Salário'),
        ('DIAS_TRABALHO', 'Por Dias de Trabalho'),
        ('DEPENDENTES', 'Por Número de Dependentes'),
    ]
    nome = models.CharField(max_length=100, verbose_name='Nome do Subsídio')
    codigo = models.CharField(max_length=20, unique=True, verbose_name='Código Interno')
    tipo_calculo = models.CharField(max_length=20, choices=TIPOS_CALCULO, default='FIXO')
    valor_padrao = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Valor Padrão')
    percentual = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Percentual (%)')
    ativo = models.BooleanField(default=True, db_index=True)
    obrigatorio = models.BooleanField(default=False, verbose_name='Obrigatório para Todos')
    apenas_especificos = models.BooleanField(default=False, verbose_name='Apenas para colaboradores específicos')
    colaboradores_especificos = models.ManyToManyField('ColaboradorInstitucional', blank=True, related_name='subsidios_especificos')
    descricao = models.TextField(blank=True, verbose_name='Descrição')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subsidios_institucionais'
        verbose_name = 'Subsídio Institucional'
        verbose_name_plural = 'Subsídios Institucionais'
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nome}"


class SubsidioReciboInstitucional(models.Model):
    recibo = models.ForeignKey('ReciboSalarialInstitucional', on_delete=models.CASCADE, related_name='subsidios_vinculados')
    subsidio = models.ForeignKey(SubsidioInstitucional, on_delete=models.CASCADE)
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Aplicado')
    valor_padrao = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Padrão Original')
    observacoes = models.TextField(blank=True, verbose_name='Observações')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'recibo_subsidios_institucionais'
        verbose_name = 'Subsídio do Recibo Institucional'
        verbose_name_plural = 'Subsídios do Recibo Institucionais'
        unique_together = ('recibo', 'subsidio')
        ordering = ['subsidio__codigo']

    def __str__(self):
        return f"{self.recibo.colaborador.nome} - {self.subsidio.nome}: {self.valor} Kz"


# ─── Recrutamento Institucional ──────────────────────────────────────────

class VagaInstitucional(models.Model):
    ESTADOS = [
        ('Aberta', 'Aberta'),
        ('Em Análise', 'Em Análise'),
        ('Encerrada', 'Encerrada'),
        ('Cancelada', 'Cancelada'),
    ]
    titulo = models.CharField(max_length=200, db_index=True)
    departamento = models.CharField(max_length=100, blank=True, default='')
    descricao = models.TextField(blank=True, default='')
    requisitos = models.TextField(blank=True, default='')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Aberta', db_index=True)
    link_externo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    vagas_numero = models.PositiveIntegerField(default=1, verbose_name='Nº de Vagas')
    salario_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salario_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    data_encerramento = models.DateField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vagas_institucionais'
        ordering = ['-criado_em']
        verbose_name = 'Vaga Institucional'
        verbose_name_plural = 'Vagas Institucionais'

    def __str__(self):
        return self.titulo

    @property
    def link_publico(self):
        from django.urls import reverse
        return reverse('rh_inst_vaga_publica', kwargs={'link_uuid': self.link_externo})


class CandidaturaInstitucional(models.Model):
    ESTADOS = [
        ('Recebida', 'Recebida'),
        ('Em Análise', 'Em Análise'),
        ('Entrevista', 'Entrevista'),
        ('Aprovado', 'Aprovado'),
        ('Rejeitado', 'Rejeitado'),
    ]
    vaga = models.ForeignKey(VagaInstitucional, on_delete=models.CASCADE, related_name='candidaturas')
    nome = models.CharField(max_length=200, db_index=True)
    email = models.EmailField(blank=True, default='', db_index=True)
    telefone = models.CharField(max_length=30, blank=True, default='')
    cv = models.FileField(upload_to='candidaturas_institucionais/cv/', null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Recebida', db_index=True)
    notas = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'candidaturas_institucionais'
        ordering = ['-criado_em']
        verbose_name = 'Candidatura Institucional'
        verbose_name_plural = 'Candidaturas Institucionais'

    def __str__(self):
        return f"{self.nome} - {self.vaga.titulo}"


class EntrevistaInstitucional(models.Model):
    TIPOS = [
        ('Presencial', 'Presencial'),
        ('Online', 'Online'),
        ('Telefónica', 'Telefónica'),
    ]
    RESULTADOS = [
        ('Pendente', 'Pendente'),
        ('Aprovado', 'Aprovado'),
        ('Reprovado', 'Reprovado'),
    ]
    candidatura = models.ForeignKey(CandidaturaInstitucional, on_delete=models.CASCADE, related_name='entrevistas')
    data_hora = models.DateTimeField(db_index=True)
    tipo = models.CharField(max_length=20, choices=TIPOS, default='Presencial')
    local_link = models.CharField(max_length=300, blank=True, default='')
    entrevistador = models.CharField(max_length=200, blank=True, default='')
    resultado = models.CharField(max_length=20, choices=RESULTADOS, default='Pendente')
    nota = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    observacoes = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'entrevistas_institucionais'
        ordering = ['-data_hora']
        verbose_name = 'Entrevista Institucional'
        verbose_name_plural = 'Entrevistas Institucionais'

    def __str__(self):
        return f"Entrevista - {self.candidatura.nome} ({self.get_tipo_display()})"


class PlanoIntegracaoInstitucional(models.Model):
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Em Curso', 'Em Curso'),
        ('Concluído', 'Concluído'),
    ]
    candidatura = models.OneToOneField(CandidaturaInstitucional, on_delete=models.CASCADE, related_name='plano_integracao')
    colaborador = models.ForeignKey('ColaboradorInstitucional', null=True, blank=True, on_delete=models.SET_NULL, related_name='planos_integracao')
    data_inicio = models.DateField(null=True, blank=True)
    data_fim_prevista = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', db_index=True)
    responsavel = models.CharField(max_length=200, blank=True, default='')
    notas = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'planos_integracao_institucionais'
        verbose_name = 'Plano de Integração Institucional'
        verbose_name_plural = 'Planos de Integração Institucionais'

    def __str__(self):
        return f"Integração - {self.candidatura.nome}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.data_inicio and self.data_fim_prevista:
            if self.data_inicio > self.data_fim_prevista:
                raise ValidationError('Data de fim prevista deve ser posterior à data de início.')

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)

    @property
    def tarefas_concluidas(self):
        return self.tarefas.filter(concluida=True).count()

    @property
    def total_tarefas(self):
        return self.tarefas.count()

    @property
    def progresso(self):
        if not self.total_tarefas:
            return 0
        return min(round(self.tarefas_concluidas / self.total_tarefas * 100), 100)


class TarefaIntegracaoInstitucional(models.Model):
    plano = models.ForeignKey(PlanoIntegracaoInstitucional, on_delete=models.CASCADE, related_name='tarefas')
    titulo = models.CharField(max_length=300)
    concluida = models.BooleanField(default=False)
    responsavel = models.CharField(max_length=200, blank=True, default='')
    prazo = models.DateField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'tarefas_integracao_institucionais'
        ordering = ['criado_em']
        verbose_name = 'Tarefa de Integração Institucional'
        verbose_name_plural = 'Tarefas de Integração Institucionais'

    def __str__(self):
        return self.titulo


# ─── Métricas de Avaliação Institucionais ─────────────────────────────────

class MetricaAvaliacaoInstitucional(models.Model):
    ciclo = models.ForeignKey(CicloAvaliacaoInstitucional, on_delete=models.CASCADE, related_name='metricas')
    nome = models.CharField(max_length=200)
    descricao = models.TextField(blank=True, default='')
    ordem = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        db_table = 'metricas_avaliacao_institucionais'
        ordering = ['ordem']
        verbose_name = 'Métrica de Avaliação Institucional'
        verbose_name_plural = 'Métricas de Avaliação Institucionais'

    def __str__(self):
        return self.nome


class NotaMetricaInstitucional(models.Model):
    avaliacao = models.ForeignKey('AvaliacaoInstitucional', on_delete=models.CASCADE, related_name='notas_metricas')
    metrica = models.ForeignKey(MetricaAvaliacaoInstitucional, on_delete=models.CASCADE)
    nota = models.PositiveSmallIntegerField(default=3)

    class Meta:
        db_table = 'notas_metricas_avaliacao_institucionais'
        unique_together = ('avaliacao', 'metrica')
        verbose_name = 'Nota de Métrica Institucional'
        verbose_name_plural = 'Notas de Métricas Institucionais'

    def __str__(self):
        return f"{self.metrica.nome}: {self.nota}"
