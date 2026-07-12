from django.db import migrations


def delete_perm(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo='aprovar_requisicao').delete()


def restore_perm(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.get_or_create(
        codigo='aprovar_requisicao',
        defaults={'nome': 'Aprovar requisições de fundos', 'grupo': 'Financeiro'},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0043_fix_grupo_casing_aprovar_requisicao"),
    ]

    operations = [
        migrations.RunPython(delete_perm, restore_perm),
    ]
