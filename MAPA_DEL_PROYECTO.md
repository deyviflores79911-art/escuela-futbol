# Mapa del proyecto: Escuela de Fútbol

Dónde está cada cosa, cómo viaja la información y qué se actualiza cuándo.
Todo corre en el servidor SQL Server `localhost\MSSQLSERVER01`.

## 1. Cómo funciona todo (flujo en un solo sentido)

```
 Personas (dueño, entrenadores)
        │  usan
        ▼
 APP WEB  app_escuela\ (Flask)  ◄──── EN VIVO ────►  BASE TRANSACCIONAL  Sistema_EscuelasDeportivas
                                                            │   (fuente de verdad)
                                                            │
                                                            ▼   SSIS (Package.dtsx), POR LOTES:
 resultados\  ◄── mineria_pagos.py ◄── DATA WAREHOUSE  DW_EscuelasDeportivas
 (metricas.json,     (última tarea del SSIS:     (copia derivada; el SSIS la rehace en cada carga)
  riesgo_alumnos.json, ACTUALIZAR_DASHBOARD)
  datos_graficos.json,
  dashboard.html, Word)
```

| Parte | Qué hace | Cuándo se actualiza |
|---|---|---|
| **App web** (pensada para el **celular**) | Usuarios, grupos, categorías, horarios y lugares, tutores, alumnos, inscripciones, mensualidades, cobros, recibos, anulaciones, deudores, resumen de caja y "Mi grupo". Lee y escribe la base transaccional. | **En vivo**, en cada pantalla. |
| **SSIS** (`Package.dtsx`) | Copia la base transaccional al Data Warehouse. | **Solo cuando el dueño lo ejecuta** desde Visual Studio. No corre solo. |
| **`mineria_pagos.py`** | Lee el DW, entrena los modelos (unos 20 s) y escribe `resultados\`. | Al final de cada ejecución del SSIS (tarea ACTUALIZAR_DASHBOARD). |

**Reglas:**
- La app es **solo operativa**: no muestra el análisis, no lee `resultados\`, no escribe en el DW y no lanza el SSIS.
- El análisis se ve en `resultados\dashboard.html` y en el Word, fuera de la app.

## 2. Carpetas y archivos

```
deportivva\
├─ MAPA_DEL_PROYECTO.md      Este archivo
├─ mineria_pagos.py          Minería de datos: lee H_PAGOS del DW, entrena y genera resultados\
├─ documento_word.py         Arma el Word con los números reales (lo usa mineria_pagos.py)
├─ datos\
│   └─ h_pagos_ejemplo.csv   Copia de H_PAGOS del 05/10 (802 pagos): mineria_pagos.py la usa si no hay conexión (o con --csv)
├─ resultados\               Salida del análisis (la escribe mineria_pagos.py):
│   ├─ metricas.json            números del análisis (los usa el Word)
│   ├─ riesgo_alumnos.json      riesgo de atraso por alumno
│   ├─ datos_graficos.json      datos de los gráficos
│   ├─ patrones.json            PCA, silueta por grupo, similitud entre categorías y matriz preparada
│   ├─ dashboard.html           dashboard con imágenes (para abrir sin la app)
│   ├─ Presentacion_Data_Mining.docx
│   └─ 01_…png a 13_…png        gráficos del dashboard y del Word
├─ sql_originales\           Scripts originales de las dos bases (no se modifican)
├─ datos_prueba\             Poner o quitar los pagos de prueba (SIM- y PRB-)
│   ├─ generar_pagos_prueba.py   502 pagos SIM- (--insertar / --quitar)
│   ├─ quitar_pagos_prueba.sql   quita los SIM- desde SSMS (F5)
│   └─ pagos_prueba_60.sql       60 pagos PRB- (@ACCION = VER / INSERTAR / BORRAR)
├─ documentos\               Textos para la presentación (informe, pruebas, guía de la demostración y fases CRISP-DM)
└─ app_escuela\              App web (ver sección 3)

