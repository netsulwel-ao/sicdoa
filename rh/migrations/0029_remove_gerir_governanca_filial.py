from django.db import migrations


def remove_gerir_governanca_filial(apps, schema_editor):
    CargoBanca = apps.get_model('rh', 'CargoBanca')
    Permissao = apps.get_model('users', 'Permissao')
    perm = Permissao.objects.filter(codigo='gerir_governanca_filial').first()
    if not perm:
        return
    for cargo in CargoBanca.objects.filter(permissoes=perm).distinct():
        cargo.permissoes.remove(perm)
    Permissao.objects.filter(codigo='gerir_governanca_filial').delete()


def reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0028_remove_filial_perm_variants'),
    ]

    operations = [
        migrations.RunPython(remove_gerir_governanca_filial, reverse),
    ]
