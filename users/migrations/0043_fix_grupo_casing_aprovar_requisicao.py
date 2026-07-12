from django.db import migrations


def fix_grupo_casing(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo='aprovar_requisicao', grupo='financeiro').update(grupo='Financeiro')


def revert(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo='aprovar_requisicao', grupo='Financeiro').update(grupo='financeiro')


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0042_seed_admin_permissao"),
    ]

    operations = [
        migrations.RunPython(fix_grupo_casing, revert),
    ]
