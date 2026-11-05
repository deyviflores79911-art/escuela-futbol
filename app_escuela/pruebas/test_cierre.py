"""
Cierre del proyecto: aviso de base apagada y rendimiento con ~1.000 pagos más.
Contra la base REAL; lo que se escribe va dentro de una transacción que se deshace al final.
Ejecutar desde app_escuela:   python -m unittest discover -s pruebas -t .
"""
import time
from unittest import mock

from datos import bd
from datos.bd import ErrorBD, consultar_uno
from pruebas.ayuda import PruebaConBaseQueSeDeshace, cliente_como
from pruebas.test_etapa2 import texto

LIMITE_SEGUNDOS = 2.0   # RNF-07: las pantallas principales responden en menos de 2 segundos


class PruebaBaseApagada(PruebaConBaseQueSeDeshace):
    def test_base_apagada_se_avisa(self):
        """Si SQL Server no responde: página clara (no un error raro) y las rutas /api/ responden 503 en JSON."""
        def sin_base():
            raise ErrorBD("No se pudo conectar con SQL Server. Revisa que el servicio MSSQL$MSSQLSERVER01 esté iniciado.")
        with mock.patch.object(bd, "conectar", sin_base):
            r = self.dueno.get("/reportes/deudores")
            self.assertEqual(r.status_code, 503)
            self.assertIn("Sin conexión con la base", texto(r))
            api = self.dueno.get("/api/reportes/caja")
            self.assertEqual(api.status_code, 503)
            self.assertIn("No se pudo conectar", api.get_json()["error"])


class PruebaRendimiento(PruebaConBaseQueSeDeshace):
    """RNF-07: con ~1.000 pagos MÁS de los que hay (unos 1.860 en total) las pantallas responden en < 2 s."""

    def test_pantallas_rapidas_con_mil_pagos_mas(self):
        with bd.transaccion() as cur:   # pagos de prueba, se deshacen al final
            cur.execute("""INSERT INTO PAGO (id_mensualidad, id_usuario, id_metodo_pago, id_estado_pago, numero_recibo,
                                             fecha_pago, monto, observaciones)
                           SELECT TOP 1000 m.id_mensualidad, 1, 1 + ABS(CHECKSUM(NEWID())) % 4, 2,
                                  'PERF-' + CAST(ROW_NUMBER() OVER (ORDER BY m.id_mensualidad) AS varchar(10)),
                                  m.fecha_vencimiento, 1.00, NULL
                           FROM MENSUALIDAD m CROSS JOIN (SELECT TOP 2 1 AS x FROM ESTADO_PAGO) dos""")
        total = consultar_uno("SELECT COUNT(*) AS n FROM PAGO")["n"]
        self.assertGreaterEqual(total, 1800)
        alumno = consultar_uno("SELECT TOP 1 i.id_alumno FROM INSCRIPCION i")["id_alumno"]
        urls = ["/", "/alumnos", "/grupos", "/caja", f"/caja/alumnos/{alumno}", "/mensualidades",
                "/reportes/deudores?periodo=todos", "/reportes/caja?desde=2025-01-01&hasta=2030-12-31",
                "/mi-grupo", "/horarios", "/tutores", "/api/reportes/caja"]
        lentas = {}
        for url in urls:
            inicio = time.perf_counter()
            r = self.dueno.get(url)
            segundos = time.perf_counter() - inicio
            self.assertEqual(r.status_code, 200, url)
            if segundos >= LIMITE_SEGUNDOS:
                lentas[url] = round(segundos, 2)
        self.assertEqual(lentas, {}, f"pantallas lentas con {total} pagos")


class PruebaCelular(PruebaConBaseQueSeDeshace):
    """La app se usa en el celular: se puede instalar y la barra de abajo depende del rol."""

    def test_se_puede_instalar_como_app(self):
        with self.dueno.get("/static/app.webmanifest") as r:
            self.assertEqual(r.status_code, 200)
            manifiesto = r.get_json(force=True)
        self.assertEqual(manifiesto["display"], "standalone")
        for icono in manifiesto["icons"]:
            with self.dueno.get("/static/" + icono["src"]) as r_icono:
                self.assertEqual(r_icono.status_code, 200, icono["src"])
        html = self.dueno.get("/").get_data(as_text=True)
        self.assertIn('rel="manifest"', html)
        self.assertIn("viewport-fit=cover", html)

    def test_barra_de_abajo_segun_el_rol(self):
        barra = self.dueno.get("/").get_data(as_text=True).split('class="barra-inferior"')[1].split("</nav>")[0]
        for opcion in ("Inicio", "Cobrar", "Inscribir", "Alumnos", "Más"):
            self.assertIn(f"<span>{opcion}</span>", barra)
        e = consultar_uno("SELECT TOP 1 u.id_usuario FROM USUARIO u JOIN ROL r ON r.id_rol = u.id_rol "
                          "WHERE r.nombre = 'Entrenador' AND u.estado = 'ACTIVO'")
        barra = cliente_como(e["id_usuario"], "ENTRENADOR").get("/").get_data(as_text=True)
        barra = barra.split('class="barra-inferior"')[1].split("</nav>")[0]
        for opcion in ("Inicio", "Mi grupo", "Más"):
            self.assertIn(f"<span>{opcion}</span>", barra)
        self.assertNotIn("Cobrar", barra)  # el entrenador no cobra
        self.assertNotIn("Alertas", barra)
