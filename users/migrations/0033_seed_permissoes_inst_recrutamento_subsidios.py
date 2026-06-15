from django.db import migrations

PERMISSOES = [
    {
        'codigo': 'gerir_recrutamento_inst',
        'nome': 'Gerir Recrutamento Institucional',
        'descricao': 'Gerir vagas, candidaturas, entrevistas e integração institucionais',
        'grupo': 'RH Institucional',
        'icone': 'fa-briefcase',
    },
    {
        'codigo': 'gerir_subsidios_inst',
        'nome': 'Gerir Subsídios Institucionais',
        'descricao': 'Configurar subsídios salariais institucionais',
        'grupo': 'RH Institucional',
        'icone': 'fa-coins',
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
        ('users', '0032_modelos_institucionais_subsidios_recrutamento_metricas'),
    ]

    operations = [
        migrations.RunPython(add_permissoes, remove_permissoes),
    ]
