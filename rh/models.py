import uuid
from django.db import models
from decimal import Decimal


# ─── Banca ────────────────────────────────────────────────────────────────────

class Banca(models.Model):
    """
    Banca do despachante. Um despachante pode ter uma única banca
    mas com filiais em diferentes províncias — todas geridas aqui.
    """
    TIPOS = [
        ('Singular', 'Empresa em Nome Individual'),
        ('Sociedade', 'Sociedade por Quotas'),
        ('SA', 'Sociedade Anónima'),
        ('Outro', 'Outro'),
    ]

    usuario_id  = models.IntegerField()                          # FK → usuarios
    nome        = models.CharField(max_length=255)
    nif         = models.CharField(max_length=50, unique=True)
    tipo        = models.CharField(max_length=20, choices=TIPOS, default='Sociedade')
    email       = models.EmailField(blank=True, default='')
    telefone    = models.CharField(max_length=30, blank=True, default='')
    endereco    = models.TextField(blank=True, default='')
    provincia   = models.CharField(max_length=100, blank=True, default='')
    municipio   = models.CharField(max_length=100, blank=True, default='')
    licenca_cdoa = models.CharField(max_length=100, blank=True, default='')
    logo        = models.ImageField(upload_to='bancas/logos/', null=True, blank=True)
    ativa       = models.BooleanField(default=True)
    criado_em   = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rh_empresas'   # reutiliza a tabela existente — não recriar
        managed  = True
        verbose_name = 'Banca'
        verbose_name_plural = 'Bancas'
        indexes = [
            models.Index(fields=['usuario_id']),
            models.Index(fields=['ativa']),
            models.Index(fields=['nif']),
        ]

    def __str__(self):
        return f"{self.nome} ({self.nif})"

    @property
    def total_colaboradores(self):
        """Retorna o número total de colaboradores incluindo todas as filiais"""
        return self.colaboradores.count()

    @property
    def total_colaboradores_sede(self):
        """Retorna o número de colaboradores na sede"""
        return self.colaboradores.filter(filial__isnull=True).count()

    @property
    def total_filiais(self):
        """Retorna o número de filiais ativas"""
        return self.filiais.filter(ativa=True).count()

    @property
    def colaboradores_por_filial(self):
        """Retorna estatísticas de colaboradores por filial - otimizado com query única"""
        from django.db.models import Count
        
        # Query única para obter contagem de colaboradores por filial
        stats = list(self.colaboradores.values('filial__provincia').annotate(
            total=Count('id')
        ).order_by('filial__provincia'))
        
        resultado = []
        # Adicionar sede (filial nula)
        sede_total = next((s['total'] for s in stats if s['filial__provincia'] is None), 0)
        if sede_total > 0:
            resultado.append({'filial': 'Sede', 'total': sede_total})
        
        # Adicionar filiais com colaboradores
        for stat in stats:
            if stat['filial__provincia']:  # Excluir sede (nula)
                resultado.append({
                    'filial': stat['filial__provincia'],
                    'total': stat['total']
                })
        
        return resultado

    def get_colaborador_by_usuario_id(self, usuario_id):
        """Retorna o colaborador associado a um usuario_id"""
        return self.colaboradores.filter(usuario_id=usuario_id).first()


class FilialBanca(models.Model):
    """Filial/delegação da banca noutra província."""
    banca     = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='filiais')
    provincia = models.CharField(max_length=100)
    municipio = models.CharField(max_length=100, blank=True, default='')
    endereco  = models.TextField(blank=True, default='')
    telefone  = models.CharField(max_length=30, blank=True, default='')
    email     = models.EmailField(blank=True, default='')
    responsavel = models.CharField(max_length=255, blank=True, default='')
    tem_responsavel = models.BooleanField(default=False, verbose_name='Deseja designar um responsável?')
    ativa     = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_filiais'
        ordering = ['provincia']
        unique_together = ('banca', 'provincia')
        indexes = [
            models.Index(fields=['banca', 'ativa']),
            models.Index(fields=['provincia']),
        ]

    def __str__(self):
        return f"{self.banca.nome} — {self.provincia}"


