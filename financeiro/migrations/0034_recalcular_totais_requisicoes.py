from django.db import migrations
from decimal import Decimal
from django.db.models import Sum


def recalcular_totais(apps, schema_editor):
    RequisicaoFundo = apps.get_model('financeiro', 'RequisicaoFundo')
    RequisicaoFundoLinha = apps.get_model('financeiro', 'RequisicaoFundoLinha')
    
    for req in RequisicaoFundo.objects.all():
        linhas = RequisicaoFundoLinha.objects.filter(requisicao=req)
        
        subtotal = sum((l.valor or 0) for l in linhas)
        valor_honorarios = linhas.filter(
            tipo_custo='Honorários do Despachante'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0')
        
        iva = (subtotal * Decimal('0.14')).quantize(Decimal('0.01'))
        retencao = (valor_honorarios * Decimal('0.065')).quantize(Decimal('0.01'))
        total = (subtotal + iva + retencao).quantize(Decimal('0.01'))
        
        RequisicaoFundo.objects.filter(pk=req.pk).update(
            subtotal_geral=subtotal,
            iva_honorarios=iva,
            retencao=retencao,
            total_geral=total,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0033_remove_campos_bancarios_requisicao'),
    ]

    operations = [
        migrations.RunPython(recalcular_totais, migrations.RunPython.noop),
    ]
