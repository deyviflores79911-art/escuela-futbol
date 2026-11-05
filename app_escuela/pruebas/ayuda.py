"""Ayudas comunes de las pruebas: sesión sin pasar por el login
y base real dentro de una transacción que se deshace al final (no deja datos)."""
import re
import time
import unittest

import pyodbc

import config
from app import app
from datos import bd
from datos.bd import consultar_uno


def cliente_como(id_usuario, rol):
    """Cliente con la sesión ya abierta (sin pasar por el login)."""
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(id_usuario=id_usuario, rol=rol, ultima_actividad=time.time())
    return c


def token_csrf(cliente, url):
    """Token CSRF de un formulario, como lo tendría el navegador."""
    return re.search(r'name="csrf_token" value="([^"]+)"', cliente.get(url).get_data(as_text=True)).group(1)


def enviar(cliente, url, datos, desde=None):
    """POST de un formulario con su token CSRF (lo toma de la página 'desde' o de la misma url)."""
    return cliente.post(url, data=dict(datos, csrf_token=token_csrf(cliente, desde or url)))


class _ConexionDePrueba:
    """
    Conexión compartida dentro de una transacción abierta: la app 'confirma' (commit) sin efecto real
    y, si una operación falla, solo se deshace esa operación (punto de guardado).
    """
    def __init__(self, cn):
        self._cn = cn

    def cursor(self):
        cur = self._cn.cursor()
        cur.execute("SAVE TRANSACTION punto_prueba")
        return cur

    @property
    def autocommit(self):
        return False

    @autocommit.setter
    def autocommit(self, _valor):
        pass

    def commit(self):
        pass

    def rollback(self):
        self._cn.cursor().execute("ROLLBACK TRANSACTION punto_prueba")

    def close(self):
        pass


class PruebaConBaseQueSeDeshace(unittest.TestCase):
    """Cada prueba trabaja contra la base REAL, pero todo lo que escribe se deshace (ROLLBACK) al terminar."""

    def setUp(self):
        self._cn = pyodbc.connect(config.CADENA_CONEXION, autocommit=True)
        self._cn.cursor().execute("BEGIN TRANSACTION")
        self._conectar_original = bd.conectar
        compartida = _ConexionDePrueba(self._cn)
        bd.conectar = lambda: compartida
        self.dueno = cliente_como(consultar_uno(
            "SELECT TOP 1 u.id_usuario FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol "
            "WHERE r.nombre = 'Administrador' AND u.estado = 'ACTIVO' ORDER BY u.id_usuario")["id_usuario"], "DUENO")

    def tearDown(self):
        bd.conectar = self._conectar_original
        self._cn.cursor().execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
        self._cn.close()

    def contar(self, sql, params=()):
        return consultar_uno(f"SELECT COUNT(*) AS n FROM {sql}", params)["n"]