class GestorFilial(models.Model):
    """
    Gestor delegado para uma filial específica.
    Um gestor pode gerir apenas a filial atribuída, mas o despachante
    mantém acesso total a todas as filiais.
    """
    colaborador = models.OneToOneField('Colaborador', on_delete=models.CASCADE, related_name='gestor_filial')
    filial = models.ForeignKey(FilialBanca, on_delete=models.CASCADE, related_name='gestores')
    ativo = models.BooleanField(default=True)
    nome_gestor = models.CharField(max_length=255, blank=True, default='')  # Para override se necessário
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rh_gestores_filial'
        unique_together = ('colaborador', 'filial')
        verbose_name = 'Gestor de Filial'
        verbose_name_plural = 'Gestores de Filial'
        indexes = [
            models.Index(fields=['colaborador', 'ativo']),
            models.Index(fields=['filial', 'ativo']),
        ]

    def __str__(self):
        return f"{self.colaborador.nome} - {self.filial.provincia}"

    @property
    def tem_acesso_total(self):
        """Verifica se este gestor tem acesso total (despachante principal via usuário da banca)"""
        # Colaboradores nunca têm acesso total, apenas o usuário principal da banca
        return False


# ─── Colaborador ──────────────────────────────────────────────────────────────

# Documentos do Colaborador
# Sistema de Subsídios Configuráveis
class Subsidio(models.Model):
    """Tipos de subsídios configuráveis por empresa"""
    TIPOS_CALCULO = [
        ('FIXO', 'Valor Fixo'),
        ('PERCENTUAL', 'Percentual do Salário'),
        ('DIAS_TRABALHO', 'Por Dias de Trabalho'),
        ('DEPENDENTES', 'Por Número de Dependentes'),
    ]
    
    banca = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='subsidios')
    nome = models.CharField(max_length=100, verbose_name='Nome do Subsídio')
    codigo = models.CharField(max_length=20, verbose_name='Código Interno')
    tipo_calculo = models.CharField(max_length=20, choices=TIPOS_CALCULO, default='FIXO')
    valor_padrao = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Valor Padrão')
    percentual = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Percentual (%)')
    ativo = models.BooleanField(default=True)
    obrigatorio = models.BooleanField(default=False, verbose_name='Obrigatório para Todos')
    descricao = models.TextField(blank=True, verbose_name='Descrição')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'rh_subsidios'
        verbose_name = 'Subsídio'
        verbose_name_plural = 'Subsídios'
        unique_together = ('banca', 'codigo')
        ordering = ['codigo']
    
    def __str__(self):
        return f"{self.codigo} - {self.nome}"
    
    @property
    def valor_calculado(self, salario_base=None, dias_trabalho=None, dependentes=None):
        """Calcula o valor do subsídio baseado no tipo de cálculo"""
        if self.tipo_calculo == 'FIXO':
            return self.valor_padrao
        elif self.tipo_calculo == 'PERCENTUAL' and self.percentual and salario_base:
            return (salario_base * self.percentual) / 100
        elif self.tipo_calculo == 'DIAS_TRABALHO' and dias_trabalho:
            return self.valor_padrao * dias_trabalho
        elif self.tipo_calculo == 'DEPENDENTES' and dependentes:
            return self.valor_padrao * dependentes
        return self.valor_padrao


class DocumentoColaborador(models.Model):
    TIPOS_DOCUMENTO = [
        ('CV', 'Curriculum Vitae'),
        ('DECLARACAO', 'Declaração'),
        ('CERTIFICADO', 'Certificado'),
        ('OUTRO', 'Outro Documento'),
    ]
    
    colaborador = models.ForeignKey('Colaborador', on_delete=models.CASCADE, related_name='documentos')
    tipo = models.CharField(max_length=20, choices=TIPOS_DOCUMENTO, default='OUTRO')
    arquivo = models.FileField(upload_to='colaboradores/documentos/%Y/%m/')
    descricao = models.CharField(max_length=255, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'rh_colaborador_documentos'
        verbose_name = 'Documento do Colaborador'
        verbose_name_plural = 'Documentos dos Colaboradores'
        ordering = ['-criado_em']
    
    def __str__(self):
        return f"{self.colaborador.nome} - {self.get_tipo_display()}"
    
    @property
    def nome_arquivo(self):
        return self.arquivo.name.split('/')[-1] if self.arquivo else ''
    
    @property
    def tamanho_formatado(self):
        if self.arquivo and self.arquivo.size:
            size = self.arquivo.size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} TB"
        return "0 B"


