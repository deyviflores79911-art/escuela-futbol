"""
Mensualidades, cobros, recibos y anulaciones.

Reglas:
  - Lo que se debe se CALCULA: saldo = monto de la mensualidad - pagos no anulados.
    (MENSUALIDAD.estado no se usa: en los datos existentes dice PENDIENTE aunque esté pagada.)
  - Cada pago y su fila de AUDITORIA_PAGO se guardan en UNA sola transacción.
  - Los recibos nuevos son PAG-0001, PAG-0002... (los REC-, SIM- y PRB- existentes no se tocan).
  - Solo se anulan pagos PAG-; la fila queda con estado Anulado y no se borra.
"""
import re
from datetime import date
from decimal import Decimal

from datos.bd import ErrorDatos, consultar, consultar_uno, transaccion

PREFIJO_RECIBO = "PAG-"
DIA_EMISION, DIA_VENCIMIENTO = 1, 10   # como las mensualidades existentes (día 1 y día 10 del mes)

# Lo pagado de una mensualidad: suma de sus pagos que no están anulados
PAGADO_SQL = """(SELECT ISNULL(SUM(p.monto), 0) FROM PAGO p
              JOIN ESTADO_PAGO e ON e.id_estado_pago = p.id_estado_pago
              WHERE p.id_mensualidad = m.id_mensualidad AND e.nombre <> 'Anulado')"""


