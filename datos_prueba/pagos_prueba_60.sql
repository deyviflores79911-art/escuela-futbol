/* =====================================================================
   60 PAGOS DE PRUEBA (SIMULADOS) - Sistema_EscuelasDeportivas
   Recibos PRB-0001 a PRB-0060 | Alumnos PRB-AL-001 a PRB-AL-010

   COMO USARLO (en SQL Server Management Studio):
     1. Cambia la palabra de @ACCION (linea de abajo):
          'VER'       -> muestra los 60 pagos que estan en la base
          'INSERTAR'  -> los agrega (si no estan ya)
          'BORRAR'    -> los quita (solo los PRB-, no toca nada mas)
     2. Presiona F5.
     3. Despues de INSERTAR o BORRAR, ejecuta el paquete SSIS.
   ===================================================================== */
DECLARE @ACCION varchar(10) = 'VER';

SET NOCOUNT ON;
SET XACT_ABORT ON;
USE Sistema_EscuelasDeportivas;

-- ---------------------------------------------------------------------
-- LOS DATOS
-- ---------------------------------------------------------------------
-- 5 familias (tutores)
DECLARE @familias TABLE (ci nvarchar(20), nombres nvarchar(100), apellidos nvarchar(100),
                         telefono nvarchar(20), correo nvarchar(100), direccion nvarchar(200));
INSERT INTO @familias VALUES
    ('4700001', 'Rosa', 'Ticona Prueba', '73300001', 'rosa.ticona.prb1@mail.com', 'Zona 11, Calle 21'),
    ('4700002', 'Wilson', 'Huanca Prueba', '73300002', 'wilson.huanca.prb2@mail.com', 'Zona 12, Calle 22'),
    ('4700003', 'Gladys', 'Limachi Prueba', '73300003', 'gladys.limachi.prb3@mail.com', 'Zona 13, Calle 23'),
    ('4700004', 'Ramiro', 'Copa Prueba', '73300004', 'ramiro.copa.prb4@mail.com', 'Zona 14, Calle 24'),
    ('4700005', 'Lourdes', 'Yujra Prueba', '73300005', 'lourdes.yujra.prb5@mail.com', 'Zona 15, Calle 25');

-- 10 alumnos (2 por familia) y su grupo
DECLARE @alumnos TABLE (codigo nvarchar(20), ci_tutor nvarchar(20), nombres nvarchar(100), apellidos nvarchar(100),
                        fecha_nacimiento date, sexo nvarchar(10), id_grupo int, fecha_inscripcion date);
INSERT INTO @alumnos VALUES
    ('PRB-AL-001', '4700001', 'Thiago', 'Ticona Prueba', '2012-08-20', 'M', 4, '2026-03-22'),
    ('PRB-AL-002', '4700001', 'Camila', 'Ticona Prueba', '2013-06-01', 'F', 4, '2026-03-07'),
    ('PRB-AL-003', '4700002', 'Bruno', 'Huanca Prueba', '2014-09-15', 'M', 2, '2026-03-17'),
    ('PRB-AL-004', '4700002', 'Abril', 'Huanca Prueba', '2015-04-14', 'F', 3, '2026-03-22'),
    ('PRB-AL-005', '4700003', 'Ian', 'Limachi Prueba', '2013-06-22', 'M', 4, '2026-03-06'),
    ('PRB-AL-006', '4700003', 'Zoe', 'Limachi Prueba', '2016-06-24', 'F', 1, '2026-03-21'),
    ('PRB-AL-007', '4700004', 'Gael', 'Copa Prueba', '2014-10-12', 'M', 2, '2026-03-23'),
    ('PRB-AL-008', '4700004', 'Mia', 'Copa Prueba', '2015-06-06', 'F', 3, '2026-03-10'),
    ('PRB-AL-009', '4700005', 'Dylan', 'Yujra Prueba', '2013-09-23', 'M', 4, '2026-03-22'),
    ('PRB-AL-010', '4700005', 'Regina', 'Yujra Prueba', '2020-02-04', 'F', 6, '2026-03-18');

