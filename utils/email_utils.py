"""
Utilitários de email para o sistema SICDOA.
Todas as funções retornam (sucesso: bool, mensagem: str).
O envio é feito em thread separada para não bloquear o request.
"""
import random
import string
import threading
import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def gerar_senha_aleatoria(tamanho=8):
    """Gera uma senha aleatória com letras, números e símbolos."""
    caracteres = string.ascii_letters + string.digits + "!@#$%&*"
    return ''.join(random.choice(caracteres) for _ in range(tamanho))


def _url_login():
    """URL absoluta da página de início de sessão."""
    from django.urls import reverse
    base = getattr(settings, 'SITE_URL', 'https://sicdoa-ycg9.onrender.com').rstrip('/')
    return f"{base}{reverse('login')}"  


def _url_vaga(vaga):
    """URL absoluta da página pública da vaga."""
    base = getattr(settings, 'SITE_URL', 'https://sicdoa-ycg9.onrender.com').rstrip('/')
    return f"{base}/vaga/{vaga.link_externo}/"
    

def _url_candidatura(vaga):
    """URL absoluta do formulário de candidatura da vaga."""
    base = getattr(settings, 'SITE_URL', 'https://sicdoa-ycg9.onrender.com').rstrip('/')
    return f"{base}/candidatar/{vaga.link_externo}/"


def _enviar_sync(assunto, texto, html, destinatarios, anexos=None):
    """Envia email de forma síncrona (chamado internamente pela thread)."""
    if not destinatarios:
        return
    prefixo = getattr(settings, 'EMAIL_SUBJECT_PREFIX', '') or ''
    if prefixo and not assunto.startswith(prefixo):
        assunto = f'{prefixo}{assunto}'
    try:
        msg = EmailMultiAlternatives(
            subject=assunto,
            body=texto,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=destinatarios if isinstance(destinatarios, list) else [destinatarios],
        )
        if html:
            msg.attach_alternative(html, "text/html")
        if anexos:
            for nome_ficheiro, conteudo, mime_type in anexos:
                msg.attach(nome_ficheiro, conteudo, mime_type)
        msg.send(fail_silently=False)
        logger.info("Email enviado para %s — assunto: %s", destinatarios, assunto)
    except Exception as e:  # noqa: BLE001
        logger.error("Falha ao enviar email para %s: %s", destinatarios, str(e))


def _enviar(assunto, texto, html, destinatarios, anexos=None):
    """
    Envia email de forma assíncrona.
    Usa Celery quando REDIS_ENABLED=1, caso contrário usa thread daemon.
    Retorna sempre (True, mensagem) porque o envio é assíncrono.
    """
    if not destinatarios:
        return False, "Nenhum destinatário definido"

    if getattr(settings, 'REDIS_ENABLED', False):
        from utils.tasks import enviar_email_task
        enviar_email_task.delay(assunto, texto, html, destinatarios, anexos=anexos)
    else:
        t = threading.Thread(
            target=_enviar_sync,
            args=(assunto, texto, html, destinatarios, anexos),
            daemon=True,
        )
        t.start()
    return True, "Email em envio"


# ─── Colaboradores ────────────────────────────────────────────────────────────

def enviar_senha_colaborador(colaborador, senha):
    """Envia credenciais de acesso ao colaborador."""
    if not colaborador.email:
        return False, "Colaborador não possui email cadastrado"

    assunto = "As suas credenciais de acesso — SICDOA"
    link_login = _url_login()

    texto = f"""Prezado(a) {colaborador.nome},

Foram criadas as suas credenciais de acesso ao Sistema SICDOA:

  Email : {colaborador.email}
  Senha : {senha}

Inicie sessão em: {link_login}

Por favor, aceda ao sistema e altere a sua senha no primeiro login.

Atenciosamente,
Equipa SICDOA
"""

    html = f"""
<!DOCTYPE html>
<html lang="pt">
<body style="margin:0;padding:0;background:#f6f7f8;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:40px 20px;">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.08);">
      <!-- Header -->
      <tr><td style="background:linear-gradient(135deg,#137fec,#0ea5e9);padding:32px 40px;">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">CDOA Sistema</h1>
        <p style="margin:6px 0 0;color:rgba(255,255,255,.85);font-size:14px;">Credenciais de Acesso</p>
      </td></tr>
      <!-- Body -->
      <tr><td style="padding:36px 40px;">
        <p style="margin:0 0 16px;color:#374151;font-size:15px;">Prezado(a) <strong>{colaborador.nome}</strong>,</p>
        <p style="margin:0 0 24px;color:#6b7280;font-size:14px;line-height:1.6;">
          A sua conta no Sistema SICDOA foi criada. Utilize as credenciais abaixo para aceder.
        </p>
        <!-- Credenciais -->
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;margin-bottom:24px;">
          <tr><td style="padding:20px 24px;">
            <p style="margin:0 0 10px;font-size:13px;color:#0369a1;font-weight:600;text-transform:uppercase;letter-spacing:.05em;">As suas credenciais</p>
            <p style="margin:0 0 8px;font-size:14px;color:#374151;"><strong>Email:</strong> {colaborador.email}</p>
            <p style="margin:0;font-size:14px;color:#374151;"><strong>Senha:</strong> <code style="background:#e0f2fe;padding:2px 8px;border-radius:4px;font-size:15px;letter-spacing:.05em;">{senha}</code></p>
          </td></tr>
        </table>
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
          <tr><td align="center">
            <a href="{link_login}" style="display:inline-block;background:#137fec;color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;padding:14px 32px;border-radius:10px;">
              Iniciar sessão no SICDOA
            </a>
          </td></tr>
          <tr><td align="center" style="padding-top:12px;">
            <p style="margin:0;font-size:12px;color:#9ca3af;word-break:break-all;">
              Ou copie este link: <a href="{link_login}" style="color:#137fec;">{link_login}</a>
            </p>
          </td></tr>
        </table>
        <p style="margin:0 0 8px;color:#ef4444;font-size:13px;font-weight:600;">Altere a sua senha no primeiro acesso.</p>
      </td></tr>
      <!-- Footer -->
      <tr><td style="background:#f9fafb;padding:20px 40px;border-top:1px solid #e5e7eb;">
        <p style="margin:0;color:#9ca3af;font-size:12px;">© 2026 CDOA Sistema · Câmara dos Despachantes Oficiais de Angola</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>
"""
    return _enviar(assunto, texto, html, colaborador.email)



