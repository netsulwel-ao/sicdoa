from django.contrib import admin
from .models import (
    Assembleia, PautaVotacao, PresencaAssembleia,
    Procuracao, Voto, ManifestoIntegridade, AtaDigital, Notificacao
)

admin.site.register(Assembleia)
admin.site.register(PautaVotacao)
admin.site.register(PresencaAssembleia)
admin.site.register(Procuracao)
admin.site.register(Voto)
admin.site.register(ManifestoIntegridade)
admin.site.register(AtaDigital)
admin.site.register(Notificacao)
