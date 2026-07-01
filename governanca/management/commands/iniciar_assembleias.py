from django.core.management.base import BaseCommand
from django.utils import timezone
from governanca.models import Assembleia
from governanca.views import _livekit_token, _enviar_convocatorias_email
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


class Command(BaseCommand):
    help = 'Inicia automaticamente assembleias cuja data/hora já passou'

    def handle(self, *args, **options):
        agora = timezone.now()
        pendentes = Assembleia.objects.filter(
            status='Agendada',
            data_hora__lte=agora,
        )
        count = 0
        for a in pendentes:
            old_status = a.status
            a.status = 'Em Curso'
            a.save()

            # Enviar convocatórias por email
            _enviar_convocatorias_email(a)

            # Gerar LiveKit room se vazio
            if not a.livekit_room:
                a.livekit_room = f'assembleia_{a.pk}'
                a.save(update_fields=['livekit_room'])

            # Notificar via WebSocket se possível
            try:
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f'assembleia_{a.pk}',
                    {
                        'type': 'broadcast_chat',
                        'data': {
                            'action': 'assembleia_iniciada',
                            'assembleia_id': a.pk,
                            'titulo': a.titulo,
                            'message': 'Assembleia iniciada automaticamente',
                        },
                    }
                )
            except Exception:
                self.stdout.write(self.style.ERROR(f"Falha ao notificar chat para assembleia #{a.pk}"))

            self.stdout.write(
                self.style.SUCCESS(
                    f'Assembleia #{a.pk} "{a.titulo}": {old_status} → Em Curso'
                )
            )
            count += 1

        if count == 0:
            self.stdout.write(self.style.WARNING('Nenhuma assembleia pendente encontrada.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{count} assembleia(s) iniciada(s) com sucesso.'))
