# Generated manually to fix migration issue

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='usuario_id',
            field=models.IntegerField(blank=True, null=True, verbose_name='ID do Despachante'),
        ),
    ]
