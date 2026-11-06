"""
Notificaciones (campana con número) y cumpleaños dentro de ellas.
Contra la base REAL; lo que se escribe se deshace al final.
"""
import re
import unittest
from datetime import date, timedelta

from datos import avisos, bd
from datos.bd import consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace, cliente_como
from pruebas.test_etapa2 import texto


def contador(html):
    m = re.search(r'class="contador">([^<]+)<', html)
    return m.group(1) if m else None


class PruebasAvisos(PruebaConBaseQueSeDeshace):
    def alumno_de_grupo(self, con_entrenador=True):
        return consultar_uno(f"""SELECT TOP 1 a.id_alumno, a.nombres, a.fecha_nacimiento, g.id_entrenador, g.id_grupo FROM ALUMNO a
            JOIN INSCRIPCION i ON i.id_alumno = a.id_alumno AND i.estado = 'ACTIVA' JOIN GRUPO g ON g.id_grupo = i.id_grupo
            WHERE a.estado = 'ACTIVO' {'AND g.id_entrenador IS NOT NULL' if con_entrenador else ''} ORDER BY a.id_alumno""")

    def cumple_en(self, id_alumno, dias, anios=10):
        dia = date.today() + timedelta(days=dias)
        with bd.transaccion() as cur:   # se deshace al final de la prueba
            cur.execute("UPDATE ALUMNO SET fecha_nacimiento = ? WHERE id_alumno = ?",
                        (date(dia.year - anios, dia.month, min(dia.day, 28)), id_alumno))

    def test_cumpleanos_de_hoy_llega_como_notificacion(self):
        a = self.alumno_de_grupo()
        self.cumple_en(a["id_alumno"], 0)
        lista = avisos.notificaciones(True)
        cumple = next((x for x in lista if x["icono"] == "pastel"), None)
        if date.today().day > 28:
            self.skipTest("Hoy es día 29-31: la prueba usa el día 28.")
        self.assertIsNotNone(cumple)
        self.assertIn(a["id_alumno"], [c["id_alumno"] for c in cumple["cumpleaneros"]])
        html = self.dueno.get("/notificaciones").get_data(as_text=True)
        self.assertIn(a["nombres"], html)
        self.assertIn("feliz%20cumplea%C3%B1os", html, "el dueño puede saludar al tutor por WhatsApp")

    def test_numero_de_la_campana_y_se_borra_al_abrir(self):
        if not avisos.notificaciones(True):
            self.skipTest("No hay notificaciones ahora.")
        self.assertIsNotNone(contador(self.dueno.get("/").get_data(as_text=True)), "la campana muestra el número")
        self.dueno.get("/notificaciones")
        self.assertIsNone(contador(self.dueno.get("/").get_data(as_text=True)), "después de abrirlas, el número se borra")

    def test_entrenador_ve_solo_los_cumpleanos_de_su_grupo(self):
        a = self.alumno_de_grupo()
        otro = consultar_uno("""SELECT TOP 1 a.id_alumno FROM ALUMNO a JOIN INSCRIPCION i ON i.id_alumno = a.id_alumno
            AND i.estado = 'ACTIVA' JOIN GRUPO g ON g.id_grupo = i.id_grupo
            WHERE a.estado = 'ACTIVO' AND (g.id_entrenador IS NULL OR g.id_entrenador <> ?)""", (a["id_entrenador"],))
        self.cumple_en(a["id_alumno"], 2)
        if otro:
            self.cumple_en(otro["id_alumno"], 2)
        suyos = [c["id_alumno"] for c in avisos.cumpleanos(dias=7, id_entrenador=a["id_entrenador"])]
        self.assertIn(a["id_alumno"], suyos)
        if otro:
            self.assertNotIn(otro["id_alumno"], suyos)
        u = consultar_uno("""SELECT u.id_usuario FROM USUARIO u JOIN ENTRENADOR e ON LOWER(e.correo) = LOWER(u.correo)
                             WHERE e.id_entrenador = ?""", (a["id_entrenador"],))
        if u:
            t = texto(cliente_como(u["id_usuario"], "ENTRENADOR").get("/notificaciones"))
            self.assertIn("Próximos cumpleaños", t)
            self.assertNotIn("wa.me", t, "el entrenador no ve teléfonos")

    def test_29_de_febrero(self):
        self.assertEqual(avisos._proximo_cumple(date(2016, 2, 29), date(2027, 2, 1)), date(2027, 2, 28))
        self.assertEqual(avisos._proximo_cumple(date(2016, 2, 29), date(2028, 2, 1)), date(2028, 2, 29))
        self.assertEqual(avisos._proximo_cumple(date(2016, 5, 10), date(2026, 5, 11)), date(2027, 5, 10))



class PruebasVencimientoEntrenador(PruebaConBaseQueSeDeshace):
    """El entrenador ve cuándo vence la mensualidad de cada niño (para avisarle), nunca montos."""

    def test_vence_manana_en_mi_grupo_y_en_notificaciones(self):
        from datos import reportes
        u = consultar_uno("""SELECT TOP 1 u.id_usuario, e.id_entrenador FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol
            JOIN ENTRENADOR e ON LOWER(e.correo) = LOWER(u.correo)
            WHERE r.nombre = 'Entrenador' AND u.estado = 'ACTIVO'
              AND EXISTS (SELECT 1 FROM GRUPO g WHERE g.id_entrenador = e.id_entrenador AND g.estado = 'ACTIVO')""")
        al_dia = [a for gr in reportes.mi_grupo(u["id_entrenador"]) for a in gr["alumnos"] if not a["debe"]]
        if not al_dia:
            self.skipTest("Nadie está al día en ese grupo.")
        a = al_dia[0]
        insc = consultar_uno("""SELECT TOP 1 i.id_inscripcion FROM INSCRIPCION i JOIN GRUPO g ON g.id_grupo = i.id_grupo
                                WHERE i.id_alumno = ? AND i.estado = 'ACTIVA' AND g.id_entrenador = ?""", (a["id_alumno"], u["id_entrenador"]))
        manana = date.today() + timedelta(days=1)
        with bd.transaccion() as cur:   # se deshace al final
            cur.execute("INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado) "
                        "VALUES (?, '2031-04', ?, ?, 123.45, 'PENDIENTE')", (insc["id_inscripcion"], date.today(), manana))
        c = cliente_como(u["id_usuario"], "ENTRENADOR")
        html = c.get("/mi-grupo").get_data(as_text=True)
        fila = html[html.index(a["alumno"]):][:600]
        self.assertIn("Vence mañana", fila)
        self.assertNotIn("Bs", html, "el entrenador nunca ve montos")
        self.assertNotIn("123", html)
        t = texto(c.get("/notificaciones"))
        self.assertIn("Recordar: mensualidad por vencer", t)
        self.assertIn(a["alumno"], t)
        self.assertNotIn("Bs", t)

    def test_textos_de_vencimiento(self):
        from datos.reportes import cuando_vence
        hoy = date(2026, 11, 6)   # viernes
        self.assertEqual(cuando_vence(hoy, hoy), "Vence hoy")
        self.assertEqual(cuando_vence(date(2026, 11, 7), hoy), "Vence mañana")
        self.assertEqual(cuando_vence(date(2026, 11, 9), hoy), "Vence el lunes 9")
        self.assertIsNone(cuando_vence(date(2026, 11, 30), hoy), "si falta mucho, no se avisa")


if __name__ == "__main__":
    unittest.main()
