from django.contrib import admin
from .models import Permissao, Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'email', 'papel', 'is_staff', 'nif', 'cedula', 'status', 'created_at')
    list_filter = ('papel', 'status', 'is_staff')
    search_fields = ('nome', 'email', 'nif', 'username')
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('username', 'password', 'nome', 'email', 'papel', 'status')}),
        ('Permissões de Admin', {'fields': ('is_staff', 'is_superuser'), 'classes': ('wide',)}),
        ('Informações Adicionais', {'fields': ('nif', 'cedula', 'telefone', 'foto', 'categoria')}),
    )


@admin.register(Permissao)
class PermissaoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome', 'grupo')
    list_filter = ('grupo',)
    search_fields = ('codigo', 'nome')
