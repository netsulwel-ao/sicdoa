from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0034_remover_campo_bai_banca'),
    ]

    operations = [
        migrations.AddField(
            model_name='banca',
            name='dados_bancarios_json',
            field=models.TextField(blank=True, default='', verbose_name='Dados Bancários (JSON)'),
        ),
    ]