def enviar_convocatoria_entrevista(entrevista):
    """Envia convocatória de entrevista ao candidato."""
    cand = entrevista.candidatura
    if not cand.email:
        return False, "Candidato não possui email"

    data_fmt = entrevista.data_hora.strftime("%d/%m/%Y às %H:%M")
    tipo_label = dict([
        ('Presencial', 'Presencial'),
        ('Online', 'Online / Videochamada'),
        ('Telefonica', 'Telefónica'),
    ]).get(entrevista.tipo, entrevista.tipo)

    local_info = entrevista.local_link or "A confirmar"
    entrevistador_info = entrevista.entrevistador or "A confirmar"
    link_vaga = _url_vaga(cand.vaga)

    assunto = f"Convocatória para Entrevista — {cand.vaga.titulo}"
    texto = f"""Prezado(a) {cand.nome},

Temos o prazer de o(a) convidar para uma entrevista referente à vaga "{cand.vaga.titulo}".

Detalhes da entrevista:
  Data e Hora  : {data_fmt}
  Tipo         : {tipo_label}
  Local / Link : {local_info}
  Entrevistador: {entrevistador_info}

Ver detalhes da vaga: {link_vaga}

Por favor, confirme a sua presença respondendo a este email.

Atenciosamente,
Equipa de Recrutamento — SICDOA
"""
    html = f"""
<!DOCTYPE html><html lang="pt">
<body style="margin:0;padding:0;background:#f6f7f8;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:40px 20px;">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.08);">
      <tr><td style="background:linear-gradient(135deg,#137fec,#0ea5e9);padding:32px 40px;">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">CDOA Sistema</h1>
        <p style="margin:6px 0 0;color:rgba(255,255,255,.85);font-size:14px;">Convocatória para Entrevista</p>
      </td></tr>
      <tr><td style="padding:36px 40px;">
        <p style="margin:0 0 16px;color:#374151;font-size:15px;">Prezado(a) <strong>{cand.nome}</strong>,</p>
        <p style="margin:0 0 24px;color:#6b7280;font-size:14px;line-height:1.6;">
          Temos o prazer de o(a) convidar para uma entrevista referente à vaga <strong>{cand.vaga.titulo}</strong>.
        </p>
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;margin-bottom:24px;">
          <tr><td style="padding:20px 24px;">
            <p style="margin:0 0 14px;font-size:13px;color:#1d4ed8;font-weight:600;text-transform:uppercase;letter-spacing:.05em;">Detalhes da Entrevista</p>
            <table cellpadding="0" cellspacing="0">
              <tr><td style="padding:4px 0;font-size:14px;color:#6b7280;width:130px;">📅 Data e Hora</td><td style="padding:4px 0;font-size:14px;color:#111827;font-weight:600;">{data_fmt}</td></tr>
              <tr><td style="padding:4px 0;font-size:14px;color:#6b7280;">🎯 Tipo</td><td style="padding:4px 0;font-size:14px;color:#111827;">{tipo_label}</td></tr>
              <tr><td style="padding:4px 0;font-size:14px;color:#6b7280;">📍 Local / Link</td><td style="padding:4px 0;font-size:14px;color:#111827;">{local_info}</td></tr>
              <tr><td style="padding:4px 0;font-size:14px;color:#6b7280;">👤 Entrevistador</td><td style="padding:4px 0;font-size:14px;color:#111827;">{entrevistador_info}</td></tr>
            </table>
          </td></tr>
        </table>
        <p style="margin:0 0 16px;color:#6b7280;font-size:13px;">Por favor, confirme a sua presença respondendo a este email.</p>
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr><td align="center">
            <a href="{link_vaga}" style="display:inline-block;background:#137fec;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;padding:12px 28px;border-radius:10px;">
              Ver detalhes da vaga
            </a>
          </td></tr>
        </table>
      </td></tr>
      <tr><td style="background:#f9fafb;padding:20px 40px;border-top:1px solid #e5e7eb;">
        <p style="margin:0;color:#9ca3af;font-size:12px;">© 2026 CDOA Sistema · Câmara dos Despachantes Oficiais de Angola</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""
    return _enviar(assunto, texto, html, cand.email)


def enviar_resultado_candidatura(candidatura):
    """Envia email de aprovação ou rejeição ao candidato."""
    if not candidatura.email:
        return False, "Candidato não possui email"

    aprovado = candidatura.estado == 'Aprovado'
    link_vaga = _url_vaga(candidatura.vaga)
    assunto = f"{'Aprovação' if aprovado else 'Resultado'} da sua candidatura — {candidatura.vaga.titulo}"

    if aprovado:
        texto = f"""Prezado(a) {candidatura.nome},

