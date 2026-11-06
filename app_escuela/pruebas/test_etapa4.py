"""
Etapa 4: deudores, resumen de caja y "Mi grupo" (Al día / Debe), en vivo.
Contra la base REAL; lo que se escribe va dentro de una transacción que se deshace al final.
Ejecutar desde app_escuela:   python -m unittest discover -s pruebas -t .
"""
import re
import time
from datetime import date
from decimal import Decimal

from datos import reportes
from datos.bd import consultar, consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace, cliente_como, enviar
from pruebas.test_etapa2 import texto
from pruebas.test_etapa3 import PERIODO, AyudaCaja

SQL_SALDOS = """SELECT x.id_mensualidad, x.monto - x.pagado AS adeudado, x.periodo, c.nombre AS categoria
                FROM (SELECT m.id_mensualidad, m.id_inscripcion, m.periodo, m.monto,
                             (SELECT ISNULL(SUM(p.monto), 0) FROM PAGO p WHERE p.id_mensualidad = m.id_mensualidad
                              AND p.id_estado_pago <> (SELECT id_estado_pago FROM ESTADO_PAGO WHERE nombre = 'Anulado')) AS pagado
                      FROM MENSUALIDAD m) x
                JOIN INSCRIPCION i ON i.id_inscripcion = x.id_inscripcion
                JOIN GRUPO g ON g.id_grupo = i.id_grupo JOIN CATEGORIA c ON c.id_categoria = g.id_categoria
                WHERE x.monto > x.pagado"""


