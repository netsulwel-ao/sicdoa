import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from governanca.utils import (
    validate_date_not_past,
    validate_date_not_future,
    validate_date_range,
    validate_no_overlap,
)


# ─── CargoBanca (cargos/perfis criados pelo despachante para os seus colaboradores) ──

class CargoBanca(models.Model):
    banca = models.ForeignKey('Banca', on_delete=models.CASCADE, related_name='cargos')
    filial = models.ForeignKey('FilialBanca', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='cargos', verbose_name='Filial',
                               help_text='Se definido, este cargo é específico desta filial.')
    nome = models.CharField(max_length=100, db_index=True)
    descricao = models.TextField(blank=True, default='')
    permissoes = models.ManyToManyField('users.Permissao', blank=True, related_name='cargos_banca')
    locked = models.BooleanField(default=False, verbose_name='Bloqueado',
                                 help_text='Se marcado, as permissões não podem ser alteradas manualmente (controladas pelo sistema)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rh_cargos_banca'
        unique_together = ['banca', 'filial', 'nome']
        verbose_name = 'Cargo da Banca'
        verbose_name_plural = 'Cargos da Banca'
        ordering = ['nome']

    def __str__(self):
        filial_label = f" — {self.filial.provincia}" if self.filial_id else ""
        return f"{self.nome}{filial_label} ({self.banca.nome})"

    @property
    def e_filial(self):
        return self.filial_id is not None


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
    nome        = models.CharField(max_length=255, db_index=True)
    nif         = models.CharField(max_length=50, unique=True)
    tipo        = models.CharField(max_length=20, choices=TIPOS, default='Sociedade')
    email       = models.EmailField(blank=True, default='', db_index=True)
    telefone    = models.CharField(max_length=30, blank=True, default='')
    endereco    = models.TextField(blank=True, default='')
    provincia   = models.CharField(max_length=100, blank=True, default='')
    municipio   = models.CharField(max_length=100, blank=True, default='')
    licenca_cdoa = models.CharField(max_length=100, blank=True, default='')
    logo        = models.ImageField(upload_to='bancas/logos/', null=True, blank=True, verbose_name='Logotipo')

    # Dados Bancários
    banco               = models.CharField(max_length=255, blank=True, default='', verbose_name='Banco')
    numero_conta        = models.CharField(max_length=50, blank=True, default='', verbose_name='Nº da Conta')
    iban                = models.CharField(max_length=50, blank=True, default='', verbose_name='IBAN')
    instrucoes_pagamento = models.TextField(blank=True, default='', verbose_name='Instruções de Pagamento')
    dados_bancarios_json = models.TextField(blank=True, default='', verbose_name='Dados Bancários (JSON)')

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
    def total_filiais(self):
        """Retorna o número de filiais ativas"""
        return self.filiais.filter(ativa=True).count()

    @property
    def bancos_lista(self):
        if not self.dados_bancarios_json:
            return []
        try:
            import json
            lista = json.loads(self.dados_bancarios_json)
            return lista if isinstance(lista, list) else []
        except (json.JSONDecodeError, ValueError):
            return []

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
    codigo = models.CharField(max_length=20, verbose_name='Código Interno', db_index=True)
    tipo_calculo = models.CharField(max_length=20, choices=TIPOS_CALCULO, default='FIXO')
    valor_padrao = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Valor Padrão')
    percentual = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Percentual (%)')
    ativo = models.BooleanField(default=True, db_index=True)
    obrigatorio = models.BooleanField(default=False, verbose_name='Obrigatório para Todos')
    apenas_especificos = models.BooleanField(
        default=False,
        verbose_name='Apenas para colaboradores específicos',
        help_text='Se marcado, este subsídio só é aplicado aos colaboradores selecionados abaixo.'
    )
    colaboradores_especificos = models.ManyToManyField(
        'Colaborador',
        blank=True,
        related_name='subsidios_especificos',
        verbose_name='Colaboradores com este subsídio',
    )
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
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'rh_colaborador_documentos'
        verbose_name = 'Documento do Colaborador'
        verbose_name_plural = 'Documentos dos Colaboradores'
        ordering = ['-criado_em']
    
    def __str__(self):
        return f"{self.colaborador.nome} - {self.get_tipo_display()}"

    def clean(self):
        import os
        allowed_extensions = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.xls', '.xlsx']
        ext = os.path.splitext(self.arquivo.name)[1].lower() if self.arquivo else ''
        if ext and ext not in allowed_extensions:
            raise ValidationError({'arquivo': f'Tipo de ficheiro "{ext}" não permitido. Permitidos: {", ".join(allowed_extensions)}'})

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
    nome        = models.CharField(max_length=255, db_index=True)
    bi          = models.CharField(max_length=50, blank=True, default='', verbose_name='Nº BI', db_index=True)
    nif         = models.CharField(max_length=50, blank=True, default='', db_index=True)
    genero      = models.CharField(max_length=1, choices=GENEROS, blank=True, default='')
    data_nascimento = models.DateField(null=True, blank=True)
    cargo       = models.CharField(max_length=30, choices=CARGOS, default='Assistente', db_index=True)
    cargo_personalizado = models.CharField(max_length=100, blank=True, default='')
    cargo_banca = models.ForeignKey('CargoBanca', null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='colaboradores')
    departamento = models.CharField(max_length=100, blank=True, default='', db_index=True)
    email       = models.EmailField(blank=True, default='', db_index=True)
    telefone    = models.CharField(max_length=30, blank=True, default='', db_index=True)
    data_admissao = models.DateField(null=True, blank=True, db_index=True)
    salario_base = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estado      = models.CharField(max_length=10, choices=ESTADOS, default='Ativo')
    foto        = models.ImageField(upload_to='colaboradores/fotos/', null=True, blank=True)
    observacoes = models.TextField(blank=True, default='')
    password    = models.CharField(max_length=255, null=True, blank=True, help_text='Senha para acesso ao sistema')  # senha com hash bcrypt (ver _hash_password)
    permissoes_filiais = models.ManyToManyField('users.Permissao', blank=True,
                                                 related_name='colaboradores_filiais',
                                                 verbose_name='Permissões de Filial (atribuídas pelo gestor)')
    banco       = models.CharField(max_length=100, blank=True, default='', verbose_name='Banco')
    num_conta   = models.CharField(max_length=50, blank=True, default='', verbose_name='Nº de Conta')
    iban        = models.CharField(max_length=50, blank=True, default='', verbose_name='IBAN')
    titular_conta = models.CharField(max_length=255, blank=True, default='', verbose_name='Titular da Conta')
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

    def clean(self):
        if self.data_admissao:
            validate_date_not_future(self.data_admissao, field_name="Data de Admissão")
        if self.data_nascimento:
            idade = (timezone.now().date() - self.data_nascimento).days / 365.25
            if idade < 18:
                raise ValidationError(
                    {'data_nascimento': 'O colaborador deve ter pelo menos 18 anos.'}
                )

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)

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

