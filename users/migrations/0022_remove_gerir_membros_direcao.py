from django.db import migrations


def remove_permission(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.filter(codigo='gerir_membros_direcao').delete()


def restore_permission(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    Permissao.objects.get_or_create(
        codigo='gerir_membros_direcao',
        defaults={
            'nome': 'Gerir Membros da Direção',
            'descricao': 'Atribuir e remover cargos da direção',
            'grupo': 'Administração',
            'icone': 'fa-users-cog',
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0021_remove_usuario_cargos_remove_usuariocargo_cargo_and_more'),
    ]
    operations = [
        migrations.RunPython(remove_permission, restore_permission),
    ]
