"""
=====================================================================
 DATA MINING - PREDICCION DE PAGOS ATRASADOS
 Escuela de futbol  |  Data Warehouse DW_EscuelasDeportivas
 Metodologia: CRISP-DM   |   Herramienta: Python
 Librerias: pandas, matplotlib, seaborn, scikit-learn
=====================================================================

AVISO SOBRE LOS DATOS (leer antes de presentar)
    H_PAGOS mezcla dos tipos de datos, y NINGUNO es de una escuela real:
      - Los pagos con recibo REC- son los datos de ejemplo de la base
        entregada con el practico.
      - Los pagos con recibo SIM- y PRB- son DATOS SIMULADOS, generados con
        generar_pagos_prueba.py (semilla 42) y pagos_prueba_60.sql para probar el modelo.
    Los resultados muestran como funciona la tecnica, pero NO describen el
    comportamiento real de los tutores.

COMO SE EJECUTA
    python mineria_pagos.py          -> lee H_PAGOS del Data Warehouse
                                        (si no hay conexion, usa el CSV)
    python mineria_pagos.py --csv    -> usa siempre el CSV de ejemplo

QUE GENERA (carpeta "resultados")
    - 13 graficos PNG
    - dashboard.html   (todos los resultados en una sola pagina)
    - metricas.json    (los numeros, para el documento)
    - Presentacion_Data_Mining.docx  (documento Word)

FASES CRISP-DM EN ESTE SCRIPT
    1. Comprension del negocio   -> que queremos resolver
    2. Comprension de los datos  -> carga y 5 graficos de exploracion
    3. Preparacion de los datos  -> variables para el modelo
    4. Modelado                  -> 3 modelos, validacion cruzada, balanceo
    5. Evaluacion                -> matriz, curva ROC, importancia, arbol
    6. Despliegue                -> clustering, dashboard y documento
"""

import base64
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                     # guardar imagenes sin abrir ventanas
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score, roc_curve, silhouette_score)
from sklearn.model_selection import StratifiedGroupKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier, plot_tree

warnings.filterwarnings("ignore", category=UserWarning)

# =====================================================================
# 0. CONFIGURACION
# =====================================================================
SERVIDOR = r"localhost\MSSQLSERVER01"
DATA_WAREHOUSE = "DW_EscuelasDeportivas"
CARPETA = Path(__file__).parent
CSV_EJEMPLO = CARPETA / "datos" / "h_pagos_ejemplo.csv"
RESULTADOS = CARPETA / "resultados"
RESULTADOS.mkdir(exist_ok=True)
SEMILLA = 42                              # para que cada ejecucion de lo mismo

# Paleta unica para todos los graficos (validada para daltonismo)
AZUL, NARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"     # a tiempo / atrasado / tercer grupo
VIOLETA = "#4a3aa7"                                        # tercer modelo
GRIS = "#c3c2b7"                                           # "sin mejora" en comparaciones
TINTA, TINTA_2, TENUE = "#0b0b0b", "#52514e", "#898781"
GRILLA, FONDO = "#e1e0d9", "#fcfcfb"
COLOR_CLASE = {0: AZUL, 1: NARANJA}
NOMBRE_CLASE = {0: "A tiempo", 1: "Atrasado"}
RAMPA_NARANJA = LinearSegmentedColormap.from_list("naranja", ["#fdf0ea", "#f6b79d", "#eb6834", "#a8401a"])
RAMPA_AZUL = LinearSegmentedColormap.from_list("azul", ["#e6f0fc", "#86b6ef", "#2a78d6", "#0d366b"])

sns.set_theme(style="white")
plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10.5,
    "figure.facecolor": FONDO, "axes.facecolor": FONDO, "savefig.facecolor": FONDO,
    "text.color": TINTA, "axes.labelcolor": TINTA_2, "axes.edgecolor": GRIS,
    "xtick.color": TINTA_2, "ytick.color": TINTA_2, "axes.titlesize": 13,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 26,
})

GRAFICOS = []        # cada grafico guardado: archivo, titulo y explicacion (para el dashboard)


def estilo(ax, grilla="y"):
    """Ejes limpios: sin bordes de arriba/derecha y con grilla suave."""
    ax.spines[["top", "right"]].set_visible(False)
    if grilla:
        ax.grid(axis=grilla, color=GRILLA, linewidth=0.8)
        ax.set_axisbelow(True)
    ax.tick_params(length=0)


def subtitulo(ax, texto):
    ax.text(0, 1.02, texto, transform=ax.transAxes, fontsize=10, color=TINTA_2, va="bottom")


def guardar(fig, archivo, titulo, explicacion, seccion):
    ruta = RESULTADOS / archivo
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)
    GRAFICOS.append({"archivo": archivo, "titulo": titulo, "explicacion": explicacion, "seccion": seccion})
    print(f"   grafico: {archivo}")


def pct(x):
    return f"{x * 100:.0f}%"


def orden_categoria(nombre):
    digitos = "".join(c for c in str(nombre) if c.isdigit())
    return int(digitos) if digitos else 0


# =====================================================================
# 1. COMPRENSION DEL NEGOCIO
# =====================================================================
# Problema: algunos tutores pagan la mensualidad despues del vencimiento.
# Objetivo: predecir que pagos van a llegar ATRASADOS y entender que
#           factores influyen (categoria, metodo de pago, monto), para que
#           la escuela recuerde el pago a tiempo a esos tutores.
# Exito:    que el modelo detecte la mayoria de los atrasos (sensibilidad)
#           sin llenar de falsas alarmas, y que supere a "adivinar siempre
#           a tiempo".
print("\n1. COMPRENSION DEL NEGOCIO: predecir pagos atrasados para recordar a tiempo.")

# =====================================================================
# 2. COMPRENSION DE LOS DATOS
# =====================================================================
print("\n2. COMPRENSION DE LOS DATOS")

CONSULTA = """
    SELECT H.id_alumno, C.nombre_categoria AS categoria, MP.nombre_metodo_pago AS metodo_pago,
           E.nombre_estado_pago AS estado_pago, T.fecha, H.numero_recibo,
           H.monto_mensualidad, H.monto_pagado, H.saldo_pendiente, H.dias_atraso, H.pago_atrasado
    FROM H_PAGOS H
    INNER JOIN D_CATEGORIA C    ON H.id_categoria   = C.id_categoria
    INNER JOIN D_METODO_PAGO MP ON H.id_metodo_pago = MP.id_metodo_pago
    INNER JOIN D_ESTADO_PAGO E  ON H.id_estado_pago = E.id_estado_pago
    INNER JOIN D_TIEMPO T       ON H.id_tiempo      = T.id_tiempo
    ORDER BY H.id_hecho;
"""


def cargar_datos():
    """Lee H_PAGOS del Data Warehouse; si no se puede, usa el CSV de ejemplo."""
    if "--csv" not in sys.argv:
        try:
            import pyodbc
            conexion = pyodbc.connect(
                "DRIVER={ODBC Driver 17 for SQL Server};"
                f"SERVER={SERVIDOR};DATABASE={DATA_WAREHOUSE};Trusted_Connection=yes;", timeout=5)
            cursor = conexion.cursor()
            cursor.execute(CONSULTA)
            columnas = [c[0] for c in cursor.description]
            tabla = pd.DataFrame.from_records(cursor.fetchall(), columns=columnas)
            conexion.close()
            return tabla, f"Data Warehouse {DATA_WAREHOUSE} ({SERVIDOR})"
        except Exception as error:
            print(f"   Sin conexion al Data Warehouse ({type(error).__name__}). Se usa el CSV de ejemplo.")
    return pd.read_csv(CSV_EJEMPLO), f"CSV de ejemplo ({CSV_EJEMPLO.name})"


pagos, FUENTE = cargar_datos()
pagos["fecha"] = pd.to_datetime(pagos["fecha"])
for columna in ["monto_mensualidad", "monto_pagado", "saldo_pendiente"]:
    pagos[columna] = pagos[columna].astype(float)
pagos["dias_atraso"] = pagos["dias_atraso"].astype(int)
pagos["atrasado"] = pagos["pago_atrasado"].astype(int)
pagos["estado"] = pagos["atrasado"].map(NOMBRE_CLASE)
categorias = sorted(pagos["categoria"].unique(), key=orden_categoria)
metodos = pagos.groupby("metodo_pago")["atrasado"].mean().sort_values(ascending=False).index.tolist()

