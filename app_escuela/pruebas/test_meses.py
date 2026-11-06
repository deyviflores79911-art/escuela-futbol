"""
Varios meses de una vez, pago adelantado, "No vino" ese mes y cambio de grupo por edad.
Contra la base REAL; lo que se escribe se deshace al final.
"""
import re
import unittest
from datetime import date

from datos import alumnos, bd, pagos
from datos.bd import consultar, consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace
from pruebas.test_etapa2 import texto


class PruebasMeses(PruebaConBaseQueSeDeshace):
    def alumno_al_dia(self):
        """Un alumno inscrito, sin beca completa, al que se le borran las deudas sin pagos (dentro de la prueba)."""
        a = consultar_uno("""SELECT TOP 1 a.id_alumno FROM ALUMNO a JOIN INSCRIPCION i ON i.id_alumno = a.id_alumno
            JOIN GRUPO g ON g.id_grupo = i.id_grupo
            WHERE a.estado = 'ACTIVO' AND i.estado = 'ACTIVA' AND g.estado = 'ACTIVO' AND a.porcentaje_beca < 100
              AND g.precio_mensual > 0 ORDER BY a.id_alumno""")
        with bd.transaccion() as cur:
            cur.execute("""DELETE m FROM MENSUALIDAD m JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
                WHERE i.id_alumno = ? AND NOT EXISTS (SELECT 1 FROM PAGO p WHERE p.id_mensualidad = m.id_mensualidad)""",
                        (a["id_alumno"],))
            cur.execute(f"""UPDATE m SET monto = {pagos.PAGADO_SQL} FROM MENSUALIDAD m
                JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion WHERE i.id_alumno = ?""", (a["id_alumno"],))
        return a["id_alumno"]

    def formulario(self, url):
        html = self.dueno.get(url).get_data(as_text=True)
        return html, {"csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', html).group(1),
                      "clave_cobro": re.search(r'name="clave_cobro" value="([^"]+)"', html).group(1),
                      "id_metodo_pago": 1, "fecha_pago": date.today().isoformat()}

    def test_pagar_tres_meses_adelantado_un_solo_recibo(self):
        id_alumno = self.alumno_al_dia()
        url = f"/caja/alumnos/{id_alumno}/adelantar"
        html, datos = self.formulario(url)
        self.assertIn('<option value="3"', html)
        plan = pagos.plan_de_meses(id_alumno, 3)
        self.assertTrue(all(x["id_mensualidad"] is None for x in plan), "son meses que todavía no existen")
        r = self.dueno.post(url, data=dict(datos, meses=3, monto="1"))   # el monto se ignora: se cobran los 3 completos
        self.assertEqual(r.status_code, 302, texto(r))
        recibo = self.dueno.get(r.headers["Location"]).get_data(as_text=True)
        for x in plan:
            self.assertIn(f"Mensualidad {x['periodo']}", recibo)
        self.assertIn(f"{sum(x['saldo'] for x in plan):.2f}".replace(".", ","), recibo)
        self.assertEqual(pagos.primera_con_saldo([id_alumno]), {}, "no debe nada")
        # El mes en curso no se vuelve a crear
        self.assertEqual(pagos.generar_mensualidades(plan[0]["periodo"], *pagos.fechas_propuestas(plan[0]["periodo"]))[0] >= 0, True)
        n = consultar_uno("""SELECT COUNT(*) AS n FROM MENSUALIDAD m JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
                             WHERE i.id_alumno = ? AND m.periodo = ?""", (id_alumno, plan[0]["periodo"]))["n"]
        self.assertEqual(n, 1)
        # Anular el recibo anula los 3 meses
        id_pago = int(r.headers["Location"].split("/pagos/")[1].split("/")[0])
        html = self.dueno.get(f"/pagos/{id_pago}/recibo").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        self.dueno.post(f"/pagos/{id_pago}/anular", data={"csrf_token": token, "motivo": "prueba de anulación"})
        self.assertEqual(len(pagos.plan_de_meses(id_alumno, 3)), 3)
        self.assertTrue(all(x["id_mensualidad"] for x in pagos.plan_de_meses(id_alumno, 3)), "vuelven a deberse")

    def test_cobrar_lo_que_debe_y_un_mes_mas(self):
        id_alumno = self.alumno_al_dia()
        periodo = pagos.periodo_actual()
        plan = pagos.plan_de_meses(id_alumno, 2)
        # crea el mes en curso como deuda y cobra 2: el que debe + el siguiente
        with bd.transaccion() as cur:
            x = plan[0]
            cur.execute("INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado) "
                        "OUTPUT INSERTED.id_mensualidad VALUES (?, ?, ?, ?, ?, 'PENDIENTE')",
                        (x["id_inscripcion"], x["periodo"], x["emision"], x["vence"], x["saldo"]))
            id_m = cur.fetchone()[0]
        html, datos = self.formulario(f"/caja/mensualidades/{id_m}/cobrar")
        self.assertIn('<option value="2"', html)
        self.assertIn("debe 1 + 1 adelantado", html)
        r = self.dueno.post(f"/caja/mensualidades/{id_m}/cobrar", data=dict(datos, meses=2))
        self.assertEqual(r.status_code, 302)
        pagados = consultar("""SELECT m.periodo FROM PAGO p JOIN MENSUALIDAD m ON m.id_mensualidad = p.id_mensualidad
            JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion WHERE i.id_alumno = ? AND m.periodo >= ?""",
                            (id_alumno, periodo))
        self.assertEqual(sorted(f["periodo"] for f in pagados), [periodo, pagos.siguiente_periodo(periodo)])

    def test_no_vino_no_se_cobra_y_se_puede_deshacer(self):
        id_alumno = self.alumno_al_dia()
        plan = pagos.plan_de_meses(id_alumno, 1)[0]
        with bd.transaccion() as cur:
            cur.execute("INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado) "
                        "OUTPUT INSERTED.id_mensualidad VALUES (?, ?, ?, ?, ?, 'PENDIENTE')",
                        (plan["id_inscripcion"], plan["periodo"], plan["emision"], plan["vence"], plan["saldo"]))
            id_m = cur.fetchone()[0]
        cuenta = self.dueno.get(f"/caja/alumnos/{id_alumno}").get_data(as_text=True)
        self.assertIn(f"/caja/mensualidades/{id_m}/no-vino", cuenta)
        token = re.search(r'name="csrf_token" value="([^"]+)"', cuenta).group(1)
        self.dueno.post(f"/caja/mensualidades/{id_m}/no-vino", data={"csrf_token": token})
        self.assertEqual(pagos.primera_con_saldo([id_alumno]), {}, "ese mes no se cobra")
        self.assertIn("No vino", texto(self.dueno.get(f"/caja/alumnos/{id_alumno}")))
        self.assertEqual(pagos.generar_mensualidades(plan["periodo"], *pagos.fechas_propuestas(plan["periodo"]))[0] >= 0, True)
        self.assertEqual(pagos.primera_con_saldo([id_alumno]), {}, "el mes automático no lo vuelve a crear")
        alumnos.cambiar_beca(id_alumno, 10, "2000-01")
        self.assertEqual(pagos.primera_con_saldo([id_alumno]), {}, "una beca nueva no lo vuelve a cobrar")
        self.dueno.post(f"/caja/mensualidades/{id_m}/cobrar-igual", data={"csrf_token": token})
        self.assertEqual(pagos.primera_con_saldo([id_alumno])[id_alumno]["id_mensualidad"], id_m)

    def test_no_vino_no_se_puede_si_ya_pago_algo(self):
        m = consultar_uno("""SELECT TOP 1 p.id_mensualidad FROM PAGO p JOIN ESTADO_PAGO e ON e.id_estado_pago = p.id_estado_pago
                             WHERE e.nombre <> 'Anulado'""")
        with self.assertRaises(bd.ErrorDatos):
            pagos.marcar_no_vino(m["id_mensualidad"])

    def test_pasa_solo_al_grupo_de_su_edad(self):
        a = consultar_uno("""SELECT TOP 1 a.id_alumno, a.fecha_nacimiento, c.edad_maxima, i.id_grupo FROM ALUMNO a
            JOIN INSCRIPCION i ON i.id_alumno = a.id_alumno AND i.estado = 'ACTIVA'
            JOIN GRUPO g ON g.id_grupo = i.id_grupo JOIN CATEGORIA c ON c.id_categoria = g.id_categoria
            WHERE a.estado = 'ACTIVO' AND EXISTS (SELECT 1 FROM GRUPO g2 JOIN CATEGORIA c2 ON c2.id_categoria = g2.id_categoria
                  WHERE g2.estado = 'ACTIVO' AND c2.edad_minima = c.edad_maxima + 1)""")
        if not a:
            self.skipTest("No hay una categoría siguiente.")
        hoy = date.today()
        with bd.transaccion() as cur:   # ahora tiene un año más que el máximo de su categoría
            cur.execute("UPDATE ALUMNO SET fecha_nacimiento = ? WHERE id_alumno = ?",
                        (date(hoy.year - a["edad_maxima"] - 1, 1, 1), a["id_alumno"]))
            cur.execute("UPDATE GRUPO SET cupo_maximo = cupo_maximo + 50")   # que haya cupo
        alumnos._edades_listas = None
        grupo, _ = alumnos.grupo_para_edad(date(hoy.year - a["edad_maxima"] - 1, 1, 1))
        if not grupo:
            self.skipTest("La categoría siguiente no tiene cupo.")
        alumnos.mover_por_edad()
        ahora = consultar_uno("SELECT id_grupo FROM INSCRIPCION WHERE id_alumno = ? AND estado = 'ACTIVA'", (a["id_alumno"],))
        self.assertNotEqual(ahora["id_grupo"], a["id_grupo"])
        self.assertIn(a["id_alumno"], [c["id_alumno"] for c in alumnos.cambios_de_grupo()])
        self.assertIn("Cambio", texto(self.dueno.get("/notificaciones")))


if __name__ == "__main__":
    unittest.main()
