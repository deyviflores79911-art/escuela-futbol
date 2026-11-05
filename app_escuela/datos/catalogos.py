"""
Catálogos de la escuela: categorías, grupos y horarios.
Nada se borra: se desactiva, para no dejar mensualidades ni pagos huérfanos.
"""
from datetime import date

from datos.bd import ErrorDatos, consultar, consultar_uno, transaccion

# Los días se guardan como ya están en la base (sin tilde) y se muestran con tilde
DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
DIA_PANTALLA = {"Miercoles": "Miércoles", "Sabado": "Sábado"}

# Inscritos que ocupan cupo: solo las inscripciones activas
_INSCRITOS = "(SELECT COUNT(*) FROM INSCRIPCION i WHERE i.id_grupo = g.id_grupo AND i.estado = 'ACTIVA')"


def orden_categoria(nombre):
    """Para ordenar Sub-8, Sub-10, Sub-12... por número y no alfabéticamente."""
    digitos = "".join(ch for ch in nombre if ch.isdigit())
    return (int(digitos) if digitos else 999, nombre)


def dia_pantalla(dia):
    return DIA_PANTALLA.get(dia, dia)


# ---------------------------------------------------------------- Categorías

def listar_categorias():
    return consultar(
        """SELECT c.id_categoria, c.nombre, c.edad_minima, c.edad_maxima, c.estado,
                  (SELECT COUNT(*) FROM GRUPO g WHERE g.id_categoria = c.id_categoria AND g.estado = 'ACTIVO') AS grupos
           FROM CATEGORIA c ORDER BY c.estado, c.edad_minima, c.nombre""")


def obtener_categoria(id_categoria):
    return consultar_uno("SELECT * FROM CATEGORIA WHERE id_categoria = ?", (id_categoria,))


def edad(fecha_nacimiento, hoy=None):
    if not fecha_nacimiento:
        return None
    hoy = hoy or date.today()
    return hoy.year - fecha_nacimiento.year - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))


def mensaje_edad(cur, nombre, anios, categoria, edad_minima, edad_maxima):
    """'Joaquín tiene 12 años y Sub-8 es de 6 a 8 años. Elige la categoría Sub-12.' Los rangos salen de la base."""
    if anios is None:
        return f"{nombre} no tiene fecha de nacimiento: regístrala antes de inscribirlo."
    cur.execute("SELECT nombre FROM CATEGORIA WHERE estado = 'ACTIVA' AND ? BETWEEN edad_minima AND edad_maxima "
                "ORDER BY edad_minima", (anios,))
    validas = [f.nombre for f in cur.fetchall()]
    texto = f"{nombre} tiene {anios} años y {categoria} es de {edad_minima} a {edad_maxima} años."
    if validas:
        return texto + f" Elige la categoría {' o '.join(validas)}."
    return texto + " No hay ninguna categoría activa para su edad."


def revisar_edades(cur, edad_minima, edad_maxima, id_grupo=None, id_categoria=None):
    """
    Regla de seguridad: un niño solo entrena con los de su edad. Si algún alumno con inscripción
    ACTIVA en ese grupo (o en los grupos de esa categoría) queda fuera del rango, no se guarda.
    """
    columna, valor = ("i.id_grupo", id_grupo) if id_grupo else ("g.id_categoria", id_categoria)
    cur.execute("SELECT a.nombres, a.apellidos, a.fecha_nacimiento FROM INSCRIPCION i "
                "JOIN ALUMNO a ON a.id_alumno = i.id_alumno JOIN GRUPO g ON g.id_grupo = i.id_grupo "
                f"WHERE i.estado = 'ACTIVA' AND {columna} = ?", (valor,))
    fuera = [f"{f.nombres} {f.apellidos or ''}".strip() for f in cur.fetchall()
             if edad(f.fecha_nacimiento) is not None and not edad_minima <= edad(f.fecha_nacimiento) <= edad_maxima]
    if fuera:
        raise ErrorDatos(f"No se guardó: {len(fuera)} alumno(s) inscrito(s) quedarían fuera del rango de "
                         f"{edad_minima}-{edad_maxima} años ({', '.join(fuera[:5])}{'…' if len(fuera) > 5 else ''}). "
                         "Un niño solo puede entrenar con los de su edad: cámbialos de grupo primero.")