tasa_general = pagos["atrasado"].mean()
recibos_pago = pagos["numero_recibo"].astype(str)
pagos_simulados = int(recibos_pago.str.match(r"(SIM|PRB)-").sum())   # SIM- y PRB-: datos simulados
pagos_entregados = int(recibos_pago.str.startswith("REC-").sum())     # REC-: base entregada con el practico
pagos_app = len(pagos) - pagos_simulados - pagos_entregados            # PAG-: registrados en la app web
print(f"   Fuente: {FUENTE}")
print(f"   {len(pagos)} pagos de {pagos['id_alumno'].nunique()} alumnos | "
      f"{pagos['atrasado'].sum()} atrasados ({pct(tasa_general)})")

# Cada categoria tiene un solo monto? Entonces monto y categoria dicen lo mismo.
montos_por_categoria = pagos.groupby("categoria")["monto_mensualidad"].nunique()
monto_igual_categoria = bool((montos_por_categoria == 1).all())

# --- Grafico 1: cantidad de pagos por metodo, a tiempo vs atrasados -------
conteo = pd.crosstab(pagos["metodo_pago"], pagos["atrasado"]).reindex(metodos)
fig, ax = plt.subplots(figsize=(8, 4.6))
base = np.zeros(len(conteo))
for clase in [0, 1]:
    ax.bar(conteo.index, conteo[clase], bottom=base, color=COLOR_CLASE[clase], width=0.6,
           edgecolor=FONDO, linewidth=2, label=NOMBRE_CLASE[clase])
    for i, valor in enumerate(conteo[clase]):
        if valor >= 6:
            ax.text(i, base[i] + valor / 2, str(valor), ha="center", va="center", color="white", fontsize=10)
    base += conteo[clase].values
for i, total in enumerate(base):
    ax.text(i, total + 2, f"{int(total)} pagos", ha="center", va="bottom", fontsize=9.5, color=TINTA_2)
estilo(ax)
ax.set_ylabel("Cantidad de pagos")
ax.set_ylim(0, base.max() * 1.15)
ax.legend(frameon=False, loc="upper left")
metodo_mas_usado = conteo.sum(axis=1).idxmax()
tasa_metodo = pagos.groupby("metodo_pago")["atrasado"].mean()
ax.set_title("Pagos por método de pago")
subtitulo(ax, f"El más usado es {metodo_mas_usado}; el de más atraso, {metodos[0]} ({pct(tasa_metodo[metodos[0]])} de sus pagos)")
guardar(fig, "01_pagos_por_metodo.png", "Pagos por método de pago",
        f"Cuántos pagos se hicieron con cada método y cuántos llegaron tarde (naranja). "
        f"{metodo_mas_usado} es el más usado; {metodos[0]} es el que más se atrasa ({pct(tasa_metodo[metodos[0]])}) "
        f"y {metodos[-1]} el que menos ({pct(tasa_metodo[metodos[-1]])}).", "exploracion")

# --- Grafico 2: boxplot de dias de atraso por categoria --------------------
fig, ax = plt.subplots(figsize=(8, 4.6))
sns.boxplot(data=pagos, x="categoria", y="dias_atraso", order=categorias, ax=ax, color="#cde2fb",
            width=0.55, linewidth=1.2, fliersize=0,
            medianprops={"color": AZUL, "linewidth": 2}, boxprops={"edgecolor": TINTA_2},
            whiskerprops={"color": TINTA_2}, capprops={"color": TINTA_2})
sns.stripplot(data=pagos, x="categoria", y="dias_atraso", order=categorias, hue="atrasado",
              palette=COLOR_CLASE, size=3.5, jitter=0.22, alpha=0.75, ax=ax, legend=False)
ax.axhline(0, color=TINTA_2, linewidth=1)
ax.axhline(15, color=NARANJA, linewidth=1, linestyle=(0, (4, 3)))
ax.text(-0.45, 0.6, "vencimiento", ha="left", va="bottom", fontsize=9, color=TINTA_2)
ax.text(len(categorias) - 0.5, 15.6, "atraso crítico (15 días)", ha="right", va="bottom", fontsize=9, color=NARANJA)
estilo(ax)
ax.set_xlabel("")
ax.set_ylabel("Días de atraso (negativo = pagó antes)")
mediana_cat = pagos.groupby("categoria")["dias_atraso"].median()
ax.set_title("Días de atraso por categoría")
subtitulo(ax, "Cada punto es un pago (naranja = atrasado). La caja contiene la mitad central de los pagos.")
guardar(fig, "02_boxplot_dias_categoria.png", "Días de atraso por categoría",
        "Cada punto es un pago; la caja muestra dónde está la mitad de los pagos y la línea azul es la mediana. "
        "Por debajo de 0 el pago llegó antes del vencimiento; por encima de 15 es un atraso crítico. "
        f"Las medianas por categoría van de {mediana_cat.min():g} a {mediana_cat.max():g} días.", "exploracion")

# --- Grafico 3: dispersion monto vs dias de atraso -------------------------
fig, ax = plt.subplots(figsize=(8, 4.6))
rng = np.random.default_rng(SEMILLA)
montos = sorted(pagos["monto_mensualidad"].unique())
for clase in [0, 1]:
    datos_clase = pagos[pagos["atrasado"] == clase]
    x = datos_clase["monto_mensualidad"] + rng.uniform(-5, 5, len(datos_clase))   # pequeno desplazamiento para que no se tapen
    ax.scatter(x, datos_clase["dias_atraso"], s=34, color=COLOR_CLASE[clase], alpha=0.8,
               edgecolor=FONDO, linewidth=1, label=NOMBRE_CLASE[clase])
ax.axhline(0, color=TINTA_2, linewidth=1)
ax.set_xticks(montos, [f"{m:g} Bs" for m in montos])
estilo(ax, grilla="both")
ax.set_xlabel("Monto de la mensualidad")
ax.set_ylabel("Días de atraso")
ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1))
correlacion = pagos["monto_mensualidad"].corr(pagos["dias_atraso"])
ax.set_title("Monto de la mensualidad vs días de atraso")
subtitulo(ax, f"Correlación = {correlacion:.2f} (cerca de 0: el monto casi no se relaciona con el atraso)"
          if abs(correlacion) < 0.2 else f"Correlación = {correlacion:.2f}")
nota_monto = (" Ojo: en estos datos cada categoría tiene un único monto, así que monto y categoría "
              "dan la misma información." if monto_igual_categoria else "")
guardar(fig, "03_scatter_monto_dias.png", "Monto vs días de atraso",
        f"Cada punto es un pago. Sirve para ver si las mensualidades más caras se pagan más tarde. "
        f"La correlación es {correlacion:.2f}: {'casi no hay relación' if abs(correlacion) < 0.2 else 'hay cierta relación'}."
        + nota_monto, "exploracion")

# --- Grafico 4: % de pagos atrasados por categoria -------------------------
tasa_cat = pagos.groupby("categoria")["atrasado"].mean().reindex(categorias)
fig, ax = plt.subplots(figsize=(8, 4.6))
barras = ax.bar(tasa_cat.index, tasa_cat.values * 100, color=NARANJA, width=0.55)
ax.bar_label(barras, labels=[pct(v) for v in tasa_cat.values], padding=3, fontsize=10)
ax.axhline(tasa_general * 100, color=TINTA_2, linewidth=1, linestyle=(0, (4, 3)))
estilo(ax)
ax.set_ylim(0, max(100, tasa_cat.max() * 120))
ax.set_ylabel("% de pagos atrasados")
ax.set_title("Porcentaje de pagos atrasados por categoría")
diferencia_cat = tasa_cat.max() - tasa_cat.min()
subtitulo(ax, f"Línea punteada = promedio de la escuela ({pct(tasa_general)}). Diferencia entre la mayor y la menor: {diferencia_cat * 100:.0f} puntos")
guardar(fig, "04_pct_atraso_categoria.png", "% de atraso por categoría",
        f"Qué porcentaje de los pagos de cada categoría llegó tarde, comparado con el promedio ({pct(tasa_general)}). "
        f"{tasa_cat.idxmax()} es la que más se atrasa ({pct(tasa_cat.max())}) y {tasa_cat.idxmin()} la que menos "
        f"({pct(tasa_cat.min())}).", "exploracion")

# --- Grafico 5: mapa de calor categoria x metodo ---------------------------
tabla_calor = pagos.pivot_table(index="categoria", columns="metodo_pago", values="atrasado", aggfunc="mean").reindex(index=categorias, columns=metodos)
tabla_n = pagos.pivot_table(index="categoria", columns="metodo_pago", values="atrasado", aggfunc="size").reindex(index=categorias, columns=metodos)
etiquetas = tabla_calor.map(lambda v: "" if pd.isna(v) else pct(v)) + tabla_n.map(lambda n: "" if pd.isna(n) else f"\n(n={int(n)})")
fig, ax = plt.subplots(figsize=(8, 4.8))
sns.heatmap(tabla_calor * 100, annot=etiquetas, fmt="", cmap=RAMPA_NARANJA, vmin=0, vmax=100,
            linewidths=2, linecolor=FONDO, ax=ax, annot_kws={"fontsize": 9.5},
            cbar_kws={"label": "% de pagos atrasados", "shrink": 0.85})
