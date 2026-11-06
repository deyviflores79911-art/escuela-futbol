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


def siguiente_periodo(periodo):
    anio, mes = map(int, periodo.split("-"))
    return f"{anio + 1:04d}-01" if mes == 12 else f"{anio:04d}-{mes + 1:02d}"


def periodo_actual():
    return date.today().strftime("%Y-%m")


def metodo_sugerido(id_alumno):
    """El método con que pagó la última vez este alumno; si nunca pagó, el más usado en la escuela."""
    fila = consultar_uno(
        """SELECT TOP 1 p.id_metodo_pago FROM PAGO p
           JOIN ESTADO_PAGO e ON e.id_estado_pago = p.id_estado_pago
           JOIN MENSUALIDAD m ON m.id_mensualidad = p.id_mensualidad
           JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
           WHERE i.id_alumno = ? AND e.nombre <> 'Anulado'
           ORDER BY p.fecha_pago DESC, p.id_pago DESC""", (id_alumno,))
    if not fila:
        fila = consultar_uno("SELECT TOP 1 id_metodo_pago FROM PAGO GROUP BY id_metodo_pago ORDER BY COUNT(*) DESC")
    return fila["id_metodo_pago"] if fila else None


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
           JOIN ALUMNO a ON a.id_alumno = i.id_alumno
           OUTER APPLY (SELECT COUNT(*) AS n FROM MENSUALIDAD m
                        WHERE m.id_inscripcion = i.id_inscripcion AND m.periodo = ?) x
           WHERE i.estado = 'ACTIVA' AND g.estado = 'ACTIVO' AND a.porcentaje_beca < 100""", (periodo,))


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
               SELECT i.id_inscripcion, ?, ?, ?, ROUND(g.precio_mensual * (100 - a.porcentaje_beca) / 100, 2), 'PENDIENTE'
               FROM INSCRIPCION i JOIN GRUPO g ON g.id_grupo = i.id_grupo
               JOIN ALUMNO a ON a.id_alumno = i.id_alumno   -- beca: descuento en %; con 100 % no paga
               WHERE i.estado = 'ACTIVA' AND g.estado = 'ACTIVO' AND a.porcentaje_beca < 100
                 AND NOT EXISTS (SELECT 1 FROM MENSUALIDAD m WITH (UPDLOCK, HOLDLOCK)
                                 WHERE m.id_inscripcion = i.id_inscripcion AND m.periodo = ?)
                 AND NOT EXISTS (SELECT 1 FROM MENSUALIDAD m JOIN INSCRIPCION i2 ON i2.id_inscripcion = m.id_inscripcion
                                 WHERE i2.id_alumno = i.id_alumno AND i2.estado = 'BAJA' AND m.periodo = ?)""",
            (periodo, fecha_emision, fecha_vencimiento, periodo, periodo))
        return cur.rowcount, omitidas


_mes_listo = None   # último día en que ya se revisó el mes en curso (en este proceso)


def asegurar_mes_actual(hoy=None):
    """Las mensualidades del mes se crean solas: la primera página del día crea las que falten del mes en curso."""
    global _mes_listo
    hoy = hoy or date.today()
    if _mes_listo == hoy:
        return 0
    periodo = hoy.strftime("%Y-%m")
    creadas, _ = generar_mensualidades(periodo, *fechas_propuestas(periodo))
    _mes_listo = hoy
    return creadas


# ---------------------------------------------------------------- Varios meses juntos / adelantado / no vino

NO_VINO = "NO VINO"   # MENSUALIDAD.estado de un mes que no se cobra (monto 0)
MAX_MESES = 12


