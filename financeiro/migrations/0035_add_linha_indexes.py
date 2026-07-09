from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0034_recalcular_totais_requisicoes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='requisicaofundolinha',
            name='documentada',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Documentada'),
        ),
        migrations.AlterField(
            model_name='requisicaofundolinha',
            name='ordem',
            field=models.PositiveSmallIntegerField(db_index=True, default=0, verbose_name='Ordem'),
        ),
    ]
