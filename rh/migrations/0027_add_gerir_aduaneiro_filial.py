from django.db import migrations


PERM_CODS_ADUANEIRO_FILIAL = [
    'gerir_aduaneiro_filial',
]

def seed_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.get_or_create(
        codigo='gerir_aduaneiro_filial',
        defaults={
            'nome': 'Gerir Módulo Aduaneiro (Apenas Filial)',
            'grupo': 'Aduaneiro',
            'icone': 'fas fa-ship',
        },
    )


def add_to_gestor_cargo(apps, schema_editor):
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')
    try:
        perm = Permissao.objects.get(codigo='gerir_aduaneiro_filial')
    except Permissao.DoesNotExist:
        return
    for cargo in CargoBanca.objects.filter(nome='Gestor de Filial', locked=True):
        cargo.permissoes.add(perm)


def reverse_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo__in=PERM_CODS_ADUANEIRO_FILIAL).delete()


def reverse_gestor(apps, schema_editor):
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')
    perm = Permissao.objects.filter(codigo__in=PERM_CODS_ADUANEIRO_FILIAL).first()
    if perm:
        for cargo in CargoBanca.objects.filter(nome='Gestor de Filial', locked=True):
            cargo.permissoes.remove(perm)


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0026_fix_gestor_cargo_banca'),
    ]

    operations = [
        migrations.RunPython(seed_permissoes, reverse_permissoes),
        migrations.RunPython(add_to_gestor_cargo, reverse_gestor),
    ]
