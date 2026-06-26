from django.db import migrations


PERM_CODS = [
    'gerir_filial',
    'criar_declaracao_unica',
    'gerir_clientes_filial',
    'gerir_financeiro_filial',
    'ver_pauta_aduaneira',
]


def fix_gestor_filial_permissoes(apps, schema_editor):
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')
    permissoes = list(Permissao.objects.filter(codigo__in=PERM_CODS))
    for cargo in CargoBanca.objects.filter(nome='Gestor de Filial'):
        cargo.permissoes.set(permissoes)


def reverse_fix(apps, schema_editor):
    """Volta às 9 permissões da migration 0024."""
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')
    old_cods = PERM_CODS + [
        'gerir_colaboradores_banca',
        'gerir_presencas_banca',
        'gerir_recrutamento_banca',
        'gerir_avaliacoes_banca',
    ]
    permissoes = list(Permissao.objects.filter(codigo__in=old_cods))
    for cargo in CargoBanca.objects.filter(nome='Gestor de Filial'):
        cargo.permissoes.set(permissoes)


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0024_gestor_filial_permissoes'),
    ]

    operations = [
        migrations.RunPython(fix_gestor_filial_permissoes, reverse_fix),
    ]