# ─── Processamento Salarial ───────────────────────────────────────────────────

class ProcessamentoSalarial(models.Model):
    ESTADOS = [
        ('Rascunho', 'Rascunho'),
        ('Processado', 'Processado'),
        ('Pago', 'Pago'),
    ]
    banca       = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='processamentos')
    filial      = models.ForeignKey(FilialBanca, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='processamentos')
    mes         = models.PositiveSmallIntegerField(db_index=True)
    ano         = models.PositiveSmallIntegerField(db_index=True)
    estado      = models.CharField(max_length=15, choices=ESTADOS, default='Rascunho')
    criado_em   = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)
    pdf_gerado  = models.BooleanField(default=False)

    class Meta:
        db_table = 'rh_processamentos'
        unique_together = ('banca', 'filial', 'mes', 'ano')
        ordering = ['-ano', '-mes']

    def clean(self):
        from django.core.exceptions import ValidationError
        dupes = ProcessamentoSalarial.objects.filter(
            banca=self.banca, mes=self.mes, ano=self.ano
        )
        if self.filial_id is None:
            dupes = dupes.filter(filial__isnull=True)
        else:
            dupes = dupes.filter(filial=self.filial)
        if self.pk:
            dupes = dupes.exclude(pk=self.pk)
        if dupes.exists():
            raise ValidationError(
                f'Já existe um processamento para {self.banca}/{self.mes:02d}/{self.ano}.'
            )

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.banca.nome} — {self.mes:02d}/{self.ano}"

    @property
    def total_liquido(self):
        return sum(r.liquido for r in self.recibos.all())

    @property
    def total_bruto(self):
        return sum(r.bruto for r in self.recibos.all())

    @property
    def total_descontos(self):
        return sum(r.total_descontos for r in self.recibos.all())


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
    
