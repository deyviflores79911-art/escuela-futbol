"""
Flujos principales del celular: inscribir en un solo paso, cobrar directo y el inicio con lo importante adelante.
Lo que se escribe en la base se deshace al final.
"""
import unittest
from datetime import date

from datos.bd import consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace, cliente_como, enviar
from pruebas.test_etapa2 import PruebasEtapa2, texto


class PruebasFlujosCelular(PruebaConBaseQueSeDeshace):
    crear_categoria = PruebasEtapa2.crear_categoria
    crear_grupo = PruebasEtapa2.crear_grupo

    def alumno_nuevo(self, codigo, nacimiento, id_grupo):
        return enviar(self.dueno, "/alumnos/nuevo", {
            "codigo": codigo, "nombres": "Niño", "apellidos": "De Prueba", "fecha_nacimiento": nacimiento,
            "sexo": "M", "direccion": "", "id_tutor": 1, "id_grupo": str(id_grupo)})

    def test_inscribir_en_un_solo_paso(self):
        id_grupo = self.crear_grupo(cupo=5, id_categoria=self.crear_categoria("Prueba Sub-90", 9, 10))
        nacimiento = date(date.today().year - 10, 1, 1).isoformat()
        r = self.alumno_nuevo("P-UNPASO", nacimiento, id_grupo)
        self.assertEqual(r.status_code, 302, texto(r)[:300])
        self.assertIn("e inscrito en Grupo de prueba", texto(self.dueno.get(r.headers["Location"])))
        a = consultar_uno("SELECT id_alumno FROM ALUMNO WHERE codigo = 'P-UNPASO'")
        self.assertEqual(self.contar("INSCRIPCION WHERE id_alumno = ? AND id_grupo = ? AND estado = 'ACTIVA'",
                                     (a["id_alumno"], id_grupo)), 1)

    def test_si_la_edad_no_cabe_no_queda_ni_el_alumno(self):
        id_grupo = self.crear_grupo(cupo=5, id_categoria=self.crear_categoria("Prueba Sub-91", 6, 8))
        nacimiento = date(date.today().year - 14, 1, 1).isoformat()
        r = self.alumno_nuevo("P-NOCABE", nacimiento, id_grupo)
        self.assertIn("tiene 14 años", texto(r))
        self.assertEqual(self.contar("ALUMNO WHERE codigo = 'P-NOCABE'"), 0, "todo o nada: el alumno tampoco se crea")

    def test_alumno_nuevo_pide_grupo_o_despues(self):
        r = enviar(self.dueno, "/alumnos/nuevo", {
            "codigo": "P-SINGRUPO", "nombres": "A", "apellidos": "B", "fecha_nacimiento": "2016-01-01",
            "sexo": "F", "direccion": "", "id_tutor": 1})
        self.assertIn("Elige el grupo donde entrenará", texto(r))

    def test_cobrar_directo_desde_la_busqueda(self):
        deudor = consultar_uno("""SELECT TOP 1 a.codigo FROM ALUMNO a JOIN INSCRIPCION i ON i.id_alumno = a.id_alumno
                                   JOIN MENSUALIDAD m ON m.id_inscripcion = i.id_inscripcion
                                   WHERE m.monto > (SELECT ISNULL(SUM(p.monto), 0) FROM PAGO p
                                                    WHERE p.id_mensualidad = m.id_mensualidad AND p.id_estado_pago <> 3)""")
        html = self.dueno.get("/caja", query_string={"q": deudor["codigo"]}).get_data(as_text=True)
        self.assertIn("/cobrar", html)
        self.assertIn("Cobrar ", html)

    def test_inicio_con_lo_importante_adelante(self):
        t = texto(self.dueno.get("/"))
        for esperado in ("Cobrar", "Inscribir", "Deudores", "Cobrado hoy"):
            self.assertIn(esperado, t)
        self.assertNotIn("Análisis de datos", t, "la app ya no tiene la parte de análisis")
        self.assertEqual(self.dueno.get("/inscribir").status_code, 200)

    def test_entrenador_ve_su_inicio_sin_caja(self):
        e = consultar_uno("SELECT TOP 1 u.id_usuario FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol "
                          "WHERE r.nombre = 'Entrenador' AND u.estado = 'ACTIVO'")
        c = cliente_como(e["id_usuario"], "ENTRENADOR")
        t = texto(c.get("/"))
        self.assertIn("Mi grupo", t)
        self.assertNotIn("Cobrado hoy", t)
        self.assertEqual(c.get("/inscribir").status_code, 403)


if __name__ == "__main__":
    unittest.main()
