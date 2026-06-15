from django.db import migrations


PERMISSOES_NOVAS = [
    # Sistema
    ('admin_banca',              'Administrador da Banca',  'Sistema'),
    # RH
    ('ver_minha_banca',          'Minha Banca',             'RH'),
    ('gerir_colaboradores_banca','Colaboradores',           'RH'),
    ('gerir_cargos_banca',       'Cargos & Permissões',     'RH'),
    ('gerir_processamento_salarial', 'Processamento Salarial', 'RH'),
    ('gerir_recrutamento_banca', 'Recrutamento',            'RH'),
    ('gerir_presencas_banca',    'Controlo de Presenças',   'RH'),
    ('gerir_avaliacoes_banca',   'Avaliação de Desempenho',  'RH'),
    # Financeiro
    ('ver_requisicoes',          'Requisições de Fundos',   'Financeiro'),
    ('ver_recibos',              'Gestão de Recibos',       'Financeiro'),
    ('ver_notas_financeiro',     'Notas',                   'Financeiro'),
    ('ver_facturas',             'Facturas',                'Financeiro'),
    ('ver_conta_corrente',       'Conta Corrente',          'Financeiro'),
    ('ver_relatorios_financeiros','Relatórios',             'Financeiro'),
]


def seed(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    for codigo, nome, grupo in PERMISSOES_NOVAS:
        Permissao.objects.get_or_create(
            codigo=codigo,
            defaults={'nome': nome, 'grupo': grupo},
        )


def unseed(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo__in=[p[0] for p in PERMISSOES_NOVAS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0034_rename_perm_banca"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