class ReciboSalarial(models.Model):
    processamento = models.ForeignKey(ProcessamentoSalarial, on_delete=models.CASCADE, related_name='recibos')
    colaborador   = models.ForeignKey(Colaborador, on_delete=models.PROTECT, related_name='recibos')
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

    @property
    def faltas_count(self):
        if self.outros_descontos and self.salario_base:
            return round(float(self.outros_descontos) / float(self.salario_base) * 22)
        return 0


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

    def clean(self):
        super().clean()
        # Valida que data_encerramento, se informada, não é anterior à data_abertura
        if self.data_encerramento and self.data_abertura:
            validate_date_range(
                self.data_abertura,
                self.data_encerramento,
                'Data de Abertura',
                'Data de Encerramento'
            )
        # Valida que data_encerramento não é no passado
        if self.data_encerramento:
            validate_date_not_past(self.data_encerramento, 'Data de Encerramento', allow_today=True)

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)

class Candidatura(models.Model):
    ESTADOS = [
        ('Recebida', 'Recebida'),
        ('Em Análise', 'Em Análise'),
        ('Entrevista', 'Entrevista Agendada'),
        ('Aprovado', 'Aprovado'),
        ('Rejeitado', 'Rejeitado'),
    ]
    vaga        = models.ForeignKey(Vaga, on_delete=models.CASCADE, related_name='candidaturas')
    nome        = models.CharField(max_length=255, db_index=True)
    email       = models.EmailField(db_index=True)
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

    def clean(self):
        from django.utils import timezone
        if self.data_entrevista and self.data_entrevista < timezone.now():
            raise ValidationError({'data_entrevista': 'A data da entrevista não pode estar no passado.'})


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
    data_hora       = models.DateTimeField(db_index=True)
    tipo            = models.CharField(max_length=15, choices=TIPOS, default='Presencial')
    local_link      = models.CharField(max_length=300, blank=True, default='',
                                       verbose_name='Local / Link')
    entrevistador   = models.CharField(max_length=255, blank=True, default='')
    resultado       = models.CharField(max_length=15, choices=RESULTADOS, default='Pendente', db_index=True)
    nota            = models.PositiveSmallIntegerField(null=True, blank=True,
                                                       help_text='Nota de 1 a 10')
    observacoes     = models.TextField(blank=True, default='')
    criado_em       = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'rh_entrevistas'
        ordering = ['data_hora']

    def __str__(self):
        return f"Entrevista — {self.candidatura.nome} ({self.data_hora:%d/%m/%Y})"

    def clean(self):
        validate_date_not_past(self.data_hora, field_name="Data e Hora", allow_today=True)

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


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
    estado          = models.CharField(max_length=10, choices=ESTADOS, default='Pendente', db_index=True)
    notas           = models.TextField(blank=True, default='')
    criado_em       = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'rh_planos_integracao'
        ordering = ['-criado_em']

    def __str__(self):
        return f'Integração - {self.candidatura.nome}'

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

    def clean(self):
        if self.data_fim_prevista:
            validate_date_range(self.data_inicio, self.data_fim_prevista, "Data de Início", "Data Fim Prevista")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class TarefaIntegracao(models.Model):
    """Tarefa individual dentro do plano de integração."""
    plano       = models.ForeignKey(PlanoIntegracao, on_delete=models.CASCADE, related_name='tarefas')
    titulo      = models.CharField(max_length=200)
    descricao   = models.TextField(blank=True, default='')
    responsavel = models.CharField(max_length=255, blank=True, default='')
    prazo       = models.DateField(null=True, blank=True, db_index=True)
    concluida   = models.BooleanField(default=False)
    criado_em   = models.DateTimeField(auto_now_add=True, db_index=True)

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
    tipo = models.CharField(max_length=25, choices=TIPOS_FATURA, db_index=True)
    estado = models.CharField(max_length=15, choices=ESTADOS, default='EMITIDA', db_index=True)
    
    # Relacionamentos
    banca = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='faturas')
    filial = models.ForeignKey(FilialBanca, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='faturas')
    colaborador = models.ForeignKey('Colaborador', on_delete=models.CASCADE, related_name='faturas', null=True, blank=True)
    processamento_salarial = models.ForeignKey('ProcessamentoSalarial', on_delete=models.CASCADE, related_name='faturas')
    
    # Valores
    valor_bruto = models.DecimalField(max_digits=15, decimal_places=2)
    valor_liquido = models.DecimalField(max_digits=15, decimal_places=2)
    valor_imposto = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dados da fatura
    data_emissao = models.DateTimeField(auto_now_add=True, db_index=True)
    data_vencimento = models.DateField(db_index=True)
    data_pagamento = models.DateTimeField(null=True, blank=True)
    
    # Descrição
    descricao = models.TextField()
    observacoes = models.TextField(blank=True, default='')
    
    # Metadados
    criado_por = models.IntegerField(null=True, blank=True, db_index=True)  # ID do usuário que criou
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
        return self.data_vencimento < timezone.now().date() and self.estado != 'Paga'

    def clean(self):
        if self.data_emissao:
            validate_date_range(self.data_emissao.date(), self.data_vencimento, "Data de Emissão", "Data de Vencimento")
        if self.data_pagamento:
            validate_date_not_future(self.data_pagamento, field_name="Data de Pagamento")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)

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
    data        = models.DateField(db_index=True)
    tipo        = models.CharField(max_length=20, choices=TIPOS, default='Entrada')
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_saida  = models.TimeField(null=True, blank=True)
    horas_extras = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    justificacao = models.TextField(blank=True, default='')
    estado      = models.CharField(max_length=10, choices=ESTADOS, default='Pendente', db_index=True)
    aprovado_por = models.ForeignKey(Colaborador, on_delete=models.SET_NULL, null=True, blank=True, 
                                    related_name='presencas_aprovadas', help_text='Quem aprovou/rejeitou este registo')
    data_aprovacao = models.DateTimeField(null=True, blank=True)
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_presencas'
        unique_together = ('colaborador', 'data')
        ordering = ['-data']

    def clean(self):
        validate_date_not_future(self.data, field_name="Data")
        if self.data_aprovacao:
            validate_date_not_future(self.data_aprovacao, field_name="Data de Aprovação")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class PedidoFerias(models.Model):
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Aprovado', 'Aprovado'),
        ('Rejeitado', 'Rejeitado'),
    ]
    colaborador  = models.ForeignKey(Colaborador, on_delete=models.CASCADE, related_name='pedidos_ferias')
    data_inicio  = models.DateField()
    data_fim     = models.DateField()
    motivo       = models.TextField(blank=True, default='')
    estado       = models.CharField(max_length=10, choices=ESTADOS, default='Pendente', db_index=True)
    aprovado_por = models.ForeignKey(Colaborador, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='ferias_aprovadas')
    data_aprovacao = models.DateTimeField(null=True, blank=True)
    criado_em    = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'rh_pedidos_ferias'
        ordering = ['-criado_em']

    @property
    def dias(self):
        return max((self.data_fim - self.data_inicio).days + 1, 0)

    def clean(self):
        # Vide rh/acesso.py docstring para fluxo completo de aprovacao.
        # Pedido de férias não pode começar no passado (a menos que seja edição)
        if not self.pk:
            validate_date_not_past(self.data_inicio, field_name="Data de Início", allow_today=True)
        validate_date_range(self.data_inicio, self.data_fim, "Data de Início", "Data de Fim")
        if self.dias <= 0:
            raise ValidationError({"data_fim": "O período de férias deve ter pelo menos 1 dia."})
        # Validar sobreposição com pedidos já aprovados
        overlap = PedidoFerias.objects.filter(
            colaborador=self.colaborador,
            estado='Aprovado',
            data_inicio__lte=self.data_fim,
            data_fim__gte=self.data_inicio,
        )
        if self.pk:
            overlap = overlap.exclude(pk=self.pk)
        if overlap.exists():
            raise ValidationError(
                f'O colaborador já tem férias aprovadas neste período '
                f'({overlap.first().data_inicio} a {overlap.first().data_fim}).'
            )

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class HistoricoPresenca(models.Model):
    """Audit trail para aprovações de presenças e férias."""
    ACOES = [
        ('CRIADA', 'Criada'),
        ('APROVADA', 'Aprovada'),
        ('REJEITADA', 'Rejeitada'),
        ('ALTERADA', 'Alterada'),
        ('REMOVIDA', 'Removida'),
        ('FALTA_AUTO', 'Falta Auto-Marcada'),
    ]
    TIPOS_REGISTO = [
        ('presenca', 'Presença'),
        ('ferias', 'Férias'),
    ]
    banca       = models.ForeignKey('Banca', on_delete=models.CASCADE, related_name='historico_presencas')
    filial      = models.ForeignKey('FilialBanca', on_delete=models.SET_NULL, null=True, blank=True)
    tipo_registo = models.CharField(max_length=20, choices=TIPOS_REGISTO)
    registo_id  = models.PositiveIntegerField()
    accao       = models.CharField(max_length=20, choices=ACOES)
    estado_anterior = models.CharField(max_length=20, blank=True, default='')
    estado_novo = models.CharField(max_length=20, blank=True, default='')
    colaborador = models.ForeignKey('Colaborador', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    colaborador_nome = models.CharField(max_length=255, blank=True, default='')
    aprovador   = models.ForeignKey('Colaborador', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    aprovador_nome = models.CharField(max_length=255, blank=True, default='')
    observacao  = models.TextField(blank=True, default='')
    criado_em   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'rh_historico_presencas'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['banca', 'tipo_registo', 'registo_id']),
            models.Index(fields=['colaborador']),
        ]


