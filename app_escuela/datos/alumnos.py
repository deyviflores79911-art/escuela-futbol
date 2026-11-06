"""
Tutores, alumnos e inscripciones.
El código del alumno y el CI del tutor no se repiten (la base no lo obliga: lo controla la app).
Una baja cambia el estado de la inscripción a BAJA; nunca se borra el historial.
"""
import re

from datos.bd import ErrorDatos, consultar, consultar_uno, transaccion
from datos.catalogos import edad, listar_grupos, mensaje_edad

SEXOS = {"M": "Masculino", "F": "Femenino"}
PREFIJO_CODIGO = "AL-"   # los códigos nuevos siguen la serie AL-051, AL-052...
MAX_RESULTADOS = 300


def _patron_like(texto):
    """Texto del usuario para LIKE, sin que %, _ o [ funcionen como comodines."""
    limpio = texto.strip().replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
    return f"%{limpio}%"


def numero_whatsapp(numero):
    """Número para el enlace wa.me: solo dígitos; a un celular boliviano de 8 dígitos le agrega el 591."""
    digitos = "".join(ch for ch in (numero or "") if ch.isdigit())
    if len(digitos) == 8:
        digitos = "591" + digitos
    return digitos or None


# ---------------------------------------------------------------- Tutores

def buscar_tutores(texto=None):
    sql = """SELECT t.*, (SELECT COUNT(*) FROM ALUMNO a WHERE a.id_tutor = t.id_tutor) AS alumnos
             FROM TUTOR t"""
    params = ()
    if texto:
        sql += " WHERE t.nombres LIKE ? OR t.apellidos LIKE ? OR t.ci LIKE ? OR t.telefono LIKE ?"
        params = (_patron_like(texto),) * 4
    return consultar(f"SELECT TOP {MAX_RESULTADOS} * FROM ({sql}) x ORDER BY apellidos, nombres", params)


def tutores_para_elegir(texto, cantidad=8):
    """Búsqueda rápida del formulario de alumno nuevo: por nombre completo, CI, teléfono o WhatsApp.
    Incluye los hijos que ya tiene, para reconocer a la familia."""
    patron = _patron_like(texto)
    return consultar(
        f"""SELECT TOP {int(cantidad)} t.id_tutor, t.nombres, t.apellidos, t.ci, ISNULL(t.whatsapp, t.telefono) AS celular,
                   (SELECT STRING_AGG(a.nombres, ', ') FROM ALUMNO a WHERE a.id_tutor = t.id_tutor AND a.estado = 'ACTIVO') AS hijos
            FROM TUTOR t
            WHERE t.nombres LIKE ? OR t.apellidos LIKE ? OR (t.nombres + ' ' + ISNULL(t.apellidos, '')) LIKE ?
               OR t.ci LIKE ? OR t.telefono LIKE ? OR t.whatsapp LIKE ?
            ORDER BY t.apellidos, t.nombres""", (patron,) * 6)


def obtener_tutor(id_tutor):
    t = consultar_uno("SELECT * FROM TUTOR WHERE id_tutor = ?", (id_tutor,))
    if t:
        t["alumnos"] = consultar("SELECT id_alumno, codigo, nombres, apellidos, estado FROM ALUMNO "
                                 "WHERE id_tutor = ? ORDER BY nombres", (id_tutor,))
    return t


def guardar_tutor(id_tutor, datos):
    """Crea o edita un tutor. Devuelve su id. El CI, si se escribe, no se repite."""
    with transaccion() as cur:
        return _guardar_tutor(cur, id_tutor, datos)


