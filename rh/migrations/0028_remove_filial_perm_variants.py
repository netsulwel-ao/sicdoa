from django.db import migrations


OLD_FILIAL_PERMS = [
    'gerir_rh_filial',
    'gerir_clientes_filial',
    'gerir_financeiro_filial',
    'gerir_aduaneiro_filial',
    'gerir_governanca_filial',
]

REPLACEMENT_PERMS = [
    'gerir_clientes',
    'gerir_financeiro',
]


def remove_old_filial_perms(apps, schema_editor):
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')
    old_perms = list(Permissao.objects.filter(codigo__in=OLD_FILIAL_PERMS))
    if not old_perms:
        return
    for cargo in CargoBanca.objects.filter(permissoes__in=old_perms).distinct():
        cargo.permissoes.remove(*old_perms)


def add_replacement_perms(apps, schema_editor):
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')
    for cargo in CargoBanca.objects.filter(nome='Gestor de Filial', locked=True):
        for cod in REPLACEMENT_PERMS:
            perm = Permissao.objects.filter(codigo=cod).first()
            if perm and not cargo.permissoes.filter(pk=perm.pk).exists():
                cargo.permissoes.add(perm)


def reverse_remove(apps, schema_editor):
    pass


def reverse_add(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0027_add_gerir_aduaneiro_filial'),
    ]

    operations = [
        migrations.RunPython(remove_old_filial_perms, reverse_remove),
        migrations.RunPython(add_replacement_perms, reverse_add),
    ]