def _plan(cur, id_alumno, n):
    """Los n meses que se cobran juntos: primero los que debe (del más antiguo) y después, adelantados, los que vienen."""
    cur.execute(f"""SELECT m.id_mensualidad, m.periodo, m.monto - {PAGADO_SQL} AS saldo, m.fecha_vencimiento
                    FROM MENSUALIDAD m JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
                    WHERE i.id_alumno = ? AND m.monto > {PAGADO_SQL}
                    ORDER BY m.periodo, m.fecha_vencimiento""", (id_alumno,))
    plan = [{"id_mensualidad": f[0], "periodo": f[1], "saldo": f[2], "vence": f[3]} for f in cur.fetchall()][:n]
    if len(plan) < n:
        cur.execute("""SELECT TOP 1 i.id_inscripcion, ROUND(g.precio_mensual * (100 - a.porcentaje_beca) / 100, 2)
                       FROM INSCRIPCION i JOIN GRUPO g ON g.id_grupo = i.id_grupo JOIN ALUMNO a ON a.id_alumno = i.id_alumno
                       WHERE i.id_alumno = ? AND i.estado = 'ACTIVA' AND g.estado = 'ACTIVO' AND a.estado = 'ACTIVO'
                         AND a.porcentaje_beca < 100
                       ORDER BY i.id_inscripcion""", (id_alumno,))
        ins = cur.fetchone()
        if ins and ins[1] > 0:
            cur.execute("SELECT MAX(m.periodo) FROM MENSUALIDAD m JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion "
                        "WHERE i.id_alumno = ?", (id_alumno,))
            ultimo = cur.fetchone()[0]
            p = max(siguiente_periodo(ultimo), periodo_actual()) if ultimo else periodo_actual()
            while len(plan) < n:
                emision, vence = fechas_propuestas(p)
                plan.append({"id_mensualidad": None, "periodo": p, "saldo": ins[1], "vence": vence,
                             "emision": emision, "id_inscripcion": ins[0]})
                p = siguiente_periodo(p)
    return plan


def plan_de_meses(id_alumno, n=6):
    with transaccion() as cur:
        return _plan(cur, id_alumno, n)


def opciones_de_meses(id_alumno):
    """Para elegir en Cobrar: de 1 a 12 meses; primero lo que debe y el resto adelantado, con el total de cada opción."""
    plan = plan_de_meses(id_alumno, MAX_MESES)
    opciones = []
    for c in range(1, len(plan) + 1):
        deben = sum(1 for x in plan[:c] if x["id_mensualidad"])
        partes = ([f"debe {deben}"] if deben else []) + ([f"{c - deben} adelantado{'s' if c - deben != 1 else ''}"] if c > deben else [])
        opciones.append({"n": c, "total": sum(x["saldo"] for x in plan[:c]), "detalle": " + ".join(partes),
                         "periodos": ", ".join(x["periodo"] for x in plan[:c])})
    return opciones


