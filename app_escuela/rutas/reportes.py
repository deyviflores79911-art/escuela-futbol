"""Reportes en vivo: deudores y resumen de caja (dueño) y "Mi grupo" (entrenador y dueño)."""
from datetime import date, datetime, timedelta

from flask import Blueprint, g, render_template, request

from datos import pagos, reportes
from datos.catalogos import orden_categoria
from rutas.seguridad import login_requerido, solo_dueno

bp = Blueprint("reportes", __name__)
SEGUNDOS_REFRESCO = 45   # las pantallas operativas se actualizan solas cada 45 s


def _fecha_param(nombre, por_defecto):
    try:
        return datetime.strptime(request.args.get(nombre, ""), "%Y-%m-%d").date()
    except ValueError:
        return por_defecto


def _rango_caja():
    hoy = date.today()
    desde, hasta = _fecha_param("desde", hoy), _fecha_param("hasta", hoy)
    return (hasta, desde) if desde > hasta else (desde, hasta)


@bp.route("/reportes/deudores")
@solo_dueno
def deudores():
    periodos = reportes.periodos_disponibles()
    pedido = request.args.get("periodo")
    if pedido == "todos":
        periodo = None
    elif pedido in periodos:
        periodo = pedido
    else:  # por defecto el mes actual; si todavía no tiene mensualidades, el último que sí tiene
        periodo = pagos.periodo_actual() if pagos.periodo_actual() in periodos else (periodos[0] if periodos else None)
    sin_mes_actual = pedido is None and pagos.periodo_actual() not in periodos
    todos = reportes.deudores(periodo)
    categoria = request.args.get("categoria") or ""
    lista = [d for d in todos if not categoria or d["categoria"] == categoria]
    categorias = sorted({d["categoria"] for d in todos}, key=orden_categoria)
    return render_template("reportes/deudores.html", deudores=lista, periodos=periodos, periodo=periodo,
                           categoria=categoria, categorias=categorias, sin_mes_actual=sin_mes_actual,
                           mes_actual=pagos.periodo_actual(), total=sum(d["adeudado"] for d in lista),
                           refresco=SEGUNDOS_REFRESCO, ahora=datetime.now())


@bp.route("/reportes/caja")
@solo_dueno
def caja():
    desde, hasta = _rango_caja()
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    fin_mes_anterior = inicio_mes - timedelta(days=1)
    atajos = [("Hoy", hoy, hoy), ("Ayer", hoy - timedelta(days=1), hoy - timedelta(days=1)),
              ("Este mes", inicio_mes, hoy), ("Mes anterior", fin_mes_anterior.replace(day=1), fin_mes_anterior)]
    return render_template("reportes/caja.html", r=reportes.resumen_caja(desde, hasta), atajos=atajos,
                           refresco=SEGUNDOS_REFRESCO, ahora=datetime.now())


@bp.route("/mi-grupo")
@login_requerido
def mi_grupo():
    """Solo los grupos del usuario (por su ficha de entrenador). Cualquier parámetro en la dirección se ignora."""
    return render_template("reportes/mi_grupo.html", grupos=reportes.mi_grupo(g.usuario["id_entrenador"]),
                           refresco=SEGUNDOS_REFRESCO, ahora=datetime.now())
