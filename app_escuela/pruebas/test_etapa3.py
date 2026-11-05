"""
Etapa 3: mensualidades, cobros, recibos, anulaciones y auditoría.
Contra la base REAL dentro de una transacción que se deshace al final: no queda ningún pago de prueba.
Ejecutar desde app_escuela:   python -m unittest discover -s pruebas -t .
"""
import re
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from app import app
from datos import pagos
from datos.bd import consultar, consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace, cliente_como, enviar
from pruebas.test_etapa2 import texto

PERIODO = "2030-01"   # un periodo sin mensualidades: así las pruebas no dependen de los datos existentes
HOY = date.today().isoformat()


class AyudaCaja:
    """Ayudas para generar mensualidades y cobrar como lo haría el navegador (las usan las Etapas 3 y 4)."""

    def generar(self, periodo=PERIODO, emision="2030-01-01", vencimiento="2030-01-10"):
        return enviar(self.dueno, "/mensualidades", {"periodo": periodo, "fecha_emision": emision,
                                                     "fecha_vencimiento": vencimiento},
                      desde=f"/mensualidades?periodo={periodo}")

    def una_mensualidad(self):
        """Una mensualidad del periodo de prueba (se genera si hace falta)."""
        if not self.contar("MENSUALIDAD WHERE periodo = ?", (PERIODO,)):
            self.generar()
        return consultar_uno("""SELECT TOP 1 m.id_mensualidad, m.monto, i.id_alumno FROM MENSUALIDAD m
                                JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
                                WHERE m.periodo = ? ORDER BY m.id_mensualidad""", (PERIODO,))

    def cobrar(self, id_mensualidad, monto, metodo=1, fecha=HOY, confirmar=False, clave=None, cliente=None):
        """Envía el formulario de cobro como el navegador: con su token CSRF y su clave de un solo uso."""
        c = cliente or self.dueno
        url = f"/caja/mensualidades/{id_mensualidad}/cobrar"
        pagina = c.get(url).get_data(as_text=True)
        datos = {"csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1),
                 "clave_cobro": clave or re.search(r'name="clave_cobro" value="([^"]+)"', pagina).group(1),
                 "id_metodo_pago": metodo, "fecha_pago": fecha, "monto": monto}
        if confirmar:
            datos["confirmar_exceso"] = "si"
        return c.post(url, data=datos), datos["clave_cobro"]

    def ultimo_pago(self):
        return consultar_uno("""SELECT TOP 1 p.*, e.nombre AS estado FROM PAGO p
                                JOIN ESTADO_PAGO e ON e.id_estado_pago = p.id_estado_pago ORDER BY p.id_pago DESC""")


