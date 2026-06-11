from django.db import migrations

PERMISSOES = [
    ('gerir_utilizadores', 'Gerir Utilizadores', 'Criar, editar e gerir todos os utilizadores do sistema', 'Administração', 'fa-user-shield'),
    ('gerir_colaboradores_inst', 'Gerir Colaboradores Institucionais', 'Gerir colaboradores da equipa administrativa', 'RH Institucional', 'fa-id-badge'),
    ('gerir_presencas_inst', 'Gerir Presenças Institucionais', 'Registar e aprovar presenças dos colaboradores institucionais', 'RH Institucional', 'fa-calendar-check'),
    ('gerir_ferias_inst', 'Gerir Férias Institucionais', 'Aprovar ou rejeitar pedidos de férias dos colaboradores institucionais', 'RH Institucional', 'fa-umbrella-beach'),
    ('gerir_avaliacoes_inst', 'Gerir Avaliações Institucionais', 'Criar ciclos e avaliar colaboradores institucionais', 'RH Institucional', 'fa-trophy'),
    ('processar_salarios_inst', 'Processar Salários Institucionais', 'Processar salários e gerar recibos dos colaboradores institucionais', 'RH Institucional', 'fa-credit-card'),
]


def seed_permissoes(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for codigo, nome, descricao, grupo, icone in PERMISSOES:
            cursor.execute(
                "SELECT COUNT(*) FROM permissoes WHERE codigo = %s", [codigo]
            )
            exists = cursor.fetchone()[0] > 0
            if not exists:
                cursor.execute(
                    "INSERT INTO permissoes (codigo, nome, descricao, grupo, icone, created_at) VALUES (%s, %s, %s, %s, %s, NOW())",
                    [codigo, nome, descricao, grupo, icone],
                )


def reverse_permissoes(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for codigo, *_ in PERMISSOES:
            cursor.execute("DELETE FROM permissoes WHERE codigo = %s", [codigo])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0015_add_colaborador_institucional_e_permissoes_diretas"),
    ]

    operations = [
        migrations.RunPython(seed_permissoes, reverse_permissoes),
    ]
