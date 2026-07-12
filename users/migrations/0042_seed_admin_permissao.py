from django.db import migrations


PERMISSOES = [
    ('admin', 'Administrador do Sistema', 'Sistema'),
]


def seed(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    for codigo, nome, grupo in PERMISSOES:
        Permissao.objects.get_or_create(
            codigo=codigo,
            defaults={'nome': nome, 'grupo': grupo},
        )


def unseed(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo__in=[p[0] for p in PERMISSOES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0041_add_usuario_assinatura"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
