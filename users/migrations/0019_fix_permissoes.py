"""Corrige permissões:
- Renomeia gerir_assembleias -> gerir_assembleia (plural -> singular)
- Remove 13 permissões fictícias que nunca são verificadas
- Adiciona 4 permissões que faltavam (verificadas em views/templates mas nunca seedadas)
"""
from django.db import migrations

PERM_FICTICIAS = [
    'gerir_assembleias',
    'gerir_cargos',
    'gerir_membros',
    'ver_gestao_financeira',
    'ver_dashboard',
    'ver_relatorios',
    'gerir_cargos_direcao',
    'designar_mesa',
    'aprovar_documentos_fin',
    'emitir_documentos_fin',
    'gerir_recebimentos',
    'consultar_relatorios_fin',
    'acesso_auditoria',
]

PERM_FALTA = [
    ('gerir_votacoes', 'Gerir Votações', 'Gerir votações em assembleias', 'Democracia Digital', 'fa-vote-yea'),
    ('gerir_membros_direcao', 'Gerir Membros da Direção', 'Atribuir e remover cargos da direção', 'Administração', 'fa-users-cog'),
    ('ver_quotas', 'Ver Quotas', 'Consultar quotas e situação financeira dos membros', 'Financeiro', 'fa-eye'),
    ('gerir_documentos', 'Gerir Documentos', 'Upload, publicação e remoção de documentos da secretaria', 'Secretaria', 'fa-file-upload'),
]


def fix_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')

    # 1. Renomear gerir_assembleias -> gerir_assembleia
    Permissao.objects.filter(codigo='gerir_assembleias').update(
        codigo='gerir_assembleia', nome='Gerir Assembleia'
    )

    # 2. Remover permissões fictícias
    Permissao.objects.filter(codigo__in=PERM_FICTICIAS).delete()

    # 3. Adicionar permissões em falta
    for codigo, nome, descricao, grupo, icone in PERM_FALTA:
        Permissao.objects.get_or_create(
            codigo=codigo,
            defaults={'nome': nome, 'descricao': descricao, 'grupo': grupo, 'icone': icone},
        )


def reverse_fix(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0018_alter_colaboradorinstitucional_area_actuacao"),
    ]
    operations = [
        migrations.RunPython(fix_permissoes, reverse_fix),
    ]
