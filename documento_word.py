"""
DOCUMENTO WORD DE LA PRESENTACION
Lo llama mineria_pagos.py al final. Usa los numeros reales de esa
ejecucion (metricas.json) y algunos graficos, asi el documento siempre
coincide con los resultados.
"""

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

AZUL = RGBColor(0x1C, 0x5C, 0xAB)
TINTA_2 = RGBColor(0x52, 0x51, 0x4E)

HERRAMIENTAS = [
    ("Python\n(pandas, scikit-learn, matplotlib, seaborn)", "Código, gratis",
     "Se conecta directo a SQL Server; cientos de algoritmos; gráficos a medida; es el estándar en la industria.",
     "Hay que programar."),
    ("Orange", "Visual (bloques), gratis",
     "Ideal para aprender: se arma el análisis arrastrando bloques, sin programar.",
     "Poco flexible para automatizar o personalizar; limitado con datos grandes."),
    ("R", "Código, gratis",
     "Muy fuerte en estadística y gráficos académicos.",
     "Menos usado en empresas para poner modelos en producción."),
    ("Weka", "Visual, gratis",
     "Clásico en universidades; muchos algoritmos listos.",
     "Interfaz antigua; difícil de integrar con otros sistemas."),
    ("Power BI", "Reportes, de pago",
     "Excelente para dashboards y se integra con SQL Server.",
     "Pocos algoritmos de Data Mining; no está hecho para entrenar modelos."),
]

FASES = [
    ("1. Comprensión del negocio", "Se definió el objetivo: predecir qué pagos llegarán atrasados para recordar a tiempo."),
    ("2. Comprensión de los datos", "Se leyó H_PAGOS del Data Warehouse y se hicieron 5 gráficos de exploración."),
    ("3. Preparación de los datos", "Se eligieron variables que se conocen antes del vencimiento y se calculó el historial de cada alumno."),
    ("4. Modelado", "Se entrenaron 3 modelos (árbol de decisión, Random Forest y regresión logística), con y sin balanceo de clases."),
    ("5. Evaluación", "Validación cruzada de 5 partes separando por alumno, matriz de confusión, curva ROC e importancia de variables."),
    ("6. Despliegue", "Agrupación de alumnos con K-Means, dashboard HTML con todos los resultados y este documento."),
]

GLOSARIO = [
    ("Exactitud", "De todos los pagos, qué porcentaje predijo bien."),
    ("Sensibilidad", "De los pagos que sí se atrasaron, qué porcentaje detectó. Es la métrica más importante para la escuela."),
    ("Precisión", "De los pagos que el modelo marcó como atrasados, qué porcentaje realmente se atrasó."),
    ("F1", "Un solo número que equilibra sensibilidad y precisión."),
    ("AUC", "Qué tan bien ordena a los alumnos de más a menos riesgo: 0.5 es adivinar al azar y 1 es perfecto."),
    ("Validación cruzada", "Dividir los datos en 5 partes y evaluar 5 veces, cada vez con una parte distinta, para que el resultado no dependa de la suerte."),
]

GRAFICOS_CON_IMAGEN = ["05_heatmap_categoria_metodo.png", "09_matriz_confusion.png",
                       "11_importancia_variables.png", "13_clustering_kmeans.png"]


def sombrear(celda, color):
    propiedades = celda._tc.get_or_add_tcPr()
    sombra = OxmlElement("w:shd")
    sombra.set(qn("w:val"), "clear")
    sombra.set(qn("w:color"), "auto")
    sombra.set(qn("w:fill"), color)
    propiedades.append(sombra)


def tabla(doc, encabezados, filas, anchos_cm):
    t = doc.add_table(rows=1, cols=len(encabezados))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for celda, texto in zip(t.rows[0].cells, encabezados):
        celda.text = ""
        corrida = celda.paragraphs[0].add_run(texto)
        corrida.bold = True
        sombrear(celda, "E6F0FC")
    for fila in filas:
        celdas = t.add_row().cells
        for celda, texto in zip(celdas, fila):
            celda.text = ""
            for i, linea in enumerate(str(texto).split("\n")):
                parrafo = celda.paragraphs[0] if i == 0 else celda.add_paragraph()
                parrafo.add_run(linea).bold = (i == 0 and celda is celdas[0])
    for fila in t.rows:
        for celda, ancho in zip(fila.cells, anchos_cm):
            celda.width = Cm(ancho)
            for parrafo in celda.paragraphs:
                parrafo.paragraph_format.space_after = Pt(2)
                for corrida in parrafo.runs:
                    corrida.font.size = Pt(9.5)
    doc.add_paragraph()
    return t


