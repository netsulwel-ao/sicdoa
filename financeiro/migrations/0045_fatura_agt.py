# Generated manually for FaturaAGT model

import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0044_alter_regime_requisicao'),
        ('rh', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FaturaAGT',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_fatura', models.CharField(blank=True, max_length=50, unique=True, verbose_name='Número da Fatura AGT')),
                ('serie', models.CharField(blank=True, max_length=20, verbose_name='Série')),
                ('nif_emitente', models.CharField(blank=True, max_length=20, verbose_name='NIF do Emitente')),
                ('nif_cliente', models.CharField(blank=True, max_length=20, verbose_name='NIF do Cliente')),
                ('nome_cliente', models.CharField(blank=True, max_length=255, verbose_name='Nome do Cliente')),
                ('descricao', models.TextField(blank=True, verbose_name='Descrição')),
                ('valor_sem_iva', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15, verbose_name='Valor sem IVA')),
                ('valor_iva', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15, verbose_name='Valor IVA')),
                ('valor_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15, verbose_name='Valor Total')),
                ('taxa_iva', models.DecimalField(decimal_places=2, default=Decimal('14.00'), max_digits=5, verbose_name='Taxa IVA (%)')),
                ('agt_id', models.CharField(blank=True, max_length=100, verbose_name='ID AGT')),
                ('agt_hash', models.CharField(blank=True, max_length=500, verbose_name='Hash AGT')),
                ('agt_qr_code', models.TextField(blank=True, verbose_name='QR Code AGT')),
                ('agt_status', models.CharField(choices=[('Pendente', 'Pendente'), ('Processando', 'Processando'), ('Validada', 'Validada'), ('Rejeitada', 'Rejeitada'), ('Erro', 'Erro')], db_index=True, default='Pendente', max_length=20, verbose_name='Status AGT')),
                ('agt_motivo_rejeicao', models.TextField(blank=True, verbose_name='Motivo de Rejeição AGT')),
                ('agt_data_validacao', models.DateTimeField(blank=True, null=True, verbose_name='Data de Validação AGT')),
                ('agt_resposta_raw', models.JSONField(blank=True, null=True, verbose_name='Resposta Raw AGT')),
                ('data_emissao', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Data de Emissão')),
                ('data_atualizacao', models.DateTimeField(auto_now=True, verbose_name='Última Atualização')),
                ('criado_por_id', models.IntegerField(blank=True, null=True, verbose_name='ID do Criador')),
                ('criado_por_nome', models.CharField(blank=True, default='', max_length=200, verbose_name='Nome do Criador')),
                ('banca', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='faturas_agt', to='rh.banca')),
                ('factura', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fatura_agt', to='financeiro.facturacliente', verbose_name='Factura')),
            ],
            options={
                'verbose_name': 'Fatura AGT',
                'verbose_name_plural': 'Faturas AGT',
                'db_table': 'financeiro_fatura_agt',
                'ordering': ['-data_emissao'],
                'indexes': [
                    models.Index(fields=['agt_status', '-data_emissao'], name='ix_fatagt_status_data'),
                    models.Index(fields=['banca', 'agt_status'], name='ix_fatagt_banca_status'),
                    models.Index(fields=['nif_cliente'], name='ix_fatagt_nif_cliente'),
                ],
            },
        ),
    ]
