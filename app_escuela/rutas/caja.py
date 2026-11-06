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
from datos import alumnos, correo, pagos
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
    return render_template("caja/caja.html", q=q, encontrados=encontrados)


@bp.route("/caja/alumnos/<int:id_alumno>")
@solo_dueno
def cuenta(id_alumno):
    a = validar.existe_o_404(alumnos.obtener_alumno(id_alumno))
    mensualidades = pagos.mensualidades_de_alumno(id_alumno)
    # Lo que se debe va arriba y de la más vieja a la más nueva: se cobra primero la más atrasada
    deudas = sorted((m for m in mensualidades if m["saldo"] > 0), key=lambda m: (m["fecha_vencimiento"], m["periodo"]))
    return render_template("caja/cuenta.html", a=a, deudas=deudas,
                           pagadas=[m for m in mensualidades if m["saldo"] <= 0],
                           pagos_alumno=pagos.pagos_de_alumno(id_alumno),
                           saldo_total=sum(m["saldo"] for m in deudas))


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
        meses = _meses(form)
        monto = validar.monto(form, "monto", errores, "El monto") if meses == 1 else None
        if not errores:
            try:
                if meses > 1:
                    id_pago, recibos = pagos.cobrar_meses(m["id_alumno"], meses, int(id_metodo), fecha, g.usuario["correo"])
                    flash(f"Cobro de {meses} meses registrado: recibos {recibos[0]} a {recibos[-1]}.", "ok")
                else:
                    id_pago, recibo, estado = pagos.registrar_pago(
                        id_mensualidad, int(id_metodo), fecha, monto, g.usuario["correo"],
                        confirmar_exceso=form.get("confirmar_exceso") == "si")
                    tipo = "pago completo" if estado == "Confirmado" else "pago parcial"
                    flash(f"Pago registrado: recibo {recibo} ({tipo}).", "ok")
                if form.get("enviar_correo") == "si" and correo.configurado():
                    _enviar_recibo_por_correo(pagos.obtener_pago(id_pago))
                # WhatsApp: el recibo se abre con el mensaje listo; el dueño solo toca Enviar
                return redirect(url_for("caja.recibo", id_pago=id_pago,
                                        whatsapp=1 if form.get("enviar_whatsapp") == "si" else None))
            except pagos.MontoMayorAlSaldo as e:
                pedir_confirmacion = True
                flash(str(e), "aviso")
            except ErrorDatos as e:
                flash(str(e), "error")
    else:
        form = {"monto": f"{m['saldo']:.2f}", "fecha_pago": date.today().isoformat(),
                "id_metodo_pago": pagos.metodo_sugerido(m["id_alumno"]),
                "enviar_whatsapp": "si" if m["tutor_celular"] else "",
                "enviar_correo": "si" if m["tutor_correo"] and correo.configurado() else ""}
    if m["saldo"] <= 0 and request.method == "GET":
        flash("Esa mensualidad ya está pagada.", "aviso")
        return redirect(url_for("caja.cuenta", id_alumno=m["id_alumno"]))
    opciones = pagos.opciones_de_meses(m["id_alumno"])
    if opciones:
        opciones[0]["total"] = m["saldo"]   # 1 mes: el que se abrió (se puede pagar una parte)
    return render_template("caja/cobrar.html", m=m, form=form, errores=errores, opciones_meses=opciones,
                           metodos_opciones=[(x["id_metodo_pago"], x["nombre"]) for x in metodos],
                           pedir_confirmacion=pedir_confirmacion, clave_cobro=_nueva_clave_cobro(),
                           hoy=date.today().isoformat(), correo_listo=correo.configurado())


def _meses(form):
    try:
        return min(max(int(form.get("meses") or 1), 1), pagos.MAX_MESES)
    except ValueError:
        return 1


