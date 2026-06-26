from django.db import migrations


PERM_CODS = [
    'gerir_filial',
    'gerir_colaboradores_banca',
    'gerir_presencas_banca',
    'criar_declaracao_unica',
    'gerir_clientes_filial',
    'gerir_financeiro_filial',
    'gerir_recrutamento_banca',
    'gerir_avaliacoes_banca',
    'ver_pauta_aduaneira',
]


def update_gestor_filial_permissoes(apps, schema_editor):
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')
    permissoes = list(Permissao.objects.filter(codigo__in=PERM_CODS))
    for cargo in CargoBanca.objects.filter(nome='Gestor de Filial'):
        cargo.permissoes.set(permissoes)


def reverse_gestor_filial_permissoes(apps, schema_editor):
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')
    gerir_filial = Permissao.objects.filter(codigo='gerir_filial').first()
    for cargo in CargoBanca.objects.filter(nome='Gestor de Filial'):
        if gerir_filial:
            cargo.permissoes.set([gerir_filial])
        else:
            cargo.permissoes.clear()


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0023_alter_processamentosalarial_unique_together_and_more'),
    ]

    operations = [
        migrations.RunPython(update_gestor_filial_permissoes, reverse_gestor_filial_permissoes),
    ]
