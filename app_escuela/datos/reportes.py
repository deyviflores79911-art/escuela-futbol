"""
Reportes operativos EN VIVO desde la base transaccional: deudores, resumen de caja y "Mi grupo".
Lo que se debe se calcula igual que en la caja: monto de la mensualidad - pagos no anulados.
"""
from datetime import date
from decimal import Decimal

from datos.alumnos import numero_whatsapp
from datos.bd import consultar
from datos.catalogos import edad, listar_grupos
from datos.pagos import PAGADO_SQL

# ---------------------------------------------------------------- Deudores (RF-18, HU-11)

def deudores(periodo=None, hoy=None):
    """
    Mensualidades con saldo de un periodo (o de todos si periodo es None), con alumno, tutor,
    teléfono, categoría, monto adeudado y días de atraso. Las más atrasadas primero.
    """
    hoy = hoy or date.today()
    condiciones, params = ["x.monto > x.pagado"], []
    if periodo:
        condiciones.append("x.periodo = ?")
        params.append(periodo)
    filas = consultar(
        f"""SELECT x.id_mensualidad, x.periodo, x.fecha_vencimiento, x.monto, x.pagado, x.monto - x.pagado AS adeudado,
                   a.id_alumno, a.codigo, a.nombres, a.apellidos,
                   t.nombres + ' ' + ISNULL(t.apellidos, '') AS tutor, t.telefono, t.whatsapp,
                   g.nombre AS grupo, c.nombre AS categoria, i.estado AS estado_inscripcion
            FROM (SELECT m.id_mensualidad, m.id_inscripcion, m.periodo, m.fecha_vencimiento, m.monto,
                         {PAGADO_SQL} AS pagado FROM MENSUALIDAD m) x
            JOIN INSCRIPCION i ON i.id_inscripcion = x.id_inscripcion
            JOIN ALUMNO a ON a.id_alumno = i.id_alumno
            LEFT JOIN TUTOR t ON t.id_tutor = a.id_tutor
            JOIN GRUPO g ON g.id_grupo = i.id_grupo
            JOIN CATEGORIA c ON c.id_categoria = g.id_categoria
            WHERE {' AND '.join(condiciones)}""", params)
    for f in filas:
        f["dias_atraso"] = max((hoy - f["fecha_vencimiento"]).days, 0)
        f["vencida"] = f["fecha_vencimiento"] < hoy
        f["contacto"] = f["whatsapp"] or f["telefono"]
        f["wa"] = numero_whatsapp(f["contacto"])
    filas.sort(key=lambda f: (-f["dias_atraso"], f["apellidos"] or "", f["nombres"]))
    return filas


def periodos_disponibles():
    return [f["periodo"] for f in consultar("SELECT DISTINCT periodo FROM MENSUALIDAD ORDER BY periodo DESC")]


# ---------------------------------------------------------------- Resumen de caja (RF-19, HU-12)

def resumen_caja(desde, hasta):
    """Pagos entre dos fechas: lista completa y totales por método SIN contar los anulados."""
    pagos = consultar(
        """SELECT p.id_pago, p.numero_recibo, p.fecha_pago, p.monto, e.nombre AS estado, mp.nombre AS metodo,
                  a.nombres, a.apellidos, a.codigo, m.periodo
           FROM PAGO p
           JOIN ESTADO_PAGO e ON e.id_estado_pago = p.id_estado_pago
           JOIN METODO_PAGO mp ON mp.id_metodo_pago = p.id_metodo_pago
           JOIN MENSUALIDAD m ON m.id_mensualidad = p.id_mensualidad
           JOIN INSCRIPCION i ON i.id_inscripcion = m.id_inscripcion
           JOIN ALUMNO a ON a.id_alumno = i.id_alumno
           WHERE p.fecha_pago BETWEEN ? AND ?
           ORDER BY p.fecha_pago DESC, p.id_pago DESC""", (desde, hasta))
    validos = [p for p in pagos if p["estado"] != "Anulado"]
    metodos = [m["nombre"] for m in consultar("SELECT nombre FROM METODO_PAGO ORDER BY id_metodo_pago")]
    por_metodo = []
    for nombre in metodos:
        del_metodo = [p for p in validos if p["metodo"] == nombre]
        por_metodo.append({"metodo": nombre, "cantidad": len(del_metodo),
                           "total": sum((p["monto"] for p in del_metodo), Decimal("0"))})
    total = sum((p["monto"] for p in validos), Decimal("0"))
    anulados = [p for p in pagos if p["estado"] == "Anulado"]
    return {
        "desde": desde, "hasta": hasta, "pagos": pagos, "por_metodo": por_metodo,
        "total": total, "cantidad": len(validos),
        "anulados": len(anulados), "total_anulado": sum((p["monto"] for p in anulados), Decimal("0")),
    }