@bp.route("/caja/alumnos/<int:id_alumno>/adelantar", methods=["GET", "POST"])
@solo_dueno
def adelantar(id_alumno):
    """Pagar por adelantado (no debe nada): se elige cuántos meses y se crean al cobrar."""
    a = validar.existe_o_404(alumnos.obtener_alumno(id_alumno))
    plan = pagos.plan_de_meses(id_alumno, 6)
    if plan and plan[0]["id_mensualidad"]:   # si debe algo, se cobra desde lo que debe
        return redirect(url_for("caja.cobrar", id_mensualidad=plan[0]["id_mensualidad"]))
    if not plan:
        flash(f"{a['nombres']} no está inscrito en un grupo (o tiene beca completa): no hay meses para adelantar.", "aviso")
        return redirect(url_for("caja.cuenta", id_alumno=id_alumno))
    metodos = pagos.metodos_activos()
    errores = validar.Errores()
    if request.method == "POST":
        form = request.form
        if not _usar_clave_cobro(form.get("clave_cobro")):
            flash("Ese cobro ya se había enviado (doble clic o recarga). No se registró otra vez.", "aviso")
            return redirect(url_for("caja.cuenta", id_alumno=id_alumno))
        id_metodo = validar.opcion(form, "id_metodo_pago", errores, "el método de pago",
                                   {str(x["id_metodo_pago"]) for x in metodos})
        fecha = validar.fecha(form, "fecha_pago", errores, "La fecha de pago", maxima=date.today())
        if not errores:
            try:
                meses = _meses(form)
                id_pago, recibos = pagos.cobrar_meses(id_alumno, meses, int(id_metodo), fecha, g.usuario["correo"])
                flash(f"Pago adelantado de {meses} mes{'es' if meses != 1 else ''}: recibo{'s' if meses != 1 else ''} "
                      f"{recibos[0]}{' a ' + recibos[-1] if meses > 1 else ''}.", "ok")
                if form.get("enviar_correo") == "si" and correo.configurado():
                    _enviar_recibo_por_correo(pagos.obtener_pago(id_pago))
                return redirect(url_for("caja.recibo", id_pago=id_pago,
                                        whatsapp=1 if form.get("enviar_whatsapp") == "si" else None))
            except ErrorDatos as e:
                flash(str(e), "error")
    else:
        form = {"fecha_pago": date.today().isoformat(), "id_metodo_pago": pagos.metodo_sugerido(id_alumno),
                "enviar_whatsapp": "si" if (a["tutor_whatsapp"] or a["tutor_telefono"]) else "",
                "enviar_correo": "si" if a.get("tutor_correo") and correo.configurado() else ""}
    x = plan[0]
    m = {"id_alumno": id_alumno, "nombres": a["nombres"], "apellidos": a["apellidos"], "periodo": x["periodo"],
         "grupo": a["grupos"], "fecha_vencimiento": x["vence"], "porcentaje_beca": a["porcentaje_beca"],
         "saldo": x["saldo"], "pagado": 0, "monto": x["saldo"],
         "tutor_celular": a["tutor_whatsapp"] or a["tutor_telefono"], "tutor_correo": a.get("tutor_correo")}
    form = dict(form)
    form.setdefault("monto", f"{x['saldo']:.2f}")
    return render_template("caja/cobrar.html", m=m, form=form, errores=errores, adelantar=True,
                           opciones_meses=pagos.opciones_de_meses(id_alumno),
                           metodos_opciones=[(x["id_metodo_pago"], x["nombre"]) for x in metodos],
                           pedir_confirmacion=False, clave_cobro=_nueva_clave_cobro(),
                           hoy=date.today().isoformat(), correo_listo=correo.configurado())


