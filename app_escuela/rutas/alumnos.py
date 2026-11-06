"""Alumnos, tutores e inscripciones (solo el dueño)."""
from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from datos import alumnos, catalogos, pagos
from datos.bd import ErrorDatos
from rutas import validar
from rutas.seguridad import destino_interno, solo_dueno

bp = Blueprint("alumnos", __name__)


def _volver(por_defecto):
    """Vuelve a la página indicada en ?volver= (por ejemplo, la ficha del grupo)."""
    return destino_interno(request.args.get("volver"), por_defecto)


def _datos_tutor(form, errores, prefijo="", whatsapp_obligatorio=False):
    """Lee y valida los campos del tutor (prefijo 'tutor_' en el formulario del alumno)."""
    p = prefijo
    datos = {
        "nombres": validar.texto(form, p + "nombres", errores, "El nombre del tutor"),
        "apellidos": validar.texto(form, p + "apellidos", errores, "El apellido del tutor"),
        "ci": validar.texto(form, p + "ci", errores, "El CI", obligatorio=False, maximo=20),
        "telefono": validar.texto(form, p + "telefono", errores, "El teléfono", obligatorio=False, maximo=20),
        "whatsapp": validar.texto(form, p + "whatsapp", errores, "El WhatsApp", obligatorio=whatsapp_obligatorio, maximo=20),
        "correo": validar.correo(form, p + "correo", errores, obligatorio=False),
        "direccion": validar.texto(form, p + "direccion", errores, "La dirección", obligatorio=False, maximo=200),
    }
    datos["telefono"] = datos["telefono"] or datos["whatsapp"]   # casi siempre es el mismo número
    return datos


# ---------------------------------------------------------------- Inscribir (botón principal del celular)

@bp.route("/inscribir")
@solo_dueno
def inscribir_inicio():
    """Dirección vieja de "Inscribir": ahora va directo al formulario de alumno nuevo."""
    return redirect(url_for("alumnos.alumno_form"))


# ---------------------------------------------------------------- Alumnos

@bp.route("/alumnos")
@solo_dueno
def lista():
    q = (request.args.get("q") or "").strip()[:60]
    estado = request.args.get("estado") if request.args.get("estado") in ("ACTIVO", "INACTIVO", "BECADO") else None
    return render_template("alumnos/lista.html", alumnos=alumnos.buscar_alumnos(q, estado), q=q, estado=estado,
                           total=alumnos.contar_alumnos(), maximo=alumnos.MAX_RESULTADOS,
                           por_pagina=30, todos=request.args.get("todos") == "1")


@bp.route("/alumnos/<int:id_alumno>")
@solo_dueno
def ficha(id_alumno):
    a = validar.existe_o_404(alumnos.obtener_alumno(id_alumno))
    return render_template("alumnos/ficha.html", a=a, grupos=alumnos.grupos_para_inscribir(id_alumno),
                           hoy=date.today().isoformat(), sexos=alumnos.SEXOS)


