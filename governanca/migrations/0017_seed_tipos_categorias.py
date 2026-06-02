from django.db import migrations


def seed_tipos(apps, schema_editor):
    TipoQuota = apps.get_model('governanca', 'TipoQuota')
    tipos = [
        ('Quota de Inscrição', 'inscricao', False, None),
        ('Quota Mensal', 'mensal', True, 30),
        ('Quota Trimestral', 'trimestral', True, 90),
        ('Quota Semestral', 'semestral', True, 180),
        ('Quota Anual', 'anual', True, 365),
        ('Quota Extraordinária', 'extraordinaria', False, None),
    ]
    for nome, slug, recorrente, dias in tipos:
        TipoQuota.objects.get_or_create(slug=slug, defaults={
            'nome': nome, 'recorrente': recorrente, 'dias_intervalo': dias,
        })


def seed_categorias(apps, schema_editor):
    CategoriaMembro = apps.get_model('governanca', 'CategoriaMembro')
    categorias = [
        ('Despachante Efectivo', 'despachante-efectivo', False, 1),
        ('Despachante Estagiário', 'despachante-estagiario', False, 2),
        ('Despachante Sénior', 'despachante-senior', False, 3),
        ('Empresa de Despacho Aduaneiro', 'empresa-despacho-aduaneiro', False, 4),
        ('Membro Honorário', 'membro-honorario', True, 5),
    ]
    for nome, slug, isento, ordem in categorias:
        CategoriaMembro.objects.get_or_create(slug=slug, defaults={
            'nome': nome, 'isento': isento, 'ordem': ordem,
        })


class Migration(migrations.Migration):

    dependencies = [
        ('governanca', '0016_categoriamembro_isencaomembro_tipoquota_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_tipos),
        migrations.RunPython(seed_categorias),
    ]