def periodo_valido(periodo):
    return bool(periodo and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", periodo))


def fechas_propuestas(periodo):
    """Emisión el día 1 y vencimiento el día 10 del periodo."""
    anio, mes = map(int, periodo.split("-"))
    return date(anio, mes, DIA_EMISION), date(anio, mes, DIA_VENCIMIENTO)


def periodo_actual():
    return date.today().strftime("%Y-%m")


def metodos_activos():
    return consultar("SELECT id_metodo_pago, nombre FROM METODO_PAGO WHERE estado = 'ACTIVO' ORDER BY id_metodo_pago")


def _id_estado(cur, nombre):
    cur.execute("SELECT id_estado_pago FROM ESTADO_PAGO WHERE nombre = ?", (nombre,))
    fila = cur.fetchone()
    if not fila:
        raise ErrorDatos(f"Falta el estado de pago '{nombre}' en el catálogo ESTADO_PAGO.")
    return fila[0]


# ---------------------------------------------------------------- Mensualidades

def resumen_periodo(periodo):
    """Cuántas inscripciones activas hay, cuántas ya tienen mensualidad de ese periodo y cuántas faltan."""
    return consultar_uno(
        """SELECT COUNT(*) AS activas, ISNULL(SUM(CASE WHEN x.n > 0 THEN 1 ELSE 0 END), 0) AS ya_generadas
           FROM INSCRIPCION i JOIN GRUPO g ON g.id_grupo = i.id_grupo
           OUTER APPLY (SELECT COUNT(*) AS n FROM MENSUALIDAD m
                        WHERE m.id_inscripcion = i.id_inscripcion AND m.periodo = ?) x
           WHERE i.estado = 'ACTIVA' AND g.estado = 'ACTIVO'""", (periodo,))


def generar_mensualidades(periodo, fecha_emision, fecha_vencimiento):
    """
    Crea una mensualidad por cada inscripción activa que todavía no tenga la de ese periodo,
    con el precio actual de su grupo. Devuelve (creadas, omitidas).
    """
    if not periodo_valido(periodo):
        raise ErrorDatos("El periodo debe tener la forma aaaa-mm, por ejemplo 2026-10.")
    if fecha_vencimiento < fecha_emision:
        raise ErrorDatos("La fecha de vencimiento no puede ser anterior a la de emisión.")
    with transaccion() as cur:
        # HOLDLOCK: nadie puede crear la misma mensualidad mientras se generan
        cur.execute(
            """SELECT COUNT(*) FROM INSCRIPCION i JOIN GRUPO g ON g.id_grupo = i.id_grupo
               WHERE i.estado = 'ACTIVA' AND g.estado = 'ACTIVO'
                 AND EXISTS (SELECT 1 FROM MENSUALIDAD m WITH (UPDLOCK, HOLDLOCK)
                             WHERE m.id_inscripcion = i.id_inscripcion AND m.periodo = ?)""", (periodo,))
        omitidas = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado)
               SELECT i.id_inscripcion, ?, ?, ?, g.precio_mensual, 'PENDIENTE'
               FROM INSCRIPCION i JOIN GRUPO g ON g.id_grupo = i.id_grupo
               WHERE i.estado = 'ACTIVA' AND g.estado = 'ACTIVO'
                 AND NOT EXISTS (SELECT 1 FROM MENSUALIDAD m WITH (UPDLOCK, HOLDLOCK)
                                 WHERE m.id_inscripcion = i.id_inscripcion AND m.periodo = ?)""",
            (periodo, fecha_emision, fecha_vencimiento, periodo))
        return cur.rowcount, omitidas


def periodos_generados():
    """Cada periodo con cuántas mensualidades tiene, cuántas están cubiertas y cuánto falta cobrar."""
    filas = consultar(
        f"""SELECT x.periodo, COUNT(*) AS mensualidades, SUM(x.monto) AS total,
                   SUM(CASE WHEN x.pagado >= x.monto THEN 1 ELSE 0 END) AS cubiertas,
                   SUM(CASE WHEN x.monto > x.pagado THEN x.monto - x.pagado ELSE 0 END) AS por_cobrar,
                   MIN(x.fecha_vencimiento) AS vencimiento
            FROM (SELECT m.periodo, m.monto, m.fecha_vencimiento, {PAGADO_SQL} AS pagado FROM MENSUALIDAD m) x
            GROUP BY x.periodo ORDER BY x.periodo DESC""")
    for f in filas:
        f["pendientes"] = f["mensualidades"] - f["cubiertas"]
    return filas


# ---------------------------------------------------------------- Estado de cuenta

def _estado_mensualidad(m, hoy=None):
    hoy = hoy or date.today()
    if m["saldo"] <= 0:
        return "Pagada"
    if m["fecha_vencimiento"] < hoy:
        return "Vencida"
    return "Parcial" if m["pagado"] > 0 else "Pendiente"


def saldo_por_alumno(ids_alumnos):
    """Total adeudado por cada alumno de la lista: {id_alumno: saldo}."""
    if not ids_alumnos:
        return {}
    marcas = ",".join("?" * len(ids_alumnos))
    filas = consultar(
        f"""SELECT i.id_alumno, SUM(CASE WHEN x.monto > x.pagado THEN x.monto - x.pagado ELSE 0 END) AS saldo
            FROM (SELECT m.id_inscripcion, m.monto, {PAGADO_SQL} AS pagado FROM MENSUALIDAD m) x
            JOIN INSCRIPCION i ON i.id_inscripcion = x.id_inscripcion
            WHERE i.id_alumno IN ({marcas}) GROUP BY i.id_alumno""", list(ids_alumnos))
    return {f["id_alumno"]: f["saldo"] for f in filas}


def primera_con_saldo(ids_alumnos):
    """Para cobrar directo: {id_alumno: {"id_mensualidad", "periodo", "saldo"}} de su mensualidad MÁS ANTIGUA con saldo."""
    if not ids_alumnos:
        return {}
    marcas = ",".join("?" * len(ids_alumnos))
    filas = consultar(
        f"""SELECT id_alumno, id_mensualidad, periodo, saldo FROM (
                SELECT i.id_alumno, x.id_mensualidad, x.periodo, x.monto - x.pagado AS saldo,
                       ROW_NUMBER() OVER (PARTITION BY i.id_alumno ORDER BY x.periodo, x.id_mensualidad) AS orden
                FROM (SELECT m.id_mensualidad, m.id_inscripcion, m.periodo, m.monto, {PAGADO_SQL} AS pagado
                      FROM MENSUALIDAD m) x
                JOIN INSCRIPCION i ON i.id_inscripcion = x.id_inscripcion
                WHERE i.id_alumno IN ({marcas}) AND x.monto > x.pagado) y
            WHERE orden = 1""", list(ids_alumnos))
    return {f["id_alumno"]: f for f in filas}


def mensualidades_de_alumno(id_alumno):
    """Todas las mensualidades del alumno (de todas sus inscripciones) con lo pagado y el saldo."""
    filas = consultar(
        f"""SELECT m.id_mensualidad, m.periodo, m.fecha_emision, m.fecha_vencimiento, m.monto,
                   {PAGADO_SQL} AS pagado, g.nombre AS grupo, i.estado AS estado_inscripcion
            FROM MENSUALIDAD m
            JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
            JOIN GRUPO g ON g.id_grupo = i.id_grupo
            WHERE i.id_alumno = ?
            ORDER BY m.periodo DESC, g.nombre""", (id_alumno,))
    for m in filas:
        m["saldo"] = m["monto"] - m["pagado"]
        m["estado"] = _estado_mensualidad(m)
        m["dias_atraso"] = (date.today() - m["fecha_vencimiento"]).days if m["estado"] == "Vencida" else 0
    return filas


def obtener_mensualidad(id_mensualidad):
    m = consultar_uno(
        f"""SELECT m.id_mensualidad, m.periodo, m.fecha_emision, m.fecha_vencimiento, m.monto, {PAGADO_SQL} AS pagado,
                   a.id_alumno, a.codigo, a.nombres, a.apellidos, g.nombre AS grupo, c.nombre AS categoria
            FROM MENSUALIDAD m
            JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
            JOIN ALUMNO a ON a.id_alumno = i.id_alumno
            JOIN GRUPO g ON g.id_grupo = i.id_grupo
            JOIN CATEGORIA c ON c.id_categoria = g.id_categoria
            WHERE m.id_mensualidad = ?""", (id_mensualidad,))
    if m:
        m["saldo"] = m["monto"] - m["pagado"]
        m["estado"] = _estado_mensualidad(m)
    return m


# ---------------------------------------------------------------- Pagos

_SELECT_PAGO = """
    SELECT p.id_pago, p.numero_recibo, p.fecha_pago, p.monto, p.observaciones,
           e.nombre AS estado, mp.nombre AS metodo,
           m.id_mensualidad, m.periodo, m.monto AS monto_mensualidad, m.fecha_vencimiento,
           a.id_alumno, a.codigo, a.nombres, a.apellidos,
           t.nombres + ' ' + ISNULL(t.apellidos, '') AS tutor, t.ci AS tutor_ci,
           ISNULL(t.whatsapp, t.telefono) AS tutor_celular,
           g.nombre AS grupo, c.nombre AS categoria,
           u.nombres + ' ' + ISNULL(u.apellidos, '') AS registrado_por
    FROM PAGO p
    JOIN ESTADO_PAGO e ON e.id_estado_pago = p.id_estado_pago
    JOIN METODO_PAGO mp ON mp.id_metodo_pago = p.id_metodo_pago
    JOIN MENSUALIDAD m ON m.id_mensualidad = p.id_mensualidad
    JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
    JOIN ALUMNO a ON a.id_alumno = i.id_alumno
    LEFT JOIN TUTOR t ON t.id_tutor = a.id_tutor
    JOIN GRUPO g ON g.id_grupo = i.id_grupo
    JOIN CATEGORIA c ON c.id_categoria = g.id_categoria
    JOIN USUARIO u ON u.id_usuario = p.id_usuario
