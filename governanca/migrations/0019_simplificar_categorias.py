from django.db import migrations


def forward(apps, schema_editor):
    CategoriaMembro = apps.get_model('governanca', 'CategoriaMembro')
    Usuario = apps.get_model('users', 'Usuario')

    # 1 — Criar as 2 categorias reais
    cat_oficial, _ = CategoriaMembro.objects.get_or_create(
        slug='despachante-oficial',
        defaults={'nome': 'Despachante Oficial', 'isento': False, 'ordem': 1},
    )
    cat_isento, _ = CategoriaMembro.objects.get_or_create(
        slug='isento',
        defaults={'nome': 'Isento', 'isento': True, 'ordem': 2},
    )

    # 2 — Actualizar Usuario.categoria com base no papel
    for u in Usuario.objects.all():
        if u.categoria_id:
            # já tem categoria — mantém a que tem a menos que seja das antigas
            old = CategoriaMembro.objects.filter(pk=u.categoria_id).first()
            if old and old.slug in ('despachante-efectivo', 'despachante-estagiario',
                                     'despachante-senior', 'empresa-despacho-aduaneiro'):
                u.categoria = cat_oficial if u.papel == 'Despachante Oficial' else cat_isento
                u.save(update_fields=['categoria_id'])
        else:
            # sem categoria — atribuir por papel
            if u.papel == 'Despachante Oficial':
                u.categoria = cat_oficial
            else:
                u.categoria = cat_isento
            u.save(update_fields=['categoria_id'])

    # 3 — Apagar categorias antigas
    CategoriaMembro.objects.filter(
        slug__in=('despachante-efectivo', 'despachante-estagiario',
                  'despachante-senior', 'empresa-despacho-aduaneiro', 'membro-honorario')
    ).delete()


def reverse(apps, schema_editor):
    CategoriaMembro = apps.get_model('governanca', 'CategoriaMembro')
    Usuario = apps.get_model('users', 'Usuario')

    # Recriar categorias antigas
    antigas = [
        ('Despachante Efectivo', 'despachante-efectivo', False, 1),
        ('Despachante Estagiário', 'despachante-estagiario', False, 2),
        ('Despachante Sénior', 'despachante-senior', False, 3),
        ('Empresa de Despacho Aduaneiro', 'empresa-despacho-aduaneiro', False, 4),
        ('Membro Honorário', 'membro-honorario', True, 5),
    ]
    for nome, slug, isento, ordem in antigas:
        CategoriaMembro.objects.get_or_create(
            slug=slug,
            defaults={'nome': nome, 'isento': isento, 'ordem': ordem},
        )

    # Deixar usuarios com as novas categorias — não revertemos isso
    # para não perder dados. O reverse é só para permitir rollback da estrutura.


class Migration(migrations.Migration):

    dependencies = [
        ('governanca', '0018_documentoassembleia_conteudo_and_more'),
        ('users', '0006_usuario_categoria'),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
