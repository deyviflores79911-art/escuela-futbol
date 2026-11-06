/* =====================================================================
   PREPARAR LA BASE EN AZURE SQL (se ejecuta UNA vez, en Azure, no en la computadora)
   Despues de copiar Sistema_EscuelasDeportivas a Azure, abrir este archivo en SSMS
   conectado a Azure, elegir la base Sistema_EscuelasDeportivas y presionar F5.
   Se puede ejecutar mas de una vez sin problema.
   ===================================================================== */
SET XACT_ABORT ON;
BEGIN TRANSACTION;

/* 1. Tabla de lugares de entrenamiento ("Como llegar").
      En la computadora estan en lugares.json; Vercel no deja guardar archivos. */
IF OBJECT_ID('dbo.LUGAR', 'U') IS NULL
    CREATE TABLE dbo.LUGAR (
        nombre NVARCHAR(100) NOT NULL PRIMARY KEY,
        enlace NVARCHAR(500) NOT NULL
    );

MERGE dbo.LUGAR AS destino
USING (VALUES
    (N'Cancha Nuevo Palmar (Calle Luciano)', N'https://maps.app.goo.gl/yi2pjXHkhbEepCnu6'),
    (N'Club Deportivo Huracán del Sur',      N'https://maps.app.goo.gl/MkekLPzbcszAhokKA')
) AS origen (nombre, enlace)
ON destino.nombre = origen.nombre
WHEN NOT MATCHED THEN INSERT (nombre, enlace) VALUES (origen.nombre, origen.enlace);

/* 2. Hora de Bolivia en las fechas automaticas (fecha de registro y fecha de auditoria).
      Azure usa la hora UTC: GETDATE() daria 4 horas de mas. */
DECLARE @sql NVARCHAR(MAX) = N'';
SELECT @sql += N'ALTER TABLE ' + QUOTENAME(SCHEMA_NAME(t.schema_id)) + N'.' + QUOTENAME(t.name)
             + N' DROP CONSTRAINT ' + QUOTENAME(dc.name) + N'; '
             + N'ALTER TABLE ' + QUOTENAME(SCHEMA_NAME(t.schema_id)) + N'.' + QUOTENAME(t.name)
             + N' ADD CONSTRAINT ' + QUOTENAME(N'DF_' + t.name + N'_' + c.name)
             + N' DEFAULT (CAST(SYSDATETIMEOFFSET() AT TIME ZONE ''SA Western Standard Time'' AS datetime))'
             + N' FOR ' + QUOTENAME(c.name) + N'; '
FROM sys.default_constraints dc
JOIN sys.tables t  ON t.object_id = dc.parent_object_id
JOIN sys.columns c ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
WHERE dc.definition LIKE N'%getdate()%';
EXEC sys.sp_executesql @sql;

/* 3. Becas: porcentaje de descuento por alumno (0 = paga completo, 100 = no paga) */
IF COL_LENGTH('dbo.ALUMNO', 'porcentaje_beca') IS NULL
    EXEC sys.sp_executesql N'ALTER TABLE dbo.ALUMNO ADD porcentaje_beca DECIMAL(5,2) NOT NULL
        CONSTRAINT DF_ALUMNO_porcentaje_beca DEFAULT 0
        CONSTRAINT CK_ALUMNO_porcentaje_beca CHECK (porcentaje_beca >= 0 AND porcentaje_beca <= 100)';

COMMIT TRANSACTION;

/* 4. Revision: debe mostrar los 2 lugares y la hora actual de Bolivia */
SELECT nombre, enlace FROM dbo.LUGAR ORDER BY nombre;
SELECT CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'SA Western Standard Time' AS datetime) AS hora_bolivia;
