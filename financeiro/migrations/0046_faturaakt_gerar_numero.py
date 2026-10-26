# Migration: fills in numero_fatura for any FaturaAGT rows that were created
# before the auto-generator was added to the model's save() method.
# Without this, rows with numero_fatura='' would violate the unique constraint
# on a fresh database import or on a database that already has such rows.

from django.db import migrations
from django.utils import timezone


def _preencher_numeros_vazios(apps, schema_editor):
    """
    Atribui numero_fatura no padrão FAT-{ano}-{seq:04d} a todos os registos
    que tenham o campo em branco.
    """
    FaturaAGT = apps.get_model('financeiro', 'FaturaAGT')
    sem_numero = FaturaAGT.objects.filter(numero_fatura='').order_by('id')
    ano = timezone.now().year

    # Encontrar o maior sequencial já existente para este ano
    ultimo = FaturaAGT.objects.filter(
        numero_fatura__startswith=f'FAT-{ano}-'
    ).order_by('-numero_fatura').first()

    if ultimo and ultimo.numero_fatura:
        try:
            seq = int(ultimo.numero_fatura.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    for fatura in sem_numero:
        fatura.numero_fatura = f'FAT-{ano}-{seq:04d}'
        fatura.save()
        seq += 1


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0045_fatura_agt'),
    ]

    operations = [
        migrations.RunPython(
            _preencher_numeros_vazios,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
