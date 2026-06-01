from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aduaneiro", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="declaracaounica",
            index=models.Index(fields=["status"], name="idx_du_status"),
        ),
        migrations.AddIndex(
            model_name="declaracaounica",
            index=models.Index(fields=["created_at"], name="idx_du_created_at"),
        ),
        migrations.AddIndex(
            model_name="declaracaounica",
            index=models.Index(fields=["usuario_id", "status"], name="idx_du_usuario_status"),
        ),
        migrations.AddIndex(
            model_name="declaracaounica",
            index=models.Index(fields=["usuario_id", "created_at"], name="idx_du_usuario_created"),
        ),
    ]
