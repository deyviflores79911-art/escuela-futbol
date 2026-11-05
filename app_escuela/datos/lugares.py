"""
Lugares de entrenamiento con su enlace de Google Maps ("Cómo llegar").
En la computadora se guardan en lugares.json; en la nube (Vercel no deja guardar archivos),
en la tabla LUGAR de Azure SQL. El nombre es el mismo texto que se guarda en HORARIO.lugar.
"""
import json
from urllib.parse import urlparse

import config
from datos.bd import ErrorDatos, consultar, transaccion

# Solo enlaces de mapas conocidos (evita guardar enlaces raros)
_HOSTS_MAPAS = {"maps.app.goo.gl", "goo.gl", "maps.google.com", "www.google.com", "google.com"}


def listar():
    """{nombre: enlace} en orden de nombre. Si el archivo no existe o está dañado, no hay lugares."""
    if config.EN_LA_NUBE:
        return {f["nombre"]: f["enlace"] for f in consultar("SELECT nombre, enlace FROM LUGAR ORDER BY nombre")}
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
    url = validar_enlace(url)
    if config.EN_LA_NUBE:
        with transaccion() as cur:
            cur.execute("UPDATE LUGAR SET enlace = ? WHERE nombre = ?", (url, nombre))
            if cur.rowcount == 0:
                cur.execute("INSERT INTO LUGAR (nombre, enlace) VALUES (?, ?)", (nombre, url))
        return
    lugares = listar()
    lugares[nombre] = url
    _escribir(lugares)


def quitar(nombre):
    lugares = listar()
    if nombre not in lugares:
        raise ErrorDatos("Ese lugar no está guardado.")
    if config.EN_LA_NUBE:
        with transaccion() as cur:
            cur.execute("DELETE FROM LUGAR WHERE nombre = ?", (nombre,))
        return
    del lugares[nombre]
    _escribir(lugares)


def _escribir(lugares):
    temporal = config.ARCHIVO_LUGARES.with_suffix(".tmp")
    temporal.write_text(json.dumps(lugares, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(config.ARCHIVO_LUGARES)  # se reemplaza de una vez: nunca queda a medio escribir
