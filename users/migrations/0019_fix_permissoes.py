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
    with schema_editor.connection.cursor() as cursor:
        # 1. Renomear gerir_assembleias -> gerir_assembleia
        cursor.execute(
            "UPDATE permissoes SET codigo = 'gerir_assembleia', nome = 'Gerir Assembleia' "
            "WHERE codigo = 'gerir_assembleias'"
        )

        # 2. Remover permissões fictícias
        for codigo in PERM_FICTICIAS:
            cursor.execute("DELETE FROM permissoes WHERE codigo = %s", [codigo])

        # 3. Adicionar permissões em falta
        for codigo, nome, descricao, grupo, icone in PERM_FALTA:
            cursor.execute(
                "SELECT COUNT(*) FROM permissoes WHERE codigo = %s", [codigo]
            )
            exists = cursor.fetchone()[0] > 0
            if not exists:
                cursor.execute(
                    "INSERT INTO permissoes (codigo, nome, descricao, grupo, icone, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, NOW())",
                    [codigo, nome, descricao, grupo, icone],
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
