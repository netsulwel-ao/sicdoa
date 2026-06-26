from django.db import migrations


PERM_CODS = [
    'gerir_filial',
    'criar_declaracao_unica',
    'gerir_clientes_filial',
    'gerir_financeiro_filial',
    'ver_pauta_aduaneira',
]


def fix_gestor_cargo_banca(apps, schema_editor):
    Colaborador = apps.get_model('rh', 'Colaborador')
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')

    permissoes = list(Permissao.objects.filter(codigo__in=PERM_CODS))

    for col in Colaborador.objects.filter(
        gestor_filial__isnull=False,
        estado='Ativo',
        cargo_banca__isnull=True,
    ).select_related('banca'):
        cargo, _ = CargoBanca.objects.get_or_create(
            banca=col.banca,
            nome='Gestor de Filial',
            defaults={
                'descricao': 'Cargo auto-atribuído pelo sistema para gestores de filial',
                'locked': True,
            },
        )
        cargo.permissoes.set(permissoes)
        col.cargo_banca = cargo
        col.save(update_fields=['cargo_banca'])


def reverse_fix(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0025_fix_gestor_filial_permissoes'),
    ]

    operations = [
        migrations.RunPython(fix_gestor_cargo_banca, reverse_fix),
    ]
