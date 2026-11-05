# Sistema de gestión de la escuela de fútbol

App web (Flask + pyodbc) sobre la base `Sistema_EscuelasDeportivas` (SQL Server `localhost\MSSQLSERVER01`).
El mapa completo del proyecto (flujo, pantallas y dónde está cada cosa) está en `..\MAPA_DEL_PROYECTO.md`.

La app es **solo operativa**: cobros, recibos, inscripciones, alumnos, grupos, horarios, deudores y "Mi grupo".
El análisis de datos no está en la app: se ve en `..\resultados\dashboard.html` y en el Word.

## Requisitos
- Windows, Python 3.14, SQL Server con la base ya creada.
- ODBC Driver 17 for SQL Server.

## Instalar
```
cd app_escuela
python -m pip install -r requirements.txt
```

## Arrancar
1. Encender SQL Server (como administrador): `net start MSSQL$MSSQLSERVER01`
2. `python app.py`
3. Abrir http://localhost:5000

## Usarla en el celular (la app está pensada para el celular)
1. El celular y la computadora deben estar en la **misma red WiFi**.
2. Al arrancar, `python app.py` muestra la dirección para el celular, por ejemplo
   `http://192.168.26.128:5000`. Escribirla en Chrome (Android) o Safari (iPhone).
3. La primera vez Windows puede preguntar si deja pasar a Python por el firewall: elegir **Redes privadas → Permitir**.
4. Para tenerla como app: en Chrome, menú ⋮ → **Agregar a pantalla principal**; en iPhone, Compartir → **Agregar a inicio**.
   Queda un ícono y se abre sin la barra del navegador.
5. Para que solo entre esta computadora: `set APP_HOST=localhost` antes de `python app.py`.

En el celular: barra de abajo con lo más usado (dueño: Inicio · Cobrar · Inscribir · Alumnos · Más),
menú "Más" por secciones que sube desde abajo, tablas convertidas en tarjetas, todo lo que se toca mide
44 px o más, teclado numérico en montos y botón "Guardar" fijo abajo en los formularios largos.

**Con Tailscale** (también fuera del WiFi): abrir `http://<IP 100.x de la computadora>:5000` con `http://`
adelante. El nombre `.ts.net` obliga a usar https: para eso, en otra terminal, `tailscale serve --bg 5000`
y abrir `https://<nombre>.ts.net` (se quita con `tailscale serve reset`).

## Publicar en internet (Vercel + Azure SQL)
La app ya está preparada: el mismo código funciona en la computadora y en la nube.
En la nube se activa sola cuando existe la variable `BD_SERVIDOR`.

**1. Base de datos en Azure (una sola vez)**
1. En https://portal.azure.com → **SQL databases** → **Create**. Usa la oferta gratis
   ("Apply offer"). Crea un servidor nuevo con **SQL authentication** (usuario y contraseña;
   anótalos) y región **Brazil South** (la más cercana a Bolivia).
2. En el servidor → **Networking**: marca **Allow Azure services and resources to access this server**
   (Vercel entra por ahí) y agrega tu IP para entrar desde SSMS.
3. En SSMS (tu computadora): clic derecho en `Sistema_EscuelasDeportivas` → **Tasks** →
   **Deploy Database to Microsoft Azure SQL Database** → conectar al servidor de Azure con ese usuario.
   Copia todas las tablas y datos (pesa unos 8 MB).
4. En SSMS, conectado a Azure, abre `preparar_azure.sql` y presiona **F5**: crea la tabla de lugares
   y pone la hora de Bolivia en las fechas automáticas.

**2. Vercel**
1. https://vercel.com → **Add New → Project** → importa el repositorio `escuela-futbol`.
2. **Root Directory**: `app_escuela`. Framework: **Flask** (lo detecta solo).
3. **Environment Variables**:

| Variable | Valor |
|---|---|
| `BD_SERVIDOR` | `<tu-servidor>.database.windows.net` |
| `BD_NOMBRE` | `Sistema_EscuelasDeportivas` |
| `BD_USUARIO` | el usuario de Azure |
| `BD_CLAVE` | la contraseña de Azure |
| `CLAVE_SECRETA` | un texto largo al azar (`python -c "import secrets; print(secrets.token_hex(32))"`) |

4. **Deploy**. Cada vez que subas cambios a GitHub, Vercel publica la versión nueva sola.

**Bueno saber**
- La base gratis de Azure "se duerme" si nadie la usa: la primera vez puede tardar hasta un minuto.
  Si sale "No se pudo conectar", espera y recarga.
- La app usa siempre la hora de Bolivia, aunque Vercel esté en otro país.
- En la nube los lugares ("Cómo llegar") se guardan en la tabla `LUGAR`, no en `lugares.json`.
- El SSIS y `mineria_pagos.py` siguen leyendo la base de **esta computadora**. Para analizar los
  pagos hechos en la nube, el SSIS tendría que apuntar a Azure.

## Poner o cambiar la contraseña de un usuario existente
```
flask --app app definir-clave marco.admin@escuela.com
```

## Pruebas automáticas
Con SQL Server encendido, desde `app_escuela`:
```
python -m unittest discover -s pruebas -t .
```

## Roles
- **Dueño** = rol `Administrador` de la tabla ROL. Ve todo y registra pagos.
- **Entrenador** = rol `Entrenador`. Se enlaza a su fila de ENTRENADOR por el correo.
- La sesión se cierra tras 30 minutos sin actividad.

### Usuarios
| Usuario | Rol | Grupo |
|---|---|---|
| marco.admin@escuela.com | Dueño | (ve todo) |
| carlos.montano@escuela.com | Entrenador | Sub-10 A |
| gabriel.cocarico@escuela.com | Entrenador | Sub-8 A |
| victor.lazo@escuela.com | Entrenador | Sub-16 A |

Las contraseñas no se guardan en este repositorio. Cada uno cambia la suya en
**Más → su nombre → cambiar contraseña**, y el dueño puede ponerla con `flask --app app definir-clave <correo>`.

## Reglas de la escuela que la app hace cumplir
- **Edad:** un niño solo puede estar en un grupo de la categoría de su edad (rangos de la tabla CATEGORIA).
  Se valida en el servidor, sin excepciones, también para el dueño.
- **Recibo, no factura:** la escuela no tiene NIT. El recibo tiene formato de factura y el escudo, pero dice
  "(Sin derecho a crédito fiscal)". Los datos de la escuela están en `config.py` → `ESCUELA`.

## Limitaciones conocidas
- El ETL (SSIS) lee todos los pagos, también los Anulados: entran al DW con su monto. El SSIS no se modifica.
- Con dos pagos parciales de una misma mensualidad, el `saldo_pendiente` del DW se calcula por fila contra el monto completo.
