from django.db import migrations


def add_subperms(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    CargoBanca = apps.get_model('rh', 'CargoBanca')

    financeiro_subs = [
        'ver_requisicoes', 'ver_recibos', 'ver_notas_financeiro',
        'ver_facturas', 'ver_conta_corrente', 'ver_relatorios_financeiros',
    ]
    rh_subs = [
        'ver_minha_banca', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
        'gerir_processamento_salarial', 'gerir_recrutamento_banca',
        'gerir_presencas_banca', 'gerir_avaliacoes_banca',
    ]

    for cargo in CargoBanca.objects.prefetch_related('permissoes').iterator(chunk_size=100):
        codigos = set(cargo.permissoes.values_list('codigo', flat=True))

        to_add = set()
        if 'gerir_financeiro' in codigos:
            to_add.update(financeiro_subs)
        if 'gerir_rh' in codigos:
            to_add.update(rh_subs)

        if to_add:
            existing = set(cargo.permissoes.values_list('codigo', flat=True))
            missing = [p for p in to_add if p not in existing]
            if missing:
                perms = Permissao.objects.filter(codigo__in=missing)
                cargo.permissoes.add(*perms)


def remove_subperms(apps, schema_editor):
    Permissao = apps.get_model('users', 'Permissao')
    CargoBanca = apps.get_model('rh', 'CargoBanca')

    financeiro_subs = [
        'ver_requisicoes', 'ver_recibos', 'ver_notas_financeiro',
        'ver_facturas', 'ver_conta_corrente', 'ver_relatorios_financeiros',
    ]
    rh_subs = [
        'ver_minha_banca', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
        'gerir_processamento_salarial', 'gerir_recrutamento_banca',
        'gerir_presencas_banca', 'gerir_avaliacoes_banca',
    ]

    for cargo in CargoBanca.objects.prefetch_related('permissoes').iterator(chunk_size=100):
        codigos = set(cargo.permissoes.values_list('codigo', flat=True))

        to_remove = set()
        if 'gerir_financeiro' in codigos:
            to_remove.update(financeiro_subs)
        if 'gerir_rh' in codigos:
            to_remove.update(rh_subs)

        if to_remove:
            perms = Permissao.objects.filter(codigo__in=to_remove)
            cargo.permissoes.remove(*perms)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0035_seed_permissoes_granulares_banca"),
    ]

    operations = [
        migrations.RunPython(add_subperms, remove_subperms),
    ]
