"""
Utilitários SSL para o sistema SICDOA.

ATENÇÃO: Este módulo desativa a verificação SSL como workaround para o
ambiente Render onde os certificados CA têm Basic Constraints não marcados
como críticos. Isto é um risco de segurança (MITM). As funções devem ser
usadas APENAS para chamadas ao portal de autenticação externo.

TODO: Resolver a causa raiz (instalar CA bundle correcto no Render) e
remover este módulo.
"""
import ssl
import urllib3

# Suprimir InsecureRequestWarning — necessário para verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def ssl_context_relaxado() -> ssl.SSLContext:
    """
    Retorna um SSLContext que não verifica certificados.
    APENAS para uso no portal de autenticação externo.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def requests_kwargs_ssl() -> dict:
    """
    Retorna kwargs para requests que desactivam verificação SSL.
    APENAS para uso no portal de autenticação externo.
    """
    return {'verify': False}