class Colaborador(models.Model):
    CARGOS = [
        ('Assistente', 'Assistente de Despacho'),
        ('Administrativo', 'Administrativo'),
        ('Financeiro', 'Financeiro'),
        ('Gestor', 'Gestor'),
        ('Outro', 'Outro'),
    ]
    ESTADOS = [
        ('Ativo', 'Ativo'),
        ('Inativo', 'Inativo'),
        ('Suspenso', 'Suspenso'),
        ('Ferias', 'De Férias'),
    ]
    GENEROS = [('M', 'Masculino'), ('F', 'Feminino'), ('O', 'Outro')]

    usuario_id  = models.IntegerField(null=True, blank=True)  # FK → usuarios
    banca       = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='colaboradores')
    filial      = models.ForeignKey(FilialBanca, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='colaboradores')
    nome        = models.CharField(max_length=255)
    bi          = models.CharField(max_length=50, blank=True, default='', verbose_name='Nº BI')
    nif         = models.CharField(max_length=50, blank=True, default='')
    genero      = models.CharField(max_length=1, choices=GENEROS, blank=True, default='')
    data_nascimento = models.DateField(null=True, blank=True)
    cargo       = models.CharField(max_length=30, choices=CARGOS, default='Assistente')
    cargo_personalizado = models.CharField(max_length=100, blank=True, default='')
    departamento = models.CharField(max_length=100, blank=True, default='')
    email       = models.EmailField(blank=True, default='')
    telefone    = models.CharField(max_length=30, blank=True, default='')
    data_admissao = models.DateField(null=True, blank=True)
    salario_base = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado      = models.CharField(max_length=10, choices=ESTADOS, default='Ativo')
    foto        = models.ImageField(upload_to='colaboradores/fotos/', null=True, blank=True)
    observacoes = models.TextField(blank=True, default='')
    password    = models.CharField(max_length=255, null=True, blank=True, help_text='Senha para acesso ao sistema')
    criado_em   = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rh_colaboradores'
        verbose_name = 'Colaborador'
        verbose_name_plural = 'Colaboradores'
        ordering = ['nome']
        indexes = [
            models.Index(fields=['banca']),
            models.Index(fields=['filial']),
            models.Index(fields=['estado']),
            models.Index(fields=['usuario_id']),
            models.Index(fields=['banca', 'filial']),
            models.Index(fields=['criado_em']),
        ]

    def __str__(self):
        return f"{self.nome} — {self.get_cargo_display()}"

    @property
    def cargo_label(self):
        return (self.cargo_personalizado
                if self.cargo == 'Outro' and self.cargo_personalizado
                else self.get_cargo_display())

    @property
    def salario_efetivo(self):
        return self.salario_base or Decimal('0')

    @property
    def local_trabalho(self):
        """Retorna 'Sede' se não tiver filial, ou nome da província da filial"""
        if not self.filial:
            return "Sede"
        return self.filial.provincia

    @property
    def e_gestor_filial(self):
        """Verifica se este colaborador é gestor de alguma filial"""
        return hasattr(self, 'gestor_filial') and self.gestor_filial.ativo

    @property
    def filiais_geridas(self):
        """Retorna as filiais que este colaborador gere"""
        if self.e_gestor_filial:
            return FilialBanca.objects.filter(gestores__colaborador=self, gestores__ativo=True)
        return FilialBanca.objects.none()

    @property
    def pode_gerir_todas_filiais(self):
        """Verifica se pode gerir todas as filiais (apenas despachante principal via usuário)"""
        return False

    @property
    def scope_colaboradores(self):
        """Retorna os colaboradores que este utilizador pode gerir"""
        if self.e_gestor_filial:
            return Colaborador.objects.filter(
                models.Q(filial=self.gestor_filial.filial) | models.Q(pk=self.pk)
            )
        return Colaborador.objects.filter(pk=self.pk)

    @property
    def pode_gerir_salarios(self):
        """Verifica se pode gerir salários (apenas despachante principal via usuário)"""
        return False

    @property
    def pode_gerir_presencas(self):
        """Verifica se pode gerir presenças (responsáveis de filial)"""
        return self.e_gestor_filial

    @property
    def pode_gerir_candidaturas(self):
        """Verifica se pode gerir candidaturas (responsáveis de filial)"""
        return self.e_gestor_filial


