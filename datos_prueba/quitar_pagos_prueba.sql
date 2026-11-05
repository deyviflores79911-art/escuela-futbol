/* =====================================================================
   QUITAR LOS PAGOS DE PRUEBA (SIMULADOS)
   Base: Sistema_EscuelasDeportivas

   Borra SOLO las filas que agrego generar_pagos_prueba.py:
     - PAGO        con numero_recibo que empieza con 'SIM-'
     - MENSUALIDAD e INSCRIPCION de los alumnos 'SIM-AL-'
     - ALUMNO      con codigo que empieza con 'SIM-AL-'
     - TUTOR       que solo tiene alumnos 'SIM-AL-'
   Los 300 pagos originales (recibos REC-) y sus tablas no se tocan.

   Todo va en una transaccion: si algo falla, no se borra nada.
   Despues, ejecuta el paquete SSIS para actualizar el Data Warehouse.
   ===================================================================== */
SET NOCOUNT ON;
SET XACT_ABORT ON;
USE Sistema_EscuelasDeportivas;

-- Cuantas filas originales hay antes (deben ser las mismas al final)
DECLARE @pagos_originales int = (SELECT COUNT(1) FROM PAGO WHERE numero_recibo NOT LIKE 'SIM-%');
DECLARE @alumnos_originales int = (SELECT COUNT(1) FROM ALUMNO WHERE codigo NOT LIKE 'SIM-AL-%');

-- Tutores que solo tienen alumnos de prueba
DECLARE @tutores TABLE (id_tutor int PRIMARY KEY);
INSERT INTO @tutores (id_tutor)
SELECT DISTINCT A.id_tutor FROM ALUMNO A
WHERE A.codigo LIKE 'SIM-AL-%' AND A.id_tutor IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM ALUMNO B WHERE B.id_tutor = A.id_tutor AND B.codigo NOT LIKE 'SIM-AL-%');

BEGIN TRAN;

-- 1) Pagos (de la tabla hija hacia la tabla padre, por las llaves foraneas)
DELETE P FROM PAGO P
INNER JOIN MENSUALIDAD M ON M.id_mensualidad = P.id_mensualidad
INNER JOIN INSCRIPCION I ON I.id_inscripcion = M.id_inscripcion
INNER JOIN ALUMNO A      ON A.id_alumno = I.id_alumno
WHERE A.codigo LIKE 'SIM-AL-%' AND P.numero_recibo LIKE 'SIM-%';
PRINT CONCAT('PAGO borrados: ', @@ROWCOUNT);

-- 2) Mensualidades
DELETE M FROM MENSUALIDAD M
INNER JOIN INSCRIPCION I ON I.id_inscripcion = M.id_inscripcion
INNER JOIN ALUMNO A      ON A.id_alumno = I.id_alumno
WHERE A.codigo LIKE 'SIM-AL-%';
PRINT CONCAT('MENSUALIDAD borradas: ', @@ROWCOUNT);

-- 3) Inscripciones
DELETE I FROM INSCRIPCION I
INNER JOIN ALUMNO A ON A.id_alumno = I.id_alumno
WHERE A.codigo LIKE 'SIM-AL-%';
PRINT CONCAT('INSCRIPCION borradas: ', @@ROWCOUNT);

-- 4) Alumnos
DELETE FROM ALUMNO WHERE codigo LIKE 'SIM-AL-%';
PRINT CONCAT('ALUMNO borrados: ', @@ROWCOUNT);

-- 5) Tutores que solo tenian alumnos de prueba
DELETE T FROM TUTOR T INNER JOIN @tutores X ON X.id_tutor = T.id_tutor;
PRINT CONCAT('TUTOR borrados: ', @@ROWCOUNT);

-- Seguridad: si cambio algo original, se deshace todo
IF (SELECT COUNT(1) FROM PAGO) <> @pagos_originales
   OR (SELECT COUNT(1) FROM ALUMNO) <> @alumnos_originales
BEGIN
    ROLLBACK;
    RAISERROR('Los totales no coinciden con las filas originales. No se borro nada.', 16, 1);
    RETURN;
END

COMMIT;
PRINT 'Listo: solo quedan los datos originales. Ejecuta el paquete SSIS para actualizar el Data Warehouse.';

SELECT (SELECT COUNT(1) FROM TUTOR) AS tutores, (SELECT COUNT(1) FROM ALUMNO) AS alumnos,
       (SELECT COUNT(1) FROM INSCRIPCION) AS inscripciones, (SELECT COUNT(1) FROM MENSUALIDAD) AS mensualidades,
       (SELECT COUNT(1) FROM PAGO) AS pagos;
