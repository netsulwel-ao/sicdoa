from django.contrib import admin
from .models import (
    Banca, FilialBanca, Colaborador, ProcessamentoSalarial, ReciboSalarial,
    Vaga, Candidatura, RegistoPresenca, PedidoFerias, CicloAvaliacao, Avaliacao,
    HistoricoPresenca, DelegacaoAprovacao, NotificacaoRH,
)


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


@admin.register(HistoricoPresenca)
class HistoricoPresencaAdmin(admin.ModelAdmin):
    list_display = ('banca', 'colaborador_nome', 'tipo_registo', 'accao', 'estado_novo', 'criado_em')
    list_filter = ('tipo_registo', 'accao', 'banca')
    search_fields = ('colaborador_nome', 'aprovador_nome')
    date_hierarchy = 'criado_em'


@admin.register(DelegacaoAprovacao)
class DelegacaoAprovacaoAdmin(admin.ModelAdmin):
    list_display = ('delegante', 'delegado', 'banca', 'data_inicio', 'data_fim', 'ativo')
    list_filter = ('ativo', 'banca')
    search_fields = ('delegante__nome', 'delegado__nome')


@admin.register(NotificacaoRH)
class NotificacaoRHAdmin(admin.ModelAdmin):
    list_display = ('destinatario', 'tipo', 'titulo', 'lida', 'criado_em')
    list_filter = ('tipo', 'lida', 'banca')
    search_fields = ('titulo', 'mensagem')
