"""
Conexión a Sistema_EscuelasDeportivas.
  - En la computadora: pyodbc + ODBC Driver 17 (autenticación de Windows).
  - En la nube (Vercel + Azure SQL): pymssql, que no necesita instalar drivers.
Reglas: siempre parámetros (?), nunca texto concatenado; lo que escribe
más de una tabla va dentro de transaccion() (o todo o nada).
"""
import time
from contextlib import contextmanager, suppress

import config


class ErrorBD(Exception):
    """La base no responde (por ejemplo, el servicio de SQL Server está apagado)."""


class ErrorDatos(Exception):
    """Regla de negocio no cumplida (correo repetido, grupo lleno...), con un mensaje claro para la pantalla."""


def conectar():
    if config.EN_LA_NUBE:
        return _conectar_nube()
    import pyodbc
    try:
        return pyodbc.connect(config.CADENA_CONEXION, timeout=5)
    except pyodbc.Error as e:
        raise ErrorBD("No se pudo conectar con SQL Server. "
                      "Revisa que el servicio MSSQL$MSSQLSERVER01 esté iniciado.") from e


# ---------------------------------------------------------------- Nube (Azure SQL con pymssql)

def a_pyformat(sql):
    """pymssql usa %s en vez de ?. Cambia solo los ? que están fuera de los textos entre comillas."""
    salida, en_texto = [], False
    for letra in sql:
        if letra == "'":
            en_texto = not en_texto
        salida.append("%s" if letra == "?" and not en_texto else letra)
    return "".join(salida)


class _CursorNube:
    """Cursor de pymssql que acepta las mismas consultas con ? que pyodbc."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=()):
        if params:
            self._cursor.execute(a_pyformat(sql), tuple(params))
        else:
            self._cursor.execute(sql)   # sin parámetros pymssql no toca el texto
        return self

    def __getattr__(self, nombre):      # description, rowcount, fetchone, fetchall...
        return getattr(self._cursor, nombre)


class _ConexionNube:
    def __init__(self, cn, compartida=False):
        self._cn = cn
        self._compartida = compartida   # la comparte toda la página: se cierra al terminar la petición

    def cursor(self):
        return _CursorNube(self._cn.cursor())

    @property
    def autocommit(self):
        return False

    @autocommit.setter
    def autocommit(self, _valor):
        pass   # pymssql ya trabaja con transacciones (autocommit apagado) por defecto

    def commit(self):
        self._cn.commit()

    def rollback(self):
        self._cn.rollback()

    def close(self):
        if not self._compartida:
            self._cn.close()


def _conectar_nube():
    """Una sola conexión por página (abrir una conexión segura hasta Azure tarda; abrir una por consulta sería lento)."""
    from flask import g, has_app_context
    if has_app_context():
        if g.get("_bd_nube") is None:
            g._bd_nube = _abrir_nube()
        return _ConexionNube(g._bd_nube, compartida=True)
    return _ConexionNube(_abrir_nube())


def cerrar_conexion(_error=None):
    """Al terminar cada petición: deshace lo que haya quedado abierto y cierra la conexión compartida."""
    from flask import g
    cn = g.pop("_bd_nube", None)
    if cn is not None:
        with suppress(Exception):   # si la conexión ya se cortó, igual se intenta cerrar
            cn.rollback()
        with suppress(Exception):
            cn.close()


def _abrir_nube():
    import pymssql
    # La base gratis de Azure "se duerme": mientras despierta responde el error 40613. Se reintenta sola.
    for intento in range(5):
        try:
            return pymssql.connect(server=config.BD_SERVIDOR, user=config.BD_USUARIO, password=config.BD_CLAVE,
                                   database=config.BD_NOMBRE, login_timeout=20, timeout=30, tds_version="7.4",
                                   encryption="require", autocommit=False)
        except pymssql.Error as e:
            if "40613" in str(e) and intento < 4:
                time.sleep(8)
                continue
            raise ErrorBD("No se pudo conectar con la base de datos en la nube. "
                          "Si la base estaba dormida, espera un minuto y recarga la página.") from e
    raise ErrorBD("La base de datos en la nube no respondió.")


# ---------------------------------------------------------------- Consultas

def _a_dicts(cur):
    columnas = [c[0] for c in cur.description]
    return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]


def consultar(sql, params=()):
    """SELECT -> lista de diccionarios."""
    cn = conectar()
    try:
        cur = cn.cursor()
        cur.execute(sql, params)
        return _a_dicts(cur)
    finally:
        cn.close()


def consultar_uno(sql, params=()):
    """SELECT -> un diccionario, o None si no hay filas."""
    filas = consultar(sql, params)
    return filas[0] if filas else None


@contextmanager
def transaccion():
    """Entrega un cursor; confirma al final o deshace todo si hay un error."""
    cn = conectar()
    cn.autocommit = False
    try:
        cur = cn.cursor()
        yield cur
        cn.commit()
    except Exception:
        cn.rollback()
        raise
    finally:
        cn.close()


def filas(cur):
    """Convierte el resultado de un cursor abierto en lista de diccionarios."""
    return _a_dicts(cur)
