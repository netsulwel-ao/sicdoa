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
