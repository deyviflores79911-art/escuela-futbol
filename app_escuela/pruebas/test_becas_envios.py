"""
Becas (porcentaje de descuento), envío del recibo por WhatsApp y correo, y la base de Azure que despierta.
Contra la base REAL; lo que se escribe se deshace al final.
"""
import re
import sys
import types
import unittest
from datetime import date
from decimal import Decimal
from unittest import mock

import config
from datos import bd
from datos.bd import consultar, consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace, enviar
from pruebas.test_etapa2 import texto
from pruebas.test_etapa3 import AyudaCaja

PERIODO_BECA = "2031-03"


class PruebasBecas(AyudaCaja, PruebaConBaseQueSeDeshace):
    def dos_alumnos_inscritos(self):
        return consultar("""SELECT TOP 2 i.id_inscripcion, i.id_alumno, g.precio_mensual FROM INSCRIPCION i
                            JOIN GRUPO g ON g.id_grupo = i.id_grupo
                            WHERE i.estado = 'ACTIVA' AND g.estado = 'ACTIVO' ORDER BY i.id_inscripcion""")

    def test_mensualidades_con_descuento_y_beca_completa_sin_mensualidad(self):
        media, completa = self.dos_alumnos_inscritos()
        with bd.transaccion() as cur:   # se deshace al final de la prueba
            cur.execute("UPDATE ALUMNO SET porcentaje_beca = 50 WHERE id_alumno = ?", (media["id_alumno"],))
            cur.execute("UPDATE ALUMNO SET porcentaje_beca = 100 WHERE id_alumno = ?", (completa["id_alumno"],))
        self.generar(periodo=PERIODO_BECA, emision="2031-03-01", vencimiento="2031-03-10")
        m = consultar_uno("SELECT monto FROM MENSUALIDAD WHERE id_inscripcion = ? AND periodo = ?",
                          (media["id_inscripcion"], PERIODO_BECA))
        self.assertEqual(m["monto"], (media["precio_mensual"] / 2).quantize(Decimal("0.01")))
        self.assertEqual(self.contar("MENSUALIDAD WHERE id_inscripcion = ? AND periodo = ?",
                                     (completa["id_inscripcion"], PERIODO_BECA)), 0, "beca 100 %: no paga")
        from datos import pagos
        r = pagos.resumen_periodo(PERIODO_BECA)
        self.assertEqual(r["activas"], r["ya_generadas"], "el becado completo no cuenta como pendiente de generar")

    def test_beca_en_el_formulario(self):
        r = enviar(self.dueno, "/alumnos/nuevo", {
            "codigo": "P-BECA", "nombres": "Beca", "apellidos": "Prueba", "fecha_nacimiento": "2016-05-05",
            "sexo": "F", "direccion": "", "id_tutor": 1, "id_grupo": "despues", "porcentaje_beca": "101"})
        self.assertIn("La beca debe estar entre 0 y 100", texto(r))
        r = enviar(self.dueno, "/alumnos/nuevo", {
            "codigo": "P-BECA", "nombres": "Beca", "apellidos": "Prueba", "fecha_nacimiento": "2016-05-05",
            "sexo": "F", "direccion": "", "id_tutor": 1, "id_grupo": "despues", "porcentaje_beca": "50"})
        self.assertEqual(r.status_code, 302, texto(r)[:300])
        a = consultar_uno("SELECT id_alumno, porcentaje_beca FROM ALUMNO WHERE codigo = 'P-BECA'")
        self.assertEqual(a["porcentaje_beca"], 50)
        self.assertIn("50 %", texto(self.dueno.get(f"/alumnos/{a['id_alumno']}")))
        self.assertIn("Beca Prueba", texto(self.dueno.get("/alumnos?estado=BECADO&todos=1")))


    def test_beca_en_cualquier_momento_desde_la_ficha(self):
        """A un alumno ya inscrito: se recalcula la mensualidad sin pagos; la que tiene pagos no se toca."""
        self.generar(periodo=PERIODO_BECA, emision="2031-03-01", vencimiento="2031-03-10")
        sin_pago, con_pago = consultar("""SELECT TOP 2 m.id_mensualidad, m.monto, i.id_alumno, g.precio_mensual
            FROM MENSUALIDAD m JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion JOIN GRUPO g ON g.id_grupo = i.id_grupo
            WHERE m.periodo = ? ORDER BY m.id_mensualidad""", (PERIODO_BECA,))
        self.cobrar(con_pago["id_mensualidad"], "10.00")
        for m in (sin_pago, con_pago):
            r = enviar(self.dueno, f"/alumnos/{m['id_alumno']}/beca", {"porcentaje_beca": "50", "aplicar_mes": "si"},
                       desde=f"/alumnos/{m['id_alumno']}")
            self.assertEqual(r.status_code, 302)
            self.assertEqual(consultar_uno("SELECT porcentaje_beca FROM ALUMNO WHERE id_alumno = ?", (m["id_alumno"],))
                             ["porcentaje_beca"], 50)
        nuevo = consultar_uno("SELECT monto FROM MENSUALIDAD WHERE id_mensualidad = ?", (sin_pago["id_mensualidad"],))
        self.assertEqual(nuevo["monto"], (sin_pago["precio_mensual"] / 2).quantize(Decimal("0.01")))
        intacta = consultar_uno("SELECT monto FROM MENSUALIDAD WHERE id_mensualidad = ?", (con_pago["id_mensualidad"],))
        self.assertEqual(intacta["monto"], con_pago["monto"], "con pagos no se recalcula")
        self.assertIn("Tiene 50 % de descuento", texto(self.dueno.get(f"/alumnos/{sin_pago['id_alumno']}")))


