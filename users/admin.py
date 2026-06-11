from django.contrib import admin
from .models import Permissao, Cargo, Usuario, UsuarioCargo


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


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'slug', 'sistema')
    search_fields = ('nome',)


@admin.register(Permissao)
class PermissaoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome', 'grupo')
    list_filter = ('grupo',)
    search_fields = ('codigo', 'nome')


@admin.register(UsuarioCargo)
class UsuarioCargoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'cargo', 'atribuido_em')
    list_select_related = ('usuario', 'cargo')