-- 60 pagos: recibo, alumno, mes, mensualidad, vence, pagado el, monto pagado, metodo, estado, usuario, observacion
DECLARE @pagos TABLE (recibo nvarchar(30), codigo nvarchar(20), periodo nvarchar(20), monto_mensualidad decimal(10,2),
                      vencimiento date, fecha_pago date, monto_pagado decimal(10,2), metodo nvarchar(50),
                      estado nvarchar(50), id_usuario int, observaciones nvarchar(255));
INSERT INTO @pagos VALUES
    ('PRB-0001', 'PRB-AL-001', '2026-04', 280.00, '2026-04-10', '2026-04-28', 280.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0002', 'PRB-AL-001', '2026-05', 280.00, '2026-05-10', '2026-05-17', 280.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0003', 'PRB-AL-001', '2026-06', 280.00, '2026-06-10', '2026-06-27', 280.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0004', 'PRB-AL-001', '2026-07', 280.00, '2026-07-10', '2026-07-21', 280.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0005', 'PRB-AL-001', '2026-08', 280.00, '2026-08-10', '2026-08-22', 280.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0006', 'PRB-AL-001', '2026-09', 280.00, '2026-09-10', '2026-09-28', 168.00, 'Efectivo', 'Parcial', 3, 'Pago parcial'),
    ('PRB-0007', 'PRB-AL-002', '2026-04', 252.00, '2026-04-10', '2026-04-22', 252.00, 'Tarjeta', 'Confirmado', 2, NULL),
    ('PRB-0008', 'PRB-AL-002', '2026-05', 252.00, '2026-05-10', '2026-05-24', 151.20, 'Efectivo', 'Parcial', 2, 'Pago parcial'),
    ('PRB-0009', 'PRB-AL-002', '2026-06', 252.00, '2026-06-10', '2026-06-30', 252.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0010', 'PRB-AL-002', '2026-07', 252.00, '2026-07-10', '2026-07-25', 252.00, 'QR', 'Confirmado', 3, NULL),
    ('PRB-0011', 'PRB-AL-002', '2026-08', 252.00, '2026-08-10', '2026-08-09', 252.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0012', 'PRB-AL-002', '2026-09', 252.00, '2026-09-10', '2026-09-13', 252.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0013', 'PRB-AL-003', '2026-04', 250.00, '2026-04-10', '2026-04-28', 150.00, 'Efectivo', 'Parcial', 2, 'Pago parcial'),
    ('PRB-0014', 'PRB-AL-003', '2026-05', 250.00, '2026-05-10', '2026-05-23', 250.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0015', 'PRB-AL-003', '2026-06', 250.00, '2026-06-10', '2026-06-18', 250.00, 'Transferencia', 'Confirmado', 3, NULL),
    ('PRB-0016', 'PRB-AL-003', '2026-07', 250.00, '2026-07-10', '2026-07-23', 250.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0017', 'PRB-AL-003', '2026-08', 250.00, '2026-08-10', '2026-08-19', 150.00, 'Efectivo', 'Parcial', 3, 'Pago parcial'),
    ('PRB-0018', 'PRB-AL-003', '2026-09', 250.00, '2026-09-10', '2026-09-08', 250.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0019', 'PRB-AL-004', '2026-04', 225.00, '2026-04-10', '2026-04-22', 225.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0020', 'PRB-AL-004', '2026-05', 225.00, '2026-05-10', '2026-05-02', 225.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0021', 'PRB-AL-004', '2026-06', 225.00, '2026-06-10', '2026-06-05', 225.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0022', 'PRB-AL-004', '2026-07', 225.00, '2026-07-10', '2026-07-02', 225.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0023', 'PRB-AL-004', '2026-08', 225.00, '2026-08-10', '2026-08-24', 135.00, 'Efectivo', 'Parcial', 2, 'Pago parcial'),
    ('PRB-0024', 'PRB-AL-004', '2026-09', 225.00, '2026-09-10', '2026-09-05', 225.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0025', 'PRB-AL-005', '2026-04', 280.00, '2026-04-10', '2026-04-13', 280.00, 'Tarjeta', 'Confirmado', 2, NULL),
    ('PRB-0026', 'PRB-AL-005', '2026-05', 280.00, '2026-05-10', '2026-05-10', 280.00, 'Tarjeta', 'Confirmado', 3, NULL),
    ('PRB-0027', 'PRB-AL-005', '2026-06', 280.00, '2026-06-10', '2026-06-05', 280.00, 'Tarjeta', 'Confirmado', 3, NULL),
    ('PRB-0028', 'PRB-AL-005', '2026-07', 280.00, '2026-07-10', '2026-07-28', 280.00, 'Tarjeta', 'Confirmado', 2, NULL),
    ('PRB-0029', 'PRB-AL-005', '2026-08', 280.00, '2026-08-10', '2026-08-07', 280.00, 'Tarjeta', 'Confirmado', 2, NULL),
    ('PRB-0030', 'PRB-AL-005', '2026-09', 280.00, '2026-09-10', '2026-09-23', 280.00, 'Tarjeta', 'Confirmado', 3, NULL),
    ('PRB-0031', 'PRB-AL-006', '2026-04', 198.00, '2026-04-10', '2026-04-28', 198.00, 'Tarjeta', 'Confirmado', 2, NULL),
    ('PRB-0032', 'PRB-AL-006', '2026-05', 198.00, '2026-05-10', '2026-05-24', 198.00, 'Tarjeta', 'Confirmado', 3, NULL),
    ('PRB-0033', 'PRB-AL-006', '2026-06', 198.00, '2026-06-10', '2026-06-14', 198.00, 'Tarjeta', 'Confirmado', 3, NULL),
    ('PRB-0034', 'PRB-AL-006', '2026-07', 198.00, '2026-07-10', '2026-07-16', 198.00, 'Tarjeta', 'Confirmado', 3, NULL),
    ('PRB-0035', 'PRB-AL-006', '2026-08', 198.00, '2026-08-10', '2026-08-09', 198.00, 'Transferencia', 'Confirmado', 3, NULL),
    ('PRB-0036', 'PRB-AL-006', '2026-09', 198.00, '2026-09-10', '2026-09-29', 198.00, 'Tarjeta', 'Confirmado', 3, NULL),
    ('PRB-0037', 'PRB-AL-007', '2026-04', 250.00, '2026-04-10', '2026-04-28', 250.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0038', 'PRB-AL-007', '2026-05', 250.00, '2026-05-10', '2026-05-14', 250.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0039', 'PRB-AL-007', '2026-06', 250.00, '2026-06-10', '2026-06-04', 250.00, 'Transferencia', 'Confirmado', 2, NULL),
    ('PRB-0040', 'PRB-AL-007', '2026-07', 250.00, '2026-07-10', '2026-07-08', 250.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0041', 'PRB-AL-007', '2026-08', 250.00, '2026-08-10', '2026-08-04', 250.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0042', 'PRB-AL-007', '2026-09', 250.00, '2026-09-10', '2026-09-26', 250.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0043', 'PRB-AL-008', '2026-04', 225.00, '2026-04-10', '2026-04-02', 225.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0044', 'PRB-AL-008', '2026-05', 225.00, '2026-05-10', '2026-05-02', 225.00, 'Efectivo', 'Confirmado', 3, NULL),
    ('PRB-0045', 'PRB-AL-008', '2026-06', 225.00, '2026-06-10', '2026-06-06', 225.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0046', 'PRB-AL-008', '2026-07', 225.00, '2026-07-10', '2026-07-04', 225.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0047', 'PRB-AL-008', '2026-08', 225.00, '2026-08-10', '2026-08-06', 225.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0048', 'PRB-AL-008', '2026-09', 225.00, '2026-09-10', '2026-09-25', 225.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0049', 'PRB-AL-009', '2026-04', 280.00, '2026-04-10', '2026-04-04', 280.00, 'QR', 'Confirmado', 2, NULL),
    ('PRB-0050', 'PRB-AL-009', '2026-05', 280.00, '2026-05-10', '2026-05-03', 280.00, 'QR', 'Confirmado', 3, NULL),
    ('PRB-0051', 'PRB-AL-009', '2026-06', 280.00, '2026-06-10', '2026-06-08', 280.00, 'QR', 'Confirmado', 3, NULL),
    ('PRB-0052', 'PRB-AL-009', '2026-07', 280.00, '2026-07-10', '2026-07-13', 280.00, 'QR', 'Confirmado', 2, NULL),
    ('PRB-0053', 'PRB-AL-009', '2026-08', 280.00, '2026-08-10', '2026-08-02', 280.00, 'QR', 'Confirmado', 2, NULL),
    ('PRB-0054', 'PRB-AL-009', '2026-09', 280.00, '2026-09-10', '2026-09-16', 280.00, 'QR', 'Confirmado', 3, NULL),
    ('PRB-0055', 'PRB-AL-010', '2026-04', 180.00, '2026-04-10', '2026-04-21', 180.00, 'Transferencia', 'Confirmado', 3, NULL),
    ('PRB-0056', 'PRB-AL-010', '2026-05', 180.00, '2026-05-10', '2026-05-05', 180.00, 'QR', 'Confirmado', 3, NULL),
    ('PRB-0057', 'PRB-AL-010', '2026-06', 180.00, '2026-06-10', '2026-06-03', 180.00, 'QR', 'Confirmado', 3, NULL),
    ('PRB-0058', 'PRB-AL-010', '2026-07', 180.00, '2026-07-10', '2026-07-07', 180.00, 'Efectivo', 'Confirmado', 2, NULL),
    ('PRB-0059', 'PRB-AL-010', '2026-08', 180.00, '2026-08-10', '2026-08-02', 180.00, 'QR', 'Confirmado', 2, NULL),
    ('PRB-0060', 'PRB-AL-010', '2026-09', 180.00, '2026-09-10', '2026-09-03', 180.00, 'QR', 'Confirmado', 2, NULL);

-- ---------------------------------------------------------------------
-- VER
-- ---------------------------------------------------------------------
IF @ACCION = 'VER'
BEGIN
    SELECT P.numero_recibo, A.codigo, A.nombres + ' ' + A.apellidos AS alumno, M.periodo, M.fecha_vencimiento,
           P.fecha_pago, DATEDIFF(day, M.fecha_vencimiento, P.fecha_pago) AS dias_atraso,
           CASE WHEN P.fecha_pago > M.fecha_vencimiento THEN 'ATRASADO' ELSE 'A tiempo' END AS situacion,
           MP.nombre AS metodo, P.monto
    FROM PAGO P JOIN MENSUALIDAD M ON M.id_mensualidad = P.id_mensualidad
    JOIN INSCRIPCION I ON I.id_inscripcion = M.id_inscripcion JOIN ALUMNO A ON A.id_alumno = I.id_alumno
    JOIN METODO_PAGO MP ON MP.id_metodo_pago = P.id_metodo_pago
    WHERE P.numero_recibo LIKE 'PRB-%' ORDER BY P.numero_recibo;
    SELECT COUNT(*) AS pagos_PRB_en_la_base FROM PAGO WHERE numero_recibo LIKE 'PRB-%';
END

-- ---------------------------------------------------------------------
-- INSERTAR
-- ---------------------------------------------------------------------
IF @ACCION = 'INSERTAR'
BEGIN
    IF EXISTS (SELECT 1 FROM PAGO WHERE numero_recibo LIKE 'PRB-%')
    BEGIN
        PRINT 'Los pagos PRB- ya estan en la base. No se inserto nada.';
    END
    ELSE
    BEGIN
        BEGIN TRAN;
        INSERT INTO TUTOR (nombres, apellidos, ci, telefono, whatsapp, correo, direccion)
        SELECT nombres, apellidos, ci, telefono, telefono, correo, direccion FROM @familias;

        INSERT INTO ALUMNO (id_tutor, codigo, nombres, apellidos, fecha_nacimiento, sexo, direccion, estado, fecha_registro)
        SELECT T.id_tutor, X.codigo, X.nombres, X.apellidos, X.fecha_nacimiento, X.sexo, T.direccion, 'ACTIVO', X.fecha_inscripcion
        FROM @alumnos X JOIN TUTOR T ON T.ci = X.ci_tutor;

        INSERT INTO INSCRIPCION (id_alumno, id_grupo, fecha_inscripcion, estado)
        SELECT A.id_alumno, X.id_grupo, X.fecha_inscripcion, 'ACTIVA'
        FROM @alumnos X JOIN ALUMNO A ON A.codigo = X.codigo;

        INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado)
        SELECT I.id_inscripcion, X.periodo, DATEFROMPARTS(YEAR(X.vencimiento), MONTH(X.vencimiento), 1),
               X.vencimiento, X.monto_mensualidad, 'PENDIENTE'
        FROM @pagos X JOIN ALUMNO A ON A.codigo = X.codigo JOIN INSCRIPCION I ON I.id_alumno = A.id_alumno;

        INSERT INTO PAGO (id_mensualidad, id_usuario, id_metodo_pago, id_estado_pago, numero_recibo, fecha_pago, monto, observaciones)
        SELECT M.id_mensualidad, X.id_usuario, MP.id_metodo_pago, EP.id_estado_pago, X.recibo, X.fecha_pago, X.monto_pagado, X.observaciones
        FROM @pagos X JOIN ALUMNO A ON A.codigo = X.codigo JOIN INSCRIPCION I ON I.id_alumno = A.id_alumno
        JOIN MENSUALIDAD M ON M.id_inscripcion = I.id_inscripcion AND M.periodo = X.periodo
        JOIN METODO_PAGO MP ON MP.nombre = X.metodo JOIN ESTADO_PAGO EP ON EP.nombre = X.estado;

        IF (SELECT COUNT(*) FROM PAGO WHERE numero_recibo LIKE 'PRB-%') <> 60
        BEGIN
            ROLLBACK;
            RAISERROR('No se insertaron exactamente 60 pagos. No se guardo nada.', 16, 1);
            RETURN;
        END
        COMMIT;
        PRINT 'Listo: 60 pagos PRB- insertados. Ahora ejecuta el paquete SSIS.';
    END
END

-- ---------------------------------------------------------------------
-- BORRAR (solo PRB-)
-- ---------------------------------------------------------------------
IF @ACCION = 'BORRAR'
BEGIN
    BEGIN TRAN;
    DELETE P FROM PAGO P JOIN MENSUALIDAD M ON M.id_mensualidad = P.id_mensualidad
      JOIN INSCRIPCION I ON I.id_inscripcion = M.id_inscripcion JOIN ALUMNO A ON A.id_alumno = I.id_alumno
      WHERE A.codigo LIKE 'PRB-AL-%' AND P.numero_recibo LIKE 'PRB-%';
    DELETE M FROM MENSUALIDAD M JOIN INSCRIPCION I ON I.id_inscripcion = M.id_inscripcion
      JOIN ALUMNO A ON A.id_alumno = I.id_alumno WHERE A.codigo LIKE 'PRB-AL-%';
    DELETE I FROM INSCRIPCION I JOIN ALUMNO A ON A.id_alumno = I.id_alumno WHERE A.codigo LIKE 'PRB-AL-%';
    DELETE FROM ALUMNO WHERE codigo LIKE 'PRB-AL-%';
    DELETE T FROM TUTOR T JOIN @familias F ON F.ci = T.ci
      WHERE NOT EXISTS (SELECT 1 FROM ALUMNO A WHERE A.id_tutor = T.id_tutor);
    COMMIT;
    PRINT 'Listo: pagos PRB- borrados. Ahora ejecuta el paquete SSIS.';
END
