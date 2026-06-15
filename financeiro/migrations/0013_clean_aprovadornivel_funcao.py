from django.db import migrations, models
import django.db.models.deletion


def alter_table(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        table = "financeiro_aprovador_nivel"
        # Drop FK on usuario_id
        try:
            cursor.execute(
                f"ALTER TABLE `{table}` DROP FOREIGN KEY "
                f"`financeiro_aprovador_nivel_usuario_id_04b51c39_fk_auth_user_id`"
            )
        except Exception:
            pass
        # Drop indexes on usuario_id
        try:
            cursor.execute(f"DROP INDEX `financeiro_aprovador_nivel_usuario_id_04b51c39_fk_auth_user_id` ON `{table}`")
        except Exception:
            pass
        try:
            cursor.execute(f"DROP INDEX `financeiro_aprovador_nivel_usuario_id_04b51c39` ON `{table}`")
        except Exception:
            pass
        # Drop usuario_id column
        try:
            cursor.execute(f"ALTER TABLE `{table}` DROP COLUMN `usuario_id`")
        except Exception:
            pass
        # Add funcao_id column
        try:
            cursor.execute(
                f"ALTER TABLE `{table}` ADD COLUMN `funcao_id` int NULL AFTER `nivel_id`"
            )
        except Exception:
            pass
        # Add FK on funcao_id
        try:
            cursor.execute(
                f"ALTER TABLE `{table}` ADD CONSTRAINT "
                f"`financeiro_aprovador_nivel_funcao_id_funcoes_id` "
                f"FOREIGN KEY (`funcao_id`) REFERENCES `funcoes`(`id`) ON DELETE CASCADE"
            )
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0012_requisicaofundo_nivel_atual_fluxoaprovacao_and_more"),
    ]

    operations = [
        migrations.RunPython(alter_table, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterUniqueTogether(
                    name="aprovadornivel",
                    unique_together=set(),
                ),
            ],
            database_operations=[],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="aprovadornivel",
                    name="funcao",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="niveis_aprovacao",
                        to="users.funcao",
                        verbose_name="Função",
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="aprovadornivel",
                    name="usuario",
                ),
            ],
            database_operations=[],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterUniqueTogether(
                    name="aprovadornivel",
                    unique_together={("nivel", "funcao")},
                ),
            ],
            database_operations=[],
        ),
    ]
