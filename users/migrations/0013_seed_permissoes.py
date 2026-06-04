from django.db import migrations

PERMISSOES = [
    ('ver_secretaria', 'Ver Secretaria', 'Acesso ao menu Secretaria - Documentos', 'Secretaria'),
    ('gerir_documentos', 'Gerir Documentos', 'Upload, publicação e remoção de documentos da secretaria', 'Secretaria'),
    ('gerir_convocatorias', 'Gerir Convocatórias', 'Criar, editar e publicar convocatórias', 'Secretaria'),
    ('gerir_assembleias', 'Gerir Assembleias', 'Criar, editar e encerrar assembleias', 'Democracia Digital'),
    ('gerir_atas', 'Gerir Atas & Decretos', 'Assinar e publicar atas e decretos', 'Democracia Digital'),
    ('gerir_consultas', 'Gerir Consultas', 'Gerir Escuta Activa / consultas públicas', 'Democracia Digital'),
    ('gerir_quotas', 'Gerir Quotas', 'Atribuir, definir e gerir quotas anuais', 'Financeiro'),
    ('ver_gestao_financeira', 'Ver Gestão Financeira', 'Acesso ao dashboard financeiro', 'Financeiro'),
    ('gerir_cargos', 'Gerir Cargos', 'Atribuir e remover cargos da direção', 'Administração'),
    ('gerir_membros', 'Gerir Membros', 'Gerir membros da direção', 'Administração'),
    ('ver_dashboard', 'Ver Dashboard', 'Acesso ao painel principal', 'Geral'),
    ('ver_relatorios', 'Ver Relatórios', 'Aceder a relatórios e estatísticas', 'Geral'),
]


def seed_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    for codigo, nome, descricao, grupo in PERMISSOES:
        Permissao.objects.get_or_create(
            codigo=codigo,
            defaults={'nome': nome, 'descricao': descricao, 'grupo': grupo}
        )


def reverse_permissoes(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo__in=[p[0] for p in PERMISSOES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0012_permissao_cargo_permissoes"),
    ]

    operations = [
        migrations.RunPython(seed_permissoes, reverse_permissoes),
    ]
