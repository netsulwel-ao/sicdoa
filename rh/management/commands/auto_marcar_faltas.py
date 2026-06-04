from datetime import date
from django.core.management.base import BaseCommand
from rh.models import Banca, RegistoPresenca


class Command(BaseCommand):
    help = 'Marca Falta para colaboradores ativos sem registo de presença num dia útil'

    def add_arguments(self, parser):
        parser.add_argument('--data', type=str, help='Data alvo (YYYY-MM-DD). Padrão: hoje')
        parser.add_argument('--banca-slug', type=str, help='Slug da banca. Padrão: todas')

    def handle(self, *args, **options):
        data_alvo = date.today()
        if options['data']:
            from datetime import datetime
            data_alvo = datetime.strptime(options['data'], '%Y-%m-%d').date()

        if data_alvo.weekday() >= 5:
            self.stdout.write(f'{data_alvo} é fim de semana — nada a fazer.')
            return

        bancas = Banca.objects.filter(activa=True)
        if options['banca_slug']:
            bancas = bancas.filter(slug=options['banca_slug'])

        total = 0
        for banca in bancas:
            cols = banca.colaboradores.filter(estado='Ativo').only('id', 'nome')
            for col in cols:
                if not RegistoPresenca.objects.filter(colaborador=col, data=data_alvo).exists():
                    try:
                        reg = RegistoPresenca(
                            colaborador=col,
                            data=data_alvo,
                            tipo='Falta',
                            estado='Pendente',
                            justificacao='Falta automática — não registou presença',
                        )
                        reg.full_clean()
                        reg.save()
                        total += 1
                    except Exception as e:
                        self.stderr.write(f'Erro ao marcar falta para {col.nome}: {e}')

        self.stdout.write(self.style.SUCCESS(f'{total} falta(s) marcada(s) em {data_alvo}.'))
