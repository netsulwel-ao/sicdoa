from django.db import migrations


def add_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.create(
        codigo='aprovar_requisicao',
        nome='Aprovar requisições de fundos',
        descricao='Aprovar requisições de fundos',
        grupo='financeiro',
        icone='fa-check-circle',
    )


def remove_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo='aprovar_requisicao').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0026_add_alterar_perfil_permissao'),
    ]

    operations = [
        migrations.RunPython(add_permissoes, remove_permissoes),
    ]