# ─── Processamento Salarial ───────────────────────────────────────────────────

class ProcessamentoSalarial(models.Model):
    ESTADOS = [
        ('Rascunho', 'Rascunho'),
        ('Processado', 'Processado'),
        ('Pago', 'Pago'),
    ]
    banca       = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='processamentos')
    mes         = models.PositiveSmallIntegerField()
    ano         = models.PositiveSmallIntegerField()
    estado      = models.CharField(max_length=15, choices=ESTADOS, default='Rascunho')
    criado_em   = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    pdf_gerado  = models.BooleanField(default=False)

    class Meta:
        db_table = 'rh_processamentos'
        unique_together = ('banca', 'mes', 'ano')
        ordering = ['-ano', '-mes']

    def __str__(self):
        return f"{self.banca.nome} — {self.mes:02d}/{self.ano}"

    @property
    def total_liquido(self):
        return sum(r.liquido for r in self.recibos.all())


class SubsidioRecibo(models.Model):
    """Vínculo entre subsídio e recibo salarial com valor personalizado"""
    recibo = models.ForeignKey('ReciboSalarial', on_delete=models.CASCADE, related_name='subsidios_vinculados')
    subsidio = models.ForeignKey(Subsidio, on_delete=models.CASCADE)
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Aplicado')
    valor_padrao = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Padrão Original')
    observacoes = models.TextField(blank=True, verbose_name='Observações')
    criado_em = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'rh_recibo_subsidios'
        verbose_name = 'Subsídio do Recibo'
        verbose_name_plural = 'Subsídios do Recibo'
        unique_together = ('recibo', 'subsidio')
        ordering = ['subsidio__codigo']
    
    def __str__(self):
        return f"{self.recibo.colaborador.nome} - {self.subsidio.nome}: {self.valor} Kz"
    
    @property
    def diferenca(self):
        """Diferença entre valor aplicado e valor padrão"""
        return self.valor - self.valor_padrao


class ReciboSalarial(models.Model):
    processamento = models.ForeignKey(ProcessamentoSalarial, on_delete=models.CASCADE, related_name='recibos')
    colaborador   = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='recibos')
    salario_base  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subsidio_alimentacao = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subsidio_transporte  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    outros_subsidios     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    horas_extras_valor   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    irt                  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    inss_trabalhador     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    inss_entidade        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    outros_descontos     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observacoes          = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'rh_recibos'
        unique_together = ('processamento', 'colaborador')

    @property
    def base_calculo_impostos(self):
        """Base de cálculo para IRT e INSS: salário base subtraído das faltas"""
        return max(Decimal('0'), self.salario_base - self.outros_descontos)

    @property
    def bruto(self):
        return (self.salario_base + self.subsidio_alimentacao + self.subsidio_transporte
                + self.outros_subsidios + self.horas_extras_valor)

    @property
    def total_descontos(self):
        return self.irt + self.inss_trabalhador + self.outros_descontos

    @property
    def liquido(self):
        # Salário líquido = (salário_base - faltas) - IRT - INSS + subsídios
        base_com_impostos = self.base_calculo_impostos - self.irt - self.inss_trabalhador
        total_subsidios = (self.subsidio_alimentacao + self.subsidio_transporte 
                          + self.outros_subsidios + self.horas_extras_valor)
        return base_com_impostos + total_subsidios


