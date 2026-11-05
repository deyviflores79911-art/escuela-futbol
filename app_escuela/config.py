"""Configuración general de la aplicación.

Funciona en dos lugares sin cambiar código:
  - En esta computadora: SQL Server local con autenticación de Windows (como siempre).
  - En la nube (Vercel + Azure SQL): se activa sola cuando existe la variable BD_SERVIDOR.
"""
import os
import secrets
import time
from datetime import timedelta
from pathlib import Path

CARPETA = Path(__file__).resolve().parent

# Hora de Bolivia siempre, también en la nube (los servidores de Vercel usan la hora UTC:
# sin esto, después de las 20:00 "hoy" sería el día siguiente)
ZONA_HORARIA = "America/La_Paz"
if hasattr(time, "tzset"):  # Linux (Vercel). En Windows ya se usa la hora de la computadora
    os.environ["TZ"] = ZONA_HORARIA
    time.tzset()

# ---- Base de datos en la nube (Azure SQL). Se configura en Vercel → Settings → Environment Variables
BD_SERVIDOR = os.environ.get("BD_SERVIDOR", "")          # ej. escuela-fortaleza.database.windows.net
BD_NOMBRE = os.environ.get("BD_NOMBRE", "Sistema_EscuelasDeportivas")
BD_USUARIO = os.environ.get("BD_USUARIO", "")
BD_CLAVE = os.environ.get("BD_CLAVE", "")
EN_LA_NUBE = bool(BD_SERVIDOR)

# ---- Base local (autenticación de Windows)
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

# Lugares de entrenamiento con su enlace de Google Maps. Los maneja el dueño en Grupos → Horarios.
# En la computadora se guardan en este archivo; en la nube, en la tabla LUGAR (Vercel no deja guardar archivos)
ARCHIVO_LUGARES = CARPETA / "lugares.json"

# "0.0.0.0" = el celular puede entrar desde la misma red WiFi. "localhost" = solo esta computadora
HOST = os.environ.get("APP_HOST", "0.0.0.0")
PUERTO = 5000


def _clave_secreta():
    """Clave que firma las sesiones. En la nube viene de la variable CLAVE_SECRETA (no se pueden guardar archivos)."""
    if os.environ.get("CLAVE_SECRETA"):
        return os.environ["CLAVE_SECRETA"]
    if EN_LA_NUBE:
        raise RuntimeError("Falta la variable CLAVE_SECRETA en Vercel (Settings → Environment Variables).")
    archivo = CARPETA / ".clave_secreta"
    if not archivo.exists():
        archivo.write_text(secrets.token_hex(32), encoding="utf-8")
    return archivo.read_text(encoding="utf-8").strip()


class Config:
    SECRET_KEY = _clave_secreta()
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=MINUTOS_INACTIVIDAD)
    SESSION_REFRESH_EACH_REQUEST = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = EN_LA_NUBE   # en la nube la página va con https (candado): la cookie solo viaja cifrada
    WTF_CSRF_TIME_LIMIT = None  # el token vive lo que dure la sesión
