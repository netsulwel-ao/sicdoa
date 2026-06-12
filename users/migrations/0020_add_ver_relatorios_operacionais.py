from django.db import migrations

PERMISSOES = [
    ('ver_relatorios_operacionais', 'Ver Relatórios Operacionais',
     'Permite visualizar os relatórios operacionais com dados de todos os despachantes',
     'Financeiro', 'fa-chart-bar'),
]


def add_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    for codigo, nome, descricao, grupo, icone in PERMISSOES:
        Permissao.objects.get_or_create(
            codigo=codigo,
            defaults={'nome': nome, 'descricao': descricao, 'grupo': grupo, 'icone': icone},
        )


def remove_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo__in=[p[0] for p in PERMISSOES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0019_fix_permissoes'),
    ]
    operations = [
        migrations.RunPython(add_permissoes, remove_permissoes),
    ]
