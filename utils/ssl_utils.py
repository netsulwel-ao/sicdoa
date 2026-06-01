"""
Utilitários SSL para o sistema SICDOA.

O ambiente de alojamento (Render) tem certificados de CA com Basic Constraints
não marcados como críticos, causando CERTIFICATE_VERIFY_FAILED em todas as
chamadas HTTPS externas feitas pelo Python.

Este módulo centraliza a criação de contextos SSL relaxados para uso em:
  - urllib.request.urlopen()
  - requests (via verify=False + supressão de warnings)
"""
import ssl
import urllib3

# Suprimir InsecureRequestWarning do requests/urllib3 globalmente
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def ssl_context_relaxado() -> ssl.SSLContext:
    """
    Retorna um SSLContext que não verifica certificados.
    Usar em: urllib.request.urlopen(req, context=ssl_context_relaxado())
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def requests_kwargs_ssl() -> dict:
    """
    Retorna kwargs para requests que desactivam verificação SSL.
    Usar em: requests.post(url, **requests_kwargs_ssl(), ...)
    """
    return {'verify': False}
