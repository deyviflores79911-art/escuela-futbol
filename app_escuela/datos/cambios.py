"""
"Huella" de los datos para que las pantallas se actualicen solas (tiempo real).
Es una consulta muy liviana: si cualquier fila de estas tablas se agrega, cambia o se anula,
la huella cambia y la pantalla abierta se vuelve a dibujar.
"""
import hashlib

import config
from datos.bd import consultar_uno

# Tablas que se ven en pantalla. CHECKSUM_AGG(BINARY_CHECKSUM(*)) cambia si cambia cualquier columna de cualquier fila.
TABLAS = ["PAGO", "MENSUALIDAD", "INSCRIPCION", "ALUMNO", "TUTOR", "GRUPO", "CATEGORIA", "HORARIO", "USUARIO", "ENTRENADOR"]
if config.EN_LA_NUBE:
    TABLAS.append("LUGAR")   # en la nube los lugares están en la base, no en lugares.json
_SQL = "SELECT " + ", ".join(
    f"(SELECT CAST(COUNT(*) AS varchar(12)) + ':' + ISNULL(CAST(CHECKSUM_AGG(BINARY_CHECKSUM(*)) AS varchar(12)), '') FROM {t}) AS {t}"
    for t in TABLAS)


def huella():
    """Texto corto que cambia cuando cambia algo que muestra la app."""
    fila = consultar_uno(_SQL)
    partes = [f"{t}={fila[t]}" for t in TABLAS]
    if not config.EN_LA_NUBE:
        try:
            partes.append(f"lugares={int(config.ARCHIVO_LUGARES.stat().st_mtime)}")
        except OSError:
            partes.append("lugares=")
    return hashlib.sha1("|".join(partes).encode()).hexdigest()[:16]
