"""
GENERADOR DE PAGOS DE PRUEBA
Base: Sistema_EscuelasDeportivas (SQL Server, localhost\\MSSQLSERVER01)

Agrega unos 500 pagos de prueba, con sus tutores, alumnos, inscripciones y
mensualidades, para probar mejor el modelo que predice pagos atrasados.

REGLAS QUE RESPETA
    - Solo hace INSERT en tablas que ya existen: TUTOR, ALUMNO, INSCRIPCION,
      MENSUALIDAD y PAGO. No crea tablas ni columnas.
    - No modifica ni borra ninguna fila existente.
    - Usa los grupos, categorias, metodos y estados de pago que ya existen.
    - Respeta las llaves foraneas y el cupo maximo de cada grupo.

COMO RECONOCER LAS FILAS NUEVAS
    - PAGO.numero_recibo empieza con "SIM-"   (SIM-0001, SIM-0002, ...)
    - ALUMNO.codigo empieza con "SIM-AL-"     (SIM-AL-001, ...)
    - Los tutores nuevos son los que solo tienen alumnos SIM-AL-.

PATRONES QUE SE SIMULAN (semilla fija: 42)
    - Cada familia (tutor) es puntual, irregular o morosa y mantiene ese
      comportamiento mes a mes, con algo de ruido.
    - Transferencia y QR son mas puntuales; Efectivo y Tarjeta, menos.
    - Quien se atraso el mes anterior tiene mas probabilidad de atrasarse.
    - Pagos parciales y dias de atraso variados (desde pagar antes del
      vencimiento hasta mas de 15 dias tarde).
    - Descuento del 10% por hermano en la mensualidad.
    - 12 meses: de octubre de 2025 a septiembre de 2026.

USO
    python generar_pagos_prueba.py             -> SOLO SIMULA y muestra el resumen (no escribe nada)
    python generar_pagos_prueba.py --insertar  -> inserta las filas en la base
    python generar_pagos_prueba.py --quitar    -> borra SOLO las filas de prueba (SIM-)

Despues de insertar hay que volver a ejecutar el paquete SSIS para que el
Data Warehouse incluya los pagos nuevos.
"""

import sys
from datetime import date, timedelta

import numpy as np
import pyodbc

SERVIDOR = r"localhost\MSSQLSERVER01"
BASE = "Sistema_EscuelasDeportivas"
SEMILLA = 42
PAGOS_OBJETIVO = 500
PERIODOS = [(2025, m) for m in range(10, 13)] + [(2026, m) for m in range(1, 10)]   # oct-2025 a sep-2026
FECHA_CORTE = date(2026, 9, 30)          # no se registran pagos posteriores a esta fecha
DIA_VENCIMIENTO = 10                      # igual que las mensualidades existentes
DESCUENTO_HERMANO = 0.10

# ------------------------------------------------------------------
# Comportamiento de las familias
# ------------------------------------------------------------------
#             % de familias, tendencia base al atraso (escala logistica)
# (calibrado para ~30-35% de atrasos en total y un AUC realista, lejos de 1.0)
PERFILES = {"puntual": (0.45, -2.6), "irregular": (0.35, -1.1), "moroso": (0.20, 0.5)}
METODOS = ["Efectivo", "Transferencia", "QR", "Tarjeta"]
# Efecto del metodo sobre el atraso: negativo = mas puntual
EFECTO_METODO = {"Efectivo": 0.40, "Transferencia": -0.45, "QR": -0.35, "Tarjeta": 0.45}
# Metodo preferido segun el perfil (Efectivo, Transferencia, QR, Tarjeta)
PREFERENCIA = {"puntual": [0.15, 0.40, 0.35, 0.10],
               "irregular": [0.35, 0.25, 0.25, 0.15],
               "moroso": [0.50, 0.15, 0.15, 0.20]}
EFECTO_MES_ANTERIOR = 0.9                 # se atraso el mes pasado -> mas probable que se atrase
EFECTO_FIESTAS = 0.25                     # diciembre y enero: un poco mas de atraso
DIAS_TARDE = {"puntual": (1, 5), "irregular": (1, 12), "moroso": (3, 25)}
PROB_PARCIAL = {"puntual": 0.04, "irregular": 0.09, "moroso": 0.16}