# ─── Recrutamento ─────────────────────────────────────────────────────────────

class Vaga(models.Model):
    ESTADOS = [
        ('Aberta', 'Aberta'),
        ('Em Análise', 'Em Análise'),
        ('Encerrada', 'Encerrada'),
        ('Cancelada', 'Cancelada'),
    ]
    banca       = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='vagas')
    filial      = models.ForeignKey(FilialBanca, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='vagas')
    titulo      = models.CharField(max_length=200)
    departamento = models.CharField(max_length=100, blank=True, default='')
    descricao   = models.TextField(blank=True, default='')
    requisitos  = models.TextField(blank=True, default='')
    salario_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salario_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vagas_numero = models.PositiveSmallIntegerField(default=1)
    link_externo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    estado      = models.CharField(max_length=15, choices=ESTADOS, default='Aberta')
    data_abertura = models.DateField(auto_now_add=True)
    data_encerramento = models.DateField(null=True, blank=True)
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_vagas'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['banca']),
            models.Index(fields=['filial']),
            models.Index(fields=['estado']),
            models.Index(fields=['banca', 'estado']),
            models.Index(fields=['criado_em']),
        ]

    @property
    def total_candidatos(self):
        return self.candidaturas.count()

    @property
    def link_candidatura_externa(self):
        """Gera link público absoluto para candidatura externa (usa SITE_URL de produção)."""
        from django.conf import settings
        base = getattr(settings, 'SITE_URL', 'https://sicdoa-ycg9.onrender.com').rstrip('/')
        return f"{base}/candidatar/{self.link_externo}/"

    @property
    def link_vaga_publica(self):
        """Gera link público absoluto para visualização da vaga (usa SITE_URL de produção)."""
        from django.conf import settings
        base = getattr(settings, 'SITE_URL', 'https://sicdoa-ycg9.onrender.com').rstrip('/')
        return f"{base}/vaga/{self.link_externo}/"


class Candidatura(models.Model):
    ESTADOS = [
        ('Recebida', 'Recebida'),
        ('Em Análise', 'Em Análise'),
        ('Entrevista', 'Entrevista Agendada'),
        ('Aprovado', 'Aprovado'),
        ('Rejeitado', 'Rejeitado'),
    ]
    vaga        = models.ForeignKey(Vaga, on_delete=models.CASCADE, related_name='candidaturas')
    nome        = models.CharField(max_length=255)
    email       = models.EmailField()
    telefone    = models.CharField(max_length=30, blank=True, default='')
    cv          = models.FileField(upload_to='recrutamento/cvs/', null=True, blank=True)
    carta_motivacao = models.TextField(blank=True, default='')
    estado      = models.CharField(max_length=15, choices=ESTADOS, default='Recebida')
    data_entrevista = models.DateTimeField(null=True, blank=True)
    notas       = models.TextField(blank=True, default='')
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_candidaturas'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['vaga']),
            models.Index(fields=['estado']),
            models.Index(fields=['vaga', 'estado']),
            models.Index(fields=['criado_em']),
        ]


# ─── Entrevistas ──────────────────────────────────────────────────────────────

class Entrevista(models.Model):
    TIPOS = [
        ('Presencial', 'Presencial'),
        ('Online', 'Online / Videochamada'),
        ('Telefonica', 'Telefónica'),
    ]
    RESULTADOS = [
        ('Pendente', 'Pendente'),
        ('Aprovado', 'Aprovado'),
        ('Reprovado', 'Reprovado'),
        ('Reagendada', 'Reagendada'),
    ]
    candidatura     = models.ForeignKey(Candidatura, on_delete=models.CASCADE, related_name='entrevistas')
    data_hora       = models.DateTimeField()
    tipo            = models.CharField(max_length=15, choices=TIPOS, default='Presencial')
    local_link      = models.CharField(max_length=300, blank=True, default='',
                                       verbose_name='Local / Link')
    entrevistador   = models.CharField(max_length=255, blank=True, default='')
    resultado       = models.CharField(max_length=15, choices=RESULTADOS, default='Pendente')
    nota            = models.PositiveSmallIntegerField(null=True, blank=True,
                                                       help_text='Nota de 1 a 10')
    observacoes     = models.TextField(blank=True, default='')
    criado_em       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_entrevistas'
        ordering = ['data_hora']

    def __str__(self):
        return f"Entrevista — {self.candidatura.nome} ({self.data_hora:%d/%m/%Y})"