"""


def obtener_pago(id_pago):
    p = consultar_uno(_SELECT_PAGO + " WHERE p.id_pago = ?", (id_pago,))
    if p:
        p["anulable"] = p["numero_recibo"].startswith(PREFIJO_RECIBO) and p["estado"] != "Anulado"
        mensualidad = obtener_mensualidad(p["id_mensualidad"])
        p["saldo_mensualidad"] = mensualidad["saldo"]
        p["auditoria"] = consultar("SELECT * FROM AUDITORIA_PAGO WHERE id_pago = ? ORDER BY fecha, id_auditoria", (id_pago,))
    return p


def pagos_de_alumno(id_alumno):
    return consultar(_SELECT_PAGO + " WHERE a.id_alumno = ? ORDER BY p.fecha_pago DESC, p.id_pago DESC", (id_alumno,))


def ultimos_pagos_app(cantidad=15):
    """Los últimos pagos registrados en esta app (recibos PAG-)."""
    return consultar(f"SELECT TOP {int(cantidad)} * FROM ({_SELECT_PAGO} WHERE p.numero_recibo LIKE 'PAG-%') x "
                     "ORDER BY id_pago DESC")


def _siguiente_recibo(cur):
    """PAG-0001, PAG-0002... El bloqueo evita que dos cobros tomen el mismo número."""
    cur.execute("SELECT MAX(TRY_CAST(SUBSTRING(numero_recibo, 5, 20) AS INT)) FROM PAGO WITH (UPDLOCK, HOLDLOCK) "
                "WHERE numero_recibo LIKE 'PAG-%'")
    ultimo = cur.fetchone()[0] or 0
    return f"{PREFIJO_RECIBO}{ultimo + 1:04d}"


def _auditar(cur, id_pago, operacion, usuario, monto_anterior, monto_nuevo, estado_anterior, estado_nuevo):
    """Fila de AUDITORIA_PAGO (dentro de la misma transacción que el cambio del pago)."""
    cur.execute("INSERT INTO AUDITORIA_PAGO (id_pago, operacion, usuario, monto_anterior, monto_nuevo, "
                "estado_anterior, estado_nuevo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (id_pago, operacion, usuario, monto_anterior, monto_nuevo, estado_anterior, estado_nuevo))


class MontoMayorAlSaldo(ErrorDatos):
    """El monto supera lo que se debe: la pantalla pide confirmarlo antes de guardar."""
    def __init__(self, saldo):
        super().__init__(f"El monto es mayor a lo que se debe (saldo {saldo:.2f}). Confírmalo para registrarlo igual.")
        self.saldo = saldo


def registrar_pago(id_mensualidad, id_metodo, fecha_pago, monto, usuario, confirmar_exceso=False):
    """
    Registra un pago y su auditoría en UNA transacción. El estado lo decide el saldo:
    si con este pago la mensualidad queda cubierta, Confirmado; si no, Parcial.
    Devuelve (id_pago, numero_recibo, estado).
    """
    monto = Decimal(monto)
    if monto <= 0:
        raise ErrorDatos("El monto debe ser mayor a cero.")
    if fecha_pago > date.today():
        raise ErrorDatos("La fecha de pago no puede ser futura.")
    with transaccion() as cur:
        # Bloquea la mensualidad: dos cobros simultáneos de la misma no pueden pasar el saldo
        cur.execute(f"SELECT m.monto, {PAGADO_SQL} AS pagado FROM MENSUALIDAD m WITH (UPDLOCK, HOLDLOCK) "
                    "WHERE m.id_mensualidad = ?", (id_mensualidad,))
        fila = cur.fetchone()
        if not fila:
            raise ErrorDatos("Esa mensualidad no existe.")
        saldo = fila.monto - fila.pagado
        if saldo <= 0:
            raise ErrorDatos("Esa mensualidad ya está pagada.")
        if monto > saldo and not confirmar_exceso:
            raise MontoMayorAlSaldo(saldo)
        cur.execute("SELECT 1 FROM METODO_PAGO WHERE id_metodo_pago = ? AND estado = 'ACTIVO'", (id_metodo,))
        if not cur.fetchone():
            raise ErrorDatos("Elige un método de pago válido.")
        estado = "Confirmado" if monto >= saldo else "Parcial"
        cur.execute("SELECT id_usuario FROM USUARIO WHERE LOWER(correo) = LOWER(?)", (usuario,))
        quien = cur.fetchone()
        if not quien:
            raise ErrorDatos("No se encontró el usuario que registra el pago.")
        recibo = _siguiente_recibo(cur)
        cur.execute("INSERT INTO PAGO (id_mensualidad, id_usuario, id_metodo_pago, id_estado_pago, numero_recibo, "
                    "fecha_pago, monto, observaciones) OUTPUT INSERTED.id_pago VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (id_mensualidad, quien[0], id_metodo, _id_estado(cur, estado), recibo, fecha_pago, monto,
                     "Pago parcial" if estado == "Parcial" else None))
        id_pago = cur.fetchone()[0]
        _auditar(cur, id_pago, "INSERT", usuario, None, monto, None, estado)
        return id_pago, recibo, estado


def anular_pago(id_pago, motivo, usuario):
    """
    Anula un pago PAG- con su motivo, en UNA transacción con su auditoría. La fila no se borra:
    queda con estado Anulado y la mensualidad vuelve a tener saldo (se calcula).
    """
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise ErrorDatos("Escribe el motivo de la anulación (al menos 5 letras).")
    with transaccion() as cur:
        cur.execute("SELECT p.numero_recibo, p.monto, p.observaciones, e.nombre AS estado FROM PAGO p WITH (UPDLOCK) "
                    "JOIN ESTADO_PAGO e ON e.id_estado_pago = p.id_estado_pago WHERE p.id_pago = ?", (id_pago,))
        p = cur.fetchone()
        if not p:
            raise ErrorDatos("Ese pago no existe.")
        if not p.numero_recibo.startswith(PREFIJO_RECIBO):
            raise ErrorDatos("Solo se pueden anular pagos registrados en esta app (recibos PAG-). "
                             "Los pagos REC-, SIM- y PRB- son datos anteriores y no se modifican.")
        if p.estado == "Anulado":
            raise ErrorDatos(f"El pago {p.numero_recibo} ya estaba anulado.")
        # El motivo queda en observaciones (AUDITORIA_PAGO no tiene columna para texto)
        nota = f"ANULADO {date.today():%d/%m/%Y} por {usuario}: {motivo}"
        if p.observaciones:
            nota += f" | antes: {p.observaciones}"
        cur.execute("UPDATE PAGO SET id_estado_pago = ?, observaciones = ? WHERE id_pago = ?",
                    (_id_estado(cur, "Anulado"), nota[:255], id_pago))
        _auditar(cur, id_pago, "ANULACION", usuario, p.monto, p.monto, p.estado, "Anulado")
        return p.numero_recibo
