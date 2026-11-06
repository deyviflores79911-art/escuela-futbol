"""
Notificaciones (la campana con el número) y cumpleaños de los alumnos.
Las notificaciones no se guardan en la base: se calculan con los datos de ese momento.
Cada una tiene un id; el número de la campana cuenta las que la persona todavía no abrió.
"""
import hashlib
from datetime import date

from datos import pagos, reportes
from datos.alumnos import numero_whatsapp
from datos.bd import consultar
from datos.catalogos import listar_grupos

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def _huella(valores):
    """Id corto que cambia si cambia la lista (por ejemplo, un alumno más fuera de su edad)."""
    return hashlib.sha1(",".join(str(v) for v in sorted(valores)).encode()).hexdigest()[:8]


def _proximo_cumple(nacimiento, hoy):
    """Fecha del próximo cumpleaños (hoy incluido). Los nacidos un 29 de febrero lo festejan el 28 en años no bisiestos."""
    for anio in (hoy.year, hoy.year + 1):
        try:
            dia = nacimiento.replace(year=anio)
        except ValueError:
            dia = date(anio, 2, 28)
        if dia >= hoy:
            return dia
    return None


# ---------------------------------------------------------------- Cumpleaños

def cumpleanos(hoy=None, dias=31, id_entrenador=None):
    """Alumnos activos e inscritos que cumplen años en los próximos 'dias' (hoy primero). Del entrenador: solo su grupo."""
    hoy = hoy or date.today()
    filtro, params = "", []
    if id_entrenador is not None:
        filtro, params = " AND g.id_entrenador = ?", [id_entrenador]
    filas = consultar(
        f"""SELECT a.id_alumno, a.nombres, a.apellidos, a.fecha_nacimiento,
                   STRING_AGG(g.nombre, ', ') AS grupos, MAX(t.nombres) AS tutor, MAX(ISNULL(t.whatsapp, t.telefono)) AS celular
            FROM ALUMNO a
            JOIN INSCRIPCION i ON i.id_alumno = a.id_alumno AND i.estado = 'ACTIVA'
            JOIN GRUPO g ON g.id_grupo = i.id_grupo
            LEFT JOIN TUTOR t ON t.id_tutor = a.id_tutor
            WHERE a.estado = 'ACTIVO' AND a.fecha_nacimiento IS NOT NULL{filtro}
            GROUP BY a.id_alumno, a.nombres, a.apellidos, a.fecha_nacimiento""", params)
    lista = []
    for f in filas:
        dia = _proximo_cumple(f["fecha_nacimiento"], hoy)
        faltan = (dia - hoy).days
        if faltan > dias:
            continue
        nombre = f"{f['nombres']} {f['apellidos'] or ''}".strip()
        lista.append({
            "id_alumno": f["id_alumno"], "alumno": nombre, "nombres": f["nombres"], "grupos": f["grupos"],
            "dia": dia, "faltan": faltan, "cumple": dia.year - f["fecha_nacimiento"].year,
            "cuando": "Hoy" if faltan == 0 else "Mañana" if faltan == 1 else f"{DIAS[dia.weekday()].capitalize()} {dia.day} de {MESES[dia.month - 1]}",
            "tutor": f["tutor"], "wa": numero_whatsapp(f["celular"]),
        })
    return sorted(lista, key=lambda c: (c["faltan"], c["alumno"]))


# ---------------------------------------------------------------- Notificaciones

def notificaciones(es_dueno, id_entrenador=None, hoy=None):
    """Lista de avisos de ahora mismo: [{id, icono, titulo, detalle, enlace, texto_enlace, nivel}]."""
    hoy = hoy or date.today()
    avisos = []

    de_hoy = [c for c in cumpleanos(hoy, 0, None if es_dueno else id_entrenador) if c["faltan"] == 0]
    if de_hoy:
        nombres = ", ".join(f"{c['nombres']} ({c['cumple']})" for c in de_hoy)
        avisos.append({"id": f"cumple:{hoy.isoformat()}:{_huella(c['id_alumno'] for c in de_hoy)}", "icono": "pastel",
                       "titulo": f"{'Cumple' if len(de_hoy) == 1 else 'Cumplen'} años hoy", "detalle": nombres,
                       "cumpleaneros": de_hoy, "enlace": None, "texto_enlace": None, "nivel": "info"})

    fuera = reportes.fuera_de_categoria(hoy)
    if not es_dueno:
        mios = {g["id_grupo"] for g in listar_grupos(solo_activos=True, id_entrenador=id_entrenador)} if id_entrenador else set()
        fuera = [f for f in fuera if f["id_grupo"] in mios]
    if fuera:
        avisos.append({"id": f"edad:{_huella(f['id_alumno'] for f in fuera)}", "icono": "alerta",
                       "titulo": f"{len(fuera)} alumno{'s' if len(fuera) != 1 else ''} en un grupo que no es de su edad",
                       "detalle": ", ".join(f"{f['alumno']} ({f['edad']} años, en {f['grupo']})" for f in fuera[:6])
                                  + ("…" if len(fuera) > 6 else ""),
                       "enlace": "alumnos.lista" if es_dueno else "reportes.mi_grupo",
                       "texto_enlace": "Ver alumnos" if es_dueno else "Ver mi grupo", "nivel": "error"})

    if not es_dueno and id_entrenador:
        pronto = [a for gr in reportes.mi_grupo(id_entrenador, hoy) for a in gr["alumnos"]
                  if not a["debe"] and a["vence_en"] is not None and a["vence_en"] <= 3]
        if pronto:
            pronto.sort(key=lambda a: (a["vence_en"], a["alumno"]))
            avisos.append({"id": f"vence:{hoy.isoformat()}:{_huella(a['id_alumno'] for a in pronto)}", "icono": "billetera",
                           "titulo": "Recordar: mensualidad por vencer",
                           "detalle": ", ".join(a["alumno"] for a in pronto),
                           "filas": [{"titulo": a["alumno"], "detalle": a["vence_texto"]} for a in pronto],
                           "enlace": "reportes.mi_grupo", "texto_enlace": "Ver mi grupo", "nivel": "aviso"})

    if es_dueno:
        llenos = [g for g in listar_grupos(solo_activos=True) if g["lleno"]]
        if llenos:
            avisos.append({"id": f"lleno:{_huella(g['id_grupo'] for g in llenos)}", "icono": "personas",
                           "titulo": f"Grupo{'s' if len(llenos) != 1 else ''} sin cupo",
                           "detalle": ", ".join(f"{g['nombre']} ({g['inscritos']}/{g['cupo_maximo']})" for g in llenos)
                                      + ". Los alumnos nuevos de esa edad quedan sin grupo.",
                           "enlace": "catalogos.grupos", "texto_enlace": "Ver grupos", "nivel": "aviso"})
    return avisos