# ---------------------------------------------------------------- Mi grupo (RF-20, RF-21, HU-13, HU-14)

def mi_grupo(id_entrenador, hoy=None):
    """
    Los grupos activos del entrenador con horarios, cupo y alumnos. De cada alumno solo se entrega
    si está AL DÍA o DEBE (saldo en alguna mensualidad ya vencida): nunca montos ni métodos de pago.
    """
    if id_entrenador is None:
        return []
    hoy = hoy or date.today()
    grupos = listar_grupos(solo_activos=True, id_entrenador=id_entrenador)
    for g in grupos:
        filas = consultar(
            f"""SELECT a.id_alumno, a.codigo, a.nombres, a.apellidos, a.fecha_nacimiento,
                       (SELECT COUNT(*) FROM (SELECT m.monto, {PAGADO_SQL} AS pagado FROM MENSUALIDAD m
                                              WHERE m.id_inscripcion = i.id_inscripcion AND m.fecha_vencimiento < ?) x
                        WHERE x.monto > x.pagado) AS vencidas_con_saldo
                FROM INSCRIPCION i JOIN ALUMNO a ON a.id_alumno = i.id_alumno
                WHERE i.id_grupo = ? AND i.estado = 'ACTIVA'
                ORDER BY a.apellidos, a.nombres""", (hoy, g["id_grupo"]))
        g["alumnos"] = [{"id_alumno": f["id_alumno"], "codigo": f["codigo"],
                         "alumno": f"{f['nombres']} {f['apellidos'] or ''}".strip(),
                         "edad": edad(f["fecha_nacimiento"], hoy),
                         "fuera_de_edad": (edad(f["fecha_nacimiento"], hoy) is not None and not
                                           g["edad_minima"] <= edad(f["fecha_nacimiento"], hoy) <= g["edad_maxima"]),
                         "debe": f["vencidas_con_saldo"] > 0} for f in filas]
        g["al_dia"] = sum(1 for a in g["alumnos"] if not a["debe"])
        g["deben"] = len(g["alumnos"]) - g["al_dia"]
    return grupos


# ---------------------------------------------------------------- Edad fuera de la categoría

def fuera_de_categoria(hoy=None):
    """Alumnos con inscripción ACTIVA en un grupo que no es de su edad (también los que cumplieron años)."""
    hoy = hoy or date.today()
    filas = consultar("""SELECT a.id_alumno, a.codigo, a.nombres, a.apellidos, a.fecha_nacimiento,
                                g.nombre AS grupo, c.edad_minima, c.edad_maxima
                         FROM INSCRIPCION i JOIN ALUMNO a ON a.id_alumno = i.id_alumno
                         JOIN GRUPO g ON g.id_grupo = i.id_grupo JOIN CATEGORIA c ON c.id_categoria = g.id_categoria
                         WHERE i.estado = 'ACTIVA' ORDER BY g.nombre, a.apellidos, a.nombres""")
    lista = []
    for f in filas:
        anios = edad(f["fecha_nacimiento"], hoy)
        if anios is not None and not f["edad_minima"] <= anios <= f["edad_maxima"]:
            lista.append({"id_alumno": f["id_alumno"], "codigo": f["codigo"], "edad": anios, "grupo": f["grupo"],
                          "alumno": f"{f['nombres']} {f['apellidos'] or ''}".strip(),
                          "rango": f"{f['edad_minima']}-{f['edad_maxima']}"})
    return lista
