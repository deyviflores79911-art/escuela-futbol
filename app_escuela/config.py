"""Configuración general de la aplicación."""
import os
import secrets
from datetime import timedelta
from pathlib import Path

CARPETA = Path(__file__).resolve().parent

# Conexión a la base existente (autenticación de Windows)
CADENA_CONEXION = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost\\MSSQLSERVER01;"
    "DATABASE=Sistema_EscuelasDeportivas;"
    "Trusted_Connection=yes;"
)

# Minutos sin actividad antes de cerrar la sesión
MINUTOS_INACTIVIDAD = 30

# Datos de la escuela para el recibo. La escuela NO tiene NIT: emite RECIBOS, no facturas.
# Lo que quede vacío no se imprime.
ESCUELA = {
    "nombre": "Escuela de Fútbol “Fortaleza”",
    "responsable": "DT. Willy's",
    "direccion": "Calle Luciano, B/ Nuevo Palmar",
    "telefono": "79445059",
    "ciudad": "Santa Cruz de la Sierra - Bolivia",
    "escudo": "img/escudo.png",
}

# Lugares de entrenamiento con su enlace de Google Maps. Los maneja el dueño en Grupos → Horarios
ARCHIVO_LUGARES = CARPETA / "lugares.json"

# "0.0.0.0" = el celular puede entrar desde la misma red WiFi. "localhost" = solo esta computadora
HOST = os.environ.get("APP_HOST", "0.0.0.0")
PUERTO = 5000


def _clave_secreta():
    """Lee la clave secreta de un archivo local; si no existe, la crea una vez."""
    archivo = CARPETA / ".clave_secreta"
    if not archivo.exists():
        archivo.write_text(secrets.token_hex(32), encoding="utf-8")
    return archivo.read_text(encoding="utf-8").strip()


class Config:
    SECRET_KEY = os.environ.get("CLAVE_SECRETA") or _clave_secreta()
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=MINUTOS_INACTIVIDAD)
    SESSION_REFRESH_EACH_REQUEST = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = None  # el token vive lo que dure la sesión
