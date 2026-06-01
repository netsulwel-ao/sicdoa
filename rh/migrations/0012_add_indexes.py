from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rh", "0011_banca_rh_empresas_usuario_8a2f5d_idx_and_more"),
    ]

    operations = [
        # ── Banca ───────────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="banca",
            index=models.Index(fields=["criado_em"], name="idx_banca_criado_em"),
        ),
        migrations.AddIndex(
            model_name="banca",
            index=models.Index(fields=["usuario_id", "ativa"], name="idx_banca_usuario_ativa"),
        ),
        # ── Subsidio ────────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="subsidio",
            index=models.Index(fields=["ativo"], name="idx_subsidio_ativo"),
        ),
        migrations.AddIndex(
            model_name="subsidio",
            index=models.Index(fields=["banca", "ativo"], name="idx_subsidio_banca_ativo"),
        ),
        # ── DocumentoColaborador ────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="documentocolaborador",
            index=models.Index(fields=["criado_em"], name="idx_doccolab_criado_em"),
        ),
        migrations.AddIndex(
            model_name="documentocolaborador",
            index=models.Index(fields=["colaborador", "criado_em"], name="idx_doccolab_colab_criado"),
        ),
        migrations.AddIndex(
            model_name="documentocolaborador",
            index=models.Index(fields=["tipo"], name="idx_doccolab_tipo"),
        ),
        # ── Colaborador ─────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="colaborador",
            index=models.Index(fields=["nome"], name="idx_colab_nome"),
        ),
        migrations.AddIndex(
            model_name="colaborador",
            index=models.Index(fields=["cargo"], name="idx_colab_cargo"),
        ),
        migrations.AddIndex(
            model_name="colaborador",
            index=models.Index(fields=["departamento"], name="idx_colab_departamento"),
        ),
        migrations.AddIndex(
            model_name="colaborador",
            index=models.Index(fields=["banca", "estado"], name="idx_colab_banca_estado"),
        ),
        migrations.AddIndex(
            model_name="colaborador",
            index=models.Index(fields=["filial", "estado"], name="idx_colab_filial_estado"),
        ),
        # ── ProcessamentoSalarial ───────────────────────────────────────────────
        migrations.AddIndex(
            model_name="processamentosalarial",
            index=models.Index(fields=["estado"], name="idx_procsal_estado"),
        ),
        migrations.AddIndex(
            model_name="processamentosalarial",
            index=models.Index(fields=["banca", "estado"], name="idx_procsal_banca_estado"),
        ),
        # ── Entrevista ──────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="entrevista",
            index=models.Index(fields=["data_hora"], name="idx_entrevista_data_hora"),
        ),
        migrations.AddIndex(
            model_name="entrevista",
            index=models.Index(fields=["resultado"], name="idx_entrevista_resultado"),
        ),
        migrations.AddIndex(
            model_name="entrevista",
            index=models.Index(fields=["candidatura", "resultado"], name="idx_entrevista_cand_result"),
        ),
        # ── PlanoIntegracao ─────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="planointegracao",
            index=models.Index(fields=["estado"], name="idx_planoest_estado"),
        ),
        migrations.AddIndex(
            model_name="planointegracao",
            index=models.Index(fields=["colaborador", "estado"], name="idx_planoest_colab_estado"),
        ),
        # ── TarefaIntegracao ────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="tarefaintegracao",
            index=models.Index(fields=["concluida"], name="idx_tarefaint_concluida"),
        ),
        migrations.AddIndex(
            model_name="tarefaintegracao",
            index=models.Index(fields=["plano", "concluida"], name="idx_tarefaint_plano_concl"),
        ),
        migrations.AddIndex(
            model_name="tarefaintegracao",
            index=models.Index(fields=["prazo"], name="idx_tarefaint_prazo"),
        ),
        # ── Fatura ──────────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="fatura",
            index=models.Index(fields=["estado"], name="idx_fatura_estado"),
        ),
        migrations.AddIndex(
            model_name="fatura",
            index=models.Index(fields=["tipo"], name="idx_fatura_tipo"),
        ),
        migrations.AddIndex(
            model_name="fatura",
            index=models.Index(fields=["data_emissao"], name="idx_fatura_data_emissao"),
        ),
        migrations.AddIndex(
            model_name="fatura",
            index=models.Index(fields=["data_vencimento"], name="idx_fatura_data_venc"),
        ),
        migrations.AddIndex(
            model_name="fatura",
            index=models.Index(fields=["criado_por"], name="idx_fatura_criado_por"),
        ),
        migrations.AddIndex(
            model_name="fatura",
            index=models.Index(fields=["banca", "estado"], name="idx_fatura_banca_estado"),
        ),
        migrations.AddIndex(
            model_name="fatura",
            index=models.Index(fields=["banca", "tipo"], name="idx_fatura_banca_tipo"),
        ),
        # ── RegistoPresenca ─────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="registopresenca",
            index=models.Index(fields=["estado"], name="idx_regpres_estado"),
        ),
        migrations.AddIndex(
            model_name="registopresenca",
            index=models.Index(fields=["tipo"], name="idx_regpres_tipo"),
        ),
        migrations.AddIndex(
            model_name="registopresenca",
            index=models.Index(fields=["colaborador", "estado"], name="idx_regpres_colab_estado"),
        ),
        # ── PedidoFerias ────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="pedidoferias",
            index=models.Index(fields=["estado"], name="idx_pedferias_estado"),
        ),
        migrations.AddIndex(
            model_name="pedidoferias",
            index=models.Index(fields=["criado_em"], name="idx_pedferias_criado_em"),
        ),
        migrations.AddIndex(
            model_name="pedidoferias",
            index=models.Index(fields=["colaborador", "estado"], name="idx_pedferias_colab_estado"),
        ),
        # ── CicloAvaliacao ──────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="cicloavaliacao",
            index=models.Index(fields=["estado"], name="idx_cicloaval_estado"),
        ),
        migrations.AddIndex(
            model_name="cicloavaliacao",
            index=models.Index(fields=["periodo_inicio"], name="idx_cicloaval_periodo_inicio"),
        ),
        migrations.AddIndex(
            model_name="cicloavaliacao",
            index=models.Index(fields=["banca", "estado"], name="idx_cicloaval_banca_estado"),
        ),
        # ── Vaga ────────────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="vaga",
            index=models.Index(fields=["departamento"], name="idx_vaga_departamento"),
        ),
        migrations.AddIndex(
            model_name="vaga",
            index=models.Index(fields=["filial", "estado"], name="idx_vaga_filial_estado"),
        ),
    ]
