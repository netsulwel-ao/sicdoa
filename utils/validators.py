import re

NIF_RE = re.compile(r'^[A-Z0-9]{1,18}$')


def limpar_nif(valor):
    """Remove espaços, hífenes e pontos e converte para maiúsculas (ex: 022230815ha-058 -> 022230815HA058)."""
    if not valor:
        return ''
    return re.sub(r'[\s.\-]', '', str(valor)).upper()


def nif_valido(valor):
    """Valida NIF: sem formato fixo, apenas letras/números, no máximo 18 caracteres."""
    return bool(valor) and bool(NIF_RE.match(limpar_nif(valor)))


def nif_ja_existe(valor, exclude_model=None, exclude_pk=None):
    """Verifica se um NIF já está registado em qualquer registo do sistema."""
    from users.models import Usuario
    from rh.models import Banca, BancaCentral, Colaborador
    from clientes.models import Cliente

    nif = limpar_nif(valor)
    if not nif:
        return False

    checks = [
        (Usuario, Usuario.objects.filter(nif__iexact=nif)),
        (Banca, Banca.objects.filter(nif__iexact=nif)),
        (BancaCentral, BancaCentral.objects.filter(nif__iexact=nif)),
        (Colaborador, Colaborador.objects.filter(nif__iexact=nif)),
        (Cliente, Cliente.objects.filter(nif__iexact=nif)),
    ]

    for model, qs in checks:
        if model is exclude_model and exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        if qs.exists():
            return True

    return False


def email_ja_existe(email, exclude_model=None, exclude_pk=None):
    """Verifica se um email já está registado em qualquer modelo do sistema."""
    from users.models import Usuario
    from rh.models import Banca, FilialBanca, Colaborador
    from clientes.models import Cliente

    email = email.strip().lower()
    if not email:
        return False

    checks = [
        (Usuario, Usuario.objects.filter(email=email)),
        (Banca, Banca.objects.filter(email=email)),
        (FilialBanca, FilialBanca.objects.filter(email=email)),
        (Colaborador, Colaborador.objects.filter(email=email)),
        (Cliente, Cliente.objects.filter(email=email)),
    ]

    for model, qs in checks:
        if model is exclude_model and exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        if qs.exists():
            return True

    return False
