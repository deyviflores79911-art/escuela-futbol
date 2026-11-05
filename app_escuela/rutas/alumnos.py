"""Alumnos, tutores e inscripciones (solo el dueño)."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from datos import alumnos, catalogos
from datos.bd import ErrorDatos
from rutas import validar
from rutas.seguridad import destino_interno, solo_dueno

bp = Blueprint("alumnos", __name__)


def _volver(por_defecto):
    """Vuelve a la página indicada en ?volver= (por ejemplo, la ficha del grupo)."""
    return destino_interno(request.args.get("volver"), por_defecto)


def _datos_tutor(form, errores, prefijo=""):
    """Lee y valida los campos del tutor (prefijo 'tutor_' en el formulario del alumno)."""
    p = prefijo
    return {
        "nombres": validar.texto(form, p + "nombres", errores, "El nombre del tutor"),
        "apellidos": validar.texto(form, p + "apellidos", errores, "El apellido del tutor"),
        "ci": validar.texto(form, p + "ci", errores, "El CI", obligatorio=False, maximo=20),
        "telefono": validar.texto(form, p + "telefono", errores, "El teléfono", obligatorio=False, maximo=20),
        "whatsapp": validar.texto(form, p + "whatsapp", errores, "El WhatsApp", obligatorio=False, maximo=20),
        "correo": validar.correo(form, p + "correo", errores, obligatorio=False),
        "direccion": validar.texto(form, p + "direccion", errores, "La dirección", obligatorio=False, maximo=200),
    }


# ---------------------------------------------------------------- Inscribir (botón principal del celular)

@bp.route("/inscribir")
@solo_dueno
def inscribir_inicio():
    """Punto de entrada de "Inscribir": alumno nuevo (un solo formulario) o buscar uno que ya está registrado."""
    q = (request.args.get("q") or "").strip()[:60]
    return render_template("alumnos/inscribir.html", q=q, encontrados=alumnos.buscar_alumnos(q, "ACTIVO") if q else [])


# ---------------------------------------------------------------- Alumnos

@bp.route("/alumnos")
@solo_dueno
def lista():
    q = (request.args.get("q") or "").strip()[:60]
    estado = request.args.get("estado") if request.args.get("estado") in ("ACTIVO", "INACTIVO") else None
    return render_template("alumnos/lista.html", alumnos=alumnos.buscar_alumnos(q, estado), q=q, estado=estado,
                           total=alumnos.contar_alumnos(), maximo=alumnos.MAX_RESULTADOS)


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
    tutores = alumnos.buscar_tutores()
    if request.method == "POST":
        id_tutor = form.get("id_tutor") or ""
        tutor_nuevo = None
        if id_tutor == "nuevo":
            tutor_nuevo = _datos_tutor(form, errores, "tutor_")
        elif id_tutor not in {str(t["id_tutor"]) for t in tutores}:
            errores["id_tutor"] = "Elige el tutor del alumno o registra uno nuevo."
        datos = {
            "codigo": validar.texto(form, "codigo", errores, "El código", maximo=20),
            "nombres": validar.texto(form, "nombres", errores, "El nombre"),
            "apellidos": validar.texto(form, "apellidos", errores, "El apellido"),
            "fecha_nacimiento": validar.fecha(form, "fecha_nacimiento", errores, "La fecha de nacimiento",
                                              maxima=date.today()),
            "sexo": validar.opcion(form, "sexo", errores, "el sexo", set(alumnos.SEXOS)),
            "direccion": validar.texto(form, "direccion", errores, "La dirección", obligatorio=False, maximo=200),
            "id_tutor": int(id_tutor) if id_tutor.isdigit() else None,
        }
        inscribir_en = None
        if not id_alumno:
            grupo = form.get("id_grupo") or ""
            if grupo.isdigit():
                inscribir_en = (int(grupo), date.today())
            elif grupo != "despues":
                errores["id_grupo"] = "Elige el grupo donde entrenará (o «Inscribir después»)."
        if not errores:
            try:
                id_guardado = alumnos.guardar_alumno(id_alumno, datos, tutor_nuevo, inscribir_en)
                inscrito = f" e inscrito en {catalogos.obtener_grupo(inscribir_en[0])['nombre']}" if inscribir_en else ""
                flash(f"Alumno {datos['nombres']} {datos['apellidos']} guardado{inscrito}.", "ok")
                return redirect(url_for("alumnos.ficha", id_alumno=id_guardado))
            except ErrorDatos as e:
                flash(str(e), "error")
    tutores_opciones = [(t["id_tutor"], f"{t['apellidos'] or ''}, {t['nombres']}" + (f" (CI {t['ci']})" if t["ci"] else ""))
                        for t in tutores]
    return render_template("alumnos/alumno_form.html", form=form, errores=errores, id_alumno=id_alumno,
                           tutores_opciones=tutores_opciones, sexos=alumnos.SEXOS, hoy_iso=date.today().isoformat(),
                           grupos=[] if id_alumno else catalogos.listar_grupos(solo_activos=True))


@bp.route("/alumnos/<int:id_alumno>/estado", methods=["POST"])
@solo_dueno
def alumno_estado(id_alumno):
    try:
        nuevo = alumnos.cambiar_estado_alumno(id_alumno)
        flash("Alumno activado." if nuevo == "ACTIVO" else "Alumno desactivado.", "ok")
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
