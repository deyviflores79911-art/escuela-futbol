"""El dueño crea, edita, desactiva y reactiva usuarios entrenadores."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from datos import usuarios
from datos.bd import ErrorDatos
from rutas import validar
from rutas.seguridad import solo_dueno

bp = Blueprint("usuarios", __name__, url_prefix="/entrenadores")


@bp.route("/")
@solo_dueno
def lista():
    return render_template("usuarios/lista.html", entrenadores=usuarios.listar_entrenadores())


@bp.route("/nuevo", methods=["GET", "POST"])
@solo_dueno
def nuevo():
    errores = validar.Errores()
    form = request.form
    if request.method == "POST":
        id_entrenador = form.get("id_entrenador") or None
        datos = {}
        if not id_entrenador:
            datos = {
                "nombres": validar.texto(form, "nombres", errores, "El nombre"),
                "apellidos": validar.texto(form, "apellidos", errores, "El apellido"),
                "correo": validar.correo(form, "correo", errores),
                "ci": validar.texto(form, "ci", errores, "El CI", obligatorio=False, maximo=20),
                "telefono": validar.texto(form, "telefono", errores, "El teléfono", obligatorio=False, maximo=20),
                "especialidad": validar.texto(form, "especialidad", errores, "La especialidad", obligatorio=False),
            }
        elif not id_entrenador.isdigit():
            errores["id_entrenador"] = "Elige un entrenador de la lista."
        clave = validar.clave(form, "clave", errores, campo_repetir="repetir")
        if not errores:
            try:
                usuarios.crear_entrenador(datos, clave, int(id_entrenador) if id_entrenador else None)
                flash("Entrenador creado. Ya puede entrar con su correo y la contraseña inicial.", "ok")
                return redirect(url_for("usuarios.lista"))
            except ErrorDatos as e:
                flash(str(e), "error")
    return render_template("usuarios/nuevo.html", errores=errores, form=form,
                           existentes=usuarios.entrenadores_sin_usuario())


def _entrenador_o_404(id_usuario):
    u = usuarios.buscar_por_id(id_usuario)
    if not u or u["rol"] != usuarios.ENTRENADOR:
        abort(404)
    return u


@bp.route("/<int:id_usuario>/editar", methods=["GET", "POST"])
@solo_dueno
def editar(id_usuario):
    u = _entrenador_o_404(id_usuario)
    errores = validar.Errores()
    form = request.form if request.method == "POST" else u
    if request.method == "POST":
        nombres = validar.texto(form, "nombres", errores, "El nombre")
        apellidos = validar.texto(form, "apellidos", errores, "El apellido")
        telefono = validar.texto(form, "telefono", errores, "El teléfono", obligatorio=False, maximo=20)
        clave = validar.clave(form, "clave", errores, obligatorio=False, campo_repetir="repetir")
        if not errores:
            try:
                usuarios.editar_entrenador(id_usuario, nombres, apellidos, telefono, clave)
                flash("Datos guardados.", "ok")
                return redirect(url_for("usuarios.lista"))
            except ErrorDatos as e:
                flash(str(e), "error")
    return render_template("usuarios/editar.html", u=u, form=form, errores=errores)


@bp.route("/<int:id_usuario>/estado", methods=["POST"])
@solo_dueno
def cambiar_estado(id_usuario):
    u = _entrenador_o_404(id_usuario)
    nuevo = "INACTIVO" if u["estado"] == "ACTIVO" else "ACTIVO"
    try:
        usuarios.cambiar_estado_entrenador(id_usuario, nuevo)
        accion = "desactivado: ya no puede entrar" if nuevo == "INACTIVO" else "activado de nuevo"
        flash(f"{u['nombres']} {u['apellidos'] or ''} fue {accion}.", "ok")
    except ErrorDatos as e:
        flash(str(e), "error")
    return redirect(url_for("usuarios.lista"))
