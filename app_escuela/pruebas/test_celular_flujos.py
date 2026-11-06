"""
Flujos principales del celular: inscribir en un solo paso, cobrar directo y el inicio con lo importante adelante.
Lo que se escribe en la base se deshace al final.
"""
import unittest
from datetime import date

from datos import bd
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


class PruebasAlumnoNuevoRapido(PruebaConBaseQueSeDeshace):
    """Alumno nuevo con menos pasos: el tutor se busca, y el hermano hereda apellido y dirección."""

    def nuevo(self, **cambios):
        datos = {"codigo": "P-RAPIDO", "nombres": "Mateo", "apellidos": "", "fecha_nacimiento": "2016-03-12",
                 "sexo": "M", "direccion": "", "id_tutor": "1", "id_grupo": "despues"}
        datos.update(cambios)
        return enviar(self.dueno, "/alumnos/nuevo", datos)

    def test_buscar_tutor_mientras_se_escribe(self):
        t = consultar_uno("SELECT TOP 1 t.id_tutor, t.nombres, t.ci FROM TUTOR t "
                          "WHERE t.ci IS NOT NULL AND EXISTS (SELECT 1 FROM ALUMNO a WHERE a.id_tutor = t.id_tutor "
                          "AND a.estado = 'ACTIVO') ORDER BY t.id_tutor")
        for q in (t["ci"], t["nombres"][:4]):
            encontrados = self.dueno.get("/api/tutores", query_string={"q": q}).get_json()
            elegido = [x for x in encontrados if x["id_tutor"] == t["id_tutor"]]
            self.assertTrue(elegido, q)
            self.assertTrue(elegido[0]["hijos"], "muestra los hijos que ya tiene")
        self.assertEqual(self.dueno.get("/api/tutores", query_string={"q": "a"}).get_json(), [], "mínimo 2 letras")
        e = consultar_uno("SELECT TOP 1 u.id_usuario FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol "
                          "WHERE r.nombre = 'Entrenador' AND u.estado = 'ACTIVO'")
        self.assertEqual(cliente_como(e["id_usuario"], "ENTRENADOR").get("/api/tutores?q=ana").status_code, 403)

    def test_hermano_hereda_apellido_y_direccion_del_tutor(self):
        with bd.transaccion() as cur:   # se deshace al final
            cur.execute("UPDATE TUTOR SET apellidos = 'Ticona Prueba', direccion = 'Calle Hermanos 123' WHERE id_tutor = 1")
        r = self.nuevo()
        self.assertEqual(r.status_code, 302, texto(r)[:300])
        a = consultar_uno("SELECT apellidos, direccion FROM ALUMNO WHERE codigo = 'P-RAPIDO'")
        self.assertEqual((a["apellidos"], a["direccion"]), ("Ticona Prueba", "Calle Hermanos 123"))

    def test_no_registra_dos_veces_al_mismo_nino(self):
        self.assertEqual(self.nuevo().status_code, 302)
        r = self.nuevo(codigo="P-RAPIDO2", nombres=" mateo ")
        self.assertIn("ya está registrado con este tutor", texto(r))
        self.assertEqual(self.contar("ALUMNO WHERE codigo IN ('P-RAPIDO', 'P-RAPIDO2')"), 1)

    def test_tutor_nuevo_con_tres_datos(self):
        r = self.nuevo(id_tutor="nuevo", tutor_nombres="Rosa", tutor_apellidos="Quispe Prueba", tutor_whatsapp="")
        self.assertIn("El WhatsApp es obligatorio", texto(r))
        r = self.nuevo(id_tutor="nuevo", tutor_nombres="Rosa", tutor_apellidos="Quispe Prueba", tutor_whatsapp="70011223")
        self.assertEqual(r.status_code, 302, texto(r)[:300])
        a = consultar_uno("SELECT a.apellidos, t.telefono, t.whatsapp FROM ALUMNO a JOIN TUTOR t ON t.id_tutor = a.id_tutor "
                          "WHERE a.codigo = 'P-RAPIDO'")
        self.assertEqual((a["apellidos"], a["telefono"], a["whatsapp"]), ("Quispe Prueba", "70011223", "70011223"))

    def test_formulario_con_tutor_ya_elegido(self):
        t = consultar_uno("SELECT TOP 1 t.id_tutor, t.nombres FROM TUTOR t JOIN ALUMNO a ON a.id_tutor = t.id_tutor "
                          "ORDER BY t.id_tutor")
        html = texto(self.dueno.get("/alumnos/nuevo", query_string={"id_tutor": t["id_tutor"]}))
        self.assertIn(t["nombres"], html)
        self.assertIn("Ya tiene:", html)


if __name__ == "__main__":
    unittest.main()
