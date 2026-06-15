from django.db import migrations

PERMISSOES = [
    {
        'codigo': 'ser_membro_mesa',
        'nome': 'Ser Membro da Mesa',
        'descricao': 'Permite pertencer à mesa da assembleia e gerar documentos oficiais',
        'grupo': 'Democracia Digital',
        'icone': 'fa-users',
    },
]

def add_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    for p in PERMISSOES:
        Permissao.objects.get_or_create(
            codigo=p['codigo'],
            defaults={
                'nome': p['nome'],
                'descricao': p['descricao'],
                'grupo': p['grupo'],
                'icone': p['icone'],
            },
        )

def remove_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo__in=[p['codigo'] for p in PERMISSOES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0030_fix_remove_papeis'),
    ]

    operations = [
        migrations.RunPython(add_permissoes, remove_permissoes),
    ]
