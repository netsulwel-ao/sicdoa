# Fix RequisicaoFundo schema mismatch

from django.db import migrations

def fix_schema(apps, schema_editor):
    # Drop existing line table and requisicao table, then recreate them
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS financeiro_requisicao_fundo_linha")
        cursor.execute("DROP TABLE IF EXISTS financeiro_requisicao_fundo")
        
        # Recreate RequisicaoFundo with correct schema
        cursor.execute("""
        CREATE TABLE financeiro_requisicao_fundo (
            id bigint AUTO_INCREMENT PRIMARY KEY,
            numero_requisicao varchar(50) UNIQUE NOT NULL,
            data_emissao datetime(6) NOT NULL,
            data_validade date NOT NULL,
            moeda_referencia varchar(3) DEFAULT 'AOA' NOT NULL,
            cambio_referencia decimal(10,2),
            pessoa_contacto varchar(200),
            estado varchar(20) DEFAULT 'Pendente' NOT NULL,
            subtotal_geral decimal(15,2) DEFAULT 0,
            iva_honorarios decimal(15,2) DEFAULT 0,
            retencao decimal(15,2) DEFAULT 0,
            total_geral decimal(15,2) DEFAULT 0,
            valor_pago decimal(15,2) DEFAULT 0,
            criado_por_id int,
            criado_por_nome varchar(200),
            observacoes longtext,
            banca_id bigint,
            filial_id bigint,
            cliente_id bigint NOT NULL,
            processo_aduaneiro_id bigint NOT NULL,
            numero_bl_awb varchar(100),
            meio_transporte varchar(100),
            origem varchar(100),
            destino varchar(100),
            mercadoria_descricao longtext,
            peso_bruto_kg decimal(12,2),
            peso_liquido_kg decimal(12,2),
            cbm_metros_cubicos decimal(10,3),
            quantidade_volumes varchar(100),
            valor_cif decimal(15,2),
            banco varchar(200),
            numero_conta varchar(50),
            iban varchar(50),
            instrucoes_envio longtext,
            assinatura_digital longtext,
            codigo_qr varchar(100),
            KEY ix_rf_estado_data (estado, data_emissao),
            KEY ix_rf_cliente_estado (cliente_id, estado),
            KEY data_emissao (data_emissao),
            KEY estado (estado),
            KEY data_validade (data_validade),
            KEY criado_por_id (criado_por_id),
            KEY banca_id (banca_id),
            KEY filial_id (filial_id),
            KEY cliente_id (cliente_id),
            KEY processo_aduaneiro_id (processo_aduaneiro_id)
        )
        """)
        
        # Recreate RequisicaoFundoLinha with correct schema
        cursor.execute("""
        CREATE TABLE financeiro_requisicao_fundo_linha (
            id bigint AUTO_INCREMENT PRIMARY KEY,
            tipo_custo varchar(50) NOT NULL,
            descricao varchar(255) NOT NULL,
            documentada tinyint(1) DEFAULT 0,
            despesa_tipo varchar(50),
            valor decimal(15,2) NOT NULL,
            documento_justificativo varchar(100),
            ordem smallint unsigned DEFAULT 0,
            requisicao_id bigint NOT NULL,
            KEY tipo_custo (tipo_custo),
            KEY requisicao_id (requisicao_id)
        )
        """)

def reverse_fix(apps, schema_editor):
    # Reverse: Drop the tables (they'll be recreated by other migrations if needed)
    pass

class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('financeiro', '0025_add_requisicao_campos_completos'),
    ]

    operations = [
        migrations.RunPython(fix_schema, reverse_fix),
    ]