def guardar_categoria(id_categoria, nombre, edad_minima, edad_maxima):
    """Crea (id_categoria=None) o edita una categoría. El nombre no se repite."""
    if edad_minima > edad_maxima:
        raise ErrorDatos("La edad mínima no puede ser mayor que la máxima.")
    with transaccion() as cur:
        cur.execute("SELECT 1 FROM CATEGORIA WITH (UPDLOCK, HOLDLOCK) "
                    "WHERE LOWER(nombre) = LOWER(?) AND id_categoria <> ?", (nombre, id_categoria or 0))
        if cur.fetchone():
            raise ErrorDatos(f"Ya existe una categoría llamada {nombre}.")
        if id_categoria:
            revisar_edades(cur, edad_minima, edad_maxima, id_categoria=id_categoria)
            cur.execute("UPDATE CATEGORIA SET nombre = ?, edad_minima = ?, edad_maxima = ? WHERE id_categoria = ?",
                        (nombre, edad_minima, edad_maxima, id_categoria))
        else:
            cur.execute("INSERT INTO CATEGORIA (nombre, edad_minima, edad_maxima, estado) VALUES (?, ?, ?, 'ACTIVA')",
                        (nombre, edad_minima, edad_maxima))


def cambiar_estado_categoria(id_categoria):
    """ACTIVA <-> INACTIVA. No se desactiva si tiene grupos activos. Devuelve el estado nuevo."""
    with transaccion() as cur:
        cur.execute("SELECT estado FROM CATEGORIA WITH (UPDLOCK) WHERE id_categoria = ?", (id_categoria,))
        fila = cur.fetchone()
        if not fila:
            raise ErrorDatos("Esa categoría no existe.")
        nuevo = "INACTIVA" if fila.estado == "ACTIVA" else "ACTIVA"
        if nuevo == "INACTIVA":
            cur.execute("SELECT COUNT(*) FROM GRUPO WHERE id_categoria = ? AND estado = 'ACTIVO'", (id_categoria,))
            activos = cur.fetchone()[0]
            if activos:
                raise ErrorDatos(f"No se puede desactivar: tiene {activos} grupo(s) activo(s). Desactívalos primero.")
        cur.execute("UPDATE CATEGORIA SET estado = ? WHERE id_categoria = ?", (nuevo, id_categoria))
        return nuevo


# ---------------------------------------------------------------- Grupos

_SELECT_GRUPO = f"""
    SELECT g.id_grupo, g.nombre, g.cupo_maximo, g.precio_mensual, g.estado,
           g.id_categoria, c.nombre AS categoria, c.edad_minima, c.edad_maxima,
           g.id_entrenador, e.nombres + ' ' + ISNULL(e.apellidos, '') AS entrenador,
           {_INSCRITOS} AS inscritos
    FROM GRUPO g
    INNER JOIN CATEGORIA c  ON c.id_categoria = g.id_categoria
    INNER JOIN ENTRENADOR e ON e.id_entrenador = g.id_entrenador
"""


def _con_libres(g):
    if g:
        g["libres"] = max((g["cupo_maximo"] or 0) - g["inscritos"], 0)
        g["lleno"] = g["libres"] == 0
    return g


def listar_grupos(solo_activos=False, id_entrenador=None):
    sql, params = _SELECT_GRUPO + " WHERE 1 = 1", []
    if solo_activos:
        sql += " AND g.estado = 'ACTIVO'"
    if id_entrenador is not None:
        sql += " AND g.id_entrenador = ?"
        params.append(id_entrenador)
    grupos = [_con_libres(g) for g in consultar(sql + " ORDER BY g.estado, c.edad_minima, g.nombre", params)]
    horarios = listar_horarios()
    for g in grupos:
        g["horarios"] = [h for h in horarios if h["id_grupo"] == g["id_grupo"] and h["estado"] == "ACTIVO"]
    return grupos


def obtener_grupo(id_grupo):
    g = _con_libres(consultar_uno(_SELECT_GRUPO + " WHERE g.id_grupo = ?", (id_grupo,)))
    if g:
        g["horarios"] = listar_horarios(id_grupo)
    return g


