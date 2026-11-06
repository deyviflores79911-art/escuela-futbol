"""
Sistema de gestión de la escuela de fútbol.
Arranque:  python app.py   ->  http://localhost:5000 (en la computadora)
                             http://<IP de la computadora>:5000 (en el celular, misma red WiFi)
"""
from decimal import ROUND_HALF_UP, Decimal
from getpass import getpass

import click
from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError, CSRFProtect

import config
from config import Config
from datos import bd, lugares, usuarios
from datos.bd import ErrorBD
from datos.letras import monto_en_letras
from rutas import (
    acceso,
    alumnos,
    avisos,
    caja,
    catalogos,
    reportes,
    seguridad,
)
from rutas import usuarios as rutas_usuarios

csrf = CSRFProtect()


def fecha(valor):
    """Fecha en formato dd/mm/aaaa."""
    return valor.strftime("%d/%m/%Y") if valor else ""


def bs(valor):
    """Monto en bolivianos con dos decimales: Bs 1.250,00"""
    if valor is None:
        return ""
    n = Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    texto = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"Bs {texto}"


def coma(valor):
    """Número con dos decimales y coma: 0,60"""
    return f"{valor:.2f}".replace(".", ",")


def letras(valor):
    """Monto en letras para el recibo: Ciento veinte 50/100 Bolivianos"""
    return monto_en_letras(valor)


def crear_app():
    app = Flask(__name__, template_folder="plantillas", static_folder="estaticos",
                static_url_path="/static")
    app.config.from_object(Config)
    app.json.sort_keys = False  # respeta el orden de los datos (Sub-8, Sub-10, Sub-12...)
    csrf.init_app(app)

    app.before_request(seguridad.cargar_usuario)
    app.teardown_appcontext(bd.cerrar_conexion)   # nube: cierra la conexión compartida de la página
    app.context_processor(seguridad.datos_plantilla)
    app.add_template_filter(fecha)
    app.add_template_filter(bs)
    app.add_template_filter(coma)
    app.add_template_filter(letras)
    app.jinja_env.globals["mapa"] = lugares.enlace  # enlace "Cómo llegar" de un lugar

    app.register_blueprint(acceso.bp)
    app.register_blueprint(rutas_usuarios.bp)
    app.register_blueprint(alumnos.bp)
    app.register_blueprint(avisos.bp)
    app.register_blueprint(catalogos.bp)
    app.register_blueprint(caja.bp)
    app.register_blueprint(reportes.bp)

    @app.errorhandler(403)
    def acceso_denegado(e):
        return render_template("error.html", titulo="Acceso denegado",
                               mensaje="No tienes permiso para ver esta pantalla."), 403

    @app.errorhandler(404)
    def no_encontrado(e):
        return render_template("error.html", titulo="No encontrado",
                               mensaje="La página o el registro que buscas no existe."), 404

    @app.errorhandler(CSRFError)
    def csrf_vencido(e):
        return render_template("error.html", titulo="Formulario vencido",
                               mensaje="El formulario expiró o no es válido. "
                                       "Vuelve atrás, recarga la página e inténtalo de nuevo."), 400

    @app.errorhandler(ErrorBD)
    def base_apagada(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": str(e)}), 503
        return render_template("error.html", titulo="Sin conexión con la base",
                               mensaje=str(e)), 503

    @app.cli.command("definir-clave")
    @click.argument("correo")
    def definir_clave(correo):
        """Pone una contraseña real (con hash) a un usuario existente: flask definir-clave correo"""
        from datos.bd import consultar_uno
        u = consultar_uno("SELECT id_usuario, nombres FROM USUARIO "
                          "WHERE LOWER(LTRIM(RTRIM(correo))) = ?", (usuarios.normalizar_correo(correo),))
        if not u:
            raise click.ClickException(f"No hay ningún usuario con el correo {correo}.")
        clave = getpass("Nueva contraseña (mínimo 8 caracteres): ")
        if len(clave) < 8:
            raise click.ClickException("La contraseña debe tener al menos 8 caracteres.")
        if getpass("Repite la contraseña: ") != clave:
            raise click.ClickException("No coinciden. No se cambió nada.")
        usuarios.cambiar_clave(u["id_usuario"], clave)
        click.echo(f"Contraseña de {u['nombres']} guardada (con hash).")

    return app


def app_sin_configurar():
    """En Vercel, si faltan variables: una página clara con las que faltan (en vez de un error 500)."""
    aviso = Flask(__name__)

    @aviso.route("/", defaults={"ruta": ""})
    @aviso.route("/<path:ruta>")
    def falta_configurar(ruta):
        lista = "".join(f"<li><code>{v}</code></li>" for v in config.FALTAN)
        return (f"<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                f"<title>Falta configurar</title><body style='font-family:sans-serif;max-width:560px;margin:2rem auto;padding:0 1rem'>"
                f"<h1>Falta configurar la app en Vercel</h1><p>En Vercel → tu proyecto → <b>Settings → Environment "
                f"Variables</b>, agrega:</p><ul>{lista}</ul><p>Después ve a <b>Deployments</b> → ⋯ → <b>Redeploy</b>.</p>"
                f"<p>Los valores están explicados en <code>app_escuela/README.md</code>.</p></body>", 503)
    return aviso


app = app_sin_configurar() if config.FALTAN else crear_app()

def _ip_en_la_red():
    """IP de esta computadora en la red WiFi (la que se escribe en el celular)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # no envía nada: solo elige la tarjeta de red
            return s.getsockname()[0]
        except OSError:
            return None


if __name__ == "__main__":
    ip = _ip_en_la_red() if config.HOST == "0.0.0.0" else None
    print(f"En esta computadora: http://localhost:{config.PUERTO}")
    if ip:
        print(f"En el celular (conectado al mismo WiFi): http://{ip}:{config.PUERTO}")
    app.run(host=config.HOST, port=config.PUERTO, debug=False)
