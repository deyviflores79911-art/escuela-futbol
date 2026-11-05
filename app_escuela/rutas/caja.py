"""Caja (cobros, recibos, anulaciones) y generación de mensualidades. Solo el dueño."""
import secrets
from datetime import date

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import config
from datos import alumnos, pagos
from datos.bd import ErrorDatos
from rutas import validar
from rutas.seguridad import solo_dueno

bp = Blueprint("caja", __name__)
MAX_CLAVES = 20   # formularios de cobro abiertos a la vez por sesión


# ---------------------------------------------------------------- Claves de un solo uso (evitan cobros dobles)

def _nueva_clave_cobro():
    clave = secrets.token_urlsafe(16)
    session["claves_cobro"] = (session.get("claves_cobro", []) + [clave])[-MAX_CLAVES:]
    return clave


def _usar_clave_cobro(clave):
    """True la primera vez; False si el formulario ya se envió (doble clic o recarga)."""
    claves = session.get("claves_cobro", [])
    if clave not in claves:
        return False
    claves.remove(clave)
    session["claves_cobro"] = claves
    return True


# ---------------------------------------------------------------- Mensualidades (RF-13, HU-07)

@bp.route("/mensualidades", methods=["GET", "POST"])
@solo_dueno
def mensualidades():
    form = request.form if request.method == "POST" else request.args
    periodo = form.get("periodo") or pagos.periodo_actual()
    errores = validar.Errores()
    if not pagos.periodo_valido(periodo):
        errores["periodo"] = "El periodo debe tener la forma aaaa-mm, por ejemplo 2026-10."
        periodo = pagos.periodo_actual()
    emision, vencimiento = pagos.fechas_propuestas(periodo)
    if request.method == "POST" and not errores:
        emision = validar.fecha(form, "fecha_emision", errores, "La fecha de emisión")
        vencimiento = validar.fecha(form, "fecha_vencimiento", errores, "La fecha de vencimiento")
        if not errores:
            try:
                creadas, omitidas = pagos.generar_mensualidades(periodo, emision, vencimiento)
                partes = [f"Se crearon {creadas} mensualidad{'es' if creadas != 1 else ''} de {periodo}."]
                if omitidas:
                    partes.append(f"Se omitieron {omitidas} porque ya existían (no se duplican).")
                flash(" ".join(partes), "ok" if creadas else "aviso")
                return redirect(url_for("caja.mensualidades", periodo=periodo))
            except ErrorDatos as e:
                flash(str(e), "error")
    return render_template("caja/mensualidades.html", periodo=periodo, errores=errores,
                           emision=emision, vencimiento=vencimiento, resumen=pagos.resumen_periodo(periodo),
                           periodos=pagos.periodos_generados())


# ---------------------------------------------------------------- Caja: buscar alumno y estado de cuenta

@bp.route("/caja")
@solo_dueno
def caja():
    q = (request.args.get("q") or "").strip()[:60]
    encontrados = alumnos.buscar_alumnos(q) if q else []
    ids = [a["id_alumno"] for a in encontrados]
    saldos = pagos.saldo_por_alumno(ids)
    primeras = pagos.primera_con_saldo(ids)
    for a in encontrados:
        a["saldo"] = saldos.get(a["id_alumno"], 0)
        a["cobrar"] = primeras.get(a["id_alumno"])  # botón "Cobrar" directo a la mensualidad más antigua
    return render_template("caja/caja.html", q=q, encontrados=encontrados, ultimos=pagos.ultimos_pagos_app())


@bp.route("/caja/alumnos/<int:id_alumno>")
@solo_dueno
def cuenta(id_alumno):
    a = validar.existe_o_404(alumnos.obtener_alumno(id_alumno))
    mensualidades = pagos.mensualidades_de_alumno(id_alumno)
    return render_template("caja/cuenta.html", a=a, mensualidades=mensualidades,
                           pagos_alumno=pagos.pagos_de_alumno(id_alumno),
                           saldo_total=sum(m["saldo"] for m in mensualidades if m["saldo"] > 0))


# ---------------------------------------------------------------- Cobrar (RF-14, RF-15, RF-17, HU-08)

@bp.route("/caja/mensualidades/<int:id_mensualidad>/cobrar", methods=["GET", "POST"])
@solo_dueno
def cobrar(id_mensualidad):
    m = validar.existe_o_404(pagos.obtener_mensualidad(id_mensualidad))
    metodos = pagos.metodos_activos()
    errores = validar.Errores()
    pedir_confirmacion = False
    if request.method == "POST":
        form = request.form
        if not _usar_clave_cobro(form.get("clave_cobro")):
            flash("Ese cobro ya se había enviado (doble clic o recarga). No se registró otra vez.", "aviso")
            return redirect(url_for("caja.cuenta", id_alumno=m["id_alumno"]))
        id_metodo = validar.opcion(form, "id_metodo_pago", errores, "el método de pago",
                                   {str(x["id_metodo_pago"]) for x in metodos})
        fecha = validar.fecha(form, "fecha_pago", errores, "La fecha de pago", maxima=date.today())
        monto = validar.monto(form, "monto", errores, "El monto")
        if not errores:
            try:
                id_pago, recibo, estado = pagos.registrar_pago(
                    id_mensualidad, int(id_metodo), fecha, monto, g.usuario["correo"],
                    confirmar_exceso=form.get("confirmar_exceso") == "si")
                tipo = "pago completo" if estado == "Confirmado" else "pago parcial"
                flash(f"Pago registrado: recibo {recibo} ({tipo}).", "ok")
                return redirect(url_for("caja.recibo", id_pago=id_pago))
            except pagos.MontoMayorAlSaldo as e:
                pedir_confirmacion = True
                flash(str(e), "aviso")
            except ErrorDatos as e:
                flash(str(e), "error")
    else:
        form = {"monto": f"{m['saldo']:.2f}", "fecha_pago": date.today().isoformat()}
    if m["saldo"] <= 0 and request.method == "GET":
        flash("Esa mensualidad ya está pagada.", "aviso")
        return redirect(url_for("caja.cuenta", id_alumno=m["id_alumno"]))
    return render_template("caja/cobrar.html", m=m, form=form, errores=errores,
                           metodos_opciones=[(x["id_metodo_pago"], x["nombre"]) for x in metodos],
                           pedir_confirmacion=pedir_confirmacion, clave_cobro=_nueva_clave_cobro(),
                           hoy=date.today().isoformat())


# ---------------------------------------------------------------- Recibo y anulación (RF-15, RF-16, HU-09, HU-10)

@bp.route("/pagos/<int:id_pago>/recibo")
@solo_dueno
def recibo(id_pago):
    return render_template("caja/recibo.html", p=validar.existe_o_404(pagos.obtener_pago(id_pago)),
                           escuela=config.ESCUELA)


@bp.route("/pagos/<int:id_pago>/anular", methods=["POST"])
@solo_dueno
def anular(id_pago):
    try:
        recibo_anulado = pagos.anular_pago(id_pago, request.form.get("motivo"), g.usuario["correo"])
        flash(f"Pago {recibo_anulado} anulado. Queda en el historial y la mensualidad vuelve a tener saldo.", "ok")
    except ErrorDatos as e:
        flash(str(e), "error")
    return redirect(url_for("caja.recibo", id_pago=id_pago))