NOMBRES_H = ["Carlos", "Jorge", "Luis", "Miguel", "Pedro", "Raul", "Oscar", "Hugo", "Victor", "Ramiro",
             "Fernando", "Gonzalo", "Marcelo", "Rodrigo", "Wilson", "Freddy", "Javier", "Edwin", "Alberto", "Rene"]
NOMBRES_M = ["Maria", "Rosa", "Patricia", "Carmen", "Silvia", "Veronica", "Gladys", "Lourdes", "Monica", "Ximena",
             "Claudia", "Roxana", "Sandra", "Elizabeth", "Norma", "Paola", "Lucia", "Ana", "Teresa", "Daniela"]
HIJOS_H = ["Thiago", "Matias", "Joaquin", "Benjamin", "Lucas", "Gael", "Dylan", "Samuel", "Leonardo", "Emiliano",
           "Bruno", "Santino", "Tomas", "Adrian", "Facundo", "Ian", "Maximiliano", "Alejandro", "Nicolas", "Rafael"]
HIJAS_M = ["Camila", "Sofia", "Valeria", "Isabella", "Luciana", "Mia", "Antonella", "Martina", "Renata", "Emilia",
           "Ariana", "Julieta", "Abril", "Catalina", "Fernanda", "Regina", "Victoria", "Zoe", "Allison", "Bianca"]
APELLIDOS = ["Mamani", "Quispe", "Choque", "Condori", "Flores", "Vargas", "Rojas", "Gutierrez", "Lopez", "Torrez",
             "Apaza", "Huanca", "Limachi", "Ticona", "Calle", "Aguilar", "Paredes", "Salazar", "Medina", "Arce",
             "Villca", "Copa", "Laura", "Nina", "Poma", "Yujra", "Callisaya", "Ramos", "Zenteno", "Guzman"]


def conectar():
    return pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};"
                          f"SERVER={SERVIDOR};DATABASE={BASE};Trusted_Connection=yes;", autocommit=False)


# ==================================================================
# 1) Leer catalogos existentes
# ==================================================================
def leer_catalogos(cursor):
    grupos = [dict(zip([c[0] for c in cursor.description], fila)) for fila in cursor.execute("""
        SELECT G.id_grupo, G.nombre, G.precio_mensual, G.cupo_maximo, C.edad_minima, C.edad_maxima,
               (SELECT COUNT(1) FROM INSCRIPCION I WHERE I.id_grupo = G.id_grupo AND I.estado = 'ACTIVA') AS inscritos
        FROM GRUPO G INNER JOIN CATEGORIA C ON C.id_categoria = G.id_categoria
        WHERE G.estado = 'ACTIVO' ORDER BY G.id_grupo""").fetchall()]
    metodos = {nombre: id_ for id_, nombre in cursor.execute("SELECT id_metodo_pago, nombre FROM METODO_PAGO WHERE estado = 'ACTIVO'")}
    estados = {nombre: id_ for id_, nombre in cursor.execute("SELECT id_estado_pago, nombre FROM ESTADO_PAGO")}
    usuarios = [fila[0] for fila in cursor.execute("""
        SELECT U.id_usuario FROM USUARIO U INNER JOIN ROL R ON R.id_rol = U.id_rol
        WHERE R.nombre = 'Secretaria' AND U.estado = 'ACTIVO' ORDER BY U.id_usuario""")]
    assert set(METODOS) <= set(metodos), "faltan metodos de pago en la base"
    assert {"Confirmado", "Parcial"} <= set(estados), "faltan estados de pago en la base"
    assert usuarios, "no hay usuarias con rol Secretaria"
    return grupos, metodos, estados, usuarios


