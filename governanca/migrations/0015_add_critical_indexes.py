from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('governanca', '0014_documentoassembleia_add_decreto'),
    ]

    operations = [
        # ── Assembleia ─────────────────────────────────────────────────────
        migrations.AlterField(
            model_name='assembleia',
            name='status',
            field=models.CharField(
                choices=[
                    ('Agendada', 'Agendada'),
                    ('Em Curso', 'Em Curso'),
                    ('Concluida', 'Concluida'),
                    ('Cancelada', 'Cancelada'),
                ],
                db_index=True,
                default='Agendada',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='assembleia',
            name='data_hora',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AddIndex(
            model_name='assembleia',
            index=models.Index(fields=['status', 'data_hora'], name='idx_assem_status_data'),
        ),

        # ── PautaVotacao ───────────────────────────────────────────────────
        migrations.AlterField(
            model_name='pautavotacao',
            name='status',
            field=models.CharField(
                choices=[
                    ('Pendente', 'Pendente'),
                    ('Em Votacao', 'Em Votacao'),
                    ('Concluida', 'Concluida'),
                ],
                db_index=True,
                default='Pendente',
                max_length=20,
            ),
        ),

        # ── Notificacao ────────────────────────────────────────────────────
        migrations.AlterField(
            model_name='notificacao',
            name='lida',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AlterField(
            model_name='notificacao',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('assembleia_agendada', 'Assembleia Agendada'),
                    ('assembleia_iniciada', 'Assembleia Iniciada'),
                    ('votacao_aberta', 'Votação Aberta'),
                    ('procuracao_solicitada', 'Procuração Solicitada'),
                    ('procuracao_confirmada', 'Procuração Confirmada'),
                    ('resultado_publicado', 'Resultado Publicado'),
                    ('ata_publicada', 'Ata Publicada'),
                    ('quota_gerada', 'Quota Gerada'),
                    ('pagamento_confirmado', 'Pagamento Confirmado'),
                    ('certidao_emitida', 'Certidão Emitida'),
                    ('carteira_expirada', 'Carteira Expirada'),
                    ('estado_suspenso', 'Estado Suspenso'),
                    ('estado_regularizado', 'Estado Regularizado'),
                    ('consulta_publicada', 'Consulta Publicada'),
                    ('novo_comentario', 'Novo Comentário'),
                    ('consulta_encerrada', 'Consulta Encerrada'),
                    ('relatorio_publicado', 'Relatório Publicado'),
                    ('versao_final_publicada', 'Versão Final Publicada'),
                    ('convocatoria_publicada', 'Convocatória Publicada'),
                    ('votacao_reaberta', 'Votação Reaberta'),
                    ('ata_assinada', 'Ata Assinada'),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
        migrations.AddIndex(
            model_name='notificacao',
            index=models.Index(fields=['usuario', 'lida'], name='idx_notif_usuario_lida'),
        ),

        # ── QuotaGerada ────────────────────────────────────────────────────
        migrations.AlterField(
            model_name='quotagerada',
            name='status',
            field=models.CharField(
                choices=[
                    ('Pendente', 'Pendente'),
                    ('Paga', 'Paga'),
                    ('Atrasada', 'Atrasada'),
                    ('Cancelada', 'Cancelada'),
                ],
                db_index=True,
                default='Pendente',
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name='quotagerada',
            name='ano',
            field=models.IntegerField(db_index=True),
        ),
        migrations.AlterField(
            model_name='quotagerada',
            name='mes',
            field=models.IntegerField(db_index=True),
        ),
        migrations.AddIndex(
            model_name='quotagerada',
            index=models.Index(fields=['ano', 'mes', 'status'], name='idx_quota_ano_mes_status'),
        ),

        # ── PagamentoQuota ─────────────────────────────────────────────────
        migrations.AlterField(
            model_name='pagamentoquota',
            name='status',
            field=models.CharField(
                choices=[
                    ('Pendente Confirmacao', 'Pendente Confirmação'),
                    ('Confirmado', 'Confirmado'),
                    ('Rejeitado', 'Rejeitado'),
                ],
                db_index=True,
                default='Pendente Confirmacao',
                max_length=25,
            ),
        ),

        # ── ConsultaPublica ────────────────────────────────────────────────
        migrations.AlterField(
            model_name='consultapublica',
            name='status',
            field=models.CharField(
                choices=[
                    ('Rascunho', 'Rascunho'),
                    ('Publicada', 'Publicada'),
                    ('EmVotacao', 'Em Votação'),
                    ('Encerrada', 'Encerrada'),
                    ('Aprovada', 'Aprovada (Versão Final)'),
                    ('Rejeitada', 'Rejeitada'),
                ],
                db_index=True,
                default='Rascunho',
                max_length=20,
            ),
        ),

        # ── EstadoFinanceiro ───────────────────────────────────────────────
        migrations.AlterField(
            model_name='estadofinanceiro',
            name='estado',
            field=models.CharField(
                choices=[
                    ('Regular', 'Regular'),
                    ('Irregular', 'Irregular'),
                    ('Suspenso', 'Suspenso'),
                ],
                db_index=True,
                default='Regular',
                max_length=15,
            ),
        ),

        # ── AtaDigital ─────────────────────────────────────────────────────
        migrations.AlterField(
            model_name='atadigital',
            name='status_assinatura',
            field=models.CharField(
                choices=[
                    ('Pendente', 'Pendente'),
                    ('Aguardando Presidente', 'Aguardando Presidente'),
                    ('Aguardando Secretario', 'Aguardando Secretário'),
                    ('Assinada', 'Assinada'),
                    ('Publicada', 'Publicada'),
                ],
                db_index=True,
                default='Pendente',
                max_length=25,
            ),
        ),
    ]