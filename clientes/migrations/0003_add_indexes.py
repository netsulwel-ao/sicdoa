from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0002_add_usuario_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cliente',
            name='usuario_id',
            field=models.IntegerField(blank=True, db_index=True, null=True, verbose_name='ID do Despachante'),
        ),
        migrations.AlterField(
            model_name='cliente',
            name='ativo',
            field=models.BooleanField(db_index=True, default=True, verbose_name='Ativo'),
        ),
    ]