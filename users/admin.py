from django.contrib import admin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'email', 'papel', 'nif', 'cedula', 'status', 'created_at')
    list_filter = ('papel', 'status')
    search_fields = ('nome', 'email', 'nif', 'username')
    ordering = ('-created_at',)
