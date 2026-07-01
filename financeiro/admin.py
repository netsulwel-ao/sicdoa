from django.contrib import admin, messages
from .models import RequisicaoFundo, FluxoAprovacao, NivelAprovacao, AprovacaoRequisicao


ADMIN = ('Administrador',)


def _pode_aprovar(request):
    papel = getattr(request.user, 'papel', '')
    return papel in ADMIN


@admin.action(description='Aprovar requisições seleccionadas')
def aprovar_requicoes(modeladmin, request, queryset):
    if not _pode_aprovar(request):
        messages.error(request, 'Apenas Administrador pode aprovar.')
        return
    objs = list(queryset.filter(estado__in=('Pendente', 'Em Aprovação')))
    for obj in objs:
        obj.estado = 'Aprovada'
        obj.responsavel_aprovacao_id_usuario = request.user.id
        obj.responsavel_aprovacao_nome = request.user.nome
    RequisicaoFundo.objects.bulk_update(
        objs, fields=['estado', 'responsavel_aprovacao_id_usuario', 'responsavel_aprovacao_nome']
    )
    messages.success(request, f'{len(objs)} requisição(ões) aprovada(s).')


@admin.action(description='Rejeitar requisições seleccionadas')
def rejeitar_requicoes(modeladmin, request, queryset):
    if not _pode_aprovar(request):
        messages.error(request, 'Apenas Administrador pode rejeitar.')
        return
    objs = list(queryset.filter(estado__in=('Pendente', 'Em Aprovação')))
    for obj in objs:
        obj.estado = 'Rejeitada'
        obj.responsavel_aprovacao_id_usuario = request.user.id
        obj.responsavel_aprovacao_nome = request.user.nome
    RequisicaoFundo.objects.bulk_update(
        objs, fields=['estado', 'responsavel_aprovacao_id_usuario', 'responsavel_aprovacao_nome']
    )
    messages.success(request, f'{len(objs)} requisição(ões) rejeitada(s).')


@admin.action(description='Cancelar requisições seleccionadas')
def cancelar_requicoes(modeladmin, request, queryset):
    if not _pode_aprovar(request):
        messages.error(request, 'Apenas Administrador pode cancelar.')
        return
    objs = list(queryset.filter(estado__in=('Pendente', 'Em Aprovação')))
    for obj in objs:
        obj.estado = 'Cancelada'
    RequisicaoFundo.objects.bulk_update(objs, fields=['estado'])
    messages.success(request, f'{len(objs)} requisição(ões) cancelada(s).')


@admin.register(RequisicaoFundo)
class RequisicaoFundoAdmin(admin.ModelAdmin):
    list_display = ('numero_requisicao', 'cliente', 'valor_solicitado', 'estado', 'solicitante_nome', 'data')
    list_filter = ('estado', 'data')
    search_fields = ('numero_requisicao', 'cliente__nome', 'solicitante_nome')
    ordering = ('-data',)
    actions = [aprovar_requicoes, rejeitar_requicoes, cancelar_requicoes]
    fieldsets = (
        (None, {'fields': ('numero_requisicao', 'cliente', 'processo_aduaneiro', 'estado')}),
        ('Valores', {'fields': ('valor_solicitado',)}),
        ('Detalhes', {'fields': ('justificacao', 'documento_justificativo')}),
        ('Responsáveis', {'fields': ('solicitante_id', 'solicitante_nome',
                                      'responsavel_aprovacao_id_usuario', 'responsavel_aprovacao_nome')}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if not request or not hasattr(request, 'user'):
            return False
        papel = getattr(request.user, 'papel', '')
        return papel == 'Administrador'

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return [f.name for f in self.model._meta.fields]
        return self.readonly_fields or []

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not _pode_aprovar(request):
            return {}
        return actions


@admin.register(FluxoAprovacao)
class FluxoAprovacaoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo', 'criado_em', 'criado_por')
    list_filter = ('ativo',)
    search_fields = ('nome',)


@admin.register(NivelAprovacao)
class NivelAprovacaoAdmin(admin.ModelAdmin):
    list_display = ('fluxo', 'ordem', 'nome', 'funcao', 'qtde_aprovadores')
    list_filter = ('fluxo',)
    ordering = ('fluxo', 'ordem')


@admin.register(AprovacaoRequisicao)
class AprovacaoRequisicaoAdmin(admin.ModelAdmin):
    list_display = ('requisicao', 'nivel', 'aprovador', 'estado', 'created_at')
    list_filter = ('estado',)