def _guardar_tutor(cur, id_tutor, datos):
    """Igual que guardar_tutor, pero dentro de la transacción de quien la llama."""
    campos = ("nombres", "apellidos", "ci", "telefono", "whatsapp", "correo", "direccion")
    valores = tuple(datos[c] for c in campos)
    if datos["ci"]:
        cur.execute("SELECT nombres + ' ' + ISNULL(apellidos, '') FROM TUTOR WITH (UPDLOCK, HOLDLOCK) "
                    "WHERE ci = ? AND id_tutor <> ?", (datos["ci"], id_tutor or 0))
        fila = cur.fetchone()
        if fila:
            raise ErrorDatos(f"El CI {datos['ci']} ya está registrado para el tutor {fila[0]}.")
    if id_tutor:
        cur.execute("UPDATE TUTOR SET " + ", ".join(f"{c} = ?" for c in campos) + " WHERE id_tutor = ?",
                    valores + (id_tutor,))
        if cur.rowcount == 0:
            raise ErrorDatos("Ese tutor no existe.")
        return id_tutor
    cur.execute(f"INSERT INTO TUTOR ({', '.join(campos)}) OUTPUT INSERTED.id_tutor VALUES (?, ?, ?, ?, ?, ?, ?)",
                valores)
    return cur.fetchone()[0]


# ---------------------------------------------------------------- Alumnos

_SELECT_ALUMNO = """
    SELECT a.id_alumno, a.codigo, a.nombres, a.apellidos, a.fecha_nacimiento, a.sexo, a.direccion,
           a.estado, a.fecha_registro, a.id_tutor,
           t.nombres AS tutor_nombres, t.apellidos AS tutor_apellidos, t.ci AS tutor_ci,
           t.telefono AS tutor_telefono, t.whatsapp AS tutor_whatsapp,
           (SELECT STRING_AGG(g.nombre, ', ') FROM INSCRIPCION i JOIN GRUPO g ON g.id_grupo = i.id_grupo
             WHERE i.id_alumno = a.id_alumno AND i.estado = 'ACTIVA') AS grupos
    FROM ALUMNO a
    LEFT JOIN TUTOR t ON t.id_tutor = a.id_tutor
"""


def _completar(a):
    if a:
        a["edad"] = edad(a["fecha_nacimiento"])
        a["tutor"] = f"{a['tutor_nombres'] or ''} {a['tutor_apellidos'] or ''}".strip() or None
    return a


def buscar_alumnos(texto=None, estado=None):
    """Busca por nombre, apellido, código o tutor (nombre, apellido o CI)."""
    condiciones, params = [], []
    if texto:
        patron = _patron_like(texto)
        condiciones.append("(a.nombres LIKE ? OR a.apellidos LIKE ? OR a.codigo LIKE ? OR "
                           "(a.nombres + ' ' + ISNULL(a.apellidos, '')) LIKE ? OR "
                           "t.nombres LIKE ? OR t.apellidos LIKE ? OR t.ci LIKE ?)")
        params += [patron] * 7
    if estado:
        condiciones.append("a.estado = ?")
        params.append(estado)
    donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = consultar(f"SELECT TOP {MAX_RESULTADOS} * FROM ({_SELECT_ALUMNO}{donde}) x "
                      "ORDER BY estado, apellidos, nombres", params)
    return [_completar(a) for a in filas]


def contar_alumnos():
    return consultar_uno("SELECT COUNT(*) AS total, SUM(CASE WHEN estado = 'ACTIVO' THEN 1 ELSE 0 END) AS activos "
                         "FROM ALUMNO")


def obtener_alumno(id_alumno):
    a = _completar(consultar_uno(_SELECT_ALUMNO + " WHERE a.id_alumno = ?", (id_alumno,)))
    if a:
        a["inscripciones"] = consultar(
            """SELECT i.id_inscripcion, i.fecha_inscripcion, i.estado, g.id_grupo, g.nombre AS grupo,
                      c.nombre AS categoria, g.precio_mensual
               FROM INSCRIPCION i
               JOIN GRUPO g ON g.id_grupo = i.id_grupo
               JOIN CATEGORIA c ON c.id_categoria = g.id_categoria
               WHERE i.id_alumno = ?
               ORDER BY CASE WHEN i.estado = 'ACTIVA' THEN 0 ELSE 1 END, i.fecha_inscripcion DESC""", (id_alumno,))
    return a


def siguiente_codigo():
    """Siguiente código libre de la serie AL-### (los SIM-AL- y PRB-AL- son de prueba)."""
    fila = consultar_uno("SELECT MAX(TRY_CAST(SUBSTRING(codigo, 4, 10) AS INT)) AS n FROM ALUMNO WHERE codigo LIKE 'AL-%'")
    return f"{PREFIJO_CODIGO}{(fila['n'] or 0) + 1:03d}"