ax.set_xlabel("")
ax.set_ylabel("")
ax.tick_params(length=0)
ax.set_title("Atraso por categoría y método de pago")
subtitulo(ax, "Más oscuro = más atraso. n = cantidad de pagos en esa combinación.")
guardar(fig, "05_heatmap_categoria_metodo.png", "Categoría vs método de pago",
        "Cada cuadro cruza una categoría con un método de pago: cuanto más oscuro, mayor el porcentaje de atrasos. "
        "Permite ver si un método se atrasa en todas las categorías o solo en algunas. "
        "Los cuadros con n pequeño (pocos pagos) son menos confiables.", "exploracion")

# =====================================================================
# 3. PREPARACION DE LOS DATOS
# =====================================================================
print("\n3. PREPARACION DE LOS DATOS")
# Que NO usamos y por que: monto_pagado, saldo_pendiente, dias_atraso y el
# estado del pago se conocen DESPUES de pagar. Usarlos seria hacer trampa
# (el modelo veria la respuesta).
#
# Que SI usamos (se conoce ANTES del vencimiento):
#   - categoria, metodo_pago, monto_mensualidad  -> los factores del objetivo
#   - pct_atrasos_previos: % de pagos anteriores del alumno que llegaron tarde
#     (su "historial"; es lo que mira cualquier cobrador en la vida real)
pagos = pagos.sort_values(["id_alumno", "fecha"]).reset_index(drop=True)
por_alumno = pagos.groupby("id_alumno")
pagos["pagos_previos"] = por_alumno.cumcount()
pagos["pct_atrasos_previos"] = (por_alumno["atrasado"].cumsum() - pagos["atrasado"]) / pagos["pagos_previos"]

# El primer pago de cada alumno no tiene historial: se deja fuera del modelo.
modelado = pagos[pagos["pagos_previos"] >= 1].copy()
CATEGORICAS = ["categoria", "metodo_pago"]
NUMERICAS = ["monto_mensualidad", "pct_atrasos_previos"]
X = modelado[CATEGORICAS + NUMERICAS]
y = modelado["atrasado"]
grupos = modelado["id_alumno"]           # para separar por alumno en la validacion
NOMBRES_VARIABLES = {"categoria": "Categoría", "metodo_pago": "Método de pago",
                     "monto_mensualidad": "Monto mensualidad", "pct_atrasos_previos": "% atrasos previos"}

n_a_tiempo, n_atrasados = int((y == 0).sum()), int((y == 1).sum())
proporcion = n_a_tiempo / n_atrasados
print(f"   Filas para el modelo: {len(modelado)} (sin el primer pago de cada alumno)")
print(f"   Clases: {n_a_tiempo} a tiempo / {n_atrasados} atrasados  ->  {proporcion:.1f} a 1")

# --- Grafico 6: balance de clases -------------------------------------------
fig, ax = plt.subplots(figsize=(6.5, 4))
barras = ax.barh(["Atrasado", "A tiempo"], [n_atrasados, n_a_tiempo], color=[NARANJA, AZUL], height=0.55)
ax.bar_label(barras, labels=[f"{n_atrasados} ({pct(n_atrasados / len(y))})", f"{n_a_tiempo} ({pct(n_a_tiempo / len(y))})"],
             padding=4, fontsize=10)
estilo(ax, grilla="x")
ax.set_xlim(0, n_a_tiempo * 1.3)
ax.set_xlabel("Cantidad de pagos")
ax.set_title("Balance de clases")
subtitulo(ax, f"Hay {proporcion:.1f} pagos a tiempo por cada atrasado")
guardar(fig, "06_balance_clases.png", "Balance de clases",
        f"Hay {proporcion:.1f} pagos a tiempo por cada pago atrasado. Cuando una clase es mayoría, el modelo tiende "
        "a favorecerla y deja pasar atrasos. Por eso se prueba una corrección (class_weight='balanced').", "modelo")

# =====================================================================
# 4. MODELADO
# =====================================================================
print("\n4. MODELADO")


def preparador(escalar):
    """Convierte texto en columnas 0/1 (one-hot). La regresion logistica
    ademas necesita los numeros en la misma escala."""
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAS),
        ("num", StandardScaler() if escalar else "passthrough", NUMERICAS),
    ])


def crear_modelos(balanceo):
    peso = "balanced" if balanceo else None
    return {
        "Árbol de decisión": Pipeline([("prep", preparador(False)), ("modelo", DecisionTreeClassifier(
            max_depth=3, min_samples_leaf=10, class_weight=peso, random_state=SEMILLA))]),
        "Random Forest": Pipeline([("prep", preparador(False)), ("modelo", RandomForestClassifier(
            n_estimators=300, min_samples_leaf=5, class_weight=peso, random_state=SEMILLA, n_jobs=-1))]),
        "Regresión logística": Pipeline([("prep", preparador(True)), ("modelo", LogisticRegression(
            max_iter=1000, class_weight=peso))]),
    }


# Validacion cruzada de 5 partes, SEPARANDO POR ALUMNO: los pagos de un mismo
# alumno quedan todos del mismo lado, asi el modelo se evalua siempre con
# alumnos que no vio al aprender.
validacion = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMILLA)
METRICAS = {"exactitud": "accuracy", "precision": "precision", "sensibilidad": "recall", "f1": "f1", "auc": "roc_auc"}
comparacion = []
for balanceo in [False, True]:
    for nombre, modelo in crear_modelos(balanceo).items():
        r = cross_validate(modelo, X, y, groups=grupos, cv=validacion, scoring=METRICAS)
        fila = {"modelo": nombre, "balanceo": balanceo}
        for metrica in METRICAS:
            fila[metrica] = float(r[f"test_{metrica}"].mean())
            fila[metrica + "_desv"] = float(r[f"test_{metrica}"].std())
        comparacion.append(fila)
        print(f"   {nombre:20s} balanceo={'si' if balanceo else 'no'}  exactitud={fila['exactitud']:.2f}  "
              f"sensibilidad={fila['sensibilidad']:.2f}  F1={fila['f1']:.2f}  AUC={fila['auc']:.2f}")
comparacion = pd.DataFrame(comparacion)
exactitud_base = n_a_tiempo / len(y)      # adivinar siempre "a tiempo"

# El mejor modelo: el de mayor F1 (equilibrio entre detectar atrasos y no dar falsas alarmas)
mejor = comparacion.loc[comparacion["f1"].idxmax()]
MEJOR_NOMBRE, MEJOR_BALANCEO = mejor["modelo"], bool(mejor["balanceo"])
print(f"   Mejor modelo (F1): {MEJOR_NOMBRE} {'con' if MEJOR_BALANCEO else 'sin'} balanceo")

# --- Grafico 7: antes y despues del balanceo -------------------------------
fig, ax = plt.subplots(figsize=(8.5, 4.6))
nombres_modelos = list(crear_modelos(False))
posiciones = np.arange(len(nombres_modelos))
for desplazamiento, balanceo, color, etiqueta in [(-0.19, False, GRIS, "Sin balanceo"), (0.19, True, AZUL, "Con class_weight='balanced'")]:
    valores = [comparacion.query("modelo == @n and balanceo == @balanceo")["sensibilidad"].iloc[0] for n in nombres_modelos]
    barras = ax.bar(posiciones + desplazamiento, np.array(valores) * 100, width=0.36, color=color,
                    edgecolor=FONDO, linewidth=2, label=etiqueta)
    ax.bar_label(barras, labels=[pct(v) for v in valores], padding=3, fontsize=10)
ax.set_xticks(posiciones, nombres_modelos)
ax.set_ylim(0, 110)
ax.set_ylabel("Sensibilidad: % de atrasos detectados")
estilo(ax)
ax.legend(frameon=False, loc="upper right", ncols=2)
arbol_antes = comparacion.query("modelo == 'Árbol de decisión' and not balanceo").iloc[0]
arbol_despues = comparacion.query("modelo == 'Árbol de decisión' and balanceo").iloc[0]
ax.set_title("Efecto del balanceo de clases")
subtitulo(ax, "Validación cruzada de 5 partes. Más alto = el modelo deja pasar menos atrasos.")
guardar(fig, "07_balanceo_antes_despues.png", "Antes y después del balanceo",
        f"Compara cuántos atrasos detecta cada modelo sin y con class_weight='balanced'. En el árbol, la sensibilidad "
        f"pasa de {pct(arbol_antes['sensibilidad'])} a {pct(arbol_despues['sensibilidad'])} y la precisión de "
        f"{pct(arbol_antes['precision'])} a {pct(arbol_despues['precision'])}: detecta más atrasos a cambio de "
        "algunas falsas alarmas más.", "modelo")

