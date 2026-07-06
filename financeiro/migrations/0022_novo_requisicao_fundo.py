# Generated migration for new RequisicaoFundo model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0021_remove_categoriaativo_banca_and_more'),
        ('clientes', '0010_alter_cliente_criado_em_alter_cliente_telefone'),
        ('aduaneiro', '0015_add_nome_banco_termo_pagamento'),
        ('rh', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RequisicaoFundo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_requisicao', models.CharField(blank=True, db_index=True, max_length=50, unique=True, verbose_name='Número da Requisição')),
                ('data_emissao', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Data de Emissão')),
                ('data_validade', models.DateField(db_index=True, verbose_name='Data de Validade')),
                ('moeda_referencia', models.CharField(default='AOA', max_length=3, verbose_name='Moeda')),
                ('cambio_referencia', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Câmbio de Referência')),
                ('pessoa_contacto', models.CharField(blank=True, max_length=200, verbose_name='Pessoa de Contacto')),
                ('estado', models.CharField(choices=[('Pendente', 'Pendente'), ('Paga Parcialmente', 'Paga Parcialmente'), ('Paga', 'Paga'), ('Anulada', 'Anulada')], db_index=True, default='Pendente', max_length=20, verbose_name='Estado')),
                ('subtotal_geral', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Subtotal Geral')),
                ('iva_honorarios', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='IVA (Honorários)')),
                ('retencao', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Retenção')),
                ('total_geral', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Total Geral a Pagar')),
                ('valor_pago', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Valor Pago')),
                ('criado_por_id', models.IntegerField(blank=True, db_index=True, null=True, verbose_name='ID do Criador')),
                ('criado_por_nome', models.CharField(blank=True, default='', max_length=200, verbose_name='Nome do Criador')),
                ('observacoes', models.TextField(blank=True, default='', verbose_name='Observações')),
                ('banca', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='requisicoes_fundos', to='rh.banca', verbose_name='Banca')),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='requisicoes_fundos', to='clientes.cliente', verbose_name='Cliente')),
                ('filial', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requisicoes_fundos', to='rh.filialbanca', verbose_name='Filial')),
                ('processo_aduaneiro', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='requisicoes_fundos', to='aduaneiro.declaracaounica', verbose_name='Processo Aduaneiro')),
            ],
            options={
                'verbose_name': 'Requisição de Fundos',
                'verbose_name_plural': 'Requisições de Fundos',
                'db_table': 'financeiro_requisicao_fundo',
                'ordering': ['-data_emissao'],
            },
        ),
        migrations.CreateModel(
            name='RequisicaoFundoLinha',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_custo', models.CharField(choices=[('Impostos e Taxas Aduaneiras (AGT)', 'Impostos e Taxas Aduaneiras (AGT)'), ('Despesas Portuárias e Terminais', 'Despesas Portuárias e Terminais'), ('Logística e Transporte', 'Logística e Transporte'), ('Honorários do Despachante', 'Honorários do Despachante')], db_index=True, max_length=50, verbose_name='Tipo de Custo')),
                ('descricao', models.CharField(max_length=255, verbose_name='Descrição')),
                ('documentada', models.BooleanField(default=False, verbose_name='Documentada')),
                ('despesa_tipo', models.CharField(blank=True, max_length=50, null=True, verbose_name='Tipo de Despesa')),
                ('valor', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Valor')),
                ('documento_justificativo', models.FileField(blank=True, null=True, upload_to='requisicoes_fundos/%Y/%m/%d/', verbose_name='Documento Justificativo')),
                ('ordem', models.PositiveSmallIntegerField(default=0, verbose_name='Ordem')),
                ('requisicao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='linhas', to='financeiro.requisicaofundo', verbose_name='Requisição')),
            ],
            options={
                'verbose_name': 'Linha de Requisição',
                'verbose_name_plural': 'Linhas de Requisição',
                'db_table': 'financeiro_requisicao_fundo_linha',
                'ordering': ['ordem'],
            },
        ),
        migrations.AddIndex(
            model_name='requisicaofundo',
            index=models.Index(fields=['estado', '-data_emissao'], name='ix_rf_estado_data'),
        ),
        migrations.AddIndex(
            model_name='requisicaofundo',
            index=models.Index(fields=['cliente', 'estado'], name='ix_rf_cliente_estado'),
        ),
    ]
