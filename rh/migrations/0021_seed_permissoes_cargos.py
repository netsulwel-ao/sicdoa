from django.db import migrations


PERMISSOES = [
    ('gerir_aduaneiro', 'Gerir Módulo Aduaneiro', 'Aduaneiro', 'fas fa-ship'),
    ('criar_declaracao_unica', 'Criar Declaração Única', 'Aduaneiro', 'fas fa-file-alt'),
    ('ver_pauta_aduaneira', 'Ver Pauta Aduaneira', 'Aduaneiro', 'fas fa-book'),
    ('gerir_rh', 'Gerir Recursos Humanos (Toda a Banca)', 'RH', 'fas fa-users'),
    ('gerir_rh_filial', 'Gerir Recursos Humanos (Apenas Filial)', 'RH', 'fas fa-users'),
    ('gerir_governanca', 'Gerir CDOA Governança (Toda a Banca)', 'Governança', 'fas fa-landmark'),
    ('gerir_governanca_filial', 'Gerir CDOA Governança (Apenas Filial)', 'Governança', 'fas fa-landmark'),
    ('gerir_clientes', 'Gerir Clientes (Toda a Banca)', 'Clientes', 'fas fa-handshake'),
    ('gerir_clientes_filial', 'Gerir Clientes (Apenas Filial)', 'Clientes', 'fas fa-handshake'),
    ('gerir_financeiro', 'Gerir Financeiro (Toda a Banca)', 'Financeiro', 'fas fa-coins'),
    ('gerir_financeiro_filial', 'Gerir Financeiro (Apenas Filial)', 'Financeiro', 'fas fa-coins'),
    ('gerir_filial', 'Responsável de Filial', 'Filial', 'fas fa-star'),
    ('ver_logs_banca', 'Ver Logs de Atividade da Banca', 'Administração', 'fas fa-history'),
]


def seed_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    for codigo, nome, grupo, icone in PERMISSOES:
        Permissao.objects.get_or_create(
            codigo=codigo,
            defaults={'nome': nome, 'grupo': grupo, 'icone': icone},
        )


def reverse_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo__in=[p[0] for p in PERMISSOES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0020_cargobanca_colaborador_cargo_banca'),
    ]

    operations = [
        migrations.RunPython(seed_permissoes, reverse_permissoes),
    ]