def entrenadores_activos():
    return consultar("SELECT id_entrenador, nombres + ' ' + ISNULL(apellidos, '') AS nombre "
                     "FROM ENTRENADOR WHERE estado = 'ACTIVO' ORDER BY nombres, apellidos")


def guardar_grupo(id_grupo, datos):
    """Crea o edita un grupo. Revisa categoría y entrenador activos, nombre único y cupo >= inscritos."""
    with transaccion() as cur:
        cur.execute("SELECT estado, edad_minima, edad_maxima FROM CATEGORIA WHERE id_categoria = ?",
                    (datos["id_categoria"],))
        categoria = cur.fetchone()
        if not categoria or categoria.estado != "ACTIVA":
            raise ErrorDatos("Elige una categoría activa.")
        cur.execute("SELECT estado FROM ENTRENADOR WHERE id_entrenador = ?", (datos["id_entrenador"],))
        fila = cur.fetchone()
        if not fila or fila.estado != "ACTIVO":
            raise ErrorDatos("Elige un entrenador activo.")
        cur.execute("SELECT 1 FROM GRUPO WITH (UPDLOCK, HOLDLOCK) WHERE LOWER(nombre) = LOWER(?) AND id_grupo <> ?",
                    (datos["nombre"], id_grupo or 0))
        if cur.fetchone():
            raise ErrorDatos(f"Ya existe un grupo llamado {datos['nombre']}.")
        valores = (datos["id_categoria"], datos["id_entrenador"], datos["nombre"], datos["cupo_maximo"], datos["precio_mensual"])
        if id_grupo:
            cur.execute("SELECT COUNT(*) FROM INSCRIPCION WITH (UPDLOCK, HOLDLOCK) WHERE id_grupo = ? AND estado = 'ACTIVA'",
                        (id_grupo,))
            inscritos = cur.fetchone()[0]
            if datos["cupo_maximo"] < inscritos:
                raise ErrorDatos(f"El cupo no puede ser menor que los {inscritos} alumnos inscritos.")
            revisar_edades(cur, categoria.edad_minima, categoria.edad_maxima, id_grupo=id_grupo)
            cur.execute("UPDATE GRUPO SET id_categoria = ?, id_entrenador = ?, nombre = ?, cupo_maximo = ?, "
                        "precio_mensual = ? WHERE id_grupo = ?", valores + (id_grupo,))
            return id_grupo
        cur.execute("INSERT INTO GRUPO (id_categoria, id_entrenador, nombre, cupo_maximo, precio_mensual, estado) "
                    "OUTPUT INSERTED.id_grupo VALUES (?, ?, ?, ?, ?, 'ACTIVO')", valores)
        return cur.fetchone()[0]


def cambiar_estado_grupo(id_grupo):
    """ACTIVO <-> INACTIVO. No se desactiva si tiene alumnos inscritos. Devuelve el estado nuevo."""
    with transaccion() as cur:
        cur.execute("SELECT g.estado, c.estado AS estado_categoria FROM GRUPO g WITH (UPDLOCK) "
                    "JOIN CATEGORIA c ON c.id_categoria = g.id_categoria WHERE g.id_grupo = ?", (id_grupo,))
        fila = cur.fetchone()
        if not fila:
            raise ErrorDatos("Ese grupo no existe.")
        nuevo = "INACTIVO" if fila.estado == "ACTIVO" else "ACTIVO"
        if nuevo == "INACTIVO":
            cur.execute("SELECT COUNT(*) FROM INSCRIPCION WHERE id_grupo = ? AND estado = 'ACTIVA'", (id_grupo,))
            inscritos = cur.fetchone()[0]
            if inscritos:
                raise ErrorDatos(f"No se puede desactivar: tiene {inscritos} alumno(s) inscrito(s). Dalos de baja primero.")
        elif fila.estado_categoria != "ACTIVA":
            raise ErrorDatos("No se puede activar: su categoría está desactivada.")
        cur.execute("UPDATE GRUPO SET estado = ? WHERE id_grupo = ?", (nuevo, id_grupo))
        return nuevo


# ---------------------------------------------------------------- Horarios