# --- Grafico 8: comparacion de modelos (validacion cruzada) ----------------
fig, ax = plt.subplots(figsize=(8.5, 4.6))
elegidos = comparacion[comparacion["balanceo"] == MEJOR_BALANCEO].set_index("modelo").reindex(nombres_modelos)
metricas_grafico = [("exactitud", "Exactitud"), ("sensibilidad", "Sensibilidad"), ("f1", "F1"), ("auc", "AUC")]
colores_modelo = dict(zip(nombres_modelos, [AZUL, AQUA, VIOLETA]))
ancho = 0.26
for i, nombre in enumerate(nombres_modelos):
    valores = [elegidos.loc[nombre, m] for m, _ in metricas_grafico]
    errores = [elegidos.loc[nombre, m + "_desv"] for m, _ in metricas_grafico]
    barras = ax.bar(np.arange(4) + (i - 1) * ancho, np.array(valores) * 100, width=ancho, color=colores_modelo[nombre],
                    edgecolor=FONDO, linewidth=2, label=nombre, yerr=np.array(errores) * 100,
                    error_kw={"ecolor": TINTA_2, "elinewidth": 1, "capsize": 2})
    ax.bar_label(barras, labels=[f"{v * 100:.0f}" for v in valores], label_type="center", fontsize=9, fontweight="bold",
                 color=TINTA if colores_modelo[nombre] == AQUA else "white")   # el aqua es claro: texto oscuro
ax.hlines(exactitud_base * 100, -0.45, 0.45, color=TINTA, linewidth=1.5, linestyle=(0, (4, 3)))
ax.text(-0.45, 101, f"línea punteada: adivinar siempre 'a tiempo' ({pct(exactitud_base)})", fontsize=9, color=TINTA_2)
ax.set_xticks(np.arange(4), [n for _, n in metricas_grafico])
ax.set_ylim(0, 115)
ax.set_ylabel("Puntaje (%)")
estilo(ax)
ax.legend(frameon=False, loc="upper center", ncols=3, bbox_to_anchor=(0.5, -0.1))
ax.set_title("Comparación de modelos")
subtitulo(ax, f"Promedio de 5 validaciones ({'con' if MEJOR_BALANCEO else 'sin'} balanceo). La rayita muestra cuánto varía.")
guardar(fig, "08_comparacion_modelos.png", "Comparación de modelos",
        f"Los tres modelos evaluados con la misma validación cruzada. El de mejor F1 es {MEJOR_NOMBRE} "
        f"(F1 {mejor['f1']:.2f}, AUC {mejor['auc']:.2f}). La línea punteada es la exactitud de adivinar siempre "
        f"'a tiempo' ({pct(exactitud_base)}): un modelo útil tiene que superarla.", "modelo")

# =====================================================================
# 5. EVALUACION
# =====================================================================
print("\n5. EVALUACION")
# Separamos un grupo de alumnos (25%) que el modelo no ve al aprender.
entrena_idx, prueba_idx = next(StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=SEMILLA).split(X, y, grupos))
X_ent, X_pru, y_ent, y_pru = X.iloc[entrena_idx], X.iloc[prueba_idx], y.iloc[entrena_idx], y.iloc[prueba_idx]
modelos_finales = crear_modelos(MEJOR_BALANCEO)
for modelo in modelos_finales.values():
    modelo.fit(X_ent, y_ent)
modelo_mejor = modelos_finales[MEJOR_NOMBRE]
prob_pru = modelo_mejor.predict_proba(X_pru)[:, 1]
pred_pru = (prob_pru >= 0.5).astype(int)
prueba = {
    "filas": int(len(y_pru)), "alumnos": int(grupos.iloc[prueba_idx].nunique()),
    "exactitud": float(accuracy_score(y_pru, pred_pru)), "precision": float(precision_score(y_pru, pred_pru, zero_division=0)),
    "sensibilidad": float(recall_score(y_pru, pred_pru)), "f1": float(f1_score(y_pru, pred_pru)),
    "auc": float(roc_auc_score(y_pru, prob_pru)), "matriz": confusion_matrix(y_pru, pred_pru).tolist(),
    "exactitud_base": float((y_pru == 0).mean()),
}
(vn, fp), (fn, vp) = prueba["matriz"]
print(f"   Prueba con {prueba['alumnos']} alumnos nuevos ({prueba['filas']} pagos): exactitud {pct(prueba['exactitud'])}, "
      f"detecta {vp} de {vp + fn} atrasos")

# --- Grafico 9: matriz de confusion -----------------------------------------
fig, ax = plt.subplots(figsize=(6.4, 5))
matriz = np.array(prueba["matriz"])
textos = np.array([[f"{vn}\nacierto", f"{fp}\nfalsa alarma"], [f"{fn}\nno detectado", f"{vp}\nacierto"]])
sns.heatmap(matriz, annot=textos, fmt="", cmap=RAMPA_AZUL, cbar=False, linewidths=3, linecolor=FONDO,
            annot_kws={"fontsize": 12}, ax=ax, vmin=0)
ax.set_xticklabels(["A tiempo", "Atrasado"])
ax.set_yticklabels(["A tiempo", "Atrasado"], rotation=0)
ax.set_xlabel("Lo que predijo el modelo")
ax.set_ylabel("Lo que pasó en realidad")
ax.tick_params(length=0)
ax.set_title(f"Matriz de confusión: {MEJOR_NOMBRE}")
subtitulo(ax, f"{prueba['filas']} pagos de {prueba['alumnos']} alumnos que el modelo no vio. Exactitud {pct(prueba['exactitud'])}.")
guardar(fig, "09_matriz_confusion.png", "Matriz de confusión",
        f"Compara lo que predijo el modelo con lo que pasó, en {prueba['alumnos']} alumnos que no vio al aprender. "
        f"Acertó {vn + vp} de {prueba['filas']} pagos; detectó {vp} de {vp + fn} atrasos; dio {fp} falsas alarmas "
        f"y dejó pasar {fn} atrasos.", "evaluacion")

# --- Grafico 10: curvas ROC ---------------------------------------------------
fig, ax = plt.subplots(figsize=(6.4, 5.4))
auc_prueba = {}
for nombre, modelo in modelos_finales.items():
    probabilidades = modelo.predict_proba(X_pru)[:, 1]
    fpr, tpr, _ = roc_curve(y_pru, probabilidades)
    auc_prueba[nombre] = float(roc_auc_score(y_pru, probabilidades))
    ax.plot(fpr, tpr, color=colores_modelo[nombre], linewidth=2, label=f"{nombre} (AUC {auc_prueba[nombre]:.2f})")
ax.plot([0, 1], [0, 1], color=TENUE, linewidth=1, linestyle=(0, (4, 3)), label="Al azar (AUC 0.50)")
ax.set_xlabel("Falsas alarmas (proporción de pagos a tiempo marcados)")
ax.set_ylabel("Atrasos detectados (sensibilidad)")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1.02)
estilo(ax, grilla="both")
ax.legend(frameon=False, loc="lower right", fontsize=9)
ax.set_title("Curva ROC")
subtitulo(ax, "Cuanto más se acerca la curva a la esquina superior izquierda, mejor.")
guardar(fig, "10_curva_roc.png", "Curva ROC",
        "Muestra el equilibrio entre detectar atrasos y dar falsas alarmas al mover el umbral de decisión. "
        "El AUC resume la curva: 0.5 es adivinar al azar y 1.0 es perfecto. "
        + ", ".join(f"{n}: {v:.2f}" for n, v in auc_prueba.items()) + ".", "evaluacion")

# --- Grafico 11: importancia de variables (por permutacion) ----------------
# Se desordena una variable a la vez y se mide cuanto empeora el modelo.
# Si empeora mucho, esa variable era importante.
importancia = permutation_importance(modelo_mejor, X_pru, y_pru, scoring="roc_auc", n_repeats=50, random_state=SEMILLA)
tabla_importancia = pd.DataFrame({
    "variable": [NOMBRES_VARIABLES[c] for c in X.columns],
    "media": importancia.importances_mean, "desv": importancia.importances_std,
}).sort_values("media")
fig, ax = plt.subplots(figsize=(7.5, 4))
ax.barh(tabla_importancia["variable"], tabla_importancia["media"], xerr=tabla_importancia["desv"], color=AZUL,
        height=0.55, error_kw={"ecolor": TINTA_2, "elinewidth": 1, "capsize": 3})