class DelegacaoAprovacao(models.Model):
    """Delegação de autoridade de aprovação durante ausência."""
    banca       = models.ForeignKey('Banca', on_delete=models.CASCADE, related_name='delegacoes_aprovacao')
    delegante   = models.ForeignKey('Colaborador', on_delete=models.CASCADE, related_name='delegacoes_feitas')
    delegado    = models.ForeignKey('Colaborador', on_delete=models.CASCADE, related_name='delegacoes_recebidas')
    data_inicio = models.DateField()
    data_fim    = models.DateField()
    ativo       = models.BooleanField(default=True)
    motivo      = models.TextField(blank=True, default='')
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_delegacoes_aprovacao'
        indexes = [
            models.Index(fields=['delegante', 'ativo']),
            models.Index(fields=['delegado', 'ativo']),
        ]

    @property
    def ativa(self):
        hoje = timezone.now().date()
        return self.ativo and self.data_inicio <= hoje <= self.data_fim

    def clean(self):
        if self.delegante_id == self.delegado_id:
            raise ValidationError('Não pode delegar a si próprio.')
        if self.data_inicio > self.data_fim:
            raise ValidationError('Data de fim deve ser posterior à data de início.')

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class NotificacaoRH(models.Model):
    """Notificações in-app do módulo RH."""
    TIPOS = [
        ('aprovacao_pendente', 'Aprovação Pendente'),
        ('pedido_aprovado', 'Pedido Aprovado'),
        ('pedido_rejeitado', 'Pedido Rejeitado'),
        ('delegacao_recebida', 'Delegação Recebida'),
        ('delegacao_expirada', 'Delegação Expirada'),
        ('sla_alerta', 'Alerta SLA'),
    ]
    banca        = models.ForeignKey('Banca', on_delete=models.CASCADE, related_name='notificacoes_rh')
    destinatario = models.ForeignKey('Colaborador', on_delete=models.CASCADE, related_name='notificacoes_rh')
    tipo         = models.CharField(max_length=30, choices=TIPOS)
    titulo       = models.CharField(max_length=255)
    mensagem     = models.TextField()
    link         = models.CharField(max_length=500, blank=True, default='')
    lida         = models.BooleanField(default=False)
    criado_em    = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'rh_notificacoes'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['destinatario', 'lida']),
        ]