class PruebasEtapa3(AyudaCaja, PruebaConBaseQueSeDeshace):
    # --------------------------------------------------------------- mensualidades (HU-07)

    def test_generar_una_por_inscripcion_activa_sin_duplicar(self):
        activas = self.contar("INSCRIPCION i JOIN GRUPO g ON g.id_grupo = i.id_grupo "
                              "WHERE i.estado = 'ACTIVA' AND g.estado = 'ACTIVO'")
        r = self.generar()
        self.assertIn(f"Se crearon {activas} mensualidades de {PERIODO}", texto(self.dueno.get(r.headers["Location"])))
        # Con el precio del grupo y las fechas elegidas
        malas = consultar("""SELECT m.id_mensualidad FROM MENSUALIDAD m JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
                             JOIN GRUPO g ON g.id_grupo = i.id_grupo
                             WHERE m.periodo = ? AND (m.monto <> g.precio_mensual OR m.fecha_emision <> '2030-01-01'
                                   OR m.fecha_vencimiento <> '2030-01-10')""", (PERIODO,))
        self.assertEqual(malas, [])
        # La segunda vez no duplica y lo informa
        r = self.generar()
        self.assertIn(f"Se crearon 0 mensualidades de {PERIODO}. Se omitieron {activas} porque ya existían",
                      texto(self.dueno.get(r.headers["Location"])))
        self.assertEqual(self.contar("MENSUALIDAD WHERE periodo = ?", (PERIODO,)), activas)

    def test_generar_valida_fechas_y_periodo(self):
        r = self.generar(emision="2030-01-15", vencimiento="2030-01-10")
        pagina = texto(self.dueno.get(r.headers.get("Location", "/mensualidades"))) + texto(r)
        self.assertIn("no puede ser anterior a la de emisión", pagina)
        self.assertEqual(self.contar("MENSUALIDAD WHERE periodo = ?", (PERIODO,)), 0)
        r = self.dueno.get("/mensualidades?periodo=2030-13")
        self.assertIn("El periodo debe tener la forma aaaa-mm", texto(r))

    # --------------------------------------------------------------- cobros (HU-08, RF-14, RF-15, RF-17)

    def test_pago_completo_recibo_correlativo_y_auditoria(self):
        m = self.una_mensualidad()
        ultimo = consultar_uno("SELECT MAX(TRY_CAST(SUBSTRING(numero_recibo, 5, 20) AS INT)) AS n FROM PAGO "
                               "WHERE numero_recibo LIKE 'PAG-%'")["n"] or 0
        r, _ = self.cobrar(m["id_mensualidad"], f"{m['monto']:.2f}")
        self.assertEqual(r.status_code, 302, texto(r)[:300])
        p = self.ultimo_pago()
        self.assertEqual(p["numero_recibo"], f"PAG-{ultimo + 1:04d}")
        self.assertEqual(p["estado"], "Confirmado")
        self.assertEqual(p["monto"], m["monto"])
        self.assertEqual(r.headers["Location"], f"/pagos/{p['id_pago']}/recibo")
        a = consultar("SELECT * FROM AUDITORIA_PAGO WHERE id_pago = ?", (p["id_pago"],))
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0]["operacion"], a[0]["usuario"], a[0]["estado_nuevo"], a[0]["monto_nuevo"]),
                         ("INSERT", "marco.admin@escuela.com", "Confirmado", m["monto"]))
        self.assertEqual(pagos.obtener_mensualidad(m["id_mensualidad"])["saldo"], 0)
        # Un segundo pago toma el número siguiente
        m2 = consultar_uno("SELECT TOP 1 id_mensualidad, monto FROM MENSUALIDAD WHERE periodo = ? AND id_mensualidad <> ?",
                           (PERIODO, m["id_mensualidad"]))
        self.cobrar(m2["id_mensualidad"], f"{m2['monto']:.2f}")
        self.assertEqual(self.ultimo_pago()["numero_recibo"], f"PAG-{ultimo + 2:04d}")

    def test_pago_parcial_y_luego_el_resto(self):
        m = self.una_mensualidad()
        self.cobrar(m["id_mensualidad"], "100")
        p = self.ultimo_pago()
        self.assertEqual((p["estado"], p["observaciones"]), ("Parcial", "Pago parcial"))
        saldo = pagos.obtener_mensualidad(m["id_mensualidad"])["saldo"]
        self.assertEqual(saldo, m["monto"] - Decimal("100"))
        self.assertIn("Parcial", texto(self.dueno.get(f"/caja/alumnos/{m['id_alumno']}")))
        self.cobrar(m["id_mensualidad"], f"{saldo:.2f}")
        self.assertEqual(self.ultimo_pago()["estado"], "Confirmado")
        self.assertEqual(pagos.obtener_mensualidad(m["id_mensualidad"])["saldo"], 0)

    def test_monto_invalido_y_fecha_futura_no_registran(self):
        m = self.una_mensualidad()
        antes = self.contar("PAGO")
        for monto, mensaje in (("0", "mayor a cero"), ("-5", "mayor a cero"), ("abc", "debe ser un número")):
            r, _ = self.cobrar(m["id_mensualidad"], monto)
            self.assertIn(mensaje, texto(r))
        manana = (date.today() + timedelta(days=1)).isoformat()
        r, _ = self.cobrar(m["id_mensualidad"], "50", fecha=manana)
        self.assertIn("no puede ser futura", texto(r))
        self.assertEqual(self.contar("PAGO"), antes)

    def test_monto_mayor_pide_confirmacion(self):
        m = self.una_mensualidad()
        antes = self.contar("PAGO")
        r, _ = self.cobrar(m["id_mensualidad"], f"{m['monto'] + 50:.2f}")
        self.assertIn("mayor a lo que se debe", texto(r))
        self.assertIn('name="confirmar_exceso"', r.get_data(as_text=True))
        self.assertEqual(self.contar("PAGO"), antes, "sin confirmar no se registra")
        r, _ = self.cobrar(m["id_mensualidad"], f"{m['monto'] + 50:.2f}", confirmar=True)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.ultimo_pago()["estado"], "Confirmado")

    def test_doble_envio_no_cobra_dos_veces(self):
        m = self.una_mensualidad()
        r, clave = self.cobrar(m["id_mensualidad"], "50")
        antes = self.contar("PAGO")
        r, _ = self.cobrar(m["id_mensualidad"], "50", clave=clave)   # mismo formulario enviado otra vez
        self.assertIn("ya se había enviado", texto(self.dueno.get(r.headers["Location"])))
        self.assertEqual(self.contar("PAGO"), antes)

    def test_pago_y_auditoria_juntos_o_ninguno(self):
        """Si la auditoría falla, tampoco queda el pago (RNF-05)."""
        m = self.una_mensualidad()
        antes = self.contar("PAGO")
        with mock.patch.object(pagos, "_auditar", side_effect=RuntimeError("falla simulada")):
            app.config["PROPAGATE_EXCEPTIONS"] = True
            try:
                with self.assertRaises(RuntimeError):
                    self.cobrar(m["id_mensualidad"], "50")
            finally:
                app.config["PROPAGATE_EXCEPTIONS"] = None
        self.assertEqual(self.contar("PAGO"), antes, "el pago no debe quedar sin su auditoría")

    # --------------------------------------------------------------- recibo (HU-09)

    def test_recibo_muestra_lo_pedido(self):
        m = self.una_mensualidad()
        self.cobrar(m["id_mensualidad"], "120.50", metodo=3)
        p = self.ultimo_pago()
        t = texto(self.dueno.get(f"/pagos/{p['id_pago']}/recibo"))
        for esperado in (p["numero_recibo"], date.today().strftime("%d/%m/%Y"), PERIODO, "QR", "Bs 120,50", "Parcial"):
            self.assertIn(esperado, t)
        alumno = consultar_uno("SELECT nombres FROM ALUMNO WHERE id_alumno = ?", (m["id_alumno"],))
        self.assertIn(alumno["nombres"], t)
        # Formato de factura, pero es un RECIBO (la escuela no tiene NIT)
        for esperado in ("Recibo de pago", "Sin derecho a crédito fiscal", "Son: Ciento veinte 50/100 Bolivianos",
                         "Monto pagado Bs 120,50", "No es una factura", "img/escudo.png"):
            self.assertIn(esperado, t + self.dueno.get(f"/pagos/{p['id_pago']}/recibo").get_data(as_text=True))
        self.assertNotIn("Código de autorización", t)
        css = Path("estaticos/css/estilos.css").read_text(encoding="utf-8")
        self.assertIn("@media print", css, "el recibo tiene versión de impresión")

    # --------------------------------------------------------------- anulación (HU-10, RF-16)

    def test_anular_con_motivo_conserva_el_pago_y_devuelve_el_saldo(self):
        m = self.una_mensualidad()
        self.cobrar(m["id_mensualidad"], f"{m['monto']:.2f}")
        p = self.ultimo_pago()
        url = f"/pagos/{p['id_pago']}/anular"
        r = enviar(self.dueno, url, {"motivo": ""}, desde=f"/pagos/{p['id_pago']}/recibo")
        self.assertIn("Escribe el motivo", texto(self.dueno.get(r.headers["Location"])))
        self.assertEqual(self.ultimo_pago()["estado"], "Confirmado")
        enviar(self.dueno, url, {"motivo": "Monto registrado por error"}, desde=f"/pagos/{p['id_pago']}/recibo")
        anulado = consultar_uno("SELECT p.observaciones, e.nombre AS estado FROM PAGO p JOIN ESTADO_PAGO e "
                                "ON e.id_estado_pago = p.id_estado_pago WHERE p.id_pago = ?", (p["id_pago"],))
        self.assertEqual(anulado["estado"], "Anulado", "el pago no se borra: queda Anulado")
        self.assertIn("Monto registrado por error", anulado["observaciones"])
        a = consultar("SELECT operacion, estado_anterior, estado_nuevo FROM AUDITORIA_PAGO WHERE id_pago = ? "
                      "ORDER BY id_auditoria", (p["id_pago"],))
        self.assertEqual([x["operacion"] for x in a], ["INSERT", "ANULACION"])
        self.assertEqual((a[1]["estado_anterior"], a[1]["estado_nuevo"]), ("Confirmado", "Anulado"))
        self.assertEqual(pagos.obtener_mensualidad(m["id_mensualidad"])["saldo"], m["monto"],
                         "la mensualidad vuelve a pendiente")
        r = enviar(self.dueno, url, {"motivo": "otra vez"}, desde=f"/pagos/{p['id_pago']}/recibo")
        self.assertIn("ya estaba anulado", texto(self.dueno.get(r.headers["Location"])))

    def test_pagos_anteriores_no_se_anulan(self):
        rec = consultar_uno("SELECT TOP 1 p.id_pago, p.id_estado_pago, p.observaciones FROM PAGO p "
                            "WHERE p.numero_recibo LIKE 'REC-%' ORDER BY p.id_pago")
        r = enviar(self.dueno, f"/pagos/{rec['id_pago']}/anular", {"motivo": "prueba de seguridad"},
                   desde=f"/pagos/{rec['id_pago']}/recibo")
        self.assertIn("Solo se pueden anular pagos registrados en esta app", texto(self.dueno.get(r.headers["Location"])))
        despues = consultar_uno("SELECT id_estado_pago, observaciones FROM PAGO WHERE id_pago = ?", (rec["id_pago"],))
        self.assertEqual((despues["id_estado_pago"], despues["observaciones"]), (rec["id_estado_pago"], rec["observaciones"]))

    # --------------------------------------------------------------- integración y permisos

    def test_el_etl_puede_leer_el_pago_nuevo(self):
        """La misma consulta que usa el paquete SSIS (RF-22) encuentra el pago con todos sus datos."""
        m = self.una_mensualidad()
        self.cobrar(m["id_mensualidad"], "75")
        p = self.ultimo_pago()
        fila = consultar_uno("""SELECT i.id_alumno, g.id_categoria, p.id_metodo_pago, p.id_estado_pago, p.numero_recibo,
                                       m.monto AS monto_mensualidad, p.monto AS monto_pagado, p.fecha_pago, m.fecha_vencimiento
                                FROM PAGO p
                                INNER JOIN MENSUALIDAD m ON p.id_mensualidad = m.id_mensualidad
                                INNER JOIN INSCRIPCION i ON m.id_inscripcion = i.id_inscripcion
                                INNER JOIN GRUPO g ON i.id_grupo = g.id_grupo
                                WHERE p.id_pago = ?""", (p["id_pago"],))
        self.assertIsNotNone(fila)
        self.assertTrue(all(fila[k] is not None for k in fila), fila)

    def test_entrenador_no_cobra_ni_anula(self):
        entrenador = consultar_uno("SELECT TOP 1 u.id_usuario FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol "
                                   "WHERE r.nombre = 'Entrenador' AND u.estado = 'ACTIVO'")
        if not entrenador:
            self.skipTest("No hay usuario entrenador activo.")
        c = cliente_como(entrenador["id_usuario"], "ENTRENADOR")
        m = self.una_mensualidad()
        for url in ("/caja", "/mensualidades", f"/caja/mensualidades/{m['id_mensualidad']}/cobrar", "/pagos/1/recibo"):
            self.assertEqual(c.get(url).status_code, 403, url)
        token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/mi-clave").get_data(as_text=True)).group(1)
        antes = self.contar("PAGO")
        r = c.post(f"/caja/mensualidades/{m['id_mensualidad']}/cobrar",
                   data={"csrf_token": token, "id_metodo_pago": 1, "fecha_pago": HOY, "monto": "10"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(c.post("/pagos/1/anular", data={"csrf_token": token, "motivo": "xxxxx"}).status_code, 403)
        self.assertEqual(self.contar("PAGO"), antes)

    def test_la_auditoria_no_se_puede_borrar_desde_la_app(self):
        reglas = [r for r in app.url_map.iter_rules() if "auditoria" in r.rule.lower()
                  or "auditoria" in r.endpoint.lower()]
        self.assertEqual(reglas, [], "no debe existir ninguna ruta que cambie o borre la auditoría")
        fuente = "".join(Path(f).read_text(encoding="utf-8") for f in ("datos/pagos.py", "rutas/caja.py"))
        self.assertNotRegex(fuente, r"(?i)(DELETE|UPDATE)\s+(FROM\s+)?AUDITORIA_PAGO")


class PruebaSinResiduosEtapa3(unittest.TestCase):
    def test_las_pruebas_no_dejan_pagos_ni_mensualidades(self):
        self.assertEqual(consultar_uno("SELECT COUNT(*) AS n FROM MENSUALIDAD WHERE periodo = ?", (PERIODO,))["n"], 0)
        self.assertEqual(consultar_uno("SELECT COUNT(*) AS n FROM PAGO p JOIN MENSUALIDAD m "
                                       "ON m.id_mensualidad = p.id_mensualidad WHERE m.periodo = ?", (PERIODO,))["n"], 0)


if __name__ == "__main__":
    unittest.main()
