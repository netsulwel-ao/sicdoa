from django.db import migrations

PERMISSOES = [
    ('acesso_auditoria', 'Acesso de Auditoria',
     'Acesso apenas de leitura a todos os módulos do sistema. Usuários com esta permissão '
     'podem visualizar dados mas não podem criar, editar ou cancelar documentos.',
     'Financeiro', 'fa-user-lock'),
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
        ('users', '0022_remove_gerir_membros_direcao'),
    ]
    operations = [
        migrations.RunPython(add_permissoes, remove_permissoes),
    ]