for i, (media, desv) in enumerate(zip(tabla_importancia["media"], tabla_importancia["desv"])):
    ax.text(max(media + desv, 0) + 0.005, i, f"{media:.3f}", va="center", fontsize=9.5)
ax.axvline(0, color=TINTA_2, linewidth=1)
estilo(ax, grilla="x")
ax.set_xlabel("Cuánto baja el AUC al desordenar la variable")
variable_top = tabla_importancia.iloc[-1]["variable"]
ax.set_title("Importancia de las variables")
subtitulo(ax, f"{MEJOR_NOMBRE}. La variable que más pesa: {variable_top}.")
guardar(fig, "11_importancia_variables.png", "Importancia de variables",
        f"Qué tanto depende el modelo de cada variable: se desordena una variable y se mide cuánto empeora. "
        f"La más importante es '{variable_top}'. Una barra cerca de 0 significa que esa variable casi no ayuda."
        + (" Monto y categoría se reparten la misma información, porque cada categoría tiene un solo monto."
           if monto_igual_categoria else ""), "evaluacion")

# --- Grafico 12: arbol de decision dibujado ---------------------------------
arbol = crear_modelos(MEJOR_BALANCEO)["Árbol de decisión"].fit(X, y)
nombres_columnas = []
for nombre in arbol.named_steps["prep"].get_feature_names_out():
    grupo, columna = nombre.split("__", 1)
    if grupo == "cat":
        variable, valor = columna.split("_", 1) if not columna.startswith("metodo_pago_") else ("metodo_pago", columna[len("metodo_pago_"):])
        nombres_columnas.append(f"{NOMBRES_VARIABLES[variable]} = {valor}")
    else:
        nombres_columnas.append(NOMBRES_VARIABLES[columna])
fig, ax = plt.subplots(figsize=(16, 7.5))
cajas = plot_tree(arbol.named_steps["modelo"], feature_names=nombres_columnas, class_names=["A TIEMPO", "ATRASADO"],
                  impurity=False, proportion=False, rounded=True, fontsize=9, ax=ax)
for caja in cajas:
    lineas = caja.get_text().split("\n")
    if len(lineas) == 1:                       # rotulos True/False de las primeras flechas
        caja.set_text("")
        continue
    muestras = next(l for l in lineas if l.startswith("samples")).split(" = ")[1]
    clase = next(l for l in lineas if l.startswith("class")).split(" = ")[1]
    marco = caja.get_bbox_patch()
    marco.set_edgecolor(GRIS)
    if " <= " in lineas[0]:
        condicion, umbral = lineas[0].split(" <= ")
        if " = " in condicion:                 # variable de texto convertida a 0/1
            caja.set_text(f"¿{condicion}?\n← no     sí →\n{muestras} pagos")
        elif condicion == "% atrasos previos":
            caja.set_text(f"¿{condicion} ≤ {float(umbral) * 100:.0f}%?\n← sí     no →\n{muestras} pagos")
        else:
            caja.set_text(f"¿{condicion} ≤ {float(umbral):g}?\n← sí     no →\n{muestras} pagos")
        marco.set_facecolor(FONDO)
    else:
        caja.set_text(f"{clase}\n{muestras} pagos")
        marco.set_facecolor("#fbd9cb" if clase == "ATRASADO" else "#cde2fb")
    if caja.arrow_patch is not None:
        caja.arrow_patch.set_color(TENUE)
ax.set_title("Árbol de decisión (reglas que aprendió el modelo)", pad=14)
ax.text(0, -0.02, "Se lee de arriba hacia abajo: cada caja blanca es una pregunta; se sigue la flecha según la respuesta "
        "hasta una caja de color, que es la predicción.", transform=ax.transAxes, fontsize=10, color=TINTA_2)
guardar(fig, "12_arbol_decision.png", "Árbol de decisión",
        "Las reglas que aprendió el árbol, como una cadena de preguntas. Es el modelo más fácil de explicar: "
        "cualquier persona puede seguir las flechas y llegar a la predicción.", "evaluacion")

# =====================================================================
# 6. DESPLIEGUE (clustering, dashboard y documento)
# =====================================================================
print("\n6. CLUSTERING Y DESPLIEGUE")
# K-Means agrupa alumnos parecidos SIN decirle la respuesta (aprendizaje no
# supervisado). Usamos dos rasgos de cada alumno: % de pagos atrasados y
# promedio de dias de atraso (pagar antes cuenta como 0).
pagos["dias_positivos"] = pagos["dias_atraso"].clip(lower=0)
alumnos = pagos.groupby("id_alumno").agg(pct_atraso=("atrasado", "mean"), dias_promedio=("dias_positivos", "mean"),
                                         pagos=("atrasado", "size"))
rasgos = StandardScaler().fit_transform(alumnos[["pct_atraso", "dias_promedio"]])
siluetas = {k: float(silhouette_score(rasgos, KMeans(n_clusters=k, n_init=20, random_state=SEMILLA).fit_predict(rasgos)))
            for k in range(2, 7)}
K = 3                                      # 3 grupos: facil de interpretar para la escuela
kmeans = KMeans(n_clusters=K, n_init=20, random_state=SEMILLA).fit(rasgos)
alumnos["grupo_num"] = kmeans.labels_
orden = alumnos.groupby("grupo_num")["pct_atraso"].mean().sort_values().index
NOMBRES_GRUPO = dict(zip(orden, ["Puntuales", "Ocasionales", "Morosos"]))
COLOR_GRUPO = {"Puntuales": AZUL, "Ocasionales": AQUA, "Morosos": NARANJA}
alumnos["grupo"] = alumnos["grupo_num"].map(NOMBRES_GRUPO)
resumen_grupos = alumnos.groupby("grupo").agg(alumnos=("pagos", "size"), pct_atraso=("pct_atraso", "mean"),
                                             dias_promedio=("dias_promedio", "mean")).reindex(["Puntuales", "Ocasionales", "Morosos"])
mejor_k = max(siluetas, key=siluetas.get)

# --- Grafico 13: clustering ----------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1, 2.2]})
ax1.plot(list(siluetas), list(siluetas.values()), color=AZUL, linewidth=2, marker="o", markersize=8)
ax1.scatter([K], [siluetas[K]], s=140, facecolor="none", edgecolor=NARANJA, linewidth=2, zorder=3)
ax1.set_xticks(list(siluetas))
ax1.set_xlabel("Cantidad de grupos (k)")
ax1.set_ylabel("Silueta (más alto = grupos más separados)")
estilo(ax1, grilla="both")
ax1.set_title("¿Cuántos grupos?")
subtitulo(ax1, f"Elegido k = {K} (círculo naranja)")
rng = np.random.default_rng(SEMILLA)
for grupo in ["Puntuales", "Ocasionales", "Morosos"]:
    sub = alumnos[alumnos["grupo"] == grupo]
    ax2.scatter(sub["pct_atraso"] * 100 + rng.uniform(-1.8, 1.8, len(sub)), sub["dias_promedio"] + rng.uniform(-0.15, 0.15, len(sub)),
                s=70, color=COLOR_GRUPO[grupo], edgecolor=FONDO, linewidth=1.5, alpha=0.9,
                label=f"{grupo} ({len(sub)} alumnos)")
ax2.set_xlabel("% de pagos atrasados del alumno")
ax2.set_ylabel("Días de atraso promedio")
estilo(ax2, grilla="both")
ax2.legend(frameon=False, loc="upper left")
ax2.set_title("Grupos de alumnos según su comportamiento de pago (K-Means)")
subtitulo(ax2, "Cada punto es un alumno. Los colores los asignó el algoritmo sin conocer la respuesta.")
fig.tight_layout()
guardar(fig, "13_clustering_kmeans.png", "Grupos de alumnos (K-Means)",
        f"K-Means separó a los alumnos en {K} grupos según cuánto y cuánto tiempo se atrasan: "
        + ", ".join(f"{g}: {int(r.alumnos)} alumnos ({pct(r.pct_atraso)} de atrasos)" for g, r in resumen_grupos.iterrows())
        + f". Según la silueta, el número de grupos más separado sería k = {mejor_k}; se eligió k = {K} porque "
          "es fácil de usar para la escuela.", "clustering")