def recuadro(doc, titulo, texto, color="FDF0EA"):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    celda = t.rows[0].cells[0]
    celda.width = Cm(16)
    sombrear(celda, color)
    parrafo = celda.paragraphs[0]
    parrafo.add_run(titulo + " ").bold = True
    parrafo.add_run(texto)
    for corrida in parrafo.runs:
        corrida.font.size = Pt(10)
    doc.add_paragraph()


def pct(x):
    return f"{x * 100:.0f}%"


def generar_documento(m, carpeta):
    carpeta = Path(carpeta)
    doc = Document()
    seccion = doc.sections[0]
    seccion.page_width, seccion.page_height = Cm(21), Cm(29.7)
    seccion.left_margin = seccion.right_margin = Cm(2.5)
    seccion.top_margin = seccion.bottom_margin = Cm(2.2)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    for nivel, tam in [(1, 15), (2, 12.5)]:
        estilo = doc.styles[f"Heading {nivel}"]
        estilo.font.name = "Calibri"
        estilo.font.size = Pt(tam)
        estilo.font.color.rgb = AZUL
        estilo.font.bold = True

    # --- Portada breve ---------------------------------------------------------
    titulo = doc.add_paragraph()
    corrida = titulo.add_run("Herramientas para implementar Data Mining")
    corrida.bold, corrida.font.size, corrida.font.color.rgb = True, Pt(22), AZUL
    sub = doc.add_paragraph()
    corrida = sub.add_run("Ejemplo preliminar: predicción de pagos atrasados en una escuela de fútbol")
    corrida.font.size, corrida.font.color.rgb = Pt(13), TINTA_2
    datos = doc.add_paragraph()
    datos.add_run("Materia: ").bold = True
    datos.add_run("Business Intelligence & Big Data\n")
    datos.add_run("Estudiante: ").bold = True
    datos.add_run("______________________\n")
    datos.add_run("Fecha: ").bold = True
    datos.add_run(m["generado"].split(" ")[0])

    pagos_app = m["pagos"] - m.get("pagos_entregados", m["pagos"]) - m.get("pagos_simulados", 0)  # PAG-
    recuadro(doc, "Aviso sobre los datos:",
             f"de los {m['pagos']} pagos de {m['alumnos']} alumnos, {m.get('pagos_entregados', m['pagos'])} son los datos "
             "de ejemplo de la base entregada con el práctico (recibos REC-)"
             + (f", {m['pagos_simulados']} son pagos SIMULADOS (recibos SIM- y PRB-), generados con "
                "generar_pagos_prueba.py y pagos_prueba_60.sql para probar el modelo" if m.get("pagos_simulados") else "")
             + (f" y {pagos_app} se registraron en la app web (recibos PAG-)" if pagos_app else "")
             + ". Ninguno proviene de una escuela real: los resultados muestran cómo funciona la técnica, "
             "pero no el comportamiento real de los tutores.")

    # --- 1. Objetivo ---------------------------------------------------------------
    doc.add_heading("1. Objetivo", level=1)
    doc.add_paragraph(
        "La escuela necesita saber qué pagos de mensualidad tienen riesgo de llegar tarde, para recordarles a los "
        "tutores antes del vencimiento. Además, quiere entender qué factores influyen en el atraso: la categoría del "
        "alumno, el método de pago y el monto de la mensualidad. Los datos salen de la tabla de hechos H_PAGOS del "
        "Data Warehouse DW_EscuelasDeportivas, cargado con un paquete SSIS.")

    # --- 2. Herramientas -----------------------------------------------------------
    doc.add_heading("2. Herramientas de Data Mining", level=1)
    tabla(doc, ["Herramienta", "Tipo", "Fortalezas", "Limitaciones"], HERRAMIENTAS, [3.6, 2.4, 5.4, 4.6])
    doc.add_heading("¿Por qué elegí Python?", level=2)
    for texto in [
        "Se conecta directamente al Data Warehouse en SQL Server (con pyodbc), sin exportar archivos a mano.",
        "Todo el análisis queda escrito en un script: se puede repetir con datos nuevos en segundos y cualquiera puede revisar cada paso.",
        "Tiene los algoritmos que necesitaba (árbol de decisión, Random Forest, regresión logística, K-Means) y la validación cruzada en una sola librería: scikit-learn.",
        "Con matplotlib y seaborn los gráficos se controlan al detalle: colores consistentes, títulos que explican el hallazgo y etiquetas legibles.",
        "Frente a Orange, que es excelente para aprender, Python permite automatizar el proceso completo y es lo que se usa en la industria.",
    ]:
        doc.add_paragraph(texto, style="List Bullet")

    # --- 3. Metodologia -----------------------------------------------------------------
    doc.add_heading("3. Metodología: CRISP-DM", level=1)
    doc.add_paragraph("CRISP-DM es la metodología más usada para proyectos de Data Mining. Tiene seis fases:")
    tabla(doc, ["Fase", "Qué hice"], FASES, [4.6, 11.4])
    doc.add_paragraph(
        "Variables usadas para predecir: categoría, método de pago, monto de la mensualidad y el porcentaje de pagos "
        "anteriores del alumno que llegaron tarde (su historial). No se usaron el monto pagado, el saldo ni los días "
        "de atraso, porque se conocen recién después de pagar y el modelo estaría viendo la respuesta.")

    # --- 4. Graficos -------------------------------------------------------------------
    doc.add_heading("4. Qué muestra cada gráfico", level=1)
    doc.add_paragraph("Todos los gráficos están en el dashboard (resultados/dashboard.html). Aquí se explica cada uno:")
    for numero, g in enumerate(m["graficos"], start=1):
        parrafo = doc.add_paragraph()
        parrafo.add_run(f"{numero}. {g['titulo']}. ").bold = True
        parrafo.add_run(g["explicacion"])
        if g["archivo"] in GRAFICOS_CON_IMAGEN:
            ancho = Cm(16) if g["archivo"].startswith("13") else Cm(12)
            doc.add_picture(str(carpeta / g["archivo"]), width=ancho)
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # --- 5. Resultados -----------------------------------------------------------------
    doc.add_heading("5. Resultados de los modelos", level=1)
    doc.add_paragraph(
        f"Promedio de la validación cruzada de 5 partes ({m['filas_modelo']} pagos). Adivinar siempre "
        f"\"a tiempo\" daría una exactitud de {pct(m['exactitud_base'])}; un modelo útil tiene que superarla.")
    filas = [(r["modelo"], "Sí" if r["balanceo"] else "No", f"{r['exactitud']:.2f}", f"{r['sensibilidad']:.2f}",
              f"{r['precision']:.2f}", f"{r['f1']:.2f}", f"{r['auc']:.2f}") for r in m["comparacion"]]
    tabla(doc, ["Modelo", "Balanceo", "Exactitud", "Sensibilidad", "Precisión", "F1", "AUC"], filas,
          [3.8, 1.9, 2.0, 2.3, 2.1, 1.8, 2.1])
    p = m["prueba"]
    (vn, fp), (fn, vp) = p["matriz"]
    doc.add_paragraph(
        f"Modelo elegido: {m['mejor_modelo']} {'con' if m['mejor_balanceo'] else 'sin'} balanceo (el de mayor F1). "
        f"Probado con {p['alumnos']} alumnos que no vio al aprender ({p['filas']} pagos), acertó {vn + vp} de "
        f"{p['filas']} ({pct(p['exactitud'])}), detectó {vp} de {vp + fn} atrasos y dio {fp} falsas alarmas.")
    doc.add_heading("Glosario de métricas", level=2)
    tabla(doc, ["Métrica", "Qué significa"], GLOSARIO, [3.4, 12.6])

    # --- 6. Conclusiones ---------------------------------------------------------------
    doc.add_heading("6. Conclusiones", level=1)
    for texto in m["conclusiones"]:
        doc.add_paragraph(texto, style="List Bullet")
    doc.add_heading("Limitaciones y próximos pasos", level=2)
    limitaciones = [
        "Son datos de ejemplo y simulados: con datos reales de la escuela los porcentajes cambiarán.",
        f"La muestra es pequeña ({m['pagos']} pagos de {m['alumnos']} alumnos en 6 meses). Con más meses el modelo será más estable.",
    ]
    if m["monto_igual_categoria"]:
        limitaciones.append("Cada categoría tiene un único monto, así que no se puede separar el efecto del monto del de la categoría.")
    limitaciones.append("Siguiente paso: ejecutar el modelo cada mes, antes del vencimiento, y enviar el recordatorio a los alumnos con mayor riesgo.")
    for texto in limitaciones:
        doc.add_paragraph(texto, style="List Bullet")

    ruta = carpeta / "Presentacion_Data_Mining.docx"
    doc.save(ruta)
    return ruta
