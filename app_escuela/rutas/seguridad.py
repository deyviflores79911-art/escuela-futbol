"""
Sesión, cierre por inactividad y permisos por rol (verificados en el servidor).
"""
import time
from functools import wraps
from urllib.parse import urlparse

from flask import abort, flash, g, redirect, request, session, url_for

from config import MINUTOS_INACTIVIDAD
from datos import usuarios
from datos.usuarios import DUENO, ENTRENADOR, NOMBRE_ROL

CABECERA_AUTOMATICA = "X-Consulta-Automatica"   # la envían los refrescos automáticos del navegador


def iniciar_sesion(u, recordar=False):
    session.clear()  # sesión nueva al entrar (evita reutilizar una anterior)
    session.permanent = True
    session["recordar"] = recordar   # en su celular: no se cierra por inactividad (dura DIAS_RECORDAR días)
    session["id_usuario"] = u["id_usuario"]
    session["rol"] = u["rol"]
    session["ultima_actividad"] = time.time()


def cargar_usuario():
    """Se ejecuta antes de cada petición: revisa inactividad y vuelve a leer el usuario."""
    g.usuario = None
    id_usuario = session.get("id_usuario")
    if not id_usuario:
        return
    if not session.get("recordar") and time.time() - session.get("ultima_actividad", 0) > MINUTOS_INACTIVIDAD * 60:
        session.clear()
        flash(f"Tu sesión se cerró por {MINUTOS_INACTIVIDAD} minutos de inactividad.", "aviso")
        return
    u = usuarios.buscar_por_id(id_usuario)
    # Si el dueño lo desactivó o le cambió el rol, la sesión se corta
    if not u or u["estado"] != "ACTIVO" or u["rol"] != session.get("rol"):
        session.clear()
        flash("Tu sesión ya no es válida. Vuelve a iniciar sesión.", "error")
        return
    # Las consultas automáticas (auto-refresco, aviso de análisis nuevo) no cuentan como actividad:
    # si no, la sesión nunca se cerraría por inactividad con una pantalla abierta
    if not request.path.startswith("/static/") and request.headers.get(CABECERA_AUTOMATICA) != "1":
        session["ultima_actividad"] = time.time()
    g.usuario = u


def destino_interno(destino, por_defecto):
    """Solo permite volver a rutas de esta app (evita redirigir a otro sitio)."""
    if destino and destino.startswith("/") and not destino.startswith("//") and not urlparse(destino).netloc:
        return destino
    return por_defecto


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if g.usuario is None:
            return redirect(url_for("acceso.login", siguiente=request.path))
        return vista(*args, **kwargs)
    return envoltura


def requiere_rol(*roles):
    """Además del login, exige uno de los roles. Si no lo tiene: 403 Acceso denegado."""
    def decorador(vista):
        @wraps(vista)
        @login_requerido
        def envoltura(*args, **kwargs):
            if g.usuario["rol"] not in roles:
                abort(403)
            return vista(*args, **kwargs)
        return envoltura
    return decorador


solo_dueno = requiere_rol(DUENO)


def datos_plantilla():
    """Variables disponibles en todas las plantillas."""
    u = g.get("usuario")
    return {
        "usuario": u,
        "es_dueno": bool(u and u["rol"] == DUENO),
        "es_entrenador": bool(u and u["rol"] == ENTRENADOR),
        "nombre_rol": NOMBRE_ROL.get(u["rol"]) if u else "",
        "minutos_inactividad": MINUTOS_INACTIVIDAD,
        "huella_datos": _huella_segura if u else None,   # se calcula solo si la plantilla la usa
        "avisos_sin_ver": _avisos_sin_ver if u else None,
    }


def _avisos_sin_ver():
    """Número de la campana (0 si la base no responde: la página igual se muestra)."""
    from rutas.avisos import sin_ver
    try:
        return sin_ver()
    except Exception:  # noqa: BLE001
        return 0


def _huella_segura():
    """Huella de los datos al dibujar la página (vacía si la base no responde: igual se compara después)."""
    from datos.cambios import huella
    try:
        return huella()
    except Exception:  # noqa: BLE001 - la página debe mostrarse aunque la huella falle
        return ""
