from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="usuario",
            index=models.Index(fields=["papel", "status"], name="idx_usuario_papel_status"),
        ),
    ]
