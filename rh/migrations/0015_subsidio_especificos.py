from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0014_add_cargo_mesa'),
    ]

    operations = [
        migrations.AddField(
            model_name='subsidio',
            name='apenas_especificos',
            field=models.BooleanField(
                default=False,
                verbose_name='Apenas para colaboradores específicos',
                help_text='Se marcado, este subsídio só é aplicado aos colaboradores selecionados.'
            ),
        ),
        migrations.AddField(
            model_name='subsidio',
            name='colaboradores_especificos',
            field=models.ManyToManyField(
                blank=True,
                related_name='subsidios_especificos',
                to='rh.colaborador',
                verbose_name='Colaboradores com este subsídio',
            ),
        ),
    ]
