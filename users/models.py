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
    nome = models.CharField(max_length=100)
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

    def __str__(self):
        return f"{self.nome} ({self.email})"