# ==================================================================
# 2) Generar las familias, alumnos y pagos (todavia en memoria)
# ==================================================================
def generar(grupos, rng):
    cupos = {g["id_grupo"]: g["cupo_maximo"] - g["inscritos"] for g in grupos}
    familias, total_pagos, n_tutor, n_alumno = [], 0, 0, 0
    while total_pagos < PAGOS_OBJETIVO:
        n_tutor += 1
        perfil = rng.choice(list(PERFILES), p=[v[0] for v in PERFILES.values()])
        mujer = rng.random() < 0.55
        nombre = rng.choice(NOMBRES_M if mujer else NOMBRES_H)
        apellido_t = rng.choice(APELLIDOS)
        telefono = f"722{n_tutor:05d}"
        tutor = {"nombres": nombre, "apellidos": f"{apellido_t} {rng.choice(APELLIDOS)}", "ci": f"{4600000 + n_tutor}",
                 "telefono": telefono, "whatsapp": telefono,
                 "correo": f"{nombre.lower()}.{apellido_t.lower()}{n_tutor}@mail.com",
                 "direccion": f"Zona {int(rng.integers(1, 30))}, Calle {int(rng.integers(1, 60))}",
                 "perfil": perfil, "metodo_preferido": rng.choice(METODOS, p=PREFERENCIA[perfil]), "alumnos": []}
        # Mes en que la familia empezo: la mayoria desde el inicio, algunas despues
        inicio = 0 if rng.random() < 0.6 else int(rng.integers(1, 8))
        n_hijos = int(rng.choice([1, 2, 3], p=[0.55, 0.35, 0.10]))
        for orden in range(n_hijos):
            disponibles = [g for g in grupos if cupos[g["id_grupo"]] > 0]
            if not disponibles:
                break
            grupo = disponibles[int(rng.integers(len(disponibles)))]
            cupos[grupo["id_grupo"]] -= 1
            n_alumno += 1
            edad = int(rng.integers(grupo["edad_minima"], grupo["edad_maxima"] + 1))
            nacimiento = date(2026 - edad, int(rng.integers(1, 13)), int(rng.integers(1, 29)))
            sexo = "F" if rng.random() < 0.3 else "M"
            anio, mes = PERIODOS[inicio]
            inscripcion = date(anio, mes, 1) - timedelta(days=int(rng.integers(3, 25)))
            precio = float(grupo["precio_mensual"])
            monto = round(precio * (1 - DESCUENTO_HERMANO), 2) if orden > 0 else precio
            tutor["alumnos"].append({
                "codigo": f"SIM-AL-{n_alumno:03d}", "nombres": rng.choice(HIJAS_M if sexo == "F" else HIJOS_H),
                "apellidos": f"{apellido_t} {rng.choice(APELLIDOS)}", "nacimiento": nacimiento, "sexo": sexo,
                "id_grupo": grupo["id_grupo"], "inscripcion": inscripcion, "monto": monto,
                "periodos": PERIODOS[inicio:], "pagos": []})
        if not tutor["alumnos"]:
            break
        simular_pagos(tutor, rng)
        familias.append(tutor)
        total_pagos += sum(1 for a in tutor["alumnos"] for p in a["pagos"] if p is not None)
    return familias


