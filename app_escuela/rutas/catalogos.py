"""Categorías, grupos y horarios (solo el dueño)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from datos import alumnos, catalogos, lugares
from datos.bd import ErrorDatos
from rutas import validar
from rutas.seguridad import solo_dueno

bp = Blueprint("catalogos", __name__)


# ---------------------------------------------------------------- Categorías

@bp.route("/categorias")
@solo_dueno
def categorias():
    return render_template("catalogos/categorias.html", categorias=catalogos.listar_categorias())


@bp.route("/categorias/nueva", methods=["GET", "POST"], defaults={"id_categoria": None})
@bp.route("/categorias/<int:id_categoria>/editar", methods=["GET", "POST"])
@solo_dueno
def categoria_form(id_categoria):
    actual = validar.existe_o_404(catalogos.obtener_categoria(id_categoria)) if id_categoria else {}
    errores = validar.Errores()
    form = request.form if request.method == "POST" else actual
    if request.method == "POST":
        nombre = validar.texto(form, "nombre", errores, "El nombre", maximo=50)
        minima = validar.entero(form, "edad_minima", errores, "La edad mínima", 3, 25)
        maxima = validar.entero(form, "edad_maxima", errores, "La edad máxima", 3, 25)
        if not errores:
            try:
                catalogos.guardar_categoria(id_categoria, nombre, minima, maxima)
                flash(f"Categoría {nombre} guardada.", "ok")
                return redirect(url_for("catalogos.categorias"))
            except ErrorDatos as e:
                flash(str(e), "error")
    return render_template("catalogos/categoria_form.html", form=form, errores=errores, id_categoria=id_categoria)


@bp.route("/categorias/<int:id_categoria>/estado", methods=["POST"])
@solo_dueno
def categoria_estado(id_categoria):
    try:
        nuevo = catalogos.cambiar_estado_categoria(id_categoria)
        flash("Categoría activada." if nuevo == "ACTIVA" else "Categoría desactivada.", "ok")
    except ErrorDatos as e:
        flash(str(e), "error")
    return redirect(url_for("catalogos.categorias"))


# ---------------------------------------------------------------- Grupos

@bp.route("/grupos")
@solo_dueno
def grupos():
    return render_template("catalogos/grupos.html", grupos=catalogos.listar_grupos())


@bp.route("/grupos/<int:id_grupo>")
@solo_dueno
def grupo(id_grupo):
    g = validar.existe_o_404(catalogos.obtener_grupo(id_grupo))
    return render_template("catalogos/grupo.html", g=g,
                           inscritos=alumnos.inscritos_de_grupo(id_grupo, incluir_bajas=True))


@bp.route("/grupos/nuevo", methods=["GET", "POST"], defaults={"id_grupo": None})
@bp.route("/grupos/<int:id_grupo>/editar", methods=["GET", "POST"])
@solo_dueno
def grupo_form(id_grupo):
    actual = validar.existe_o_404(catalogos.obtener_grupo(id_grupo)) if id_grupo else {}
    errores = validar.Errores()
    form = request.form if request.method == "POST" else actual
    categorias = [c for c in catalogos.listar_categorias() if c["estado"] == "ACTIVA"]
    entrenadores = catalogos.entrenadores_activos()
    if request.method == "POST":
        datos = {
            "nombre": validar.texto(form, "nombre", errores, "El nombre", maximo=50),
            "id_categoria": validar.opcion(form, "id_categoria", errores, "una categoría",
                                           {str(c["id_categoria"]) for c in categorias}),
            "id_entrenador": validar.opcion(form, "id_entrenador", errores, "un entrenador",
                                            {str(e["id_entrenador"]) for e in entrenadores}),
            "cupo_maximo": validar.entero(form, "cupo_maximo", errores, "El cupo máximo", 1, 200),
            "precio_mensual": validar.monto(form, "precio_mensual", errores, "El precio mensual"),
        }
        if not errores:
            try:
                id_guardado = catalogos.guardar_grupo(id_grupo, datos)
                flash(f"Grupo {datos['nombre']} guardado.", "ok")
                return redirect(url_for("catalogos.grupo", id_grupo=id_guardado))
            except ErrorDatos as e:
                flash(str(e), "error")
    return render_template(
        "catalogos/grupo_form.html", form=form, errores=errores, id_grupo=id_grupo,
        opciones_categorias=[(c["id_categoria"], f"{c['nombre']} ({c['edad_minima']}-{c['edad_maxima']} años)")
                             for c in categorias],
        opciones_entrenadores=[(e["id_entrenador"], e["nombre"]) for e in entrenadores])


@bp.route("/grupos/<int:id_grupo>/estado", methods=["POST"])
@solo_dueno
def grupo_estado(id_grupo):
    try:
        nuevo = catalogos.cambiar_estado_grupo(id_grupo)
        flash("Grupo activado." if nuevo == "ACTIVO" else "Grupo desactivado.", "ok")
    except ErrorDatos as e:
        flash(str(e), "error")
    return redirect(url_for("catalogos.grupo", id_grupo=id_grupo))


# ---------------------------------------------------------------- Horarios

@bp.route("/grupos/<int:id_grupo>/horarios/nuevo", methods=["GET", "POST"], defaults={"id_horario": None})
@bp.route("/grupos/<int:id_grupo>/horarios/<int:id_horario>/editar", methods=["GET", "POST"])
@solo_dueno
def horario_form(id_grupo, id_horario):
    g = validar.existe_o_404(catalogos.obtener_grupo(id_grupo))
    actual = validar.existe_o_404(catalogos.obtener_horario(id_horario)) if id_horario else {}
    if actual and actual["id_grupo"] != id_grupo:
        abort(404)
    errores = validar.Errores()
    form = request.form if request.method == "POST" else {
        **actual, "hora_inicio": actual.get("hora_inicio") and actual["hora_inicio"].strftime("%H:%M"),
        "hora_fin": actual.get("hora_fin") and actual["hora_fin"].strftime("%H:%M")}
    if request.method == "POST":
        dia = validar.opcion(form, "dia_semana", errores, "un día", set(catalogos.DIAS))
        inicio = validar.hora(form, "hora_inicio", errores, "La hora de inicio")
        fin = validar.hora(form, "hora_fin", errores, "La hora de fin")
        lugar = validar.texto(form, "lugar", errores, "El lugar", obligatorio=False)
        if not errores:
            try:
                catalogos.guardar_horario(id_horario, id_grupo, dia, inicio, fin, lugar)
                flash("Horario guardado.", "ok")
                return redirect(url_for("catalogos.grupo", id_grupo=id_grupo))
            except ErrorDatos as e:
                flash(str(e), "error")
    return render_template("catalogos/horario_form.html", g=g, form=form, errores=errores, id_horario=id_horario,
                           dias=[(d, catalogos.dia_pantalla(d)) for d in catalogos.DIAS], lugares=lugares.listar())


@bp.route("/horarios/<int:id_horario>/estado", methods=["POST"])
@solo_dueno
def horario_estado(id_horario):
    try:
        nuevo, id_grupo = catalogos.cambiar_estado_horario(id_horario)
        flash("Horario activado." if nuevo == "ACTIVO" else "Horario desactivado.", "ok")
    except ErrorDatos as e:
        flash(str(e), "error")
        return redirect(url_for("catalogos.grupos"))
    return redirect(url_for("catalogos.grupo", id_grupo=id_grupo))


# ---------------------------------------------------------------- Horarios de la semana (varios grupos a la vez)

@bp.route("/horarios", methods=["GET", "POST"])
@solo_dueno
def horarios():
    """El dueño pone el horario de la semana: días + hora + lugar para varios grupos en un solo formulario."""
    grupos = catalogos.semana()
    errores = validar.Errores()
    form = request.form
    if request.method == "POST":
        quitar = form.get("accion") == "quitar"
        dias = [d for d in form.getlist("dias") if d in catalogos.DIAS]
        validos = {g["id_grupo"] for g in grupos}
        ids = [int(i) for i in form.getlist("grupos") if i.isdigit() and int(i) in validos]
        if not dias:
            errores["dias"] = "Elige al menos un día."
        if not ids:
            errores["grupos"] = "Elige al menos un grupo."
        inicio = fin = lugar = None
        if not quitar:
            inicio = validar.hora(form, "hora_inicio", errores, "La hora de inicio")
            fin = validar.hora(form, "hora_fin", errores, "La hora de fin")
            lugar = form.get("lugar") or ""
            if lugar == "__nuevo__":
                lugar = validar.texto(form, "lugar_nuevo", errores, "El nombre del lugar")
                enlace = (form.get("enlace_nuevo") or "").strip()
                if lugar and enlace and not errores:
                    try:
                        lugares.guardar(lugar, enlace)
                    except ErrorDatos as e:
                        errores["enlace_nuevo"] = str(e)
            elif lugar not in lugares.listar():
                errores["lugar"] = "Elige un lugar de la lista o agrega uno nuevo."
        if not errores:
            try:
                n_grupos, creados = catalogos.aplicar_horario(ids, dias, inicio, fin, lugar, quitar=quitar)
                nombres = ", ".join(catalogos.dia_pantalla(d) for d in catalogos.DIAS if d in dias)
                if quitar:
                    flash(f"Se quitaron los entrenamientos de {nombres} en {n_grupos} grupo(s).", "ok")
                else:
                    flash(f"Horario guardado: {nombres} {inicio:%H:%M}–{fin:%H:%M} en {lugar} "
                          f"para {n_grupos} grupo(s) ({creados} horarios).", "ok")
                return redirect(url_for("catalogos.horarios"))
            except ErrorDatos as e:
                flash(str(e), "error")
    return render_template("catalogos/horarios.html", grupos=grupos, form=form, errores=errores,
                           lugares=lugares.listar(),
                           dias=[(d, catalogos.dia_pantalla(d)) for d in catalogos.DIAS])


@bp.route("/lugares/nuevo", methods=["POST"])
@solo_dueno
def lugar_nuevo():
    try:
        lugares.guardar(request.form.get("nombre"), request.form.get("enlace"))
        flash("Lugar guardado.", "ok")
    except ErrorDatos as e:
        flash(str(e), "error")
    return redirect(url_for("catalogos.horarios") + "#lugares")


@bp.route("/lugares/quitar", methods=["POST"])
@solo_dueno
def lugar_quitar():
    try:
        lugares.quitar(request.form.get("nombre"))
        flash("Lugar quitado de la lista. Los horarios que ya lo usan no cambian.", "ok")
    except ErrorDatos as e:
        flash(str(e), "error")
    return redirect(url_for("catalogos.horarios") + "#lugares")