# ─── Avaliação de Desempenho ──────────────────────────────────────────────────

class CicloAvaliacao(models.Model):
    ESTADOS = [
        ('Aberto', 'Aberto'),
        ('Em Curso', 'Em Curso'),
        ('Encerrado', 'Encerrado'),
    ]
    banca       = models.ForeignKey(Banca, on_delete=models.CASCADE, related_name='ciclos_avaliacao')
    nome        = models.CharField(max_length=200)
    periodo_inicio = models.DateField(db_index=True)
    periodo_fim = models.DateField()
    estado      = models.CharField(max_length=10, choices=ESTADOS, default='Aberto')
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_ciclos_avaliacao'
        ordering = ['-periodo_inicio']

    def clean(self):
        validate_date_range(self.periodo_inicio, self.periodo_fim, "Período de Início", "Período de Fim")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class MetricaAvaliacao(models.Model):
    ciclo = models.ForeignKey(CicloAvaliacao, on_delete=models.CASCADE, related_name='metricas')
    nome = models.CharField(max_length=100)
    descricao = models.CharField(max_length=255, blank=True, default='')
    ordem = models.PositiveSmallIntegerField(default=0, db_index=True)

    class Meta:
        db_table = 'rh_metricas_avaliacao'
        ordering = ['ordem']
        unique_together = ('ciclo', 'nome')

    def __str__(self):
        return f'{self.ciclo.nome} — {self.nome}'


