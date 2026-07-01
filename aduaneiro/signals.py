import json

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from utils.cache_utils import cache_invalidate_prefix

from .models import DeclaracaoUnica, HistoricoDU


@receiver(post_save, sender=DeclaracaoUnica)
@receiver(post_delete, sender=DeclaracaoUnica)
def invalida_cache_du(sender, instance, **kwargs):
    cache_invalidate_prefix(f'du_lista_{instance.usuario_id}')


def registrar_versao_du(du, campos_alterados, request=None):
    """Regista uma versão no histórico da DU (chamado após save)."""
    utilizador_id = None
    utilizador_nome = ''
    if request:
        utilizador_id = request.session.get('usuario_id')
        u = request.session.get('usuario', {})
        utilizador_nome = u.get('nome', '')
    HistoricoDU.objects.create(
        du=du,
        dados_json=du.dados_json or '{}',
        status=du.status or '',
        numero_du=du.numero_du or '',
        codigo_processo=du.codigo_processo or '',
        campos_alterados=json.dumps(campos_alterados, ensure_ascii=False),
        utilizador_id=utilizador_id,
        utilizador_nome=utilizador_nome,
    )
