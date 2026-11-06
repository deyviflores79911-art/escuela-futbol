"""Iniciar sesión, cerrar sesión, inicio según rol y cambio de contraseña."""
from datetime import date

from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from datos import alumnos, pagos, reportes, usuarios
from datos.cambios import huella
from rutas import validar
from rutas.seguridad import destino_interno, iniciar_sesion, login_requerido

bp = Blueprint("acceso", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.usuario:
        return redirect(url_for("acceso.inicio"))
    correo = ""
    if request.method == "POST":
        correo = (request.form.get("correo") or "").strip()
        clave = request.form.get("clave") or ""
        if not correo or not clave:
            flash("Escribe tu correo y tu contraseña.", "error")
        else:
            u, error = usuarios.verificar_login(correo, clave)
            if error:
                flash(error, "error")
            else:
                iniciar_sesion(u)
                return redirect(destino_interno(request.args.get("siguiente"), url_for("acceso.inicio")))
    return render_template("login.html", correo=correo)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Cerraste sesión.", "ok")
    return redirect(url_for("acceso.login"))


@bp.route("/")
@login_requerido
def inicio():
    if g.usuario["rol"] == usuarios.DUENO:
        deudas = reportes.deudores()
        hoy = reportes.resumen_caja(date.today(), date.today())
        return render_template("inicio_dueno.html", hoy=hoy, alumnos=alumnos.contar_alumnos(),
                               fuera_de_edad=reportes.fuera_de_categoria(),
                               mes=pagos.periodo_actual(), mes_resumen=pagos.resumen_periodo(pagos.periodo_actual()),
                               deudas={"cantidad": len(deudas), "total": sum(d["adeudado"] for d in deudas)})
    return render_template("inicio_entrenador.html", grupos=reportes.mi_grupo(g.usuario["id_entrenador"]),
                           hoy=date.today())


@bp.route("/mi-clave", methods=["GET", "POST"])
@login_requerido
def mi_clave():
    errores = validar.Errores()
    if request.method == "POST":
        actual = request.form.get("actual") or ""
        nueva = validar.clave(request.form, "nueva", errores, campo_repetir="repetir")
        _, error = usuarios.verificar_login(g.usuario["correo"], actual)
        if error:
            errores["actual"] = "La contraseña actual no es correcta."
        if not errores:
            usuarios.cambiar_clave(g.usuario["id_usuario"], nueva)
            flash("Tu contraseña se cambió.", "ok")
            return redirect(url_for("acceso.inicio"))
    return render_template("mi_clave.html", errores=errores)


@bp.route("/api/cambios")
@login_requerido
def cambios():
    """Huella de los datos: las pantallas la consultan cada pocos segundos y se actualizan solas si cambia."""
    return jsonify({"huella": huella()})
