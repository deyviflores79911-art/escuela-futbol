"""
Lugares de entrenamiento con su enlace de Google Maps ("Cómo llegar").
Se guardan en lugares.json (no en la base: así no se cambia la estructura de HORARIO).
El nombre es el mismo texto que se guarda en HORARIO.lugar.
"""
import json
from urllib.parse import urlparse

import config
from datos.bd import ErrorDatos

# Solo enlaces de mapas conocidos (evita guardar enlaces raros)
_HOSTS_MAPAS = {"maps.app.goo.gl", "goo.gl", "maps.google.com", "www.google.com", "google.com"}


def listar():
    """{nombre: enlace} en orden de nombre. Si el archivo no existe o está dañado, no hay lugares."""
    try:
        datos = json.loads(config.ARCHIVO_LUGARES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {str(k): str(v) for k, v in sorted(datos.items(), key=lambda kv: kv[0].lower())}


def enlace(nombre):
    return listar().get(nombre) if nombre else None


def validar_enlace(url):
    u = urlparse((url or "").strip())
    if u.scheme != "https" or u.netloc.lower() not in _HOSTS_MAPAS:
        raise ErrorDatos("El enlace debe ser de Google Maps (empieza con https://maps.app.goo.gl/ o https://maps.google.com/). "
                         "En Maps toca Compartir → Copiar enlace.")
    if u.netloc.lower() in {"www.google.com", "google.com"} and not u.path.startswith("/maps"):
        raise ErrorDatos("El enlace debe ser de Google Maps.")
    return url.strip()


def guardar(nombre, url):
    nombre = (nombre or "").strip()
    if not nombre or len(nombre) > 100:
        raise ErrorDatos("El nombre del lugar es obligatorio (máximo 100 caracteres).")
    lugares = listar()
    lugares[nombre] = validar_enlace(url)
    _escribir(lugares)


def quitar(nombre):
    lugares = listar()
    if nombre not in lugares:
        raise ErrorDatos("Ese lugar no está guardado.")
    del lugares[nombre]
    _escribir(lugares)


def _escribir(lugares):
    temporal = config.ARCHIVO_LUGARES.with_suffix(".tmp")
    temporal.write_text(json.dumps(lugares, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(config.ARCHIVO_LUGARES)  # se reemplaza de una vez: nunca queda a medio escribir
