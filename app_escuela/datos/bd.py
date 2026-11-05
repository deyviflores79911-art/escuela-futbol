"""
Conexión a Sistema_EscuelasDeportivas con pyodbc.
Reglas: siempre parámetros (?), nunca texto concatenado; lo que escribe
más de una tabla va dentro de transaccion() (o todo o nada).
"""
from contextlib import contextmanager

import pyodbc

from config import CADENA_CONEXION


class ErrorBD(Exception):
    """La base no responde (por ejemplo, el servicio de SQL Server está apagado)."""


class ErrorDatos(Exception):
    """Regla de negocio no cumplida (correo repetido, grupo lleno...), con un mensaje claro para la pantalla."""


def conectar():
    try:
        return pyodbc.connect(CADENA_CONEXION, timeout=5)
    except pyodbc.Error as e:
        raise ErrorBD("No se pudo conectar con SQL Server. "
                      "Revisa que el servicio MSSQL$MSSQLSERVER01 esté iniciado.") from e


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
