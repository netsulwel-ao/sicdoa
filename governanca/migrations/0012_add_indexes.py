from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("governanca", "0011_remove_quotaconfig_juros_atraso_and_more"),
    ]

    operations = [
        # ── Assembleia ──────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="assembleia",
            index=models.Index(fields=["status"], name="idx_assembleia_status"),
        ),
        migrations.AddIndex(
            model_name="assembleia",
            index=models.Index(fields=["data_hora"], name="idx_assembleia_data_hora"),
        ),
        migrations.AddIndex(
            model_name="assembleia",
            index=models.Index(fields=["status", "data_hora"], name="idx_assembleia_status_data"),
        ),
        # ── PautaVotacao ────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="pautavotacao",
            index=models.Index(fields=["status"], name="idx_pauta_status"),
        ),
        migrations.AddIndex(
            model_name="pautavotacao",
            index=models.Index(fields=["ordem"], name="idx_pauta_ordem"),
        ),
        migrations.AddIndex(
            model_name="pautavotacao",
            index=models.Index(fields=["assembleia", "status"], name="idx_pauta_assem_status"),
        ),
        migrations.AddIndex(
            model_name="pautavotacao",
            index=models.Index(fields=["assembleia", "ordem"], name="idx_pauta_assem_ordem"),
        ),
        # ── PresencaAssembleia ──────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="presencaassembleia",
            index=models.Index(fields=["presente_em"], name="idx_presenca_presente_em"),
        ),
        migrations.AddIndex(
            model_name="presencaassembleia",
            index=models.Index(fields=["assembleia", "presente_em"], name="idx_presenca_assem_presente"),
        ),
        # ── Procuracao ──────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="procuracao",
            index=models.Index(fields=["status"], name="idx_procuracao_status"),
        ),
        migrations.AddIndex(
            model_name="procuracao",
            index=models.Index(fields=["assembleia", "outorgado"], name="idx_proc_assem_outorgado"),
        ),
        migrations.AddIndex(
            model_name="procuracao",
            index=models.Index(fields=["outorgante", "status"], name="idx_proc_outorgante_status"),
        ),
        migrations.AddIndex(
            model_name="procuracao",
            index=models.Index(fields=["outorgado", "status"], name="idx_proc_outorgado_status"),
        ),
        # ── Voto ────────────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="voto",
            index=models.Index(fields=["opcao"], name="idx_voto_opcao"),
        ),
        migrations.AddIndex(
            model_name="voto",
            index=models.Index(fields=["pauta", "opcao"], name="idx_voto_pauta_opcao"),
        ),
        migrations.AddIndex(
            model_name="voto",
            index=models.Index(fields=["votado_em"], name="idx_voto_votado_em"),
        ),
        # ── ReciboVoto ──────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="recibovoto",
            index=models.Index(fields=["verificado"], name="idx_recibo_verificado"),
        ),
        # ── AtaDigital ──────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="atadigital",
            index=models.Index(fields=["status_assinatura"], name="idx_ata_status_assinatura"),
        ),
        migrations.AddIndex(
            model_name="atadigital",
            index=models.Index(fields=["created_at"], name="idx_ata_created_at"),
        ),
        migrations.AddIndex(
            model_name="atadigital",
            index=models.Index(fields=["publicado_em"], name="idx_ata_publicado_em"),
        ),
        migrations.AddIndex(
            model_name="atadigital",
            index=models.Index(fields=["assembleia", "status_assinatura"], name="idx_ata_assem_status"),
        ),
        # ── Notificacao ─────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="notificacao",
            index=models.Index(fields=["lida"], name="idx_notif_lida"),
        ),
        migrations.AddIndex(
            model_name="notificacao",
            index=models.Index(fields=["tipo"], name="idx_notif_tipo"),
        ),
        migrations.AddIndex(
            model_name="notificacao",
            index=models.Index(fields=["created_at"], name="idx_notif_created_at"),
        ),
        migrations.AddIndex(
            model_name="notificacao",
            index=models.Index(fields=["usuario", "lida"], name="idx_notif_usuario_lida"),
        ),
        migrations.AddIndex(
            model_name="notificacao",
            index=models.Index(fields=["usuario", "created_at"], name="idx_notif_usuario_created"),
        ),
        # ── DocumentoAssembleia ─────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="documentoassembleia",
            index=models.Index(fields=["tipo"], name="idx_doc_tipo"),
        ),
        migrations.AddIndex(
            model_name="documentoassembleia",
            index=models.Index(fields=["publicado"], name="idx_doc_publicado"),
        ),
        migrations.AddIndex(
            model_name="documentoassembleia",
            index=models.Index(fields=["created_at"], name="idx_doc_created_at"),
        ),
        migrations.AddIndex(
            model_name="documentoassembleia",
            index=models.Index(fields=["assembleia", "tipo"], name="idx_doc_assem_tipo"),
        ),
        migrations.AddIndex(
            model_name="documentoassembleia",
            index=models.Index(fields=["assembleia", "publicado"], name="idx_doc_assem_publicado"),
        ),
        # ── MembroMesa ──────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="membromesa",
            index=models.Index(fields=["funcao"], name="idx_mesa_funcao"),
        ),
        migrations.AddIndex(
            model_name="membromesa",
            index=models.Index(fields=["ordem"], name="idx_mesa_ordem"),
        ),
        migrations.AddIndex(
            model_name="membromesa",
            index=models.Index(fields=["assembleia", "funcao"], name="idx_mesa_assem_funcao"),
        ),
        # ── MensagemChat ────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="mensagemchat",
            index=models.Index(fields=["created_at"], name="idx_chat_created_at"),
        ),
        migrations.AddIndex(
            model_name="mensagemchat",
            index=models.Index(fields=["assembleia", "created_at"], name="idx_chat_assem_created"),
        ),
        # ── ConsultaPublica ─────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="consultapublica",
            index=models.Index(fields=["status"], name="idx_consulta_status"),
        ),
        migrations.AddIndex(
            model_name="consultapublica",
            index=models.Index(fields=["created_at"], name="idx_consulta_created_at"),
        ),
        migrations.AddIndex(
            model_name="consultapublica",
            index=models.Index(fields=["status", "created_at"], name="idx_consulta_status_created"),
        ),
        # ── VotacaoConsulta ─────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="votacaoconsulta",
            index=models.Index(fields=["ativa"], name="idx_votcons_ativa"),
        ),
        migrations.AddIndex(
            model_name="votacaoconsulta",
            index=models.Index(fields=["data_inicio"], name="idx_votcons_data_inicio"),
        ),
        migrations.AddIndex(
            model_name="votacaoconsulta",
            index=models.Index(fields=["consulta", "ativa"], name="idx_votcons_consulta_ativa"),
        ),
        # ── VotoConsulta ────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="votoconsulta",
            index=models.Index(fields=["votacao", "voto"], name="idx_votcons_votacao_voto"),
        ),
        # ── QuotaConfig ─────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="quotaconfig",
            index=models.Index(fields=["ativa"], name="idx_qconfig_ativa"),
        ),
        # ── QuotaGerada ─────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="quotagerada",
            index=models.Index(fields=["status"], name="idx_qgerada_status"),
        ),
        migrations.AddIndex(
            model_name="quotagerada",
            index=models.Index(fields=["data_vencimento"], name="idx_qgerada_data_venc"),
        ),
        migrations.AddIndex(
            model_name="quotagerada",
            index=models.Index(fields=["despachante", "status"], name="idx_qgerada_desp_status"),
        ),
        migrations.AddIndex(
            model_name="quotagerada",
            index=models.Index(fields=["status", "data_vencimento"], name="idx_qgerada_status_venc"),
        ),
        # ── PagamentoQuota ──────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="pagamentoquota",
            index=models.Index(fields=["status"], name="idx_pagto_status"),
        ),
        migrations.AddIndex(
            model_name="pagamentoquota",
            index=models.Index(fields=["metodo"], name="idx_pagto_metodo"),
        ),
        migrations.AddIndex(
            model_name="pagamentoquota",
            index=models.Index(fields=["data_pagamento"], name="idx_pagto_data_pagto"),
        ),
        migrations.AddIndex(
            model_name="pagamentoquota",
            index=models.Index(fields=["quota", "status"], name="idx_pagto_quota_status"),
        ),
        migrations.AddIndex(
            model_name="pagamentoquota",
            index=models.Index(fields=["despachante", "status"], name="idx_pagto_desp_status"),
        ),
        # ── EstadoFinanceiro ────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="estadofinanceiro",
            index=models.Index(fields=["estado"], name="idx_estfin_estado"),
        ),
        # ── CertidaoRegularidade ────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="certidaoregularidade",
            index=models.Index(fields=["data_emissao"], name="idx_certidao_data_emissao"),
        ),
        migrations.AddIndex(
            model_name="certidaoregularidade",
            index=models.Index(fields=["despachante", "data_emissao"], name="idx_certidao_desp_emissao"),
        ),
        # ── CarteiraProfissional ────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="carteiraprofissional",
            index=models.Index(fields=["status"], name="idx_carteira_status"),
        ),
        migrations.AddIndex(
            model_name="carteiraprofissional",
            index=models.Index(fields=["status", "data_validade"], name="idx_carteira_status_validade"),
        ),
        # ── Convocatoria ────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="convocatoria",
            index=models.Index(fields=["status"], name="idx_convocatoria_status"),
        ),
        migrations.AddIndex(
            model_name="convocatoria",
            index=models.Index(fields=["assembleia", "status"], name="idx_convocatoria_assem_status"),
        ),
        # ── RespostaPresenca ────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="respostapresenca",
            index=models.Index(fields=["resposta"], name="idx_respres_resposta"),
        ),
        migrations.AddIndex(
            model_name="respostapresenca",
            index=models.Index(fields=["assembleia", "resposta"], name="idx_respres_assem_resposta"),
        ),
        # ── LogAssembleia ───────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="logassembleia",
            index=models.Index(fields=["acao"], name="idx_log_acao"),
        ),
        migrations.AddIndex(
            model_name="logassembleia",
            index=models.Index(fields=["assembleia", "acao"], name="idx_log_assem_acao"),
        ),
    ]