@bp.route("/caja/mensualidades/<int:id_mensualidad>/no-vino", methods=["POST"])
@solo_dueno
def no_vino(id_mensualidad):
    try:
        id_alumno, periodo = pagos.marcar_no_vino(id_mensualidad)
        flash(f"Mes {periodo}: no vino, no se cobra.", "ok")
        return redirect(url_for("caja.cuenta", id_alumno=id_alumno))
    except ErrorDatos as e:
        flash(str(e), "error")
        m = pagos.obtener_mensualidad(id_mensualidad)
        return redirect(url_for("caja.cuenta", id_alumno=m["id_alumno"]) if m else url_for("caja.caja"))


@bp.route("/caja/mensualidades/<int:id_mensualidad>/cobrar-igual", methods=["POST"])
@solo_dueno
def cobrar_igual(id_mensualidad):
    try:
        id_alumno = pagos.volver_a_cobrar(id_mensualidad)
        flash("Ese mes se vuelve a cobrar.", "ok")
        return redirect(url_for("caja.cuenta", id_alumno=id_alumno))
    except ErrorDatos as e:
        flash(str(e), "error")
        return redirect(url_for("caja.caja"))


# ---------------------------------------------------------------- Recibo y anulación (RF-15, RF-16, HU-09, HU-10)

@bp.route("/pagos/<int:id_pago>/recibo")
@solo_dueno
def recibo(id_pago):
    p = validar.existe_o_404(pagos.obtener_pago(id_pago))
    return render_template("caja/recibo.html", p=p, escuela=config.ESCUELA,
                           wa=alumnos.numero_whatsapp(p["tutor_celular"]) or "",
                           mensaje_wa=render_template("caja/_mensaje_recibo.txt", p=p, escuela=config.ESCUELA).strip(),
                           abrir_whatsapp=request.args.get("whatsapp") == "1", correo_listo=correo.configurado(),
                           siguiente=pagos.primera_con_saldo([p["id_alumno"]]).get(p["id_alumno"]))


def _enviar_recibo_por_correo(p):
    """Manda el recibo al correo del tutor. Si falla, el pago igual queda registrado: solo se avisa."""
    if p["estado"] == "Anulado":
        flash("Ese recibo está anulado: no se envía.", "aviso")
        return False
    try:
        escudo = (config.CARPETA / "estaticos" / config.ESCUELA["escudo"]).read_bytes()
        correo.enviar(p["tutor_correo"], f"Recibo {p['numero_recibo']} · {config.ESCUELA['nombre']}",
                      render_template("caja/_mensaje_recibo.txt", p=p, escuela=config.ESCUELA),
                      render_template("caja/recibo_correo.html", p=p, escuela=config.ESCUELA),
                      imagen=("escudo", escudo, "png"))
    except ErrorDatos as e:
        flash(str(e), "aviso")
        return False
    flash(f"Recibo enviado por correo a {p['tutor_correo']}.", "ok")
    return True


@bp.route("/pagos/<int:id_pago>/enviar-correo", methods=["POST"])
@solo_dueno
def enviar_correo(id_pago):
    _enviar_recibo_por_correo(validar.existe_o_404(pagos.obtener_pago(id_pago)))
    return redirect(url_for("caja.recibo", id_pago=id_pago))


@bp.route("/pagos/<int:id_pago>/anular", methods=["POST"])
@solo_dueno
def anular(id_pago):
    try:
        p = pagos.obtener_pago(id_pago)
        otros = [x["id_pago"] for x in (p["juntos"] if p else []) if x["id_pago"] != id_pago]
        recibo_anulado = pagos.anular_pago(id_pago, request.form.get("motivo"), g.usuario["correo"])
        for otro in otros:
            pagos.anular_pago(otro, request.form.get("motivo"), g.usuario["correo"])
        if otros:
            flash(f"Cobro de {len(otros) + 1} meses anulado. Queda en el historial y esos meses vuelven a tener saldo.", "ok")
        else:
            flash(f"Pago {recibo_anulado} anulado. Queda en el historial y la mensualidad vuelve a tener saldo.", "ok")
    except ErrorDatos as e:
        flash(str(e), "error")
    return redirect(url_for("caja.recibo", id_pago=id_pago))