# ─── Integração de Novos Colaboradores ───────────────────────────────────────

class PlanoIntegracao(models.Model):
    """Plano de integração criado quando um candidato é aprovado."""
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Em Curso', 'Em Curso'),
        ('Concluído', 'Concluído'),
    ]
    candidatura     = models.OneToOneField(Candidatura, on_delete=models.CASCADE,
                                           related_name='plano_integracao')
    colaborador     = models.ForeignKey(Colaborador, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='plano_integracao',
                                        help_text='Preenchido após criação do colaborador')
    data_inicio     = models.DateField()
    data_fim_prevista = models.DateField(null=True, blank=True)
    responsavel     = models.CharField(max_length=255, blank=True, default='')
    estado          = models.CharField(max_length=10, choices=ESTADOS, default='Pendente')
    notas           = models.TextField(blank=True, default='')
    criado_em       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_planos_integracao'
        ordering = ['-criado_em']

    def __str__(self):
        return f"Integração — {self.candidatura.nome}"

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
        return round(self.tarefas_concluidas / self.total_tarefas * 100)


class TarefaIntegracao(models.Model):
    """Tarefa individual dentro do plano de integração."""
    plano       = models.ForeignKey(PlanoIntegracao, on_delete=models.CASCADE, related_name='tarefas')
    titulo      = models.CharField(max_length=200)
    descricao   = models.TextField(blank=True, default='')
    responsavel = models.CharField(max_length=255, blank=True, default='')
    prazo       = models.DateField(null=True, blank=True)
    concluida   = models.BooleanField(default=False)
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_tarefas_integracao'
        ordering = ['prazo', 'criado_em']


# ─── Controlo de Presenças ────────────────────────────────────────────────────

# Sistema de Faturação
class Fatura(models.Model):
    TIPOS_FATURA = [
        ('SALARIO_DESPACHANTE', 'Pagamento de Salário - Despachante'),
        ('SALARIO_COLABORADOR', 'Pagamento de Salário - Colaborador'),
    ]
    ESTADOS = [
        ('EMITIDA', 'Emitida'),
        ('PAGA', 'Paga'),
        ('CANCELADA', 'Cancelada'),
    ]
    
    codigo = models.CharField(max_length=50, unique=True)  # Fatura-2024-0001
    tipo = models.CharField(max_length=25, choices=TIPOS_FATURA)
    estado = models.CharField(max_length=15, choices=ESTADOS, default='EMITIDA')
    
    # Relacionamentos
    banca = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='faturas')
    colaborador = models.ForeignKey('Colaborador', on_delete=models.CASCADE, related_name='faturas', null=True, blank=True)
    processamento_salarial = models.ForeignKey('ProcessamentoSalarial', on_delete=models.CASCADE, related_name='faturas')
    
    # Valores
    valor_bruto = models.DecimalField(max_digits=15, decimal_places=2)
    valor_liquido = models.DecimalField(max_digits=15, decimal_places=2)
    valor_imposto = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dados da fatura
    data_emissao = models.DateTimeField(auto_now_add=True)
    data_vencimento = models.DateField()
    data_pagamento = models.DateTimeField(null=True, blank=True)
    
    # Descrição
    descricao = models.TextField()
    observacoes = models.TextField(blank=True, default='')
    
    # Metadados
    criado_por = models.IntegerField(null=True, blank=True)  # ID do usuário que criou
    atualizado_em = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'rh_faturas'
        verbose_name = 'Fatura'
        verbose_name_plural = 'Faturas'
        ordering = ['-data_emissao']
    
    def __str__(self):
        return f"{self.codigo} - {self.get_tipo_display()}"
    
    @property
    def valor_total(self):
        return self.valor_liquido
    
    @property
    def esta_vencida(self):
        from django.utils import timezone
        return self.data_vencimento < timezone.now().date() and self.estado != 'PAGA'
    
    @property
    def dias_vencida(self):
        from django.utils import timezone
        if self.esta_vencida:
            return (timezone.now().date() - self.data_vencimento).days
        return 0
    
    def marcar_como_paga(self):
        from django.utils import timezone
        self.estado = 'PAGA'
        self.data_pagamento = timezone.now()
        self.save()