Fuera de esta carpeta:
C:\Users\msi\Desktop\prueba_dashboard\      Copia para la prueba "el dashboard reacciona" (Paso 7 de la guía)
C:\Users\msi\source\repos\ETL_EscuelasDeportivas\ETL_EscuelasDeportivas\
    Package.dtsx                            Paquete SSIS
    Package.dtsx.respaldo_20261004_235209   Respaldo: original, antes de los cambios
    Package.dtsx.respaldo_20261005_000349   Respaldo: con ACTUALIZAR_DASHBOARD y la fórmula anterior de DIAS_ATRASO
```

**No mover** `mineria_pagos.py`, `datos\` ni `resultados\`: el SSIS ejecuta
`C:\Users\msi\Desktop\deportivva\mineria_pagos.py` por su ruta completa.

## 3. La app web (`app_escuela\`)

```
app_escuela\
├─ app.py              Arranque, filtros de fecha y Bs, errores y registro de pantallas
├─ config.py           Conexión a la base, inactividad, datos de la escuela (recibo) y HOST (celular)
├─ lugares.json        Lugares de entrenamiento y su enlace de Google Maps (los maneja el dueño en Horarios)
├─ datos\              Acceso a datos (solo consultas con parámetros)
│   ├─ bd.py              conexión y transacciones con la base transaccional
│   ├─ usuarios.py        usuarios, roles y entrenadores
│   ├─ catalogos.py       categorías, grupos, horarios (también de varios grupos a la vez) y la regla de edad
│   ├─ lugares.py         lugares de entrenamiento y enlaces de Google Maps (lugares.json)
│   ├─ letras.py          montos en letras para el recibo ("Ciento veinte 50/100 Bolivianos")
│   ├─ alumnos.py         tutores, alumnos (código único, búsqueda) e inscripciones (cupo, edad, baja; alumno nuevo + grupo en un paso)
│   ├─ pagos.py           mensualidades, cobros (PAG-####), anulaciones y AUDITORIA_PAGO
│   ├─ reportes.py        deudores, resumen de caja y "Mi grupo" (Al día / Debe)
│   └─ cambios.py         "huella" de los datos para el tiempo real
├─ rutas\              Pantallas y permisos por rol (verificados en el servidor)
│   ├─ seguridad.py       sesión, inactividad, login_requerido / solo_dueno
│   ├─ acceso.py          login, logout, inicio, mi contraseña y /api/cambios (tiempo real)
│   ├─ usuarios.py        gestión de entrenadores (solo dueño)
│   ├─ catalogos.py       /grupos, /categorias, /horarios y /lugares (solo dueño)
│   ├─ alumnos.py         /inscribir, /alumnos, /tutores e inscripciones (solo dueño)
│   ├─ caja.py            /caja, /mensualidades, cobrar, recibo y anular (solo dueño)
│   ├─ reportes.py        /reportes/deudores, /reportes/caja (solo dueño) y /mi-grupo (cada uno el suyo)
│   └─ validar.py         validaciones de formularios en el servidor
├─ plantillas\         HTML (Jinja)
├─ estaticos\          css\estilos.css (colores en variables; bloque "Celular"), js\, fuentes\, js\vendor\chart.umd.min.js (gráfico del Resumen de caja),
│                      img\ (escudo e íconos de la app) y app.webmanifest (instalar en el celular)
└─ pruebas\            Pruebas automáticas contra la base real
```

### Pantallas de la app

| Pantalla | Quién la ve | De dónde salen los datos |
|---|---|---|
| Inicio | Dueño: botones grandes Cobrar, Inscribir, Deudores, Alumnos y "Cobrado hoy". Entrenador: qué entrena hoy, dónde y "Cómo llegar" | Base, en vivo |
| Inscribir (alumno nuevo + tutor + grupo en un paso, o buscar uno registrado) | Solo dueño | Base, en vivo. Solo deja elegir grupos de la edad del niño |
| Alumnos y Tutores | Solo dueño | Base, en vivo |
| Grupos, Categorías y Horarios (días, hora y lugar a varios grupos a la vez; lugares con "Cómo llegar") | Solo dueño | Base, en vivo; lugares en `lugares.json` |
| Usuarios (entrenadores) | Solo dueño | Base, en vivo |
| Cobrar (botón directo a la mensualidad más antigua), estado de cuenta, recibo (formato de factura, escudo, monto en letras; **recibo, no factura**: la escuela no tiene NIT), anular y Mensualidades | Solo dueño | Base, en vivo |
| Reportes: Deudores y Resumen de caja | Solo dueño | Base, en vivo; se actualizan solos cada 45 s |
| Mi grupo (horarios, cupo, Al día / Debe) | Entrenador y dueño (cada uno solo sus grupos, sin montos) | Base, en vivo; se actualiza sola cada 45 s |
| Mi contraseña | Dueño y entrenador | Base |

El único gráfico de la app (Resumen de caja) se dibuja en el navegador con Chart.js.

**En el celular:** barra fija abajo (dueño: Inicio · Cobrar · Inscribir · Alumnos · Más; entrenador: Inicio · Mi grupo ·
Más), menú "Más" por secciones (Dinero, Escuela, Mi cuenta), tablas convertidas en tarjetas,
todo lo que se toca mide 44 px o más, y se puede agregar a la pantalla de inicio como app (ícono con el escudo).

## 4. ¿Dónde está…?

| Qué | Dónde |
|---|---|
| **Conexión de la app** (base transaccional) | `app_escuela\config.py` → `CADENA_CONEXION` |
| **Conexión de la minería** (Data Warehouse) | `mineria_pagos.py`, constantes `SERVIDOR` y `DATA_WAREHOUSE` y función `cargar_datos()` |
| **Conexión de los datos de prueba** | `datos_prueba\generar_pagos_prueba.py`, constantes `SERVIDOR` y `BASE` |
| **Conexiones del SSIS** | `Package.dtsx`: 2 por base (OLE DB y ADO.NET), `.\MSSQLSERVER01` |
| **Umbrales de riesgo Alto / Medio / Bajo** | `mineria_pagos.py`: `UMBRAL_ALTO`, `UMBRAL_MEDIO`, `MIN_PAGOS_HISTORIAL` |
| **Qué es "simulado"** | Recibos SIM- y PRB-. Los REC- son los de ejemplo de la base entregada; los PAG- los registra la app. |
| **Colores y tipografías** | `app_escuela\estaticos\css\estilos.css` (variables al inicio, modo claro y oscuro) |
| **Permisos por rol** | `app_escuela\rutas\seguridad.py` |
| **Regla del cupo** (no inscribir si el grupo está lleno) | `app_escuela\datos\alumnos.py`, función `_inscribir()` (transacción con bloqueo) |
| **Regla de edad** (un niño solo en la categoría de su edad, sin excepciones) | `datos\alumnos.py` (`_inscribir()`, `guardar_alumno()`) y `datos\catalogos.py` (`revisar_edades()`, `mensaje_edad()`); avisos en `datos\reportes.py` (`fuera_de_categoria()`) |
| **Datos de la escuela en el recibo** (nombre, teléfono, dirección, escudo) | `app_escuela\config.py` → `ESCUELA` |
| **Lugares y "Cómo llegar"** | `app_escuela\lugares.json` (se editan en la pantalla Horarios) |
| **Tablas que se vuelven tarjetas en el celular** | `app_escuela\estaticos\js\app.js` → `tablasComoTarjetas()` + bloque "Celular" de `estilos.css` |
| **Entrar desde el celular** | `app_escuela\config.py` → `HOST` (0.0.0.0 = red WiFi). `python app.py` muestra la dirección |
| **Patrones (PCA, silueta, similitud, matriz preparada)** | `mineria_pagos.py`, bloque final (línea 901) → `resultados\patrones.json` |
| **Pago + auditoría en una transacción** | `app_escuela\datos\pagos.py`, funciones `registrar_pago()` y `anular_pago()` |
| **Número de recibo PAG-####** | `app_escuela\datos\pagos.py`, función `_siguiente_recibo()` (con bloqueo) |
| **Saldo de una mensualidad** | Se calcula: monto − pagos no anulados (`MENSUALIDAD.estado` no se usa) |
| **"Debe" en Mi grupo** | Saldo en alguna mensualidad ya vencida (`app_escuela\datos\reportes.py`, `mi_grupo()`) |
| **Actualización automática** | `app_escuela\estaticos\js\app.js` (zonas `data-vivo`) y `datos\cambios.py`; no cuenta como actividad para el cierre por inactividad (`rutas\seguridad.py`) |
| **Estados que usa la app** | ACTIVO/INACTIVO (alumno, grupo, horario), ACTIVA/INACTIVA (categoría), ACTIVA/BAJA (inscripción) |

Las conexiones **no se unifican a propósito**: van a bases distintas, y unificarlas ataría
`mineria_pagos.py` a la app. Lo único repetido es el nombre del servidor.

## 5. Cómo se usa

- **Arrancar la app:** encender SQL Server (`net start MSSQL$MSSQLSERVER01` como administrador),
  luego `cd app_escuela` y `python app.py`, y abrir http://localhost:5000
- **En el celular:** misma red WiFi (o Tailscale) y abrir la dirección que muestra `python app.py`.
  Detalles en `app_escuela\README.md`.
- **Actualizar el análisis** (`resultados\`): ejecutar el paquete SSIS desde Visual Studio.
- **Pruebas automáticas (89):** `cd app_escuela` y `python -m unittest discover -s pruebas -t .`
  Las que crean datos trabajan dentro de una transacción que se deshace al final: no dejan filas
  (solo avanzan los números de ID, porque SQL Server no los devuelve).

## 6. Calidad del código

- 05/11/2026: se quitó de la app toda la parte de análisis (pantallas Análisis, Alertas de atraso y Estado del sistema).
- `ruff` no marca imports sin usar, errores ni desorden de importaciones en `app_escuela`.
- `vulture` no encuentra funciones sin usar; tampoco hay plantillas, clases CSS, íconos ni scripts sin usar.
- Rendimiento comprobado con unos 1.860 pagos (más del doble de los actuales): la pantalla más lenta respondió en 0,23 s.
- `mineria_pagos.py`, `documento_word.py` y `generar_pagos_prueba.py` tienen solo detalles de estilo (líneas largas,
  nombres de una letra); no se tocaron porque funcionan y se usan para presentar.

## 7. Limitaciones conocidas

- El ETL copia todos los pagos al DW, **también los anulados**: el análisis los cuenta como pagos.
- El 13/10 se pasó a 45 alumnos a la categoría de su edad: sus mensualidades viejas conservan el precio del grupo
  anterior, así que una categoría puede tener más de un monto.
- La app usa `http` (sin candado). Dentro de Tailscale no es un riesgo; para `https` se puede usar `tailscale serve`.
- El servidor de Flask es el de desarrollo: la computadora tiene que estar prendida con la app corriendo.
- Con dos pagos parciales de una misma mensualidad, el `saldo_pendiente` del DW se calcula por fila.
- Los datos son de ejemplo y simulados (300 REC- de ejemplo, 562 SIM- y PRB- simulados): el análisis muestra
  cómo funciona la técnica, no el comportamiento real.
- `datos\h_pagos_ejemplo.csv` es una copia del 05/10 (802 pagos, sin los PRB-). Solo se usa si no hay
  conexión al DW y en la prueba "el dashboard reacciona" (Paso 7 de la guía).
- El gráfico 2 del dashboard (boxplot) mueve sus puntos un poco al azar ("jitter"), así que su imagen
  cambia en cada ejecución aunque los datos sean los mismos.
