from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0044_delete_aprovar_requisicao"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usuario",
            name="foto",
            field=models.ImageField(
                blank=True,
                max_length=255,
                null=True,
                upload_to="usuarios/fotos/",
            ),
        ),
    ]
