from django.contrib import admin
from .models import Banca, FilialBanca, Colaborador, ProcessamentoSalarial, ReciboSalarial
from .models import Vaga, Candidatura, RegistoPresenca, PedidoFerias, CicloAvaliacao, Avaliacao


@admin.register(Banca)
class BancaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'nif', 'tipo', 'email', 'ativa', 'criado_em')
    list_filter = ('tipo', 'ativa', 'provincia')
    search_fields = ('nome', 'nif')


@admin.register(FilialBanca)
class FilialBancaAdmin(admin.ModelAdmin):
    list_display = ('banca', 'provincia', 'municipio', 'responsavel', 'ativa')
    list_filter = ('provincia', 'ativa')
    search_fields = ('banca__nome', 'provincia', 'responsavel')


@admin.register(Colaborador)
class ColaboradorAdmin(admin.ModelAdmin):
    list_display = ('nome', 'banca', 'filial', 'cargo', 'estado', 'data_admissao')
    list_filter = ('cargo', 'estado', 'banca')
    search_fields = ('nome', 'bi', 'nif', 'email')