Temos o prazer de informar que a sua candidatura para a vaga "{candidatura.vaga.titulo}" foi APROVADA.

Entraremos em contacto brevemente para os próximos passos do processo de integração.

Ver detalhes da vaga: {link_vaga}

Parabéns e bem-vindo(a) à equipa!

Atenciosamente,
Equipa de Recrutamento — SICDOA
"""
        cor_header = "linear-gradient(135deg,#16a34a,#15803d)"
        icone = ""
        titulo_header = "Candidatura Aprovada"
        corpo_html = f"""
        <p style="margin:0 0 16px;color:#374151;font-size:15px;">Prezado(a) <strong>{candidatura.nome}</strong>,</p>
        <p style="margin:0 0 20px;color:#6b7280;font-size:14px;line-height:1.6;">
          Temos o prazer de informar que a sua candidatura para a vaga <strong>{candidatura.vaga.titulo}</strong> foi <strong style="color:#16a34a;">APROVADA</strong>.
        </p>
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:20px 24px;margin-bottom:24px;">
          <p style="margin:0;font-size:14px;color:#15803d;">🎉 Parabéns! Entraremos em contacto brevemente para os próximos passos do processo de integração.</p>
        </div>
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;">
          <tr><td align="center">
            <a href="{link_vaga}" style="display:inline-block;background:#16a34a;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;padding:12px 28px;border-radius:10px;">
              Ver detalhes da vaga
            </a>
          </td></tr>
        </table>
"""
    else:
        texto = f"""Prezado(a) {candidatura.nome},

Agradecemos o seu interesse na vaga "{candidatura.vaga.titulo}".

Após análise cuidadosa do seu perfil, informamos que não foi possível avançar com a sua candidatura neste momento.

Guardamos o seu perfil para futuras oportunidades.

Atenciosamente,
Equipa de Recrutamento — SICDOA
"""
        cor_header = "linear-gradient(135deg,#6b7280,#4b5563)"
        icone = "📋"
        titulo_header = "Resultado da Candidatura"
        corpo_html = f"""
        <p style="margin:0 0 16px;color:#374151;font-size:15px;">Prezado(a) <strong>{candidatura.nome}</strong>,</p>
        <p style="margin:0 0 20px;color:#6b7280;font-size:14px;line-height:1.6;">
          Agradecemos o seu interesse na vaga <strong>{candidatura.vaga.titulo}</strong>. Após análise cuidadosa, informamos que não foi possível avançar com a sua candidatura neste momento.
        </p>
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:20px 24px;margin-bottom:24px;">
          <p style="margin:0;font-size:14px;color:#6b7280;">O seu perfil ficará guardado para futuras oportunidades.</p>
        </div>
"""

    html = f"""
<!DOCTYPE html><html lang="pt">
<body style="margin:0;padding:0;background:#f6f7f8;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:40px 20px;">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.08);">
      <tr><td style="background:{cor_header};padding:32px 40px;">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">CDOA Sistema</h1>
        <p style="margin:6px 0 0;color:rgba(255,255,255,.85);font-size:14px;">{icone} {titulo_header}</p>
      </td></tr>
      <tr><td style="padding:36px 40px;">{corpo_html}</td></tr>
      <tr><td style="background:#f9fafb;padding:20px 40px;border-top:1px solid #e5e7eb;">
        <p style="margin:0;color:#9ca3af;font-size:12px;">© 2026 CDOA Sistema · Câmara dos Despachantes Oficiais de Angola</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""
    return _enviar(assunto, texto, html, candidatura.email)
