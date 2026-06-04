from django.db import models


class Usuario(models.Model):
    PAPEIS = [
        ('Administrador', 'Administrador'),
        ('Despachante Oficial', 'Despachante Oficial'),
        ('Operador', 'Operador'),
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
    cedula = models.CharField(max_length=50, null=True, blank=True)
    papel = models.CharField(max_length=50, choices=PAPEIS, default='Despachante Oficial', db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Ativo', db_index=True)
    categoria = models.ForeignKey('governanca.CategoriaMembro', on_delete=models.SET_NULL, null=True, blank=True)
    sso_portal_id = models.IntegerField(null=True, blank=True)
    ultimo_acesso = models.DateTimeField(null=True, blank=True)
    nif = models.TextField(blank=True, default='')
    is_secretario = models.BooleanField(default=False)
    is_vice_secretario = models.BooleanField(default=False)
    cargos = models.ManyToManyField('Cargo', through='UsuarioCargo', through_fields=('usuario', 'cargo'), blank=True, related_name='membros')
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
    def cargos_lista(self):
        return self.cargos.all()

    def has_cargo(self, slug):
        return self.cargos.filter(slug=slug).exists()

    def __str__(self):
        return f"{self.usuario.nome} -> {self.cargo.nome}"


class Permissao(models.Model):
    codigo = models.SlugField(max_length=100, unique=True,
        help_text='Identificador único (ex: ver_secretaria, gerir_quotas)')
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True, default='')
    grupo = models.CharField(max_length=100, blank=True, default='',
        help_text='Agrupamento visual (ex: Secretaria, Financeiro)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'permissoes'
        verbose_name = 'Permissão'
        verbose_name_plural = 'Permissões'
        ordering = ['grupo', 'nome']

    def __str__(self):
        return self.nome


class Cargo(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    descricao = models.TextField(blank=True, default='')
    sistema = models.BooleanField(default=False, help_text='Cargo automático do sistema (não pode ser removido manualmente)')
    permissoes = models.ManyToManyField('Permissao', blank=True, related_name='cargos')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cargos'
        verbose_name = 'Cargo'
        verbose_name_plural = 'Cargos'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class UsuarioCargo(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='vinculos_cargo')
    cargo = models.OneToOneField(Cargo, on_delete=models.CASCADE, related_name='vinculo')
    atribuido_em = models.DateTimeField(auto_now_add=True)
    atribuido_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='atribuicoes_cargo')

    class Meta:
        db_table = 'usuarios_cargos'
        verbose_name = 'Vinculo de Cargo'
        verbose_name_plural = 'Vinculos de Cargos'

    def __str__(self):
        return f"{self.usuario.nome} -> {self.cargo.nome}"
