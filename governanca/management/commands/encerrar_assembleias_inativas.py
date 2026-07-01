from django.core.management.base import BaseCommand
from django.utils import timezone
from governanca.models import Assembleia, ManifestoIntegridade, LogAssembleia
from governanca.views import _notificar_para_papel
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json


class Command(BaseCommand):
    help = 'Encerra automaticamente assembleias sem actividade há mais de 20 minutos'

    def handle(self, *args, **options):
        agora = timezone.now()
        limite = agora - timezone.timedelta(minutes=20)
        inativas = Assembleia.objects.filter(
            status='Em Curso',
            ultima_actividade__lt=limite,
        )
        count = 0
        for a in inativas:
            pautas_em_votacao = a.pautas.with_vote_counts().filter(status='Em Votacao')
            for pauta in pautas_em_votacao:
                pauta.status = 'Concluida'
                pauta.encerrado_em = agora
                pauta.apurar_resultado()

            a.status = 'Concluida'
            a.data_encerramento = agora
            a.hash_integridade = a.gerar_hash_integridade()
            a.save()

            todas_pautas = a.pautas.with_vote_counts()
            ManifestoIntegridade.objects.create(
                assembleia=a,
                hash_consolidado=a.hash_integridade,
                dados_json=json.dumps({
                    'presentes': a.presentes_count,
                    'total_pautas': a.total_pautas,
                    'pautas': [{'id': p.id, 'titulo': p.titulo, 'resultado': p.resultado_final} for p in todas_pautas],
                }, ensure_ascii=False),
                gerado_por=None,
            )

            _notificar_para_papel('Administrador', 'resultado_publicado',
                                  f'Assembleia Encerrada por Inactividade: {a.titulo}',
                                  'A assembleia foi encerrada automaticamente por falta de actividade durante 20 minutos.',
                                  f'/governanca/assembleia/{a.pk}/')

            LogAssembleia.objects.create(
                assembleia=a,
                usuario=None,
                acao='assembleia_concluida_auto',
                detalhes={
                    'motivo': 'inactividade_20min',
                    'hash': a.hash_integridade,
                    'total_pautas': a.total_pautas,
                },
            )

            try:
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f'assembleia_{a.pk}',
                    {
                        'type': 'broadcast_chat',
                        'data': {
                            'action': 'assembleia_encerrada',
                            'assembleia_id': a.pk,
                            'titulo': a.titulo,
                            'message': 'Assembleia encerrada por inactividade',
                        },
                    }
                )
            except Exception:
                self.stdout.write(self.style.ERROR(f"Falha ao notificar chat para assembleia #{a.pk}"))

            self.stdout.write(
                self.style.SUCCESS(
                    f'Assembleia #{a.pk} "{a.titulo}": auto-encerrada por inactividade'
                )
            )
            count += 1

        if count == 0:
            self.stdout.write(self.style.WARNING('Nenhuma assembleia inactiva encontrada.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{count} assembleia(s) encerrada(s) por inactividade.'))
