"""
Usuarios y roles. La tabla ROL tiene 'Administrador' (= Dueño), 'Secretaria'
y 'Entrenador'. Solo Dueño y Entrenador entran a esta aplicación.
Un usuario entrenador se enlaza a su fila de ENTRENADOR por el correo.
"""
from werkzeug.security import check_password_hash, generate_password_hash

from datos.bd import ErrorDatos, consultar, consultar_uno, transaccion

DUENO = "DUENO"
ENTRENADOR = "ENTRENADOR"
ROLES_SISTEMA = {"Administrador": DUENO, "Entrenador": ENTRENADOR}
NOMBRE_ROL = {DUENO: "Dueño", ENTRENADOR: "Entrenador"}

_SELECT_USUARIO = """
    SELECT u.id_usuario, u.nombres, u.apellidos, u.correo, u.telefono,
           u.estado, u.password_hash, r.nombre AS rol_bd,
           e.id_entrenador
    FROM USUARIO u
    INNER JOIN ROL r ON r.id_rol = u.id_rol
    LEFT JOIN ENTRENADOR e
           ON LOWER(LTRIM(RTRIM(e.correo))) = LOWER(LTRIM(RTRIM(u.correo)))
"""


def normalizar_correo(correo):
    return (correo or "").strip().lower()


def _con_rol(u):
    if u:
        u["rol"] = ROLES_SISTEMA.get(u["rol_bd"])
    return u


def verificar_login(correo, clave):
    """Devuelve (usuario, None) si los datos son correctos, o (None, mensaje)."""
    u = _con_rol(consultar_uno(
        _SELECT_USUARIO + " WHERE LOWER(LTRIM(RTRIM(u.correo))) = ?",
        (normalizar_correo(correo),)))
    # Mismo mensaje si el correo no existe o la clave falla (no revela qué correos existen)
    mensaje = "Correo o contraseña incorrectos."
    if not u or not u["password_hash"]:
        return None, mensaje
    try:
        clave_ok = check_password_hash(u["password_hash"], clave)
    except ValueError:  # claves de relleno como 'hash1' no son un hash válido
        clave_ok = False
    if not clave_ok:
        return None, mensaje
    if u["estado"] != "ACTIVO":
        return None, "Tu usuario está desactivado. Habla con el dueño de la escuela."
    if u["rol"] is None:
        return None, "Tu rol no tiene acceso a este sistema."
    return u, None


def buscar_por_id(id_usuario):
    return _con_rol(consultar_uno(_SELECT_USUARIO + " WHERE u.id_usuario = ?", (id_usuario,)))


def listar_entrenadores():
    """Usuarios con rol Entrenador, con los datos de su fila ENTRENADOR."""
    return consultar(
        """SELECT u.id_usuario, u.nombres, u.apellidos, u.correo, u.telefono,
                  u.estado, e.id_entrenador, e.especialidad
           FROM USUARIO u
           INNER JOIN ROL r ON r.id_rol = u.id_rol AND r.nombre = 'Entrenador'
           LEFT JOIN ENTRENADOR e
                  ON LOWER(LTRIM(RTRIM(e.correo))) = LOWER(LTRIM(RTRIM(u.correo)))
           ORDER BY u.estado, u.nombres, u.apellidos""")


def entrenadores_sin_usuario():
    """Filas de ENTRENADOR con correo que todavía no tienen usuario."""
    return consultar(
        """SELECT e.id_entrenador, e.nombres, e.apellidos, e.correo, e.telefono, e.especialidad
           FROM ENTRENADOR e
           WHERE e.correo IS NOT NULL AND LTRIM(RTRIM(e.correo)) <> ''
             AND NOT EXISTS (SELECT 1 FROM USUARIO u
                             WHERE LOWER(LTRIM(RTRIM(u.correo))) = LOWER(LTRIM(RTRIM(e.correo))))
           ORDER BY e.nombres, e.apellidos""")


