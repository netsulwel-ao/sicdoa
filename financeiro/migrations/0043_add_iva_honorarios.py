from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0042_merge_20260727_1855'),
    ]

    operations = [
        migrations.AddField(
            model_name='requisicaofundo',
            name='iva_honorarios',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='IVA (Honorários)'),
        ),
    ]
