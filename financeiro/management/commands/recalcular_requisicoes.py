from django.core.management.base import BaseCommand
from financeiro.models import RequisicaoFundo


class Command(BaseCommand):
    help = 'Recalcula retenção para todas as requisições de fundos existentes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria feito sem fazer alterações',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        requisicoes = RequisicaoFundo.objects.all()
        total = requisicoes.count()
        
        self.stdout.write(f'Total de requisições a processar: {total}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nenhuma alteração será feita'))
        
        atualizadas = 0
        for req in requisicoes:
            req._recalcular_totais()
            
            if not dry_run:
                req.save(update_fields=['subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral'])
            
            self.stdout.write(
                f'{req.numero_requisicao}: '
                f'Subtotal={req.subtotal_geral} | '
                f'IVA={req.iva_honorarios} | '
                f'Retenção={req.retencao} | '
                f'Total={req.total_geral}'
            )
            atualizadas += 1
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'[DRY-RUN] Seriam atualizadas {atualizadas} requisições'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✓ {atualizadas} requisições atualizadas com sucesso'))