class RegistoPresenca(models.Model):
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
    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='presencas')
    data        = models.DateField()
    tipo        = models.CharField(max_length=20, choices=TIPOS, default='Entrada')
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_saida  = models.TimeField(null=True, blank=True)
    horas_extras = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    justificacao = models.TextField(blank=True, default='')
    estado      = models.CharField(max_length=10, choices=ESTADOS, default='Pendente')
    aprovado_por = models.ForeignKey(Colaborador, on_delete=models.SET_NULL, null=True, blank=True, 
                                    related_name='presencas_aprovadas', help_text='Quem aprovou/rejeitou este registo')
    data_aprovacao = models.DateTimeField(null=True, blank=True)
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_presencas'
        unique_together = ('colaborador', 'data')
        ordering = ['-data']


class PedidoFerias(models.Model):
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Aprovado', 'Aprovado'),
        ('Rejeitado', 'Rejeitado'),
    ]
    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='pedidos_ferias')
    data_inicio = models.DateField()
    data_fim    = models.DateField()
    motivo      = models.TextField(blank=True, default='')
    estado      = models.CharField(max_length=10, choices=ESTADOS, default='Pendente')
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_pedidos_ferias'
        ordering = ['-criado_em']

    @property
    def dias(self):
        return (self.data_fim - self.data_inicio).days + 1


# ─── Avaliação de Desempenho ──────────────────────────────────────────────────

class CicloAvaliacao(models.Model):
    ESTADOS = [
        ('Aberto', 'Aberto'),
        ('Em Curso', 'Em Curso'),
        ('Encerrado', 'Encerrado'),
    ]
    banca       = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='ciclos_avaliacao')
    nome        = models.CharField(max_length=200)
    periodo_inicio = models.DateField()
    periodo_fim = models.DateField()
    estado      = models.CharField(max_length=10, choices=ESTADOS, default='Aberto')
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_ciclos_avaliacao'
        ordering = ['-periodo_inicio']


class Avaliacao(models.Model):
    ciclo       = models.ForeignKey(CicloAvaliacao, on_delete=models.CASCADE, related_name='avaliacoes')
    colaborador = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='avaliacoes')
    pontualidade     = models.PositiveSmallIntegerField(default=3)
    produtividade    = models.PositiveSmallIntegerField(default=3)
    qualidade_trabalho = models.PositiveSmallIntegerField(default=3)
    trabalho_equipa  = models.PositiveSmallIntegerField(default=3)
    iniciativa       = models.PositiveSmallIntegerField(default=3)
    nota_global      = models.DecimalField(max_digits=3, decimal_places=1, default=3)
    pontos_fortes    = models.TextField(blank=True, default='')
    pontos_melhoria  = models.TextField(blank=True, default='')
    plano_desenvolvimento = models.TextField(blank=True, default='')
    criado_em        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_avaliacoes'
        unique_together = ('ciclo', 'colaborador')

    @property
    def classificacao(self):
        n = float(self.nota_global)
        if n >= 4.5: return ('Excelente', 'green')
        if n >= 3.5: return ('Bom', 'blue')
        if n >= 2.5: return ('Satisfatório', 'amber')
        return ('Necessita Melhoria', 'red')