def simular_pagos(tutor, rng):
    """Decide, mes a mes, cuando y como paga cada alumno de la familia."""
    perfil = tutor["perfil"]
    base = PERFILES[perfil][1]
    atraso_anterior = {a["codigo"]: False for a in tutor["alumnos"]}
    periodos = sorted({p for a in tutor["alumnos"] for p in a["periodos"]})
    for anio, mes in periodos:
        choque_familiar = rng.normal(0, 0.5)            # un mes malo o bueno para toda la familia
        decision_familiar = None
        for alumno in tutor["alumnos"]:
            if (anio, mes) not in alumno["periodos"]:
                continue
            # Hermanos: casi siempre se pagan el mismo dia y con el mismo metodo
            if decision_familiar is not None and rng.random() < 0.85:
                metodo, atrasado, dias = decision_familiar
            else:
                metodo = tutor["metodo_preferido"] if rng.random() < 0.75 else rng.choice(METODOS)
                logit = (base + EFECTO_METODO[metodo] + choque_familiar + rng.normal(0, 0.3)
                         + (EFECTO_MES_ANTERIOR if atraso_anterior[alumno["codigo"]] else 0)
                         + (EFECTO_FIESTAS if mes in (12, 1) else 0))
                atrasado = rng.random() < 1 / (1 + np.exp(-logit))
                if atrasado:
                    minimo, maximo = DIAS_TARDE[perfil]
                    dias = int(rng.integers(minimo, maximo + 1))
                else:
                    dias = -int(rng.choice(range(10), p=[0.2, 0.14, 0.12, 0.11, 0.1, 0.09, 0.08, 0.07, 0.05, 0.04]))
                decision_familiar = (metodo, atrasado, dias)
            emision = date(anio, mes, 1)
            vencimiento = date(anio, mes, DIA_VENCIMIENTO)
            fecha_pago = max(vencimiento + timedelta(days=dias), emision)
            atraso_anterior[alumno["codigo"]] = dias > 0
            if fecha_pago > FECHA_CORTE:                 # todavia no pago: la mensualidad queda sin pago
                alumno["pagos"].append(None)
                continue
            parcial = rng.random() < PROB_PARCIAL[perfil]
            monto = round(alumno["monto"] * float(rng.choice([0.5, 0.6, 0.7, 0.8])), 2) if parcial else alumno["monto"]
            alumno["pagos"].append({"periodo": f"{anio}-{mes:02d}", "emision": emision, "vencimiento": vencimiento,
                                    "fecha": fecha_pago, "metodo": metodo, "monto": monto, "parcial": parcial})
    # Las mensualidades sin pago tambien necesitan su periodo y fechas
    for alumno in tutor["alumnos"]:
        for i, (anio, mes) in enumerate(alumno["periodos"]):
            if alumno["pagos"][i] is None:
                alumno["pagos"][i] = {"periodo": f"{anio}-{mes:02d}", "emision": date(anio, mes, 1),
                                      "vencimiento": date(anio, mes, DIA_VENCIMIENTO), "sin_pago": True}


def resumen(familias):
    pagos = [p for f in familias for a in f["alumnos"] for p in a["pagos"] if not p.get("sin_pago")]
    atrasados = [p for p in pagos if p["fecha"] > p["vencimiento"]]
    print(f"Tutores: {len(familias)} | Alumnos: {sum(len(f['alumnos']) for f in familias)} | "
          f"Mensualidades: {sum(len(a['pagos']) for f in familias for a in f['alumnos'])} | Pagos: {len(pagos)}")
    print(f"Pagos atrasados: {len(atrasados)} ({len(atrasados) / len(pagos):.0%}) | parciales: "
          f"{sum(p['parcial'] for p in pagos)} | mas de 15 dias tarde: "
          f"{sum((p['fecha'] - p['vencimiento']).days > 15 for p in pagos)}")
    print("Familias por perfil:", {k: sum(f["perfil"] == k for f in familias) for k in PERFILES})
    for metodo in METODOS:
        del_metodo = [p for p in pagos if p["metodo"] == metodo]
        tarde = sum(p["fecha"] > p["vencimiento"] for p in del_metodo)
        print(f"   {metodo:13s} {len(del_metodo):4d} pagos  {tarde / max(len(del_metodo), 1):.0%} atrasados")