def listar_horarios(id_grupo=None):
    sql, params = "SELECT * FROM HORARIO", ()
    if id_grupo is not None:
        sql, params = sql + " WHERE id_grupo = ?", (id_grupo,)
    filas = consultar(sql, params)
    for h in filas:
        h["dia"] = dia_pantalla(h["dia_semana"])
    return sorted(filas, key=lambda h: (h["estado"] != "ACTIVO", DIAS.index(h["dia_semana"])
                                        if h["dia_semana"] in DIAS else 9, h["hora_inicio"]))


def obtener_horario(id_horario):
    return consultar_uno("SELECT * FROM HORARIO WHERE id_horario = ?", (id_horario,))


def guardar_horario(id_horario, id_grupo, dia, hora_inicio, hora_fin, lugar):
    if hora_fin <= hora_inicio:
        raise ErrorDatos("La hora de fin debe ser posterior a la de inicio.")
    with transaccion() as cur:
        if id_horario:
            cur.execute("UPDATE HORARIO SET dia_semana = ?, hora_inicio = ?, hora_fin = ?, lugar = ? "
                        "WHERE id_horario = ? AND id_grupo = ?", (dia, hora_inicio, hora_fin, lugar, id_horario, id_grupo))
            if cur.rowcount == 0:
                raise ErrorDatos("Ese horario no existe.")
        else:
            cur.execute("INSERT INTO HORARIO (id_grupo, dia_semana, hora_inicio, hora_fin, lugar, estado) "
                        "VALUES (?, ?, ?, ?, ?, 'ACTIVO')", (id_grupo, dia, hora_inicio, hora_fin, lugar))


def cambiar_estado_horario(id_horario):
    with transaccion() as cur:
        cur.execute("UPDATE HORARIO SET estado = CASE WHEN estado = 'ACTIVO' THEN 'INACTIVO' ELSE 'ACTIVO' END "
                    "OUTPUT INSERTED.estado, INSERTED.id_grupo WHERE id_horario = ?", (id_horario,))
        fila = cur.fetchone()
        if not fila:
            raise ErrorDatos("Ese horario no existe.")
        return fila.estado, fila.id_grupo


def aplicar_horario(ids_grupos, dias, hora_inicio=None, hora_fin=None, lugar=None, quitar=False):
    """
    Horario de varios grupos y días de una vez (pantalla Horarios), todo en UNA transacción.
    En cada grupo, los horarios activos de esos días se desactivan (nada se borra) y, si no es
    'quitar', se crea el nuevo. Así se puede armar la semana por partes: L-M-V en un lugar y
    M-J en otro. Devuelve (grupos, horarios creados).
    """
    if not ids_grupos:
        raise ErrorDatos("Elige al menos un grupo.")
    if not dias or not set(dias) <= set(DIAS):
        raise ErrorDatos("Elige al menos un día.")
    if not quitar and (hora_inicio is None or hora_fin is None or hora_fin <= hora_inicio):
        raise ErrorDatos("La hora de fin debe ser posterior a la de inicio.")
    marcas = ", ".join("?" * len(dias))
    creados = 0
    with transaccion() as cur:
        for id_grupo in ids_grupos:
            cur.execute("SELECT estado FROM GRUPO WITH (UPDLOCK) WHERE id_grupo = ?", (id_grupo,))
            fila = cur.fetchone()
            if not fila or fila.estado != "ACTIVO":
                raise ErrorDatos("Uno de los grupos no existe o está desactivado. No se cambió nada.")
            cur.execute(f"UPDATE HORARIO SET estado = 'INACTIVO' WHERE id_grupo = ? AND estado = 'ACTIVO' "
                        f"AND dia_semana IN ({marcas})", (id_grupo, *dias))
            if not quitar:
                for dia in dias:
                    cur.execute("INSERT INTO HORARIO (id_grupo, dia_semana, hora_inicio, hora_fin, lugar, estado) "
                                "VALUES (?, ?, ?, ?, ?, 'ACTIVO')", (id_grupo, dia, hora_inicio, hora_fin, lugar))
                    creados += 1
    return len(ids_grupos), creados


def semana():
    """Grupos activos con sus horarios activos, para ver toda la semana de un vistazo."""
    grupos = listar_grupos(solo_activos=True)
    horarios = [h for h in listar_horarios() if h["estado"] == "ACTIVO"]
    for g in grupos:
        g["semana"] = [h for h in horarios if h["id_grupo"] == g["id_grupo"]]
    return grupos