def guardar_alumno(id_alumno, datos, tutor_nuevo=None, inscribir_en=None):
    """
    Crea o edita un alumno y devuelve su id. El código no se repite y el tutor debe existir.
    Si viene tutor_nuevo, se registra primero, en la MISMA transacción: si el alumno falla,
    tampoco queda el tutor. Si viene inscribir_en=(id_grupo, fecha) al crear, se inscribe en la
    misma transacción: si la inscripción no se puede (edad, cupo), tampoco queda el alumno.
    Si el apellido (o, en un alumno nuevo, la dirección) queda vacío, se usa el del tutor:
    los hermanos no tienen que volver a escribirlo.
    """
    datos = dict(datos, codigo=datos["codigo"].strip().upper())
    if not re.fullmatch(r"[A-Z0-9-]{2,20}", datos["codigo"]):
        raise ErrorDatos("El código solo puede tener letras, números y guiones (por ejemplo AL-051).")
    campos = ("id_tutor", "codigo", "nombres", "apellidos", "fecha_nacimiento", "sexo", "direccion")
    with transaccion() as cur:
        if tutor_nuevo:
            datos["id_tutor"] = _guardar_tutor(cur, None, tutor_nuevo)
        cur.execute("SELECT apellidos, direccion FROM TUTOR WHERE id_tutor = ?", (datos["id_tutor"],))
        tutor = cur.fetchone()
        if not tutor:
            raise ErrorDatos("Busca y elige al tutor, o registra uno nuevo.")
        if not datos["apellidos"]:
            datos["apellidos"] = tutor.apellidos
            if not datos["apellidos"]:
                raise ErrorDatos("Escribe el apellido del alumno.")
        if not id_alumno and not datos["direccion"]:
            datos["direccion"] = tutor.direccion
        if not id_alumno:
            # El mismo niño dos veces (doble toque, o lo registraron antes): no se duplica
            cur.execute("SELECT codigo FROM ALUMNO WHERE id_tutor = ? AND LOWER(LTRIM(RTRIM(nombres))) = LOWER(?) "
                        "AND fecha_nacimiento = ?", (datos["id_tutor"], datos["nombres"].strip(), datos["fecha_nacimiento"]))
            repetido = cur.fetchone()
            if repetido:
                raise ErrorDatos(f"{datos['nombres']} ya está registrado con este tutor (código {repetido[0]}). "
                                 "Búscalo en Alumnos para inscribirlo en otro grupo.")
        cur.execute("SELECT nombres + ' ' + ISNULL(apellidos, '') FROM ALUMNO WITH (UPDLOCK, HOLDLOCK) "
                    "WHERE UPPER(codigo) = ? AND id_alumno <> ?", (datos["codigo"], id_alumno or 0))
        fila = cur.fetchone()
        if fila:
            raise ErrorDatos(f"El código {datos['codigo']} ya lo tiene {fila[0]}. Usa otro.")
        valores = tuple(datos[c] for c in campos)
        if id_alumno:
            # Si cambia la fecha de nacimiento, su edad debe seguir entrando en cada grupo donde entrena
            nueva = edad(datos["fecha_nacimiento"])
            cur.execute("SELECT g.nombre, c.nombre AS categoria, c.edad_minima, c.edad_maxima FROM INSCRIPCION i "
                        "JOIN GRUPO g ON g.id_grupo = i.id_grupo JOIN CATEGORIA c ON c.id_categoria = g.id_categoria "
                        "WHERE i.id_alumno = ? AND i.estado = 'ACTIVA'", (id_alumno,))
            for g in cur.fetchall():
                if nueva is None or not g.edad_minima <= nueva <= g.edad_maxima:
                    raise ErrorDatos(mensaje_edad(cur, datos["nombres"], nueva, g.categoria, g.edad_minima, g.edad_maxima)
                                     + f" Está inscrito en {g.nombre}: no se guardó la fecha.")
            cur.execute("UPDATE ALUMNO SET " + ", ".join(f"{c} = ?" for c in campos) + " WHERE id_alumno = ?",
                        valores + (id_alumno,))
            if cur.rowcount == 0:
                raise ErrorDatos("Ese alumno no existe.")
            return id_alumno
        cur.execute(f"INSERT INTO ALUMNO ({', '.join(campos)}, estado) OUTPUT INSERTED.id_alumno "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVO')", valores)
        nuevo_id = cur.fetchone()[0]
        if inscribir_en:
            _inscribir(cur, nuevo_id, *inscribir_en)
        return nuevo_id


def cambiar_estado_alumno(id_alumno):
    """ACTIVO <-> INACTIVO. No se desactiva si sigue inscrito en algún grupo. Devuelve el estado nuevo."""
    with transaccion() as cur:
        cur.execute("SELECT estado FROM ALUMNO WITH (UPDLOCK) WHERE id_alumno = ?", (id_alumno,))
        fila = cur.fetchone()
        if not fila:
            raise ErrorDatos("Ese alumno no existe.")
        nuevo = "INACTIVO" if fila.estado == "ACTIVO" else "ACTIVO"
        if nuevo == "INACTIVO":
            cur.execute("SELECT COUNT(*) FROM INSCRIPCION WHERE id_alumno = ? AND estado = 'ACTIVA'", (id_alumno,))
            if cur.fetchone()[0]:
                raise ErrorDatos("No se puede desactivar: sigue inscrito en un grupo. Dale de baja primero.")
        cur.execute("UPDATE ALUMNO SET estado = ? WHERE id_alumno = ?", (nuevo, id_alumno))
        return nuevo


# ---------------------------------------------------------------- Inscripciones

def grupo_para_edad(fecha_nacimiento, hoy=None):
    """
    El grupo que le toca por su edad (regla de la escuela): uno de su categoría, el que tiene más cupos libres.
    Devuelve (grupo, None) o (None, motivo) si no hay ninguno de su edad con cupo.
    """
    anios = edad(fecha_nacimiento, hoy)
    if anios is None:
        return None, "falta la fecha de nacimiento"
    de_su_edad = [g for g in listar_grupos(solo_activos=True) if g["edad_minima"] <= anios <= g["edad_maxima"]]
    con_cupo = [g for g in de_su_edad if not g["lleno"]]
    if con_cupo:
        return max(con_cupo, key=lambda g: (g["libres"], -g["id_grupo"])), None
    if de_su_edad:
        llenos = " y ".join(g["nombre"] for g in de_su_edad)
        return None, f"tiene {anios} años y {llenos} {'están llenos' if len(de_su_edad) > 1 else 'está lleno'}"
    return None, f"tiene {anios} años y no hay ningún grupo activo de su edad"



def grupos_para_inscribir(id_alumno):
    """Grupos activos con sus cupos libres, marcando dónde ya está inscrito el alumno."""
    inscrito_en = {f["id_grupo"] for f in consultar(
        "SELECT id_grupo FROM INSCRIPCION WHERE id_alumno = ? AND estado = 'ACTIVA'", (id_alumno,))}
    grupos = listar_grupos(solo_activos=True)
    for g in grupos:
        g["ya_inscrito"] = g["id_grupo"] in inscrito_en
    return grupos


def inscribir(id_alumno, id_grupo, fecha_inscripcion):
    """
    Inscribe con estado ACTIVA. Todo dentro de una transacción con bloqueo del grupo,
    para que dos inscripciones al mismo tiempo no puedan pasar el cupo.
    """
    with transaccion() as cur:
        return _inscribir(cur, id_alumno, id_grupo, fecha_inscripcion)


def _inscribir(cur, id_alumno, id_grupo, fecha_inscripcion):
    """Inscripción dentro de una transacción ya abierta. Devuelve (id_inscripcion, nombre del grupo)."""
    cur.execute("SELECT g.nombre, g.cupo_maximo, g.estado, c.nombre AS categoria, c.edad_minima, c.edad_maxima "
                "FROM GRUPO g WITH (UPDLOCK, HOLDLOCK) JOIN CATEGORIA c ON c.id_categoria = g.id_categoria "
                "WHERE g.id_grupo = ?", (id_grupo,))
    grupo = cur.fetchone()
    if not grupo or grupo.estado != "ACTIVO":
        raise ErrorDatos("Ese grupo no existe o está desactivado.")
    cur.execute("SELECT estado, nombres, fecha_nacimiento FROM ALUMNO WHERE id_alumno = ?", (id_alumno,))
    alumno = cur.fetchone()
    if not alumno or alumno.estado != "ACTIVO":
        raise ErrorDatos("El alumno no existe o está desactivado.")
    # Regla sin excepciones (también para el dueño): la edad el día de la inscripción
    # debe estar en el rango de la categoría del grupo
    anios = edad(alumno.fecha_nacimiento, fecha_inscripcion)
    if anios is None or not grupo.edad_minima <= anios <= grupo.edad_maxima:
        raise ErrorDatos(mensaje_edad(cur, alumno.nombres, anios, grupo.categoria,
                                      grupo.edad_minima, grupo.edad_maxima) + " No se inscribió.")
    cur.execute("SELECT 1 FROM INSCRIPCION WITH (UPDLOCK, HOLDLOCK) "
                "WHERE id_alumno = ? AND id_grupo = ? AND estado = 'ACTIVA'", (id_alumno, id_grupo))
    if cur.fetchone():
        raise ErrorDatos(f"El alumno ya está inscrito en {grupo.nombre}.")
    cur.execute("SELECT COUNT(*) FROM INSCRIPCION WITH (UPDLOCK, HOLDLOCK) WHERE id_grupo = ? AND estado = 'ACTIVA'",
                (id_grupo,))
    inscritos = cur.fetchone()[0]
    if grupo.cupo_maximo is not None and inscritos >= grupo.cupo_maximo:
        raise ErrorDatos(f"{grupo.nombre} está lleno: tiene {inscritos} de {grupo.cupo_maximo} cupos ocupados. "
                         "No se inscribió.")
    cur.execute("INSERT INTO INSCRIPCION (id_alumno, id_grupo, fecha_inscripcion, estado) "
                "OUTPUT INSERTED.id_inscripcion VALUES (?, ?, ?, 'ACTIVA')", (id_alumno, id_grupo, fecha_inscripcion))
    return cur.fetchone()[0], grupo.nombre


def dar_de_baja(id_inscripcion):
    """ACTIVA -> BAJA. La fila y sus mensualidades y pagos se conservan. Devuelve (id_alumno, grupo)."""
    with transaccion() as cur:
        cur.execute("UPDATE i SET estado = 'BAJA' OUTPUT INSERTED.id_alumno, INSERTED.id_grupo "
                    "FROM INSCRIPCION i WHERE i.id_inscripcion = ? AND i.estado = 'ACTIVA'", (id_inscripcion,))
        fila = cur.fetchone()
        if not fila:
            raise ErrorDatos("Esa inscripción no existe o ya estaba dada de baja.")
        return fila.id_alumno, fila.id_grupo


def inscritos_de_grupo(id_grupo, incluir_bajas=False):
    sql = """SELECT i.id_inscripcion, i.fecha_inscripcion, i.estado, a.id_alumno, a.codigo, a.nombres, a.apellidos,
                    a.fecha_nacimiento, t.nombres + ' ' + ISNULL(t.apellidos, '') AS tutor,
                    ISNULL(t.whatsapp, t.telefono) AS telefono
             FROM INSCRIPCION i
             JOIN ALUMNO a ON a.id_alumno = i.id_alumno
             LEFT JOIN TUTOR t ON t.id_tutor = a.id_tutor
             WHERE i.id_grupo = ?"""
    if not incluir_bajas:
        sql += " AND i.estado = 'ACTIVA'"
    filas = consultar(sql + " ORDER BY CASE WHEN i.estado = 'ACTIVA' THEN 0 ELSE 1 END, a.apellidos, a.nombres",
                      (id_grupo,))
    for f in filas:
        f["edad"] = edad(f["fecha_nacimiento"])
    return filas
