from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0039_alter_facturacliente_cliente_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='requisicaofundo',
            name='iva_honorarios',
        ),
    ]