# ==================================================================
# 3) Insertar en la base (una sola transaccion)
# ==================================================================
def huella_existente(cursor):
    """Resumen numerico de las filas originales, para comprobar que no cambian."""
    consultas = {
        "TUTOR": "SELECT COUNT(1), CHECKSUM_AGG(BINARY_CHECKSUM(id_tutor, nombres, apellidos, ci, telefono, whatsapp, correo, direccion)) FROM TUTOR",
        "ALUMNO": "SELECT COUNT(1), CHECKSUM_AGG(BINARY_CHECKSUM(id_alumno, id_tutor, codigo, nombres, apellidos, fecha_nacimiento, sexo, direccion, estado, fecha_registro)) FROM ALUMNO",
        "INSCRIPCION": "SELECT COUNT(1), CHECKSUM_AGG(BINARY_CHECKSUM(id_inscripcion, id_alumno, id_grupo, fecha_inscripcion, estado)) FROM INSCRIPCION",
        "MENSUALIDAD": "SELECT COUNT(1), CHECKSUM_AGG(BINARY_CHECKSUM(id_mensualidad, id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado)) FROM MENSUALIDAD",
        "PAGO": "SELECT COUNT(1), CHECKSUM_AGG(BINARY_CHECKSUM(id_pago, id_mensualidad, id_usuario, id_metodo_pago, id_estado_pago, numero_recibo, fecha_pago, monto, observaciones)) FROM PAGO",
    }
    return {t: tuple(cursor.execute(sql + filtro).fetchone()) for t, sql in consultas.items()
            for filtro in [{"TUTOR": " WHERE id_tutor <= ?", "ALUMNO": " WHERE id_alumno <= ?",
                            "INSCRIPCION": " WHERE id_inscripcion <= ?", "MENSUALIDAD": " WHERE id_mensualidad <= ?",
                            "PAGO": " WHERE id_pago <= ?"}[t].replace("?", str(MAXIMOS[t]))]}


def insertar(conexion, familias, metodos, estados, usuarios, rng):
    cursor = conexion.cursor()
    nuevas = {"TUTOR": 0, "ALUMNO": 0, "INSCRIPCION": 0, "MENSUALIDAD": 0, "PAGO": 0}
    n_recibo = 0
    for f in familias:
        id_tutor = cursor.execute(
            "INSERT INTO TUTOR (nombres, apellidos, ci, telefono, whatsapp, correo, direccion) "
            "OUTPUT INSERTED.id_tutor VALUES (?, ?, ?, ?, ?, ?, ?)",
            f["nombres"], f["apellidos"], f["ci"], f["telefono"], f["whatsapp"], f["correo"], f["direccion"]).fetchval()
        nuevas["TUTOR"] += 1
        for a in f["alumnos"]:
            id_alumno = cursor.execute(
                "INSERT INTO ALUMNO (id_tutor, codigo, nombres, apellidos, fecha_nacimiento, sexo, direccion, estado, fecha_registro) "
                "OUTPUT INSERTED.id_alumno VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVO', ?)",
                id_tutor, a["codigo"], a["nombres"], a["apellidos"], a["nacimiento"], a["sexo"], f["direccion"],
                a["inscripcion"]).fetchval()
            id_insc = cursor.execute(
                "INSERT INTO INSCRIPCION (id_alumno, id_grupo, fecha_inscripcion, estado) "
                "OUTPUT INSERTED.id_inscripcion VALUES (?, ?, ?, 'ACTIVA')",
                id_alumno, a["id_grupo"], a["inscripcion"]).fetchval()
            nuevas["ALUMNO"] += 1
            nuevas["INSCRIPCION"] += 1
            for p in a["pagos"]:
                # Mismo valor de estado que usan las mensualidades existentes
                id_mens = cursor.execute(
                    "INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado) "
                    "OUTPUT INSERTED.id_mensualidad VALUES (?, ?, ?, ?, ?, 'PENDIENTE')",
                    id_insc, p["periodo"], p["emision"], p["vencimiento"], a["monto"]).fetchval()
                nuevas["MENSUALIDAD"] += 1
                if p.get("sin_pago"):
                    continue
                n_recibo += 1
                cursor.execute(
                    "INSERT INTO PAGO (id_mensualidad, id_usuario, id_metodo_pago, id_estado_pago, numero_recibo, fecha_pago, monto, observaciones) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    id_mens, int(rng.choice(usuarios)), metodos[p["metodo"]],
                    estados["Parcial"] if p["parcial"] else estados["Confirmado"], f"SIM-{n_recibo:04d}",
                    p["fecha"], p["monto"], "Pago parcial" if p["parcial"] else None)
                nuevas["PAGO"] += 1
    return nuevas