# --- Conclusiones calculadas a partir de los resultados ---------------------
conclusiones = [
    f"El {pct(tasa_general)} de los pagos llegó atrasado ({pagos['atrasado'].sum()} de {len(pagos)}).",
    (f"El método de pago sí marca diferencia: {metodos[0]} se atrasa en el {pct(tasa_metodo[metodos[0]])} de los casos "
     f"y {metodos[-1]} solo en el {pct(tasa_metodo[metodos[-1]])}."
     if tasa_metodo.max() - tasa_metodo.min() >= 0.15 else
     f"El método de pago casi no marca diferencia: todos se atrasan entre el {pct(tasa_metodo.min())} y el "
     f"{pct(tasa_metodo.max())} de las veces."),
    (f"La categoría influye poco: entre la que más y la que menos se atrasa hay {diferencia_cat * 100:.0f} puntos."
     if diferencia_cat < 0.15 else
     f"La categoría influye: {tasa_cat.idxmax()} se atrasa {diferencia_cat * 100:.0f} puntos más que {tasa_cat.idxmin()}."),
    (f"El monto no aporta información propia: cada categoría tiene un solo monto y la correlación con los días "
     f"de atraso es {correlacion:.2f}." if monto_igual_categoria else
     f"La correlación entre monto y días de atraso es {correlacion:.2f}."),
    f"La variable que más ayuda a predecir es '{variable_top}'.",
    (f"El mejor modelo fue {MEJOR_NOMBRE} {'con' if MEJOR_BALANCEO else 'sin'} balanceo: en validación cruzada detecta "
     f"el {pct(mejor['sensibilidad'])} de los atrasos con un AUC de {mejor['auc']:.2f}, frente a una exactitud de "
     f"{pct(exactitud_base)} si se adivina siempre 'a tiempo'."
     if mejor["auc"] >= 0.6 else
     f"Ningún modelo logra predecir bien: el mejor ({MEJOR_NOMBRE}) tiene un AUC de {mejor['auc']:.2f}, cerca de 0.5 "
     "(adivinar al azar). En estos datos de ejemplo el atraso no depende de las variables disponibles, así que no hay "
     "un patrón que aprender. Con datos reales de la escuela habría que repetir el análisis."),
    f"Con el balanceo de clases, la detección de atrasos del árbol pasa de {pct(arbol_antes['sensibilidad'])} a "
    f"{pct(arbol_despues['sensibilidad'])} y la precisión de {pct(arbol_antes['precision'])} a {pct(arbol_despues['precision'])}.",
    (f"K-Means identificó {int(resumen_grupos.loc['Morosos', 'alumnos'])} alumnos con comportamiento moroso: "
     "son los primeros a quienes conviene recordar el pago."
     if resumen_grupos.loc["Morosos", "pct_atraso"] >= 0.6 else
     f"K-Means separó a los alumnos en {K} grupos, pero las diferencias son pequeñas: el grupo con más atraso se "
     f"atrasa en el {pct(resumen_grupos.loc['Morosos', 'pct_atraso'])} de sus pagos y el de menos en el "
     f"{pct(resumen_grupos.loc['Puntuales', 'pct_atraso'])}."),
]

# --- metricas.json ------------------------------------------------------------
metricas = {
    "generado": datetime.now().strftime("%d/%m/%Y %H:%M"), "fuente": FUENTE, "pagos_simulados": pagos_simulados, "pagos_entregados": pagos_entregados,
    "pagos": int(len(pagos)), "alumnos": int(pagos["id_alumno"].nunique()), "atrasados": int(pagos["atrasado"].sum()),
    "tasa_atraso": float(tasa_general), "filas_modelo": int(len(modelado)),
    "clases": {"a_tiempo": n_a_tiempo, "atrasado": n_atrasados, "proporcion": float(proporcion)},
    "tasa_por_metodo": {k: float(v) for k, v in tasa_metodo.items()},
    "tasa_por_categoria": {k: float(v) for k, v in tasa_cat.items()},
    "metodo_mas_usado": metodo_mas_usado, "monto_igual_categoria": monto_igual_categoria,
    "correlacion_monto_dias": float(correlacion), "exactitud_base": float(exactitud_base),
    "comparacion": comparacion.to_dict(orient="records"),
    "mejor_modelo": MEJOR_NOMBRE, "mejor_balanceo": MEJOR_BALANCEO, "prueba": prueba, "auc_prueba": auc_prueba,
    "importancia": dict(zip(tabla_importancia["variable"], tabla_importancia["media"].astype(float))),
    "variable_top": variable_top, "siluetas": siluetas, "k": K, "mejor_k": mejor_k,
    "grupos": {g: {"alumnos": int(r.alumnos), "pct_atraso": float(r.pct_atraso), "dias_promedio": float(r.dias_promedio)}
               for g, r in resumen_grupos.iterrows()},
    "conclusiones": conclusiones, "graficos": GRAFICOS,
}
(RESULTADOS / "metricas.json").write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")

# --- Dashboard HTML (una sola pagina, con las imagenes incluidas) -----------
def imagen_base64(archivo):
    return base64.b64encode((RESULTADOS / archivo).read_bytes()).decode()


def tarjetas(seccion, ancho_completo=()):
    piezas = []
    for g in GRAFICOS:
        if g["seccion"] != seccion:
            continue
        clase = "tarjeta ancha" if g["archivo"] in ancho_completo else "tarjeta"
        piezas.append(f'<figure class="{clase}"><img src="data:image/png;base64,{imagen_base64(g["archivo"])}" '
                      f'alt="{g["titulo"]}"><figcaption>{g["explicacion"]}</figcaption></figure>')
    return "\n".join(piezas)


filas_tabla = "\n".join(
    f"<tr{' class=destacada' if (r['modelo'] == MEJOR_NOMBRE and r['balanceo'] == MEJOR_BALANCEO) else ''}>"
    f"<td>{r['modelo']}</td><td>{'Sí' if r['balanceo'] else 'No'}</td>"
    + "".join(f"<td class=num>{r[m]:.2f} <span>±{r[m + '_desv']:.2f}</span></td>" for m in METRICAS) + "</tr>"
    for r in comparacion.to_dict(orient="records"))