class _SMTPFalso:
    """Servidor de correo de mentira: guarda lo que se 'envía'."""
    enviados = []

    def __init__(self, servidor, puerto, timeout=None):
        self.servidor = servidor

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        pass

    def login(self, usuario, clave):
        self.usuario = usuario

    def send_message(self, msg):
        _SMTPFalso.enviados.append(msg)


class PruebasEnvioRecibo(AyudaCaja, PruebaConBaseQueSeDeshace):
    def setUp(self):
        super().setUp()
        _SMTPFalso.enviados = []

    def con_correo(self):
        return mock.patch.multiple(config, CORREO_USUARIO="escuela@ejemplo.com", CORREO_CLAVE="clave-app")

    def cobrar_con(self, **marcas):
        m = self.una_mensualidad()
        url = f"/caja/mensualidades/{m['id_mensualidad']}/cobrar"
        pagina = self.dueno.get(url).get_data(as_text=True)
        datos = {"csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1),
                 "clave_cobro": re.search(r'name="clave_cobro" value="([^"]+)"', pagina).group(1),
                 "id_metodo_pago": 1, "fecha_pago": date.today().isoformat(), "monto": "10.00", **marcas}
        return self.dueno.post(url, data=datos), pagina

    def test_sin_cuenta_de_correo_la_opcion_esta_desactivada(self):
        _, pagina = self.cobrar_con()
        self.assertRegex(pagina, r'name="enviar_correo" value="si"\s+disabled')

    def test_con_cuenta_de_correo_se_envia_al_tutor(self):
        with self.con_correo(), mock.patch("smtplib.SMTP", _SMTPFalso):
            r, _ = self.cobrar_con(enviar_correo="si")
            self.assertEqual(r.status_code, 302)
            p = self.ultimo_pago()
            tutor = consultar_uno("""SELECT t.correo FROM PAGO p JOIN MENSUALIDAD m ON m.id_mensualidad = p.id_mensualidad
                JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion JOIN ALUMNO a ON a.id_alumno = i.id_alumno
                JOIN TUTOR t ON t.id_tutor = a.id_tutor WHERE p.id_pago = ?""", (p["id_pago"],))
            self.assertEqual(len(_SMTPFalso.enviados), 1)
            msg = _SMTPFalso.enviados[0]
            self.assertEqual(msg["To"], tutor["correo"])
            self.assertIn(p["numero_recibo"], msg["Subject"])
            self.assertIn("Sin derecho a crédito fiscal", msg.get_body(("html",)).get_content())
            self.assertIn("Recibo enviado por correo", texto(self.dueno.get(r.headers["Location"])))
            # También desde el botón del recibo
            r = enviar(self.dueno, f"/pagos/{p['id_pago']}/enviar-correo", {}, desde=f"/pagos/{p['id_pago']}/recibo")
            self.assertEqual(len(_SMTPFalso.enviados), 2)

    def test_whatsapp_marcado_abre_el_mensaje_listo(self):
        r, _ = self.cobrar_con(enviar_whatsapp="si")
        self.assertIn("whatsapp=1", r.headers["Location"])
        html = self.dueno.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("data-abrir-solo", html)
        r, _ = self.cobrar_con()
        self.assertNotIn("whatsapp=1", r.headers["Location"])


class PruebaAzureDespierta(unittest.TestCase):
    def test_reintenta_mientras_la_base_despierta(self):
        intentos = []

        class ErrorPymssql(Exception):
            pass

        def conectar(**_):
            intentos.append(1)
            if len(intentos) < 3:
                raise ErrorPymssql("(40613, b'Database is not currently available')")
            return "conexion"

        falso = types.SimpleNamespace(connect=conectar, Error=ErrorPymssql)
        with mock.patch.dict(sys.modules, {"pymssql": falso}), mock.patch("time.sleep"):
            self.assertEqual(bd._abrir_nube(), "conexion")
        self.assertEqual(len(intentos), 3)


if __name__ == "__main__":
    unittest.main()
