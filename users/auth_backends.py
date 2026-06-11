import bcrypt
from .models import Usuario


class UsuarioBackend:
    def authenticate(self, request, username=None, password=None):
        if not username or not password:
            return None
        try:
            user = Usuario.objects.get(email=username, status='Ativo')
        except Usuario.DoesNotExist:
            try:
                user = Usuario.objects.get(username=username, status='Ativo')
            except Usuario.DoesNotExist:
                return None
        hash_bytes = user.password.replace('$2y$', '$2b$').encode('utf-8') if user.password else b''
        if hash_bytes and bcrypt.checkpw(password.encode('utf-8'), hash_bytes):
            return user
        return None

    def get_user(self, user_id):
        try:
            return Usuario.objects.get(pk=user_id)
        except Usuario.DoesNotExist:
            return None