@bp.route("/alumnos/nuevo", methods=["GET", "POST"], defaults={"id_alumno": None})
@bp.route("/alumnos/<int:id_alumno>/editar", methods=["GET", "POST"])
@solo_dueno
def alumno_form(id_alumno):
    actual = validar.existe_o_404(alumnos.obtener_alumno(id_alumno)) if id_alumno else {}
    errores = validar.Errores()
    if request.method == "POST":
        form = request.form
    elif actual:
        form = {**actual, "fecha_nacimiento": actual["fecha_nacimiento"] and actual["fecha_nacimiento"].isoformat(),
                "id_tutor": str(actual["id_tutor"] or "")}
    else:
        form = {"codigo": alumnos.siguiente_codigo(), "id_tutor": request.args.get("id_tutor", "")}
    if request.method == "POST":
        id_tutor = form.get("id_tutor") or ""
        tutor_nuevo = None
        if id_tutor == "nuevo":
            tutor_nuevo = _datos_tutor(form, errores, "tutor_", whatsapp_obligatorio=True)
        elif not id_tutor.isdigit():
            errores["id_tutor"] = "Busca y elige al tutor, o toca «Tutor nuevo»."
        datos = {
            "codigo": validar.texto(form, "codigo", errores, "El código", maximo=20),
            "nombres": validar.texto(form, "nombres", errores, "El nombre"),
            "apellidos": validar.texto(form, "apellidos", errores, "El apellido", obligatorio=False),  # vacío = el del tutor
            "fecha_nacimiento": validar.fecha(form, "fecha_nacimiento", errores, "La fecha de nacimiento",
                                              maxima=date.today()),
            "sexo": validar.opcion(form, "sexo", errores, "el sexo", set(alumnos.SEXOS)),
            "direccion": validar.texto(form, "direccion", errores, "La dirección", obligatorio=False, maximo=200),
            "id_tutor": int(id_tutor) if id_tutor.isdigit() else None,
            "porcentaje_beca": validar.entero(form, "porcentaje_beca", errores, "La beca", 0, 100, obligatorio=False) or 0,
        }
        if "sexo" in errores:
            errores["sexo"] = "Elige el sexo: Masculino o Femenino."
        inscribir_en, sin_grupo = None, None
        if not id_alumno:
            grupo = form.get("id_grupo") or "auto"
            if grupo.isdigit():
                inscribir_en = (int(grupo), date.today())
            elif grupo == "auto":   # lo normal: el sistema elige el grupo por la edad
                if datos["fecha_nacimiento"]:
                    elegido, sin_grupo = alumnos.grupo_para_edad(datos["fecha_nacimiento"])
                    if elegido:
                        inscribir_en = (elegido["id_grupo"], date.today())
            elif grupo != "despues":
                errores["id_grupo"] = "Elige el grupo donde entrenará (o «Inscribir después»)."
        if not errores:
            try:
                id_guardado = alumnos.guardar_alumno(id_alumno, datos, tutor_nuevo, inscribir_en)
                inscrito = f" e inscrito en {catalogos.obtener_grupo(inscribir_en[0])['nombre']}" if inscribir_en else ""
                nombre = f"{datos['nombres']} {datos['apellidos'] or ''}".strip()
                if sin_grupo:
                    flash(f"{nombre} quedó registrado sin grupo: {sin_grupo}. Inscríbelo desde su ficha cuando haya cupo.", "aviso")
                else:
                    flash(f"Alumno {nombre} guardado{inscrito}.", "ok")
                if datos["porcentaje_beca"]:
                    flash(f"Beca de {datos['porcentaje_beca']} %: se aplica a las mensualidades que se generen desde ahora"
                          + (" (no se le generan: no paga)." if datos["porcentaje_beca"] == 100 else "."), "ok")
                return redirect(url_for("alumnos.ficha", id_alumno=id_guardado))
            except ErrorDatos as e:
                flash(str(e), "error")
    id_tutor = str(form.get("id_tutor") or "")
    tutor = alumnos.obtener_tutor(int(id_tutor)) if id_tutor.isdigit() else None
    return render_template("alumnos/alumno_form.html", form=form, errores=errores, id_alumno=id_alumno,
                           tutor=tutor, tutor_nuevo=id_tutor == "nuevo", hoy_iso=date.today().isoformat(),
                           grupos=[] if id_alumno else catalogos.listar_grupos(solo_activos=True))


@bp.route("/api/tutores")
@solo_dueno
def api_tutores():
    """Búsqueda rápida de tutores para el formulario de alumno (mientras se escribe)."""
    q = (request.args.get("q") or "").strip()[:60]
    return jsonify(alumnos.tutores_para_elegir(q) if len(q) >= 2 else [])


@bp.route("/alumnos/<int:id_alumno>/beca", methods=["POST"])
@solo_dueno
def beca(id_alumno):
    """Dar, cambiar o quitar la beca desde la ficha, en cualquier momento."""
    a = validar.existe_o_404(alumnos.obtener_alumno(id_alumno))
    errores = validar.Errores()
    porcentaje = validar.entero(request.form, "porcentaje_beca", errores, "La beca", 0, 100, obligatorio=False) or 0
    if errores:
        flash(" ".join(errores.values()), "error")
        return redirect(url_for("alumnos.ficha", id_alumno=id_alumno))
    desde = pagos.periodo_actual() if request.form.get("aplicar_mes") == "si" else None
    try:
        recalculadas = alumnos.cambiar_beca(id_alumno, porcentaje, desde)
    except ErrorDatos as e:
        flash(str(e), "error")
        return redirect(url_for("alumnos.ficha", id_alumno=id_alumno))
    if porcentaje:
        texto = f"{a['nombres']} tiene ahora beca de {porcentaje} %" + (" (no paga)" if porcentaje == 100 else "") + "."
    else:
        texto = f"Se quitó la beca de {a['nombres']}: paga la mensualidad completa."
    if desde:
        texto += f" Se recalcularon {recalculadas} mensualidad{'es' if recalculadas != 1 else ''} sin pagos desde {desde}."
    else:
        texto += " Se aplica a las mensualidades que se generen desde ahora."
    flash(texto, "ok")
    return redirect(url_for("alumnos.ficha", id_alumno=id_alumno))