class NotaMetrica(models.Model):
    avaliacao = models.ForeignKey('Avaliacao', on_delete=models.CASCADE, related_name='notas_metricas')
    metrica = models.ForeignKey(MetricaAvaliacao, on_delete=models.CASCADE, related_name='notas')
    nota = models.PositiveSmallIntegerField(default=3)

    class Meta:
        db_table = 'rh_notas_metricas'
        unique_together = ('avaliacao', 'metrica')

    def __str__(self):
        return f'{self.avaliacao.colaborador.nome} — {self.metrica.nome}: {self.nota}'


class Avaliacao(models.Model):
    ciclo       = models.ForeignKey(CicloAvaliacao, on_delete=models.CASCADE, related_name='avaliacoes')
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT, related_name='avaliacoes')
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
        n = float(str(self.nota_global))
        if n >= 4.5: return ('Excelente', 'green')
        if n >= 3.5: return ('Bom', 'blue')
        if n >= 2.5: return ('Satisfatório', 'amber')
        return ('Necessita Melhoria', 'red')


# ─── Mesa da Assembleia (cargos globais) ───────────────────────────────────────

class CargoMesa(models.Model):
    FUNCOES = [
        ('Presidente', 'Presidente'),
        ('Vice-Presidente', 'Vice-Presidente'),
        ('1º Secretário', '1º Secretário'),
        ('2º Secretário', '2º Secretário'),
        ('Secretário', 'Secretário'),
        ('Vogal', 'Vogal'),
    ]
    usuario = models.OneToOneField('users.Usuario', on_delete=models.CASCADE, related_name='cargo_mesa')
    funcao = models.CharField(max_length=30, choices=FUNCOES, unique=True)
    atribuido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rh_cargos_mesa'
        verbose_name = 'Cargo da Mesa'
        verbose_name_plural = 'Cargos da Mesa'

    def __str__(self):
        return f'{self.usuario.nome} — {self.funcao}'
