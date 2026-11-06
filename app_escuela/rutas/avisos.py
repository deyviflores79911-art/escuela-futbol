"""Notificaciones: la campana con el número de avisos sin ver (también los cumpleaños)."""
from flask import Blueprint, g, render_template, session

from datos import avisos
from rutas.seguridad import login_requerido

bp = Blueprint("avisos", __name__)
MAX_VISTOS = 60


def _mis_avisos():
    u = g.usuario
    return avisos.notificaciones(u["rol"] == "DUENO", u.get("id_entrenador"))


def sin_ver():
    """Cuántos avisos de ahora todavía no abrió esta persona (el número rojo de la campana)."""
    if "avisos_sin_ver" not in g:
        vistos = set(session.get("avisos_vistos", []))
        g.avisos_sin_ver = sum(1 for a in _mis_avisos() if a["id"] not in vistos)
    return g.avisos_sin_ver


@bp.route("/notificaciones")
@login_requerido
def notificaciones():
    lista = _mis_avisos()
    vistos = set(session.get("avisos_vistos", []))
    for a in lista:
        a["nuevo"] = a["id"] not in vistos
    # Al abrirlas quedan vistas: el número de la campana vuelve a cero hasta que aparezca algo nuevo
    session["avisos_vistos"] = ([a["id"] for a in lista] + [v for v in session.get("avisos_vistos", [])
                                                            if v not in {a["id"] for a in lista}])[:MAX_VISTOS]
    g.avisos_sin_ver = 0
    u = g.usuario
    proximos = [c for c in avisos.cumpleanos(dias=7, id_entrenador=None if u["rol"] == "DUENO" else u.get("id_entrenador"))
                if c["faltan"] >= 1]
    return render_template("avisos/notificaciones.html", avisos=lista, proximos=proximos)
