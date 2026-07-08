# Generated migration to fix IVA and Retenção calculation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0029_add_outras_despesas_tipo_custo'),
    ]

    operations = [
        # This migration only updates the calculation logic in models.py
        # No database schema changes needed - the fields already exist
        # The _recalcular_totais() method has been updated to:
        # 1. Calculate IVA = 14% ONLY on "Honorários do Despachante"
        # 2. Calculate Retenção = 6.5% ONLY on "Honorários do Despachante"
        # 3. Calculate Total = Subtotal + IVA - Retenção
        migrations.RunPython(
            code=lambda apps, schema_editor: None,
            reverse_code=lambda apps, schema_editor: None,
        ),
    ]
