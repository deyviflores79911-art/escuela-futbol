"""
Menos pasos en el día a día: sesión que se mantiene en el celular, método de pago sugerido,
cobrar el mes siguiente desde el recibo y búsqueda mientras se escribe.
"""
import re
import time
import unittest
from datetime import date

from datos import pagos
from datos.bd import consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace, cliente_como
from pruebas.test_etapa2 import texto
from pruebas.test_etapa3 import AyudaCaja


class PruebasSesion(PruebaConBaseQueSeDeshace):
    def sesion_vieja(self, recordar):
        c = cliente_como(self.dueno_id(), "DUENO")
        with c.session_transaction() as s:
            s["ultima_actividad"] = time.time() - 3 * 3600   # 3 horas sin usar la app
            s["recordar"] = recordar
        return c

    def dueno_id(self):
        return consultar_uno("SELECT TOP 1 u.id_usuario FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol "
                             "WHERE r.nombre = 'Administrador' AND u.estado = 'ACTIVO'")["id_usuario"]

    def test_mantener_la_sesion_en_el_celular(self):
        self.assertEqual(self.sesion_vieja(True).get("/").status_code, 200, "con 'Mantener la sesión' sigue adentro")
        self.assertEqual(self.sesion_vieja(False).get("/").status_code, 302, "sin marcarla, se cierra por inactividad")

    def test_el_login_ofrece_mantener_la_sesion(self):
        from app import app
        html = app.test_client().get("/login").get_data(as_text=True)
        self.assertIn('name="recordar"', html)


class PruebasCobroRapido(AyudaCaja, PruebaConBaseQueSeDeshace):
    def test_metodo_sugerido_es_el_ultimo_que_uso(self):
        m = self.una_mensualidad()
        self.cobrar(m["id_mensualidad"], "1.00", metodo=3, fecha=date.today().isoformat())
        self.assertEqual(pagos.metodo_sugerido(m["id_alumno"]), 3)
        html = self.dueno.get(f"/caja/mensualidades/{m['id_mensualidad']}/cobrar").get_data(as_text=True)
        self.assertRegex(html, r'name="id_metodo_pago" value="3" required\s+checked')

    def test_recibo_ofrece_cobrar_el_mes_siguiente(self):
        m = self.una_mensualidad()
        r, _ = self.cobrar(m["id_mensualidad"], "1.00", fecha=date.today().isoformat())   # queda saldo
        html = self.dueno.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("Cobrar el mes", html)
        self.assertIn("/cobrar", re.search(r'class="boton boton-cobrar" href="([^"]+)"', html).group(1))

    def test_busqueda_devuelve_solo_la_zona_de_resultados(self):
        html = self.dueno.get("/caja?q=ma").get_data(as_text=True)
        self.assertIn('data-busqueda-vivo="#resultados"', html)
        self.assertIn('id="resultados"', html)
        for ruta in ("/alumnos?q=ma", "/tutores?q=ma", "/inscribir?q=ma"):
            self.assertIn('id="resultados"', self.dueno.get(ruta).get_data(as_text=True), ruta)


if __name__ == "__main__":
    unittest.main()