def cobrar_meses(id_alumno, n, id_metodo, fecha_pago, usuario):
    """
    Cobra n meses completos de una vez (los que debe y, si alcanza, adelantados) en UNA transacción.
    Un pago por mes, todos con la misma observación: el recibo los muestra juntos. Devuelve (id_pago, recibos).
    """
    if not 1 <= n <= MAX_MESES:
        raise ErrorDatos(f"Se pueden cobrar de 1 a {MAX_MESES} meses.")
    if fecha_pago > date.today():
        raise ErrorDatos("La fecha de pago no puede ser futura.")
    with transaccion() as cur:
        cur.execute("SELECT COUNT(*) FROM MENSUALIDAD m WITH (UPDLOCK, HOLDLOCK) "
                    "JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion WHERE i.id_alumno = ?", (id_alumno,))
        cur.fetchone()
        plan = _plan(cur, id_alumno, n)
        if len(plan) < n:
            raise ErrorDatos(f"Solo hay {len(plan)} mes{'es' if len(plan) != 1 else ''} para cobrar "
                             "(para adelantar, el alumno tiene que estar inscrito en un grupo).")
        cur.execute("SELECT 1 FROM METODO_PAGO WHERE id_metodo_pago = ? AND estado = 'ACTIVO'", (id_metodo,))
        if not cur.fetchone():
            raise ErrorDatos("Elige un método de pago válido.")
        cur.execute("SELECT id_usuario FROM USUARIO WHERE LOWER(correo) = LOWER(?)", (usuario,))
        quien = cur.fetchone()
        if not quien:
            raise ErrorDatos("No se encontró el usuario que registra el pago.")
        confirmado = _id_estado(cur, "Confirmado")
        ids, recibos, nota = [], [], None
        for x in plan:
            if x["id_mensualidad"] is None:
                cur.execute("INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado) "
                            "OUTPUT INSERTED.id_mensualidad VALUES (?, ?, ?, ?, ?, 'PENDIENTE')",
                            (x["id_inscripcion"], x["periodo"], x["emision"], x["vence"], x["saldo"]))
                x["id_mensualidad"] = cur.fetchone()[0]
            recibo = _siguiente_recibo(cur)
            if n > 1 and nota is None:
                nota = f"Cobro de {n} meses · {recibo}"
            cur.execute("INSERT INTO PAGO (id_mensualidad, id_usuario, id_metodo_pago, id_estado_pago, numero_recibo, "
                        "fecha_pago, monto, observaciones) OUTPUT INSERTED.id_pago VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (x["id_mensualidad"], quien[0], id_metodo, confirmado, recibo, fecha_pago, x["saldo"], nota))
            id_pago = cur.fetchone()[0]
            _auditar(cur, id_pago, "INSERT", usuario, None, x["saldo"], None, "Confirmado")
            ids.append(id_pago)
            recibos.append(recibo)
        return ids[0], recibos


def marcar_no_vino(id_mensualidad):
    """El alumno no vino ese mes: no se le cobra (monto 0). Solo si ese mes no tiene pagos. Devuelve (id_alumno, periodo)."""
    with transaccion() as cur:
        cur.execute(f"SELECT i.id_alumno, m.periodo, {PAGADO_SQL} FROM MENSUALIDAD m WITH (UPDLOCK) "
                    "JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion WHERE m.id_mensualidad = ?", (id_mensualidad,))
        f = cur.fetchone()
        if not f:
            raise ErrorDatos("Esa mensualidad no existe.")
        if f[2] > 0:
            raise ErrorDatos("Ese mes ya tiene pagos: primero anula el pago desde su recibo.")
        cur.execute("UPDATE MENSUALIDAD SET monto = 0, estado = ? WHERE id_mensualidad = ?", (NO_VINO, id_mensualidad))
        return f[0], f[1]


def volver_a_cobrar(id_mensualidad):
    """Deshace «No vino»: el mes vuelve a cobrarse con el precio del grupo y la beca de ahora."""
    with transaccion() as cur:
        cur.execute("""UPDATE m SET monto = ROUND(g.precio_mensual * (100 - a.porcentaje_beca) / 100, 2), estado = 'PENDIENTE'
                       OUTPUT i.id_alumno
                       FROM MENSUALIDAD m JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
                       JOIN GRUPO g ON g.id_grupo = i.id_grupo JOIN ALUMNO a ON a.id_alumno = i.id_alumno
                       WHERE m.id_mensualidad = ? AND m.estado = ?""", (id_mensualidad, NO_VINO))
        f = cur.fetchone()
        if not f:
            raise ErrorDatos("Ese mes no estaba marcado como «No vino».")
        return f[0]


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
                   {PAGADO_SQL} AS pagado, g.nombre AS grupo, i.estado AS estado_inscripcion, m.estado AS marca
            FROM MENSUALIDAD m
            JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
            JOIN GRUPO g ON g.id_grupo = i.id_grupo
            WHERE i.id_alumno = ?
            ORDER BY m.periodo DESC, g.nombre""", (id_alumno,))
    for m in filas:
        m["saldo"] = m["monto"] - m["pagado"]
        m["estado"] = "No vino" if m["marca"] == NO_VINO else _estado_mensualidad(m)
        m["dias_atraso"] = (date.today() - m["fecha_vencimiento"]).days if m["estado"] == "Vencida" else 0
    return filas


def obtener_mensualidad(id_mensualidad):
    m = consultar_uno(
        f"""SELECT m.id_mensualidad, m.periodo, m.fecha_emision, m.fecha_vencimiento, m.monto, {PAGADO_SQL} AS pagado,
                   a.id_alumno, a.codigo, a.nombres, a.apellidos, a.porcentaje_beca, g.nombre AS grupo, c.nombre AS categoria,
                   ISNULL(t.whatsapp, t.telefono) AS tutor_celular, t.correo AS tutor_correo
            FROM MENSUALIDAD m
            JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
            JOIN ALUMNO a ON a.id_alumno = i.id_alumno
            LEFT JOIN TUTOR t ON t.id_tutor = a.id_tutor
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
           ISNULL(t.whatsapp, t.telefono) AS tutor_celular, t.correo AS tutor_correo,
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
        # Cobro de varios meses: todos sus pagos van en el mismo recibo
        p["juntos"] = []
        if (p["observaciones"] or "").startswith("Cobro de ") and p["estado"] != "Anulado":
            p["juntos"] = consultar(_SELECT_PAGO + " WHERE p.observaciones = ? AND e.nombre <> 'Anulado' ORDER BY m.periodo",
                                    (p["observaciones"],))
        p["lineas"] = p["juntos"] or [p]
        p["total"] = sum(x["monto"] for x in p["lineas"])
        p["auditoria"] = consultar("SELECT * FROM AUDITORIA_PAGO WHERE id_pago = ? ORDER BY fecha, id_auditoria", (id_pago,))
    return p


def pagos_de_alumno(id_alumno):
    return consultar(_SELECT_PAGO + " WHERE a.id_alumno = ? ORDER BY p.fecha_pago DESC, p.id_pago DESC", (id_alumno,))


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