class PruebasEtapa4(AyudaCaja, PruebaConBaseQueSeDeshace):
    def entrenador(self):
        e = consultar_uno("""SELECT TOP 1 u.id_usuario, en.id_entrenador FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol
                             JOIN ENTRENADOR en ON LOWER(en.correo) = LOWER(u.correo)
                             WHERE r.nombre = 'Entrenador' AND u.estado = 'ACTIVO'""")
        if not e:
            self.skipTest("No hay usuario entrenador activo enlazado a su ficha.")
        return e, cliente_como(e["id_usuario"], "ENTRENADOR")

    # --------------------------------------------------------------- deudores (RF-18, HU-11)

    def test_deudores_coinciden_con_la_base(self):
        esperado = consultar(SQL_SALDOS + " AND x.periodo = '2026-09'")
        lista = reportes.deudores("2026-09")
        self.assertEqual({d["id_mensualidad"] for d in lista}, {e["id_mensualidad"] for e in esperado})
        self.assertEqual(sum(d["adeudado"] for d in lista), sum(e["adeudado"] for e in esperado))
        t = texto(self.dueno.get("/reportes/deudores?periodo=2026-09"))
        self.assertIn(f"{len(esperado)} mensualidades con saldo", t)
        total = f"{sum(e['adeudado'] for e in esperado):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        self.assertIn(f"Bs {total} por cobrar", t)
        todas = consultar(SQL_SALDOS)
        self.assertEqual(len(reportes.deudores(None)), len(todas))

    def test_deudores_muestra_lo_pedido_y_dias_de_atraso(self):
        d = reportes.deudores("2026-09")[0]
        self.assertEqual(d["dias_atraso"], (date.today() - d["fecha_vencimiento"]).days)
        t = texto(self.dueno.get("/reportes/deudores?periodo=2026-09"))
        for dato in (d["nombres"], d["tutor"], d["contacto"], d["categoria"], f"{d['dias_atraso']} días"):
            self.assertIn(str(dato), t)

    def test_filtro_por_categoria_y_lista_vacia(self):
        cat = reportes.deudores("2026-09")[0]["categoria"]
        html = self.dueno.get(f"/reportes/deudores?periodo=2026-09&categoria={cat}").get_data(as_text=True)
        categorias = set(re.findall(r'data-categoria="(Sub-\d+)"', html))
        self.assertEqual(categorias, {cat})
        self.assertIn("Nadie debe", texto(self.dueno.get("/reportes/deudores?periodo=2026-09&categoria=Ninguna")))

    def test_al_pagar_sale_de_deudores_en_vivo(self):
        m = self.una_mensualidad()
        self.assertIn(m["id_mensualidad"], {d["id_mensualidad"] for d in reportes.deudores(PERIODO)})
        self.cobrar(m["id_mensualidad"], f"{m['monto']:.2f}")
        self.assertNotIn(m["id_mensualidad"], {d["id_mensualidad"] for d in reportes.deudores(PERIODO)})

    # --------------------------------------------------------------- resumen de caja (RF-19, HU-12)

    def test_resumen_de_caja_suma_por_metodo_sin_anulados(self):
        hoy = date.today()
        antes = reportes.resumen_caja(hoy, hoy)
        m = self.una_mensualidad()
        self.cobrar(m["id_mensualidad"], "100", metodo=2)            # Transferencia
        p1 = self.ultimo_pago()
        self.cobrar(m["id_mensualidad"], "30", metodo=3)             # QR
        p2 = self.ultimo_pago()
        enviar(self.dueno, f"/pagos/{p2['id_pago']}/anular", {"motivo": "prueba de anulación"},
               desde=f"/pagos/{p2['id_pago']}/recibo")
        r = reportes.resumen_caja(hoy, hoy)
        self.assertEqual(r["total"], antes["total"] + Decimal("100"), "el anulado no se suma")
        self.assertEqual(r["anulados"], antes["anulados"] + 1)
        transfer = next(x for x in r["por_metodo"] if x["metodo"] == "Transferencia")
        transfer_antes = next(x for x in antes["por_metodo"] if x["metodo"] == "Transferencia")
        self.assertEqual(transfer["total"], transfer_antes["total"] + Decimal("100"))
        self.assertEqual(sum(x["total"] for x in r["por_metodo"]), r["total"])
        api = self.dueno.get(f"/api/reportes/caja?desde={hoy}&hasta={hoy}").get_json()
        self.assertAlmostEqual(api["total"], float(r["total"]), places=2)
        t = texto(self.dueno.get(f"/reportes/caja?desde={hoy}&hasta={hoy}"))
        self.assertIn(p1["numero_recibo"], t)
        self.assertIn("no se suma", t)

    def test_resumen_de_un_mes_coincide_con_sql(self):
        fila = consultar_uno("""SELECT COUNT(*) AS n, SUM(p.monto) AS total FROM PAGO p JOIN ESTADO_PAGO e
                                ON e.id_estado_pago = p.id_estado_pago
                                WHERE p.fecha_pago BETWEEN '2026-09-01' AND '2026-09-30' AND e.nombre <> 'Anulado'""")
        r = reportes.resumen_caja(date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual((r["cantidad"], r["total"]), (fila["n"], fila["total"]))

    # --------------------------------------------------------------- mi grupo (RF-20, RF-21, HU-13, HU-14)

    def test_entrenador_ve_solo_su_grupo_con_al_dia_o_debe(self):
        e, c = self.entrenador()
        suyos = {f["id_alumno"] for f in consultar(
            "SELECT i.id_alumno FROM INSCRIPCION i JOIN GRUPO g ON g.id_grupo = i.id_grupo "
            "WHERE i.estado = 'ACTIVA' AND g.estado = 'ACTIVO' AND g.id_entrenador = ?", (e["id_entrenador"],))}
        self.assertTrue(suyos)
        grupos = reportes.mi_grupo(e["id_entrenador"])
        self.assertEqual({a["id_alumno"] for g in grupos for a in g["alumnos"]}, suyos)
        # "Debe" = saldo en alguna mensualidad vencida (misma regla calculada en SQL)
        deben = {f["id_alumno"] for f in consultar(
            """SELECT DISTINCT i.id_alumno FROM MENSUALIDAD m JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
               JOIN GRUPO g ON g.id_grupo = i.id_grupo
               WHERE g.id_entrenador = ? AND i.estado = 'ACTIVA' AND m.fecha_vencimiento < CAST(GETDATE() AS date)
                 AND m.monto > (SELECT ISNULL(SUM(p.monto), 0) FROM PAGO p WHERE p.id_mensualidad = m.id_mensualidad
                                AND p.id_estado_pago <> 3)""", (e["id_entrenador"],))}
        self.assertEqual({a["id_alumno"] for g in grupos for a in g["alumnos"] if a["debe"]}, deben)
        # La pantalla: sin montos, sin métodos, sin otros grupos, aunque se escriban parámetros a mano
        html = c.get("/mi-grupo?id_entrenador=999&grupo=1").get_data(as_text=True)
        t = texto(c.get("/mi-grupo"))
        self.assertEqual(html.count("<strong>"), c.get("/mi-grupo").get_data(as_text=True).count("<strong>"))
        for prohibido in ("Bs ", "Efectivo", "Transferencia", "Tarjeta", "QR"):
            self.assertNotIn(prohibido, t, prohibido)
        self.assertIn("Al día", t)
        self.assertNotIn("monto", " ".join(str(a) for g in grupos for a in g["alumnos"]).lower())

    def test_dueno_sin_grupos_ve_mensaje(self):
        sin = consultar_uno("SELECT en.id_entrenador FROM ENTRENADOR en WHERE LOWER(en.correo) = 'marco.admin@escuela.com' "
                            "AND NOT EXISTS (SELECT 1 FROM GRUPO g WHERE g.id_entrenador = en.id_entrenador)")
        if not sin:
            self.skipTest("El dueño ya tiene grupos asignados.")
        self.assertIn("No tienes grupos asignados", texto(self.dueno.get("/mi-grupo")))

    def test_entrenador_no_ve_reportes_del_dueno(self):
        _, c = self.entrenador()
        for url in ("/reportes/deudores", "/reportes/caja", "/api/reportes/caja"):
            self.assertEqual(c.get(url).status_code, 403, url)

    # --------------------------------------------------------------- en vivo

    def test_pantallas_operativas_se_actualizan_solas(self):
        for url in ("/reportes/deudores", "/reportes/caja", "/mi-grupo"):
            html = self.dueno.get(url).get_data(as_text=True)
            self.assertRegex(html, r'data-vivo="\d+"', url)
            self.assertIn("data-hace", html)
            self.assertIn("data-actualizar", html)

    def test_refresco_automatico_no_cuenta_como_actividad(self):
        """Con una pantalla abierta que se refresca sola, la sesión igual se cierra por inactividad."""
        c = self.dueno
        hace_un_rato = time.time() - 20 * 60
        with c.session_transaction() as s:
            s["ultima_actividad"] = hace_un_rato
        c.get("/reportes/deudores", headers={"X-Consulta-Automatica": "1"})
        with c.session_transaction() as s:
            self.assertEqual(s["ultima_actividad"], hace_un_rato, "el refresco automático no renueva la sesión")
        c.get("/reportes/deudores")
        with c.session_transaction() as s:
            self.assertGreater(s["ultima_actividad"], hace_un_rato, "una acción de la persona sí la renueva")


if __name__ == "__main__":
    import unittest
    unittest.main()