def quitar(conexion):
    """Borra solo las filas de prueba, de la tabla hija a la tabla padre."""
    cursor = conexion.cursor()
    tutores = [r[0] for r in cursor.execute("""
        SELECT DISTINCT A.id_tutor FROM ALUMNO A WHERE A.codigo LIKE 'SIM-AL-%'
          AND NOT EXISTS (SELECT 1 FROM ALUMNO B WHERE B.id_tutor = A.id_tutor AND B.codigo NOT LIKE 'SIM-AL-%')""")]
    pasos = [
        ("PAGO", "DELETE P FROM PAGO P INNER JOIN MENSUALIDAD M ON M.id_mensualidad = P.id_mensualidad "
                 "INNER JOIN INSCRIPCION I ON I.id_inscripcion = M.id_inscripcion INNER JOIN ALUMNO A ON A.id_alumno = I.id_alumno "
                 "WHERE A.codigo LIKE 'SIM-AL-%' AND P.numero_recibo LIKE 'SIM-%'"),
        ("MENSUALIDAD", "DELETE M FROM MENSUALIDAD M INNER JOIN INSCRIPCION I ON I.id_inscripcion = M.id_inscripcion "
                        "INNER JOIN ALUMNO A ON A.id_alumno = I.id_alumno WHERE A.codigo LIKE 'SIM-AL-%'"),
        ("INSCRIPCION", "DELETE I FROM INSCRIPCION I INNER JOIN ALUMNO A ON A.id_alumno = I.id_alumno WHERE A.codigo LIKE 'SIM-AL-%'"),
        ("ALUMNO", "DELETE FROM ALUMNO WHERE codigo LIKE 'SIM-AL-%'"),
    ]
    for tabla, sql in pasos:
        cursor.execute(sql)
        print(f"   {tabla}: {cursor.rowcount} filas de prueba borradas")
    if tutores:
        cursor.execute(f"DELETE FROM TUTOR WHERE id_tutor IN ({','.join('?' * len(tutores))})", *tutores)
        print(f"   TUTOR: {cursor.rowcount} filas de prueba borradas")
    conexion.commit()


# ==================================================================
# Programa principal
# ==================================================================
if __name__ == "__main__":
    conexion = conectar()
    cursor = conexion.cursor()

    if "--quitar" in sys.argv:
        quitar(conexion)
        sys.exit("Listo. Vuelve a ejecutar el paquete SSIS para actualizar el Data Warehouse.")

    rng = np.random.default_rng(SEMILLA)
    grupos, metodos, estados, usuarios = leer_catalogos(cursor)
    familias = generar(grupos, rng)
    print("=== Datos de prueba generados (semilla 42) ===")
    resumen(familias)

    if "--insertar" not in sys.argv:
        print("\nSolo simulacion: no se escribio nada. Usa --insertar para guardarlos en la base.")
        sys.exit(0)

    if cursor.execute("SELECT COUNT(1) FROM PAGO WHERE numero_recibo LIKE 'SIM-%'").fetchval():
        sys.exit("Ya hay pagos de prueba (SIM-) en la base. Usa --quitar antes de volver a insertarlos.")

    MAXIMOS = {t: cursor.execute(f"SELECT ISNULL(MAX({c}), 0) FROM {t}").fetchval() for t, c in
               [("TUTOR", "id_tutor"), ("ALUMNO", "id_alumno"), ("INSCRIPCION", "id_inscripcion"),
                ("MENSUALIDAD", "id_mensualidad"), ("PAGO", "id_pago")]}
    antes = huella_existente(cursor)
    try:
        nuevas = insertar(conexion, familias, metodos, estados, usuarios, rng)
        despues = huella_existente(cursor)
        assert antes == despues, "las filas existentes cambiaron: se cancela todo"
        conexion.commit()
    except Exception:
        conexion.rollback()
        print("ERROR: no se guardo nada (la transaccion se deshizo).")
        raise
    print("\n=== Filas nuevas insertadas ===")
    for tabla, n in nuevas.items():
        print(f"   {tabla:12s} {n}")
    print("Filas existentes sin cambios: verificado.")
    print("Ahora vuelve a ejecutar el paquete SSIS para que el Data Warehouse incluya los pagos nuevos.")