@bp.route("/alumnos/<int:id_alumno>/estado", methods=["POST"])
@solo_dueno
def alumno_estado(id_alumno):
    try:
        nuevo = alumnos.cambiar_estado_alumno(id_alumno)
        flash("Alumno activado. Inscríbelo en su grupo." if nuevo == "ACTIVO"
              else "Alumno dado de baja de la escuela. Su historial y sus pagos se conservan.", "ok")
    except ErrorDatos as e:
        flash(str(e), "error")
    return redirect(url_for("alumnos.ficha", id_alumno=id_alumno))


# ---------------------------------------------------------------- Inscripciones

@bp.route("/alumnos/<int:id_alumno>/inscribir", methods=["POST"])
@solo_dueno
def inscribir(id_alumno):
    errores = validar.Errores()
    id_grupo = validar.entero(request.form, "id_grupo", errores, "El grupo", 1)
    fecha = validar.fecha(request.form, "fecha_inscripcion", errores, "La fecha de inscripción")
    if errores:
        flash(" ".join(errores.values()), "error")
    else:
        try:
            _, grupo = alumnos.inscribir(id_alumno, id_grupo, fecha)
            flash(f"Inscrito en {grupo}. La inscripción quedó ACTIVA.", "ok")
        except ErrorDatos as e:
            flash(str(e), "error")
    return redirect(url_for("alumnos.ficha", id_alumno=id_alumno))


@bp.route("/inscripciones/<int:id_inscripcion>/baja", methods=["POST"])
@solo_dueno
def baja(id_inscripcion):
    try:
        id_alumno, _ = alumnos.dar_de_baja(id_inscripcion)
        flash("Inscripción dada de baja. Su historial y sus pagos se conservan.", "ok")
        return redirect(_volver(url_for("alumnos.ficha", id_alumno=id_alumno)))
    except ErrorDatos as e:
        flash(str(e), "error")
        return redirect(_volver(url_for("alumnos.lista")))


# ---------------------------------------------------------------- Tutores

@bp.route("/tutores")
@solo_dueno
def tutores():
    q = (request.args.get("q") or "").strip()[:60]
    return render_template("alumnos/tutores.html", tutores=alumnos.buscar_tutores(q), q=q,
                           maximo=alumnos.MAX_RESULTADOS)


@bp.route("/tutores/<int:id_tutor>")
@solo_dueno
def tutor(id_tutor):
    return render_template("alumnos/tutor.html", t=validar.existe_o_404(alumnos.obtener_tutor(id_tutor)))


@bp.route("/tutores/nuevo", methods=["GET", "POST"], defaults={"id_tutor": None})
@bp.route("/tutores/<int:id_tutor>/editar", methods=["GET", "POST"])
@solo_dueno
def tutor_form(id_tutor):
    actual = validar.existe_o_404(alumnos.obtener_tutor(id_tutor)) if id_tutor else {}
    errores = validar.Errores()
    form = request.form if request.method == "POST" else actual
    if request.method == "POST":
        datos = _datos_tutor(form, errores)
        if not errores:
            try:
                id_guardado = alumnos.guardar_tutor(id_tutor, datos)
                flash(f"Tutor {datos['nombres']} {datos['apellidos']} guardado.", "ok")
                return redirect(url_for("alumnos.tutor", id_tutor=id_guardado))
            except ErrorDatos as e:
                flash(str(e), "error")
    return render_template("alumnos/tutor_form.html", form=form, errores=errores, id_tutor=id_tutor)
