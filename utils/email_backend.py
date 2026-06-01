"""
Backend de email personalizado que ignora erros de verificação de certificado SSL.

Necessário porque o ambiente de alojamento (Render) tem certificados de CA com
Basic Constraints não marcados como críticos, causando CERTIFICATE_VERIFY_FAILED
ao ligar ao SMTP do Gmail via STARTTLS.
"""
from django.core.mail.backends.smtp import EmailBackend
from utils.ssl_utils import ssl_context_relaxado


class SSLRelaxedEmailBackend(EmailBackend):
    """
    Backend SMTP que sobrescreve a propriedade ssl_context do Django para
    usar um contexto sem verificação de certificado.
    """

    @property
    def ssl_context(self):
        return ssl_context_relaxado()