def crear_entrenador(datos, clave, id_entrenador=None):
    """
    Crea el usuario de un entrenador. Si id_entrenador viene, se enlaza a esa
    fila existente (sin modificarla); si no, se crea también la fila ENTRENADOR.
    Todo en una sola transacción.
    """
    with transaccion() as cur:
        if id_entrenador:
            cur.execute("SELECT nombres, apellidos, correo, telefono FROM ENTRENADOR "
                        "WHERE id_entrenador = ?", (id_entrenador,))
            e = cur.fetchone()
            if not e or not (e.correo or "").strip():
                raise ErrorDatos("Ese entrenador no existe o no tiene correo.")
            nombres, apellidos, telefono = e.nombres, e.apellidos, e.telefono
            correo = normalizar_correo(e.correo)
        else:
            nombres, apellidos = datos["nombres"], datos["apellidos"]
            telefono, correo = datos["telefono"], normalizar_correo(datos["correo"])
            # UPDLOCK/HOLDLOCK: evita que dos personas creen el mismo correo a la vez
            cur.execute("SELECT 1 FROM ENTRENADOR WITH (UPDLOCK, HOLDLOCK) "
                        "WHERE LOWER(LTRIM(RTRIM(correo))) = ?", (correo,))
            if cur.fetchone():
                raise ErrorDatos("Ya hay un entrenador con ese correo. "
                                   "Elígelo en la lista de entrenadores existentes.")
            cur.execute(
                "INSERT INTO ENTRENADOR (nombres, apellidos, ci, telefono, correo, especialidad, estado) "
                "VALUES (?, ?, ?, ?, ?, ?, 'ACTIVO')",
                (nombres, apellidos, datos["ci"], telefono, correo, datos["especialidad"]))

        cur.execute("SELECT 1 FROM USUARIO WITH (UPDLOCK, HOLDLOCK) "
                    "WHERE LOWER(LTRIM(RTRIM(correo))) = ?", (correo,))
        if cur.fetchone():
            raise ErrorDatos("Ya existe un usuario con ese correo.")
        cur.execute("SELECT id_rol FROM ROL WHERE nombre = 'Entrenador'")
        id_rol = cur.fetchone().id_rol
        cur.execute(
            "INSERT INTO USUARIO (id_rol, nombres, apellidos, correo, password_hash, telefono, estado) "
            "VALUES (?, ?, ?, ?, ?, ?, 'ACTIVO')",
            (id_rol, nombres, apellidos, correo, generate_password_hash(clave), telefono))


def editar_entrenador(id_usuario, nombres, apellidos, telefono, clave_nueva=None):
    """Edita datos del usuario entrenador. El correo no se cambia: es el enlace con ENTRENADOR."""
    with transaccion() as cur:
        cur.execute(
            "UPDATE u SET nombres = ?, apellidos = ?, telefono = ? FROM USUARIO u "
            "INNER JOIN ROL r ON r.id_rol = u.id_rol AND r.nombre = 'Entrenador' "
            "WHERE u.id_usuario = ?", (nombres, apellidos, telefono, id_usuario))
        if cur.rowcount == 0:
            raise ErrorDatos("Ese usuario no existe o no es entrenador.")
        if clave_nueva:
            cur.execute("UPDATE USUARIO SET password_hash = ? WHERE id_usuario = ?",
                        (generate_password_hash(clave_nueva), id_usuario))


def cambiar_estado_entrenador(id_usuario, estado):
    """ACTIVO o INACTIVO. Solo afecta a usuarios con rol Entrenador."""
    with transaccion() as cur:
        cur.execute(
            "UPDATE u SET estado = ? FROM USUARIO u "
            "INNER JOIN ROL r ON r.id_rol = u.id_rol AND r.nombre = 'Entrenador' "
            "WHERE u.id_usuario = ?", (estado, id_usuario))
        if cur.rowcount == 0:
            raise ErrorDatos("Ese usuario no existe o no es entrenador.")


def cambiar_clave(id_usuario, clave_nueva):
    with transaccion() as cur:
        cur.execute("UPDATE USUARIO SET password_hash = ? WHERE id_usuario = ?",
                    (generate_password_hash(clave_nueva), id_usuario))
