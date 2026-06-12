from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0007_facturarecibo_factura"),
    ]

    operations = [
        migrations.AddField(
            model_name="requisicaofundo",
            name="motivo_rejeicao",
            field=models.TextField(blank=True, default="", verbose_name="Motivo da Rejeição"),
        ),
        migrations.AddField(
            model_name="recibocliente",
            name="estado",
            field=models.CharField(
                blank=True,
                choices=[("Pendente", "Pendente"), ("Cancelado", "Cancelado")],
                default=None,
                max_length=20,
                null=True,
                verbose_name="Estado",
            ),
        ),
    ]
