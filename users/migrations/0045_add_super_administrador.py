from django.db import migrations


def validate_super_admin_count(apps, schema_editor):
    """Garante que existe no máximo 1 Super Administrador no sistema."""
    Usuario = apps.get_model('users', 'Usuario')
    count = Usuario.objects.filter(papel='Super Administrador').count()
    if count > 1:
        raise migrations.exceptions.ValidationError(
            f'Existem {count} Super Administradores. Apenas 1 é permitido.'
        )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0044_delete_aprovar_requisicao"),
    ]

    operations = [
        migrations.RunPython(validate_super_admin_count, migrations.RunPython.noop),
    ]