dashboard = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data Mining - Pagos atrasados</title>
<style>
:root {{ color-scheme: light; --fondo:#f9f9f7; --tarjeta:#fcfcfb; --tinta:#0b0b0b; --tinta2:#52514e; --tenue:#898781; --linea:#e1e0d9; --azul:#2a78d6; --naranja:#eb6834; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--fondo); color:var(--tinta); font-family:system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.5; }}
main {{ max-width:1180px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ font-size:30px; margin:0 0 6px; }} h2 {{ font-size:21px; margin:36px 0 4px; }}
.sub {{ color:var(--tinta2); margin:0 0 14px; }}
.aviso {{ border-left:4px solid var(--naranja); background:#fdf0ea; padding:10px 14px; border-radius:0 8px 8px 0; margin:14px 0; font-size:14px; }}
.fichas {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin:18px 0 4px; }}
.ficha {{ background:var(--tarjeta); border:1px solid var(--linea); border-radius:12px; padding:14px 16px; }}
.ficha b {{ display:block; font-size:30px; line-height:1.1; }} .ficha span {{ font-size:13px; color:var(--tinta2); }}
.fase {{ display:inline-block; font-size:12px; font-weight:700; letter-spacing:.06em; color:var(--tinta2); margin-top:36px; }}
.fase + h2 {{ margin-top:2px; }}
.grilla {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr)); gap:16px; margin-top:12px; }}
.tarjeta {{ margin:0; background:var(--tarjeta); border:1px solid var(--linea); border-radius:14px; padding:14px; }}
.tarjeta.ancha {{ grid-column:1 / -1; }}
.tarjeta img {{ width:100%; height:auto; display:block; }}
figcaption {{ font-size:14px; color:var(--tinta2); margin-top:8px; }}
.tabla-caja {{ overflow-x:auto; background:var(--tarjeta); border:1px solid var(--linea); border-radius:14px; padding:8px 14px; margin-top:12px; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th {{ text-align:left; color:var(--tinta2); font-weight:600; padding:8px 10px; border-bottom:1px solid var(--linea); white-space:nowrap; }}
td {{ padding:8px 10px; border-bottom:1px solid var(--linea); white-space:nowrap; }}
td.num {{ font-variant-numeric:tabular-nums; }} td span {{ color:var(--tenue); font-size:12px; }}
tr.destacada td {{ background:#e6f0fc; font-weight:600; }}
ol {{ background:var(--tarjeta); border:1px solid var(--linea); border-radius:14px; padding:16px 16px 16px 40px; margin-top:12px; }}
li {{ margin:6px 0; }}
footer {{ margin-top:32px; font-size:13px; color:var(--tenue); }}
</style></head><body><main>
<h1>Data Mining: ¿qué pagos llegarán atrasados?</h1>
<p class="sub">Escuela de fútbol · Data Warehouse {DATA_WAREHOUSE} · Metodología CRISP-DM · Python (pandas, matplotlib, seaborn, scikit-learn)</p>
<div class="aviso"><b>Datos de ejemplo y simulados.</b> {pagos_entregados} pagos son los datos de ejemplo de la base entregada con el práctico
(recibos REC-){f', <b>{pagos_simulados} son pagos SIMULADOS</b> (recibos SIM- y PRB-), generados con generar_pagos_prueba.py y pagos_prueba_60.sql para probar el modelo' if pagos_simulados else ''}{f' y {pagos_app} se registraron en la app web (recibos PAG-)' if pagos_app else ''}.
Ninguno proviene de una escuela real: los resultados muestran cómo funciona la técnica, no el comportamiento real de los tutores.
Fuente leída: {FUENTE}.</div>
<div class="fichas">
  <div class="ficha"><b>{len(pagos)}</b><span>pagos de {pagos['id_alumno'].nunique()} alumnos</span></div>
  <div class="ficha"><b>{pct(tasa_general)}</b><span>de pagos atrasados</span></div>
  <div class="ficha"><b>{pct(mejor['sensibilidad'])}</b><span>de atrasos detectados ({MEJOR_NOMBRE})</span></div>
  <div class="ficha"><b>{mejor['auc']:.2f}</b><span>AUC (0.5 = azar, 1 = perfecto)</span></div>
  <div class="ficha"><b>{int(resumen_grupos.loc['Morosos', 'alumnos'])}</b><span>alumnos en el grupo "Morosos"</span></div>
</div>

<span class="fase">FASE 2 · COMPRENSIÓN DE LOS DATOS</span>
<h2>Exploración</h2>
<p class="sub">Antes de modelar, se mira qué relación tienen el método de pago, la categoría y el monto con el atraso.</p>
<div class="grilla">{tarjetas("exploracion")}</div>

<span class="fase">FASES 3 Y 4 · PREPARACIÓN Y MODELADO</span>
<h2>Modelos de clasificación</h2>
<p class="sub">Variables usadas: categoría, método de pago, monto y % de atrasos previos del alumno. Validación cruzada de 5 partes,
separando por alumno ({len(modelado)} pagos; se excluye el primer pago de cada alumno porque aún no tiene historial).</p>
<div class="tabla-caja"><table>
<tr><th>Modelo</th><th>Balanceo</th><th>Exactitud</th><th>Precisión</th><th>Sensibilidad</th><th>F1</th><th>AUC</th></tr>
{filas_tabla}
</table></div>
<div class="grilla">{tarjetas("modelo")}</div>

<span class="fase">FASE 5 · EVALUACIÓN</span>
<h2>¿Qué tan bien predice y por qué?</h2>
<div class="grilla">{tarjetas("evaluacion", ancho_completo=("12_arbol_decision.png",))}</div>

<span class="fase">EXTRA · APRENDIZAJE NO SUPERVISADO</span>
<h2>Grupos de alumnos</h2>
<div class="grilla">{tarjetas("clustering", ancho_completo=("13_clustering_kmeans.png",))}</div>

<span class="fase">FASE 6 · DESPLIEGUE</span>
<h2>Conclusiones</h2>
<ol>{"".join(f"<li>{c}</li>" for c in conclusiones)}</ol>
<footer>Generado por mineria_pagos.py el {metricas['generado']}.</footer>
</main></body></html>"""
(RESULTADOS / "dashboard.html").write_text(dashboard, encoding="utf-8")
print(f"   dashboard: {RESULTADOS / 'dashboard.html'}")

# --- Documento Word ---------------------------------------------------------
try:
    from documento_word import generar_documento
    ruta_word = generar_documento(metricas, RESULTADOS)
    print(f"   documento: {ruta_word}")
except ImportError:
    print("   (documento_word.py no encontrado: se omite el Word)")
except PermissionError:
    # Pasa si el .docx esta abierto en Word: el dashboard ya se actualizo igual.
    print("   AVISO: no se pudo actualizar el Word porque esta abierto. Cierralo y vuelve a ejecutar.")


# --- Riesgo por alumno (lo usa la pantalla "Alertas de atraso" de app_escuela) ---
# Estima el PROXIMO pago de cada alumno con el mejor modelo, entrenado ahora con
# todas las filas. Solo AGREGA resultados/riesgo_alumnos.json: no cambia nada de lo anterior.
UMBRAL_ALTO = 0.60           # probabilidad de atraso >= 0.60 -> riesgo Alto
UMBRAL_MEDIO = 0.40          # entre 0.40 y 0.60 -> Medio (zona dudosa alrededor del corte 0.5); menos -> Bajo
MIN_PAGOS_HISTORIAL = 3      # con menos pagos no se estima: "Sin historial suficiente"
ULTIMOS_N = 4                # pagos recientes que se cuentan para el motivo

modelo_riesgo = crear_modelos(MEJOR_BALANCEO)[MEJOR_NOMBRE].fit(X, y)
historial = pagos.groupby("id_alumno")
proximo = pd.DataFrame({
    "categoria": historial["categoria"].last(),
    "metodo_pago": historial["metodo_pago"].agg(lambda s: s.mode().iloc[0]),   # su metodo habitual
    "monto_mensualidad": historial["monto_mensualidad"].last(),
    "pct_atrasos_previos": historial["atrasado"].mean(),                       # todo su historial
    "pagos": historial.size(),
    "atrasos": historial["atrasado"].sum(),
    "ultimos": historial["atrasado"].agg(lambda s: len(s.tail(ULTIMOS_N))),
    "atrasos_ultimos": historial["atrasado"].agg(lambda s: int(s.tail(ULTIMOS_N).sum())),
})
proximo["probabilidad"] = modelo_riesgo.predict_proba(proximo[CATEGORICAS + NUMERICAS])[:, 1]


def nivel_riesgo(fila):
    if fila.pagos < MIN_PAGOS_HISTORIAL:
        return "Sin historial suficiente"
    if fila.probabilidad >= UMBRAL_ALTO:
        return "Alto"
    return "Medio" if fila.probabilidad >= UMBRAL_MEDIO else "Bajo"


riesgo = {
    "generado": metricas["generado"], "fuente": FUENTE,
    "modelo": MEJOR_NOMBRE, "balanceo": MEJOR_BALANCEO, "auc": float(mejor["auc"]),
    "umbrales": {"alto": UMBRAL_ALTO, "medio": UMBRAL_MEDIO,
                 "min_pagos_historial": MIN_PAGOS_HISTORIAL, "ultimos_n": ULTIMOS_N},
    "tasa_por_metodo": metricas["tasa_por_metodo"],
    "alumnos": [
        {"id_alumno": int(id_alumno), "nivel": nivel_riesgo(f),
         "probabilidad": round(float(f.probabilidad), 3) if f.pagos >= MIN_PAGOS_HISTORIAL else None,
         "categoria": f.categoria, "metodo_habitual": f.metodo_pago,
         "pagos": int(f.pagos), "atrasos": int(f.atrasos),
         "ultimos": int(f.ultimos), "atrasos_ultimos": int(f.atrasos_ultimos)}
        for id_alumno, f in proximo.iterrows()
    ],
}
# Se escribe en un archivo temporal y luego se reemplaza: la app nunca lee un archivo a medias.
temporal = RESULTADOS / "riesgo_alumnos.json.tmp"
temporal.write_text(json.dumps(riesgo, ensure_ascii=False, indent=2), encoding="utf-8")
temporal.replace(RESULTADOS / "riesgo_alumnos.json")
print(f"   riesgo por alumno: {RESULTADOS / 'riesgo_alumnos.json'}")


# --- Datos de los graficos (los usa la pantalla "Analisis" de app_escuela) -------
# La app dibuja los graficos en el navegador con estos numeros. Solo AGREGA
# resultados/datos_graficos.json: no cambia metricas.json, el dashboard ni el Word.
from sklearn.tree import export_text

dias_por_categoria = {}
for categoria in categorias:
    dias = pagos.loc[pagos["categoria"] == categoria, "dias_atraso"]
    dias_por_categoria[categoria] = {
        "n": int(len(dias)), "minimo": float(dias.min()), "q1": float(dias.quantile(0.25)),
        "mediana": float(dias.median()), "q3": float(dias.quantile(0.75)), "maximo": float(dias.max()),
        "promedio": float(dias.mean())}
curvas_roc = {}
for nombre, modelo in modelos_finales.items():   # mismos modelos ya entrenados: misma curva del grafico 10
    fpr, tpr, _ = roc_curve(y_pru, modelo.predict_proba(X_pru)[:, 1])
    curvas_roc[nombre] = {"fpr": [round(float(v), 4) for v in fpr], "tpr": [round(float(v), 4) for v in tpr]}

datos_graficos = {
    "generado": metricas["generado"],             # el mismo de metricas.json: asi la app sabe que van juntos
    "pagos_por_prefijo": {k: int(v) for k, v in recibos_pago.str.extract(r"^([A-Za-z]+)-", expand=False)
                          .fillna("OTRO").str.upper().value_counts().items()},
    "pagos_por_estado": {k: int(v) for k, v in pagos["estado_pago"].value_counts().items()},
    "conteo_por_metodo": {m: {"a_tiempo": int(conteo.loc[m].get(0, 0)), "atrasado": int(conteo.loc[m].get(1, 0))}
                          for m in metodos},
    "dias_por_categoria": dias_por_categoria,
    "calor_categoria_metodo": {
        c: {m: None if pd.isna(tabla_n.loc[c, m]) else
            {"tasa": float(tabla_calor.loc[c, m]), "n": int(tabla_n.loc[c, m])} for m in metodos}
        for c in categorias},
    "curvas_roc": curvas_roc,
    "kmeans_alumnos": [{"pct_atraso": round(float(a.pct_atraso), 4), "dias_promedio": round(float(a.dias_promedio), 3),
                        "grupo": a.grupo} for a in alumnos.itertuples()],
    "reglas_arbol": export_text(arbol.named_steps["modelo"], feature_names=nombres_columnas, decimals=2),
}
temporal = RESULTADOS / "datos_graficos.json.tmp"
temporal.write_text(json.dumps(datos_graficos, ensure_ascii=False, indent=2), encoding="utf-8")
temporal.replace(RESULTADOS / "datos_graficos.json")
print(f"   datos de graficos: {RESULTADOS / 'datos_graficos.json'}")


# --- Patrones para la pantalla "Analisis" de app_escuela --------------------------
# Solo AGREGA resultados/patrones.json: no cambia metricas.json, los graficos, el
# dashboard ni el Word. Contiene:
#   1. Segmentacion con PCA: resume el perfil de cada alumno (varias variables) en 2 ejes.
#   2. Silueta de cada grupo de K-Means: que tan bien separado esta cada grupo.
#   3. Similitud del coseno entre categorias: que categorias pagan de forma parecida.
#   4. Muestra de la matriz preparada (fase 3): asi entran los datos al modelo.
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_samples
from sklearn.metrics.pairwise import cosine_similarity

# 1. PCA del perfil de cada alumno (los colores son los mismos grupos de K-Means de la fase 6)
perfil = pd.DataFrame({
    "pct_atraso": alumnos["pct_atraso"],
    "dias_promedio": alumnos["dias_promedio"],
    "dias_maximo": historial["dias_positivos"].max(),
    "pagos": alumnos["pagos"],
    "monto_mensualidad": historial["monto_mensualidad"].mean(),
}).reindex(alumnos.index)
NOMBRES_PERFIL = {"pct_atraso": "% de pagos atrasados", "dias_promedio": "Días de atraso promedio",
                  "dias_maximo": "Mayor atraso (días)", "pagos": "Cantidad de pagos",
                  "monto_mensualidad": "Monto de la mensualidad"}
for metodo in metodos:                      # que tanto usa cada metodo de pago
    perfil[f"pct_{metodo}"] = historial["metodo_pago"].agg(lambda s, m=metodo: float((s == m).mean())).reindex(alumnos.index)
    NOMBRES_PERFIL[f"pct_{metodo}"] = f"% de pagos con {metodo}"
perfil = perfil.fillna(0)
pca = PCA(n_components=2, random_state=SEMILLA)
coordenadas = pca.fit_transform(StandardScaler().fit_transform(perfil))


def variables_del_eje(i, cantidad=3):
    """Las variables que mas pesan en el eje i (para explicar que significa el eje)."""
    cargas = pd.Series(pca.components_[i], index=perfil.columns)
    principales = cargas.abs().sort_values(ascending=False).index[:cantidad]
    return [{"variable": NOMBRES_PERFIL[v], "carga": round(float(cargas[v]), 3)} for v in principales]


# 2. Silueta de cada alumno con los mismos rasgos y grupos de K-Means; se promedia por grupo
silueta_alumno = silhouette_samples(rasgos, kmeans.labels_)
silueta_grupos = {g: round(float(silueta_alumno[(alumnos["grupo"] == g).to_numpy()].mean()), 3)
                  for g in ["Puntuales", "Ocasionales", "Morosos"] if (alumnos["grupo"] == g).any()}

# 3. Perfil de pago de cada categoria (todo entre 0 y 1, asi el coseno queda entre 0 y 1)
perfil_cat = pd.DataFrame(index=categorias)
perfil_cat["tasa_atraso"] = pagos.groupby("categoria")["atrasado"].mean()
dias_cat = pagos.groupby("categoria")["dias_positivos"].mean()
perfil_cat["dias_promedio"] = (dias_cat - dias_cat.min()) / (dias_cat.max() - dias_cat.min() or 1)
for metodo in metodos:
    perfil_cat[f"pct_{metodo}"] = pagos.assign(es=pagos["metodo_pago"] == metodo).groupby("categoria")["es"].mean()
perfil_cat = perfil_cat.fillna(0)
similitud = cosine_similarity(perfil_cat.to_numpy())
pares = [(categorias[i], categorias[j], float(similitud[i, j]))
         for i in range(len(categorias)) for j in range(i + 1, len(categorias))]
mas_parecidas = max(pares, key=lambda p: p[2]) if pares else None
menos_parecidas = min(pares, key=lambda p: p[2]) if pares else None

# 4. Muestra de la matriz preparada: texto convertido en columnas 0/1 (one-hot) + numeros
matriz = pd.get_dummies(modelado[CATEGORICAS], prefix=["Cat", "Método"], prefix_sep=": ", dtype=int)
matriz = matriz[[f"Cat: {c}" for c in categorias if f"Cat: {c}" in matriz] + [f"Método: {m}" for m in metodos if f"Método: {m}" in matriz]]
matriz["Monto mensualidad"] = modelado["monto_mensualidad"].round(2)
matriz["% atrasos previos"] = modelado["pct_atrasos_previos"].round(3)
matriz["Atrasado (lo que se predice)"] = modelado["atrasado"].astype(int)
muestra = matriz.head(8)

patrones = {
    "generado": metricas["generado"], "fuente": FUENTE,
    "pca": {
        "variables": [NOMBRES_PERFIL[c] for c in perfil.columns],
        "varianza": [round(float(v), 4) for v in pca.explained_variance_ratio_],
        "ejes": [variables_del_eje(0), variables_del_eje(1)],
        "alumnos": [{"id_alumno": int(id_alumno), "grupo": alumnos.loc[id_alumno, "grupo"],
                     "x": round(float(coordenadas[i, 0]), 3), "y": round(float(coordenadas[i, 1]), 3),
                     "pct_atraso": round(float(alumnos.loc[id_alumno, "pct_atraso"]), 4),
                     "dias_promedio": round(float(alumnos.loc[id_alumno, "dias_promedio"]), 2),
                     "pagos": int(alumnos.loc[id_alumno, "pagos"])}
                    for i, id_alumno in enumerate(alumnos.index)],
    },
    "silueta": {"global": round(float(siluetas[K]), 3), "umbral": 0.25, "por_grupo": silueta_grupos},
    "similitud_categorias": {
        "categorias": categorias,
        "matriz": [[round(float(v), 3) for v in fila] for fila in similitud],
        "variables": ["% de atraso", "Días de atraso (escalado 0-1)"] + [f"% pagos con {m}" for m in metodos],
        "mas_parecidas": None if not mas_parecidas else {"a": mas_parecidas[0], "b": mas_parecidas[1], "valor": round(mas_parecidas[2], 3)},
        "menos_parecidas": None if not menos_parecidas else {"a": menos_parecidas[0], "b": menos_parecidas[1], "valor": round(menos_parecidas[2], 3)},
    },
    "matriz_preparada": {
        "filas": int(len(matriz)), "columnas": list(matriz.columns),
        "muestra": [[(v.item() if hasattr(v, "item") else v) for v in fila] for fila in muestra.itertuples(index=False)],
    },
}
temporal = RESULTADOS / "patrones.json.tmp"
temporal.write_text(json.dumps(patrones, ensure_ascii=False, indent=2), encoding="utf-8")
temporal.replace(RESULTADOS / "patrones.json")
print(f"   patrones (PCA, silueta, similitud, matriz): {RESULTADOS / 'patrones.json'} | PCA explica el "
      f"{sum(pca.explained_variance_ratio_) * 100:.0f} %")

print("\nListo. Abre resultados/dashboard.html para ver todo.")
if "--no-abrir" not in sys.argv:
    import webbrowser
    webbrowser.open((RESULTADOS / "dashboard.html").as_uri())
