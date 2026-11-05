"""
Pantalla Horarios: el dueño pone la semana de varios grupos a la vez y maneja los lugares.
Lo que se escribe en la base se deshace al final; lugares.json se usa en una copia temporal.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import config
from datos import catalogos, lugares
from datos.bd import ErrorDatos, consultar, consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace, cliente_como, enviar
from pruebas.test_etapa2 import texto

PALMAR = "Cancha de prueba Palmar"
HURACAN = "Club de prueba Huracán"


class PruebasHorarios(PruebaConBaseQueSeDeshace):
    def setUp(self):
        super().setUp()
        self.original = config.ARCHIVO_LUGARES
        self.carpeta_lugares = Path(tempfile.mkdtemp())
        config.ARCHIVO_LUGARES = self.carpeta_lugares / "lugares.json"
        config.ARCHIVO_LUGARES.write_text(json.dumps({PALMAR: "https://maps.app.goo.gl/abc", HURACAN: "https://maps.app.goo.gl/xyz"},
                                                     ensure_ascii=False), encoding="utf-8")
        self.grupos = [g["id_grupo"] for g in consultar("SELECT TOP 2 id_grupo FROM GRUPO WHERE estado = 'ACTIVO' ORDER BY id_grupo")]

    def tearDown(self):
        config.ARCHIVO_LUGARES = self.original
        shutil.rmtree(self.carpeta_lugares, ignore_errors=True)
        super().tearDown()

    def activos(self, id_grupo):
        return {h["dia_semana"]: h["lugar"] for h in consultar(
            "SELECT dia_semana, lugar FROM HORARIO WHERE id_grupo = ? AND estado = 'ACTIVO'", (id_grupo,))}

    def poner(self, dias, lugar, grupos=None, **extra):
        datos = {"accion": "poner", "dias": dias, "hora_inicio": "17:00", "hora_fin": "18:30", "lugar": lugar,
                 "grupos": [str(g) for g in (grupos or self.grupos)], **extra}
        return enviar(self.dueno, "/horarios", datos)

    def test_semana_en_dos_partes_para_varios_grupos(self):
        r = self.poner(["Lunes", "Miercoles", "Viernes"], PALMAR)
        self.assertEqual(r.status_code, 302, texto(r)[:300])
        r = self.poner(["Martes", "Jueves"], HURACAN)
        self.assertIn("Horario guardado", texto(self.dueno.get(r.headers["Location"])))
        for g in self.grupos:
            self.assertEqual(self.activos(g), {"Lunes": PALMAR, "Miercoles": PALMAR, "Viernes": PALMAR,
                                               "Martes": HURACAN, "Jueves": HURACAN})

    def test_repetir_un_dia_lo_reemplaza_sin_borrar(self):
        g = self.grupos[0]
        antes = self.contar("HORARIO WHERE id_grupo = ?", (g,))
        self.poner(["Lunes"], PALMAR, grupos=[g])
        self.poner(["Lunes"], HURACAN, grupos=[g])
        self.assertEqual(self.activos(g).get("Lunes"), HURACAN)
        self.assertEqual(self.contar("HORARIO WHERE id_grupo = ? AND estado = 'ACTIVO' AND dia_semana = 'Lunes'", (g,)), 1)
        self.assertEqual(self.contar("HORARIO WHERE id_grupo = ?", (g,)), antes + 2, "los anteriores no se borran")

    def test_quitar_un_dia(self):
        g = self.grupos[0]
        self.poner(["Sabado"], PALMAR, grupos=[g])
        r = enviar(self.dueno, "/horarios", {"accion": "quitar", "dias": ["Sabado"], "grupos": [str(g)]})
        self.assertIn("Se quitaron", texto(self.dueno.get(r.headers["Location"])))
        self.assertNotIn("Sabado", self.activos(g))

    def test_validaciones(self):
        t = texto(self.poner([], PALMAR))
        self.assertIn("Elige al menos un día", t)
        t = texto(self.poner(["Lunes"], PALMAR, grupos=[999999]))
        self.assertIn("Elige al menos un grupo", t)
        t = texto(self.poner(["Lunes"], PALMAR, hora_inicio="18:00", hora_fin="17:00"))
        self.assertIn("La hora de fin debe ser posterior", texto(self.dueno.get("/horarios")) + t)
        t = texto(self.poner(["Lunes"], "Lugar que no existe"))
        self.assertIn("Elige un lugar de la lista", t)
        with self.assertRaises(ErrorDatos):
            catalogos.aplicar_horario(self.grupos, ["Feriado"])

    def test_lugar_nuevo_con_enlace_y_quitarlo(self):
        g = self.grupos[0]
        r = self.poner(["Domingo"], "__nuevo__", grupos=[g], lugar_nuevo="Cancha nueva de prueba",
                       enlace_nuevo="https://maps.app.goo.gl/nuevo")
        self.assertEqual(r.status_code, 302, texto(r)[:300])
        self.assertEqual(lugares.enlace("Cancha nueva de prueba"), "https://maps.app.goo.gl/nuevo")
        self.assertEqual(self.activos(g).get("Domingo"), "Cancha nueva de prueba")
        enviar(self.dueno, "/lugares/quitar", {"nombre": "Cancha nueva de prueba"}, desde="/horarios")
        self.assertIsNone(lugares.enlace("Cancha nueva de prueba"))
        self.assertEqual(self.activos(g).get("Domingo"), "Cancha nueva de prueba", "el horario no cambia")

    def test_solo_enlaces_de_google_maps(self):
        for malo in ("http://maps.app.goo.gl/x", "https://sitio-raro.com/maps", "javascript:alert(1)", "https://www.google.com/search"):
            with self.assertRaises(ErrorDatos, msg=malo):
                lugares.guardar("Lugar", malo)
        lugares.guardar("Lugar", "https://www.google.com/maps/place/x")

    def test_mi_grupo_muestra_como_llegar(self):
        e = consultar_uno("SELECT TOP 1 u.id_usuario, en.id_entrenador FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol "
                          "JOIN ENTRENADOR en ON LOWER(en.correo) = LOWER(u.correo) JOIN GRUPO g ON g.id_entrenador = en.id_entrenador "
                          "WHERE r.nombre = 'Entrenador' AND u.estado = 'ACTIVO' AND g.estado = 'ACTIVO'")
        id_grupo = consultar_uno("SELECT TOP 1 id_grupo FROM GRUPO WHERE id_entrenador = ? AND estado = 'ACTIVO'",
                                 (e["id_entrenador"],))["id_grupo"]
        self.poner(["Lunes"], PALMAR, grupos=[id_grupo])
        html = cliente_como(e["id_usuario"], "ENTRENADOR").get("/mi-grupo").get_data(as_text=True)
        self.assertIn("https://maps.app.goo.gl/abc", html)
        self.assertIn("Cómo llegar", html)

    def test_solo_el_dueno(self):
        e = consultar_uno("SELECT TOP 1 u.id_usuario FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol "
                          "WHERE r.nombre = 'Entrenador' AND u.estado = 'ACTIVO'")
        entrenador = cliente_como(e["id_usuario"], "ENTRENADOR")
        self.assertEqual(entrenador.get("/horarios").status_code, 403)
        self.assertEqual(enviar(entrenador, "/lugares/nuevo", {"nombre": "X", "enlace": "https://maps.app.goo.gl/x"}, desde="/").status_code, 403)


if __name__ == "__main__":
    unittest.main()
