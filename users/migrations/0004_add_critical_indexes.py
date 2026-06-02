from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_remove_usuario_idx_usuario_papel_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usuario',
            name='papel',
            field=models.CharField(
                choices=[
                    ('Administrador', 'Administrador'),
                    ('Despachante Oficial', 'Despachante Oficial'),
                    ('Operador', 'Operador'),
                    ('Visualizador', 'Visualizador'),
                ],
                db_index=True,
                default='Despachante Oficial',
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='usuario',
            name='status',
            field=models.CharField(
                choices=[
                    ('Ativo', 'Ativo'),
                    ('Inativo', 'Inativo'),
                    ('Suspenso', 'Suspenso'),
                ],
                db_index=True,
                default='Ativo',
                max_length=10,
            ),
        ),
    ]