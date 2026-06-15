from django.db import migrations


def rename_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    updates = {
        'gerir_clientes': 'Gerir Clientes',
        'gerir_rh': 'Gerir Recursos Humanos',
        'gerir_financeiro': 'Gerir Financeiro',
    }
    for codigo, novo_nome in updates.items():
        Permissao.objects.filter(codigo=codigo).update(nome=novo_nome)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0033_seed_permissoes_inst_recrutamento_subsidios"),
    ]

    operations = [
        migrations.RunPython(rename_permissoes, migrations.RunPython.noop),
    ]
