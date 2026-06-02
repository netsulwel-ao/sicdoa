from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('governanca', '0013_remove_assembleia_idx_assembleia_status_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentoassembleia',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('ata', 'Ata'),
                    ('relatorio', 'Relatório'),
                    ('decreto', 'Decreto'),
                    ('outro', 'Outro'),
                ],
                default='ata',
                max_length=20,
            ),
        ),
    ]