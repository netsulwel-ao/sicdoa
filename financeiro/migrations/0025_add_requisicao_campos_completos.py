# Generated migration for RequisicaoFundo fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0024_remove_requisicao_approval_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='requisicaofundo',
            name='numero_bl_awb',
            field=models.CharField(blank=True, max_length=100, verbose_name='Número B/L/AWB/Carta Porte'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='meio_transporte',
            field=models.CharField(blank=True, max_length=100, verbose_name='Meio de Transporte/Navio/Voo'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='origem',
            field=models.CharField(blank=True, max_length=100, verbose_name='Origem (País/Porto/Aeroporto)'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='destino',
            field=models.CharField(blank=True, max_length=100, verbose_name='Destino (País/Porto/Aeroporto)'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='mercadoria_descricao',
            field=models.TextField(blank=True, verbose_name='Descrição Sumária da Mercadoria'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='peso_bruto_kg',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Peso Bruto (Kg)'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='peso_liquido_kg',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Peso Líquido (Kg)'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='cbm_metros_cubicos',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='CBM (Metros cúbicos)'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='quantidade_volumes',
            field=models.CharField(blank=True, max_length=100, verbose_name='Quantidade e Tipo de Volumes'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='valor_cif',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Valor CIF'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='banco',
            field=models.CharField(blank=True, max_length=200, verbose_name='Nome do Banco'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='numero_conta',
            field=models.CharField(blank=True, max_length=50, verbose_name='Número de Conta'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='iban',
            field=models.CharField(blank=True, max_length=50, verbose_name='IBAN'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='instrucoes_envio',
            field=models.TextField(blank=True, verbose_name='Instruções de Envio'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='assinatura_digital',
            field=models.TextField(blank=True, verbose_name='Assinatura Digital (Base64)'),
        ),
        migrations.AddField(
            model_name='requisicaofundo',
            name='codigo_qr',
            field=models.ImageField(blank=True, null=True, upload_to='requisicoes_fundos/qr/%Y/%m/%d/', verbose_name='Código QR'),
        ),
    ]
