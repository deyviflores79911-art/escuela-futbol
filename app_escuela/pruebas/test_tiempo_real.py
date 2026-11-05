"""
Tiempo real: la "huella" de los datos cambia cuando cambia la base, y las pantallas la consultan para actualizarse solas.
"""
import time
import unittest

from datos.bd import transaccion
from pruebas.ayuda import PruebaConBaseQueSeDeshace

AUTOMATICA = {"X-Consulta-Automatica": "1"}


class PruebaHuellaBase(PruebaConBaseQueSeDeshace):
    def test_cambia_cuando_cambia_la_base(self):
        antes = self.dueno.get("/api/cambios", headers=AUTOMATICA).get_json()["huella"]
        with transaccion() as cur:   # dentro de la transacción de la prueba: se deshace al final
            cur.execute("UPDATE TOP (1) HORARIO SET lugar = ISNULL(lugar, '') + ' (prueba)'")
        self.assertNotEqual(antes, self.dueno.get("/api/cambios", headers=AUTOMATICA).get_json()["huella"])

    def test_la_consulta_automatica_no_mantiene_viva_la_sesion(self):
        hace_un_rato = time.time() - 60
        with self.dueno.session_transaction() as s:
            s["ultima_actividad"] = hace_un_rato
        self.assertEqual(self.dueno.get("/api/cambios", headers=AUTOMATICA).status_code, 200)
        with self.dueno.session_transaction() as s:
            self.assertEqual(s["ultima_actividad"], hace_un_rato,
                             "revisar si hay cambios no cuenta como actividad: la sesión igual se cierra a los 30 min")

    def test_la_pagina_nace_con_su_huella(self):
        html = self.dueno.get("/").get_data(as_text=True)
        self.assertIn('data-huella="', html)
        self.assertIn('data-url-cambios="/api/cambios"', html)

    def test_sin_sesion_no_responde(self):
        from app import app
        r = app.test_client().get("/api/cambios")
        self.assertEqual(r.status_code, 302)


if __name__ == "__main__":
    unittest.main()
