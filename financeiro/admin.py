from django.contrib import admin, messages
from .models import RequisicaoFundo


ADMIN_GF = ('Administrador', 'Gestor Financeiro')


def _pode_aprovar(request):
    papel = getattr(request.user, 'papel', '')
    return papel in ADMIN_GF


@admin.action(description='Aprovar requisições seleccionadas')
def aprovar_requicoes(modeladmin, request, queryset):
    if not _pode_aprovar(request):
        messages.error(request, 'Apenas Administrador ou Gestor Financeiro pode aprovar.')
        return
    count = 0
    for obj in queryset.filter(estado__in=('Pendente', 'Em Aprovação')):
        obj.estado = 'Aprovada'
        obj.responsavel_aprovacao_id_usuario = request.user.id
        obj.responsavel_aprovacao_nome = request.user.nome
        obj.save(update_fields=['estado', 'responsavel_aprovacao_id_usuario', 'responsavel_aprovacao_nome'])
        count += 1
    messages.success(request, f'{count} requisição(ões) aprovada(s).')


@admin.action(description='Rejeitar requisições seleccionadas')
def rejeitar_requicoes(modeladmin, request, queryset):
    if not _pode_aprovar(request):
        messages.error(request, 'Apenas Administrador ou Gestor Financeiro pode rejeitar.')
        return
    count = 0
    for obj in queryset.filter(estado__in=('Pendente', 'Em Aprovação')):
        obj.estado = 'Rejeitada'
        obj.responsavel_aprovacao_id_usuario = request.user.id
        obj.responsavel_aprovacao_nome = request.user.nome
        obj.save(update_fields=['estado', 'responsavel_aprovacao_id_usuario', 'responsavel_aprovacao_nome'])
        count += 1
    messages.success(request, f'{count} requisição(ões) rejeitada(s).')


@admin.action(description='Cancelar requisições seleccionadas')
def cancelar_requicoes(modeladmin, request, queryset):
    if not _pode_aprovar(request):
        messages.error(request, 'Apenas Administrador ou Gestor Financeiro pode cancelar.')
        return
    count = 0
    for obj in queryset.filter(estado__in=('Pendente', 'Em Aprovação')):
        obj.estado = 'Cancelada'
        obj.save(update_fields=['estado'])
        count += 1
    messages.success(request, f'{count} requisição(ões) cancelada(s).')


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
