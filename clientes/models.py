from django.db import models
from django.core.exceptions import ValidationError


class Cliente(models.Model):
    """Modelo para cadastro de clientes do despachante"""
    
    nome = models.CharField(max_length=255, db_index=True, verbose_name='Nome do Cliente')
    nif = models.CharField(max_length=50, unique=True, verbose_name='NIF')
    localizacao = models.TextField(verbose_name='Localização')
    telefone = models.CharField(max_length=30, blank=True, default='', verbose_name='Telefone')
    email = models.EmailField(blank=True, default='', db_index=True, verbose_name='Email')
    observacoes = models.TextField(blank=True, default='', verbose_name='Observações')
    limite_financeiro = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name='Limite Financeiro por Cliente')
    saldo_conta_corrente = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name='Saldo da Conta Corrente')
    usuario_id = models.IntegerField(null=True, blank=True, db_index=True, verbose_name='ID do Despachante')
    ativo = models.BooleanField(default=True, db_index=True, verbose_name='Ativo')
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação')
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name='Última Atualização')

    class Meta:
        db_table = 'clientes_clientes'
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.nif})"

    def clean(self):
        """Validação personalizada para o NIF"""
        if self.nif:
            # Verificar se já existe outro cliente com o mesmo NIF
            existing_cliente = Cliente.objects.filter(nif=self.nif).exclude(pk=self.pk).first()
            if existing_cliente:
                raise ValidationError({'nif': 'Já existe um cliente cadastrado com este NIF.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
