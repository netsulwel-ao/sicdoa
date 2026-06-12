from django.db import migrations


PERMISSOES = [
    ('alterar_perfil', 'Alterar Próprio Perfil',
     'Permite que o colaborador edite os seus próprios dados pessoais (nome, telefone, username) e altere a sua palavra-passe.',
     'Colaborador', 'fa-user-edit'),
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
        ('users', '0025_funcao_usuario_funcao'),
    ]
    operations = [
        migrations.RunPython(add_permissoes, remove_permissoes),
    ]
