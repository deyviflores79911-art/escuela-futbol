"""
Envío del recibo por correo (Gmail u otro servidor SMTP).
Queda listo para usar: se activa solo cuando existen CORREO_USUARIO y CORREO_CLAVE (ver config.py).
"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import config
from datos.bd import ErrorDatos


def configurado():
    return bool(config.CORREO_USUARIO and config.CORREO_CLAVE)


def enviar(destino, asunto, texto, html, imagen=None):
    """Manda un correo con versión texto y HTML. imagen=(cid, bytes, 'png') va dentro del HTML (el escudo)."""
    if not configurado():
        raise ErrorDatos("Falta configurar el correo de la escuela (CORREO_USUARIO y CORREO_CLAVE).")
    if not destino:
        raise ErrorDatos("El tutor no tiene correo registrado.")
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr((config.ESCUELA["nombre"], config.CORREO_USUARIO))
    msg["To"] = destino
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    if imagen:
        cid, datos, subtipo = imagen
        msg.get_payload()[1].add_related(datos, "image", subtipo, cid=f"<{cid}>")
    try:
        with smtplib.SMTP(config.CORREO_SERVIDOR, config.CORREO_PUERTO, timeout=20) as servidor:
            servidor.starttls(context=ssl.create_default_context())
            servidor.login(config.CORREO_USUARIO, config.CORREO_CLAVE)
            servidor.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise ErrorDatos(f"No se pudo enviar el correo a {destino}. Revisa la cuenta de correo de la escuela. ({e})") from e
