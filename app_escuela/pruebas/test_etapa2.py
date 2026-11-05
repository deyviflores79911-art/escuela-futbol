"""
Etapa 2: categorías, grupos, horarios, tutores, alumnos e inscripciones.
Se prueba contra la base REAL dentro de una transacción que se deshace al final: no queda ninguna fila.
Ejecutar desde app_escuela:   python -m unittest discover -s pruebas -t .
"""
import html
import re
import unittest
from datetime import date, timedelta

from datos.bd import consultar, consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace, cliente_como, enviar

HOY = date.today().isoformat()


def texto(respuesta):
    """Lo que lee una persona en la página: sin etiquetas HTML y con los espacios normalizados."""
    sin_etiquetas = re.sub(r"<[^>]+>", " ", respuesta.get_data(as_text=True))
    return " ".join(html.unescape(sin_etiquetas).split())


class PruebasEtapa2(PruebaConBaseQueSeDeshace):
    # --------------------------------------------------------------- ayudas para crear datos

    def crear_categoria(self, nombre="Prueba Sub-99", minima=9, maxima=10):
        r = enviar(self.dueno, "/categorias/nueva", {"nombre": nombre, "edad_minima": minima, "edad_maxima": maxima})
        self.assertEqual(r.status_code, 302, texto(r)[:300])
        return consultar_uno("SELECT id_categoria FROM CATEGORIA WHERE nombre = ?", (nombre,))["id_categoria"]

    def crear_grupo(self, nombre="Grupo de prueba", cupo=2, precio="210.50", id_categoria=None):
        id_categoria = id_categoria or self.crear_categoria()
        r = enviar(self.dueno, "/grupos/nuevo", {"nombre": nombre, "id_categoria": id_categoria, "id_entrenador": 1,
                                                 "cupo_maximo": cupo, "precio_mensual": precio})
        self.assertEqual(r.status_code, 302, texto(r)[:300])
        return consultar_uno("SELECT id_grupo FROM GRUPO WHERE nombre = ?", (nombre,))["id_grupo"]

    def crear_alumno(self, codigo="PRUEBA-001", nombres="Ana", apellidos="Prueba Test", id_tutor=1, **extra):
        datos = {"codigo": codigo, "nombres": nombres, "apellidos": apellidos, "fecha_nacimiento": "2016-05-20",
                 "sexo": "F", "direccion": "", "id_tutor": id_tutor, "id_grupo": "despues", **extra}
        r = enviar(self.dueno, "/alumnos/nuevo", datos)
        return r, consultar_uno("SELECT id_alumno FROM ALUMNO WHERE codigo = ?", (codigo.upper(),))

    def inscribir(self, id_alumno, id_grupo):
        return enviar(self.dueno, f"/alumnos/{id_alumno}/inscribir",
                      {"id_grupo": id_grupo, "fecha_inscripcion": HOY}, desde=f"/alumnos/{id_alumno}")

    # --------------------------------------------------------------- categorías (CU-03)

    def test_categoria_crear_repetir_y_validar(self):
        self.crear_categoria("Prueba Sub-99")
        r = enviar(self.dueno, "/categorias/nueva", {"nombre": "prueba sub-99", "edad_minima": 5, "edad_maxima": 6})
        self.assertIn("Ya existe una categoría", texto(self.dueno.get("/categorias")) + texto(r))
        r = enviar(self.dueno, "/categorias/nueva", {"nombre": "Otra", "edad_minima": 12, "edad_maxima": 9})
        self.assertIn("La edad mínima no puede ser mayor", texto(r))
        r = enviar(self.dueno, "/categorias/nueva", {"nombre": "", "edad_minima": "x", "edad_maxima": ""})
        self.assertIn("El nombre es obligatorio", texto(r))
        self.assertIn("debe ser un número entero", texto(r))

    def test_categoria_con_grupos_no_se_desactiva(self):
        id_categoria = self.crear_categoria()
        self.crear_grupo(id_categoria=id_categoria)
        r = enviar(self.dueno, f"/categorias/{id_categoria}/estado", {}, desde="/categorias")
        self.assertIn("tiene 1 grupo(s) activo(s)", texto(self.dueno.get(r.headers["Location"])))
        fila = consultar_uno("SELECT estado FROM CATEGORIA WHERE id_categoria = ?", (id_categoria,))
        self.assertEqual(fila["estado"], "ACTIVA")

    # --------------------------------------------------------------- grupos (HU-03)

    def test_grupo_sin_precio_ni_cupo_validos_no_se_guarda(self):
        id_categoria = self.crear_categoria()
        antes = self.contar("GRUPO")
        for cupo, precio, mensaje in [("0", "200", "El cupo máximo debe estar entre 1 y 200"),
                                      ("", "200", "El cupo máximo es obligatorio"),
                                      ("10", "", "El precio mensual es obligatorio"),
                                      ("10", "-5", "El precio mensual debe ser mayor a cero"),
                                      ("10", "abc", "El precio mensual debe ser un número")]:
            r = enviar(self.dueno, "/grupos/nuevo", {"nombre": "Grupo malo", "id_categoria": id_categoria,
                                                     "id_entrenador": 1, "cupo_maximo": cupo, "precio_mensual": precio})
            self.assertEqual(r.status_code, 200)
            self.assertIn(mensaje, texto(r))
        self.assertEqual(self.contar("GRUPO"), antes, "ningún grupo inválido debe guardarse")

    def test_grupo_muestra_inscritos_y_cupos_libres(self):
        id_grupo = self.crear_grupo(cupo=3, precio="210,50")
        g = consultar_uno("SELECT cupo_maximo, precio_mensual FROM GRUPO WHERE id_grupo = ?", (id_grupo,))
        self.assertEqual((g["cupo_maximo"], str(g["precio_mensual"])), (3, "210.50"), "acepta coma decimal")
        _, a = self.crear_alumno()
        self.inscribir(a["id_alumno"], id_grupo)
        ficha = texto(self.dueno.get(f"/grupos/{id_grupo}"))
        self.assertIn("1 / 3", ficha)
        self.assertIn("2 cupos libres", ficha)

    def test_lista_de_grupos_coincide_con_la_base(self):
        pagina = texto(self.dueno.get("/grupos"))
        for g in consultar("SELECT g.nombre, g.cupo_maximo, (SELECT COUNT(*) FROM INSCRIPCION i WHERE i.id_grupo = g.id_grupo "
                           "AND i.estado = 'ACTIVA') AS inscritos FROM GRUPO g WHERE g.estado = 'ACTIVO'"):
            self.assertIn(f"{g['inscritos']} de {g['cupo_maximo']} cupos ocupados", pagina, g["nombre"])

    def test_cupo_no_baja_de_los_inscritos_y_grupo_con_alumnos_no_se_desactiva(self):
        id_grupo = self.crear_grupo(cupo=2)
        _, a = self.crear_alumno()
        self.inscribir(a["id_alumno"], id_grupo)
        _, b = self.crear_alumno("PRUEBA-002", "Beto")
        self.inscribir(b["id_alumno"], id_grupo)
        id_categoria = consultar_uno("SELECT id_categoria FROM GRUPO WHERE id_grupo = ?", (id_grupo,))["id_categoria"]
        r = enviar(self.dueno, f"/grupos/{id_grupo}/editar", {"nombre": "Grupo de prueba", "id_categoria": id_categoria,
                                                              "id_entrenador": 1, "cupo_maximo": 1, "precio_mensual": "200"})
        self.assertIn("no puede ser menor que los 2 alumnos inscritos", texto(r))
        r = enviar(self.dueno, f"/grupos/{id_grupo}/estado", {}, desde=f"/grupos/{id_grupo}")
        self.assertIn("tiene 2 alumno(s) inscrito(s)", texto(self.dueno.get(r.headers["Location"])))

    # --------------------------------------------------------------- horarios (RF-07)

    def test_horarios(self):
        id_grupo = self.crear_grupo()
        url = f"/grupos/{id_grupo}/horarios/nuevo"
        r = enviar(self.dueno, url, {"dia_semana": "Miercoles", "hora_inicio": "17:00", "hora_fin": "16:00", "lugar": ""})
        self.assertIn("La hora de fin debe ser posterior", texto(r))
        r = enviar(self.dueno, url, {"dia_semana": "Feriado", "hora_inicio": "16:00", "hora_fin": "17:00", "lugar": ""})
        self.assertIn("no es válido", texto(r), "un día inventado en el formulario se rechaza")
        r = enviar(self.dueno, url, {"dia_semana": "Miercoles", "hora_inicio": "16:00", "hora_fin": "17:30", "lugar": "Cancha 9"})
        self.assertEqual(r.status_code, 302)
        h = consultar_uno("SELECT * FROM HORARIO WHERE id_grupo = ?", (id_grupo,))
        self.assertEqual(h["dia_semana"], "Miercoles", "se guarda como el resto de la base (sin tilde)")
        self.assertIn("Miércoles", texto(self.dueno.get(f"/grupos/{id_grupo}")), "se muestra con tilde")

    # --------------------------------------------------------------- tutores y alumnos (HU-04)

    def test_alumno_campos_obligatorios_y_fecha_futura(self):
        manana = (date.today() + timedelta(days=1)).isoformat()
        r = enviar(self.dueno, "/alumnos/nuevo", {"codigo": "", "nombres": "", "apellidos": "", "fecha_nacimiento": manana,
                                                  "sexo": "X", "id_tutor": ""})
        t = texto(r)
        for mensaje in ("El código es obligatorio", "El nombre es obligatorio", "El apellido es obligatorio",
                        "no puede ser futura", "El sexo no es válido", "Elige el tutor"):
            self.assertIn(mensaje, t)

    def test_codigo_no_se_repite(self):
        r, _ = self.crear_alumno(codigo="al-001")  # AL-001 ya existe (en minúsculas también cuenta)
        self.assertIn("El código AL-001 ya lo tiene", texto(r))

    def test_alumno_con_tutor_nuevo_en_una_sola_transaccion(self):
        tutores = self.contar("TUTOR")
        nuevo = {"id_tutor": "nuevo", "tutor_nombres": "Rosa", "tutor_apellidos": "Tutora Prueba", "tutor_ci": "99887766",
                 "tutor_telefono": "70000001", "tutor_whatsapp": "70000001", "tutor_correo": "", "tutor_direccion": ""}
        # Si el alumno falla (código repetido), tampoco debe quedar el tutor
        r, _ = self.crear_alumno(codigo="AL-001", **nuevo)
        self.assertIn("ya lo tiene", texto(r))
        self.assertEqual(self.contar("TUTOR"), tutores, "no debe quedar un tutor a medias")
        r, a = self.crear_alumno(codigo="PRUEBA-010", **nuevo)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.contar("TUTOR"), tutores + 1)
        tutor = consultar_uno("SELECT t.ci FROM ALUMNO a JOIN TUTOR t ON t.id_tutor = a.id_tutor WHERE a.id_alumno = ?",
                              (a["id_alumno"],))
        self.assertEqual(tutor["ci"], "99887766")

    def test_ci_de_tutor_no_se_repite(self):
        r = enviar(self.dueno, "/tutores/nuevo", {"nombres": "X", "apellidos": "Y", "ci": "4500001"})
        self.assertIn("ya está registrado para el tutor", texto(r))

    def test_busqueda_por_nombre_apellido_codigo_y_tutor(self):
        self.crear_alumno(codigo="PRUEBA-777", nombres="Zacarías", apellidos="Buscable Únicoz", id_tutor=1)
        tutor = consultar_uno("SELECT nombres, ci FROM TUTOR WHERE id_tutor = 1")
        for q in ("Zacarías", "Únicoz", "prueba-777", "Zacarías Buscable", tutor["ci"], tutor["nombres"]):
            self.assertIn("PRUEBA-777", texto(self.dueno.get("/alumnos", query_string={"q": q})), q)
        self.assertNotIn("PRUEBA-777", texto(self.dueno.get("/alumnos", query_string={"q": "%"})), "el % no es comodín")

    # --------------------------------------------------------------- inscripciones (HU-05, HU-06)

    def test_inscribir_queda_activa_y_grupo_lleno_no_inscribe(self):
        id_grupo = self.crear_grupo(cupo=1)
        _, a = self.crear_alumno()
        r = self.inscribir(a["id_alumno"], id_grupo)
        self.assertIn("quedó ACTIVA", texto(self.dueno.get(r.headers["Location"])))
        self.assertEqual(self.contar("INSCRIPCION WHERE id_alumno = ? AND estado = 'ACTIVA'", (a["id_alumno"],)), 1)
        # Ya inscrito en ese grupo: avisa
        r = self.inscribir(a["id_alumno"], id_grupo)
        self.assertIn("ya está inscrito", texto(self.dueno.get(r.headers["Location"])))
        # Grupo lleno: avisa y no inscribe
        _, b = self.crear_alumno("PRUEBA-002", "Beto")
        r = self.inscribir(b["id_alumno"], id_grupo)
        self.assertIn("está lleno", texto(self.dueno.get(r.headers["Location"])))
        self.assertEqual(self.contar("INSCRIPCION WHERE id_alumno = ?", (b["id_alumno"],)), 0)

    def test_edad_fuera_de_la_categoria_no_inscribe(self):
        id_categoria = self.crear_categoria("Prueba Sub-98", minima=6, maxima=8)
        id_grupo = self.crear_grupo(cupo=5, id_categoria=id_categoria)
        _, a = self.crear_alumno()  # nacido en 2016: tiene 10 años
        r = self.inscribir(a["id_alumno"], id_grupo)
        self.assertIn("No se inscribió", texto(self.dueno.get(r.headers["Location"])))
        self.assertEqual(self.contar("INSCRIPCION WHERE id_alumno = ?", (a["id_alumno"],)), 0)

    def _nacido_hace(self, anios, dias_mas=0):
        hoy = date.today()
        return (hoy.replace(year=hoy.year - anios) - timedelta(days=dias_mas)).isoformat()

    def test_regla_de_edad_en_sub8_limites_y_mensaje(self):
        """Sub-8 con el rango que tiene en la base: 6 y 8 entran (límites), 7 entra, 5 y 9 no."""
        sub8 = consultar_uno("SELECT TOP 1 g.id_grupo, c.edad_minima, c.edad_maxima FROM GRUPO g "
                             "JOIN CATEGORIA c ON c.id_categoria = g.id_categoria "
                             "WHERE c.nombre = 'Sub-8' AND g.estado = 'ACTIVO'")
        self.assertEqual((sub8["edad_minima"], sub8["edad_maxima"]), (6, 8))
        # Más cupo para que el grupo lleno no se mezcle con la regla de edad (se deshace al final)
        from datos import catalogos
        grupo = catalogos.obtener_grupo(sub8["id_grupo"])
        catalogos.guardar_grupo(sub8["id_grupo"], {**grupo, "cupo_maximo": grupo["cupo_maximo"] + 10})
        casos = [("P-E6", self._nacido_hace(6), True),            # cumple 6 hoy: límite inferior
                 ("P-E7", self._nacido_hace(7, 100), True),       # caso válido
                 ("P-E8", self._nacido_hace(9, -1), True),        # cumple 9 mañana: aún tiene 8, límite superior
                 ("P-E5", self._nacido_hace(6, -1), False),       # cumple 6 mañana: tiene 5, por debajo
                 ("P-E9", self._nacido_hace(9), False)]           # cumple 9 hoy: por encima
        for codigo, nacimiento, entra in casos:
            _, a = self.crear_alumno(codigo, fecha_nacimiento=nacimiento)
            r = self.inscribir(a["id_alumno"], sub8["id_grupo"])
            mensaje = texto(self.dueno.get(r.headers["Location"]))
            activa = self.contar("INSCRIPCION WHERE id_alumno = ? AND estado = 'ACTIVA'", (a["id_alumno"],))
            self.assertEqual(activa, 1 if entra else 0, f"{codigo}: {mensaje[:200]}")
            if not entra:
                self.assertIn("Sub-8 es de 6 a 8 años", mensaje)
        # El mensaje ofrece la categoría que le corresponde, también al dueño (nadie se salta la regla)
        _, joaquin = self.crear_alumno("P-E12", "Joaquín", fecha_nacimiento=self._nacido_hace(12, 30))
        r = self.inscribir(joaquin["id_alumno"], sub8["id_grupo"])
        self.assertIn("Joaquín tiene 12 años y Sub-8 es de 6 a 8 años. Elige la categoría Sub-12.",
                      texto(self.dueno.get(r.headers["Location"])))
        self.assertEqual(self.contar("INSCRIPCION WHERE id_alumno = ?", (joaquin["id_alumno"],)), 0)

    def test_regla_de_edad_al_editar_categoria_grupo_y_alumno(self):
        from datos import alumnos, catalogos
        from datos.bd import ErrorDatos
        id_categoria = self.crear_categoria("Prueba Sub-98", minima=9, maxima=10)
        id_grupo = self.crear_grupo(cupo=5, id_categoria=id_categoria)
        _, a = self.crear_alumno()  # 10 años
        self.inscribir(a["id_alumno"], id_grupo)
        self.assertEqual(self.contar("INSCRIPCION WHERE id_alumno = ? AND estado = 'ACTIVA'", (a["id_alumno"],)), 1)
        # La categoría no puede cambiar su rango dejando fuera a un inscrito
        with self.assertRaises(ErrorDatos):
            catalogos.guardar_categoria(id_categoria, "Prueba Sub-98", 6, 8)
        # El grupo no puede pasar a una categoría de otra edad
        otra = self.crear_categoria("Prueba Sub-97", minima=13, maxima=14)
        grupo = catalogos.obtener_grupo(id_grupo)
        with self.assertRaises(ErrorDatos):
            catalogos.guardar_grupo(id_grupo, {"id_categoria": otra, "id_entrenador": grupo["id_entrenador"],
                                               "nombre": grupo["nombre"], "cupo_maximo": 5, "precio_mensual": 200})
        # El alumno no puede cambiar su fecha de nacimiento a una edad que no entra en su grupo
        ficha = consultar_uno("SELECT * FROM ALUMNO WHERE id_alumno = ?", (a["id_alumno"],))
        ficha["fecha_nacimiento"] = date(ficha["fecha_nacimiento"].year - 5, 1, 1)
        with self.assertRaises(ErrorDatos):
            alumnos.guardar_alumno(a["id_alumno"], ficha)

    def test_baja_conserva_el_historial_y_libera_el_cupo(self):
        id_grupo = self.crear_grupo(cupo=1)
        _, a = self.crear_alumno()
        self.inscribir(a["id_alumno"], id_grupo)
        insc = consultar_uno("SELECT id_inscripcion FROM INSCRIPCION WHERE id_alumno = ?", (a["id_alumno"],))
        # No se puede desactivar al alumno mientras siga inscrito
        r = enviar(self.dueno, f"/alumnos/{a['id_alumno']}/estado", {}, desde=f"/alumnos/{a['id_alumno']}")
        self.assertIn("sigue inscrito", texto(self.dueno.get(r.headers["Location"])))
        r = enviar(self.dueno, f"/inscripciones/{insc['id_inscripcion']}/baja?volver=/grupos/{id_grupo}", {},
                   desde=f"/alumnos/{a['id_alumno']}")
        self.assertEqual(r.headers["Location"], f"/grupos/{id_grupo}")
        fila = consultar_uno("SELECT estado FROM INSCRIPCION WHERE id_inscripcion = ?", (insc["id_inscripcion"],))
        self.assertEqual(fila["estado"], "BAJA", "la fila se conserva con estado BAJA")
        self.assertIn("Baja", texto(self.dueno.get(f"/alumnos/{a['id_alumno']}")), "sigue visible en el historial")
        self.assertIn("1 cupo libre", texto(self.dueno.get(f"/grupos/{id_grupo}")))
        # Una baja repetida avisa en vez de fallar
        r = enviar(self.dueno, f"/inscripciones/{insc['id_inscripcion']}/baja", {}, desde=f"/alumnos/{a['id_alumno']}")
        self.assertIn("ya estaba dada de baja", texto(self.dueno.get(r.headers["Location"])))

    def test_volver_no_redirige_a_otro_sitio(self):
        id_grupo = self.crear_grupo()
        _, a = self.crear_alumno()
        self.inscribir(a["id_alumno"], id_grupo)
        insc = consultar_uno("SELECT id_inscripcion FROM INSCRIPCION WHERE id_alumno = ?", (a["id_alumno"],))
        r = enviar(self.dueno, f"/inscripciones/{insc['id_inscripcion']}/baja?volver=https://otro-sitio.com", {},
                   desde=f"/alumnos/{a['id_alumno']}")
        self.assertEqual(r.headers["Location"], f"/alumnos/{a['id_alumno']}")

    # --------------------------------------------------------------- permisos

    def test_entrenador_no_entra_ni_escribe(self):
        entrenador = consultar_uno("SELECT TOP 1 u.id_usuario FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol "
                                   "WHERE r.nombre = 'Entrenador' AND u.estado = 'ACTIVO'")
        if not entrenador:
            self.skipTest("No hay usuario entrenador activo.")
        c = cliente_como(entrenador["id_usuario"], "ENTRENADOR")
        for url in ("/grupos", "/grupos/1", "/categorias", "/alumnos", "/alumnos/1", "/tutores", "/grupos/nuevo"):
            self.assertEqual(c.get(url).status_code, 403, url)
        token = enviar.__globals__["token_csrf"](c, "/mi-clave")
        antes = self.contar("INSCRIPCION")
        r = c.post("/alumnos/1/inscribir", data={"id_grupo": 1, "fecha_inscripcion": HOY, "csrf_token": token})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.contar("INSCRIPCION"), antes)


class PruebaSinResiduos(unittest.TestCase):
    def test_las_pruebas_no_dejan_datos(self):
        for tabla, columna, patron in [("CATEGORIA", "nombre", "Prueba Sub-99"), ("GRUPO", "nombre", "Grupo de prueba"),
                                       ("ALUMNO", "codigo", "PRUEBA-%"), ("TUTOR", "ci", "99887766")]:
            n = consultar_uno(f"SELECT COUNT(*) AS n FROM {tabla} WHERE {columna} LIKE ?", (patron,))["n"]
            self.assertEqual(n, 0, f"quedó una fila de prueba en {tabla}")


if __name__ == "__main__":
    unittest.main()
