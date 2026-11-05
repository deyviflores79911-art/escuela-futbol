/* ============================================================
   SISTEMA TRANSACCIONAL: Sistema_EscuelasDeportivas
   Version final (14 tablas). Es UNA SOLA escuela de futbol
   (un unico cliente), por eso NO existe tabla ESCUELA: tenerla
   no aportaria nada, siempre seria una sola fila.

   LOGICA DE NEGOCIO (imaginando el sistema corriendo):

   - La escuela tiene ENTRENADORES y ofrece GRUPOS.
   - Un GRUPO pertenece a UNA categoria (Sub-12, etc.) y tiene
     UN entrenador.
   - CATEGORIA es un catalogo (Sub-8...Sub-16).
   - Un ALUMNO se registra una vez (tabla ALUMNO) y luego se
     INSCRIBE en uno o varios GRUPOS a lo largo del tiempo
     (tabla INSCRIPCION).
   - Cada INSCRIPCION genera, mes a mes, una MENSUALIDAD (lo
     que debe).
   - Cada MENSUALIDAD puede recibir uno o varios PAGOS (lo que
     pago, permite pagos parciales).
   - METODO_PAGO y ESTADO_PAGO son catalogos (no texto libre),
     para alimentar directamente las dimensiones D_METODO_PAGO
     y D_ESTADO_PAGO del DW sin adivinar categorias desde texto
     libre en el ETL.
   - AUDITORIA_PAGO registra cambios sobre PAGO (requisito de
     auditoria del laboratorio).

   CADENA COMPLETA HASTA EL HECHO DE PAGO:
   PAGO -> MENSUALIDAD -> INSCRIPCION -> GRUPO -> CATEGORIA
                        -> INSCRIPCION -> ALUMNO
   PAGO -> METODO_PAGO
   PAGO -> ESTADO_PAGO
   PAGO -> fecha_pago -> D_TIEMPO (en el DW)

   Esa cadena es la que el ETL usara para llenar H_PAGOS con
   id_alumno, id_categoria, id_metodo_pago, id_estado_pago e
   id_tiempo.
   ============================================================ */

IF DB_ID('Sistema_EscuelasDeportivas') IS NOT NULL
BEGIN
    ALTER DATABASE Sistema_EscuelasDeportivas SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE Sistema_EscuelasDeportivas;
END
GO

CREATE DATABASE Sistema_EscuelasDeportivas;
GO

USE Sistema_EscuelasDeportivas;
GO

/* ---------- 1. ROL ---------- */
CREATE TABLE ROL (
    id_rol      INT IDENTITY(1,1) NOT NULL,
    nombre      NVARCHAR(50)  NOT NULL,
    descripcion NVARCHAR(200) NULL,
    CONSTRAINT PK_ROL PRIMARY KEY (id_rol)
);
GO

/* ---------- 2. USUARIO ---------- */
CREATE TABLE USUARIO (
    id_usuario     INT IDENTITY(1,1) NOT NULL,
    id_rol         INT             NOT NULL,
    nombres        NVARCHAR(100)   NOT NULL,
    apellidos      NVARCHAR(100)   NULL,
    correo         NVARCHAR(100)   NULL,
    password_hash  NVARCHAR(255)   NULL,
    telefono       NVARCHAR(20)    NULL,
    estado         NVARCHAR(20)    NOT NULL DEFAULT 'ACTIVO',
    fecha_registro DATE            NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_USUARIO PRIMARY KEY (id_usuario),
    CONSTRAINT FK_USUARIO_ROL FOREIGN KEY (id_rol) REFERENCES ROL (id_rol)
);
GO

/* ---------- 3. TUTOR ---------- */
CREATE TABLE TUTOR (
    id_tutor  INT IDENTITY(1,1) NOT NULL,
    nombres   NVARCHAR(100) NOT NULL,
    apellidos NVARCHAR(100) NULL,
    ci        NVARCHAR(20)  NULL,
    telefono  NVARCHAR(20)  NULL,
    whatsapp  NVARCHAR(20)  NULL,
    correo    NVARCHAR(100) NULL,
    direccion NVARCHAR(200) NULL,
    CONSTRAINT PK_TUTOR PRIMARY KEY (id_tutor)
);
GO

/* ---------- 4. ENTRENADOR ---------- */
CREATE TABLE ENTRENADOR (
    id_entrenador INT IDENTITY(1,1) NOT NULL,
    nombres       NVARCHAR(100) NOT NULL,
    apellidos     NVARCHAR(100) NULL,
    ci            NVARCHAR(20)  NULL,
    telefono      NVARCHAR(20)  NULL,
    correo        NVARCHAR(100) NULL,
    especialidad  NVARCHAR(100) NULL,
    estado        NVARCHAR(20)  NOT NULL DEFAULT 'ACTIVO',
    CONSTRAINT PK_ENTRENADOR PRIMARY KEY (id_entrenador)
);
GO

/* ---------- 5. CATEGORIA (catalogo) ---------- */
CREATE TABLE CATEGORIA (
    id_categoria INT IDENTITY(1,1) NOT NULL,
    nombre       NVARCHAR(50) NOT NULL,
    edad_minima  INT NULL,
    edad_maxima  INT NULL,
    estado       NVARCHAR(20) NOT NULL DEFAULT 'ACTIVA',
    CONSTRAINT PK_CATEGORIA PRIMARY KEY (id_categoria)
);
GO

/* ---------- 6. GRUPO ---------- */
CREATE TABLE GRUPO (
    id_grupo       INT IDENTITY(1,1) NOT NULL,
    id_categoria   INT NOT NULL,
    id_entrenador  INT NOT NULL,
    nombre         NVARCHAR(50) NOT NULL,
    cupo_maximo    INT NULL,
    precio_mensual DECIMAL(10,2) NOT NULL,
    estado         NVARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    CONSTRAINT PK_GRUPO PRIMARY KEY (id_grupo),
    CONSTRAINT FK_GRUPO_CATEGORIA FOREIGN KEY (id_categoria) REFERENCES CATEGORIA (id_categoria),
    CONSTRAINT FK_GRUPO_ENTRENADOR FOREIGN KEY (id_entrenador) REFERENCES ENTRENADOR (id_entrenador)
);
GO

/* ---------- 7. HORARIO ---------- */
CREATE TABLE HORARIO (
    id_horario  INT IDENTITY(1,1) NOT NULL,
    id_grupo    INT NOT NULL,
    dia_semana  NVARCHAR(15) NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fin    TIME NOT NULL,
    lugar       NVARCHAR(100) NULL,
    estado      NVARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    CONSTRAINT PK_HORARIO PRIMARY KEY (id_horario),
    CONSTRAINT FK_HORARIO_GRUPO FOREIGN KEY (id_grupo) REFERENCES GRUPO (id_grupo)
);
GO

/* ---------- 8. ALUMNO ---------- */
CREATE TABLE ALUMNO (
    id_alumno         INT IDENTITY(1,1) NOT NULL,
    id_tutor          INT NULL,
    codigo            NVARCHAR(20) NOT NULL,
    nombres           NVARCHAR(100) NOT NULL,
    apellidos         NVARCHAR(100) NULL,
    fecha_nacimiento  DATE NULL,
    sexo              NVARCHAR(10) NULL,
    direccion         NVARCHAR(200) NULL,
    estado            NVARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    fecha_registro    DATE NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_ALUMNO PRIMARY KEY (id_alumno),
    CONSTRAINT FK_ALUMNO_TUTOR FOREIGN KEY (id_tutor) REFERENCES TUTOR (id_tutor)
);
GO

/* ---------- 9. INSCRIPCION ---------- */
CREATE TABLE INSCRIPCION (
    id_inscripcion    INT IDENTITY(1,1) NOT NULL,
    id_alumno         INT NOT NULL,
    id_grupo          INT NOT NULL,
    fecha_inscripcion DATE NOT NULL,
    estado            NVARCHAR(20) NOT NULL DEFAULT 'ACTIVA',
    CONSTRAINT PK_INSCRIPCION PRIMARY KEY (id_inscripcion),
    CONSTRAINT FK_INSCRIPCION_ALUMNO FOREIGN KEY (id_alumno) REFERENCES ALUMNO (id_alumno),
    CONSTRAINT FK_INSCRIPCION_GRUPO FOREIGN KEY (id_grupo) REFERENCES GRUPO (id_grupo)
);
GO

/* ---------- 10. MENSUALIDAD ---------- */
CREATE TABLE MENSUALIDAD (
    id_mensualidad    INT IDENTITY(1,1) NOT NULL,
    id_inscripcion    INT NOT NULL,
    periodo           NVARCHAR(20) NOT NULL,   -- ej '2026-09'
    fecha_emision     DATE NOT NULL,
    fecha_vencimiento DATE NOT NULL,
    monto             DECIMAL(10,2) NOT NULL,
    estado            NVARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    CONSTRAINT PK_MENSUALIDAD PRIMARY KEY (id_mensualidad),
    CONSTRAINT FK_MENSUALIDAD_INSCRIPCION FOREIGN KEY (id_inscripcion) REFERENCES INSCRIPCION (id_inscripcion)
);
GO

/* ---------- 11. METODO_PAGO (catalogo, alimenta D_METODO_PAGO) ---------- */
CREATE TABLE METODO_PAGO (
    id_metodo_pago INT IDENTITY(1,1) NOT NULL,
    nombre         NVARCHAR(50) NOT NULL,
    estado         NVARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    CONSTRAINT PK_METODO_PAGO PRIMARY KEY (id_metodo_pago)
);
GO

/* ---------- 12. ESTADO_PAGO (catalogo, alimenta D_ESTADO_PAGO) ---------- */
CREATE TABLE ESTADO_PAGO (
    id_estado_pago INT IDENTITY(1,1) NOT NULL,
    nombre         NVARCHAR(50) NOT NULL,
    CONSTRAINT PK_ESTADO_PAGO PRIMARY KEY (id_estado_pago)
);
GO

/* ---------- 13. PAGO ---------- */
CREATE TABLE PAGO (
    id_pago        INT IDENTITY(1,1) NOT NULL,
    id_mensualidad INT NOT NULL,
    id_usuario     INT NOT NULL,   -- quien recibe/registra el pago
    id_metodo_pago INT NOT NULL,
    id_estado_pago INT NOT NULL,
    numero_recibo  NVARCHAR(30) NOT NULL,
    fecha_pago     DATE NOT NULL,
    monto          DECIMAL(10,2) NOT NULL,
    observaciones  NVARCHAR(255) NULL,
    CONSTRAINT PK_PAGO PRIMARY KEY (id_pago),
    CONSTRAINT FK_PAGO_MENSUALIDAD FOREIGN KEY (id_mensualidad) REFERENCES MENSUALIDAD (id_mensualidad),
    CONSTRAINT FK_PAGO_USUARIO FOREIGN KEY (id_usuario) REFERENCES USUARIO (id_usuario),
    CONSTRAINT FK_PAGO_METODO FOREIGN KEY (id_metodo_pago) REFERENCES METODO_PAGO (id_metodo_pago),
    CONSTRAINT FK_PAGO_ESTADO FOREIGN KEY (id_estado_pago) REFERENCES ESTADO_PAGO (id_estado_pago)
);
GO

/* ---------- 14. AUDITORIA_PAGO ---------- */
CREATE TABLE AUDITORIA_PAGO (
    id_auditoria    INT IDENTITY(1,1) NOT NULL,
    id_pago         INT NOT NULL,
    operacion       NVARCHAR(20) NOT NULL,   -- INSERT / UPDATE / ANULACION
    usuario         NVARCHAR(100) NULL,
    fecha           DATETIME NOT NULL DEFAULT GETDATE(),
    monto_anterior  DECIMAL(10,2) NULL,
    monto_nuevo     DECIMAL(10,2) NULL,
    estado_anterior NVARCHAR(20) NULL,
    estado_nuevo    NVARCHAR(20) NULL,
    CONSTRAINT PK_AUDITORIA_PAGO PRIMARY KEY (id_auditoria),
    CONSTRAINT FK_AUDITORIA_PAGO FOREIGN KEY (id_pago) REFERENCES PAGO (id_pago)
);
GO

/* ============================================================
   DATOS DE EJEMPLO (~300 registros de pagos/mensualidades,
   generados para simular un semestre real: 50 alumnos x 6
   meses de mensualidades, con un pago por mensualidad,
   incluyendo pagos parciales y atrasados para probar los
   indicadores calculados en el DW).
   ============================================================ */

-- ROL
INSERT INTO ROL (nombre, descripcion) VALUES
('Administrador', 'Control total del sistema'),
('Secretaria', 'Registra alumnos, inscripciones y pagos'),
('Entrenador', 'Dirige los entrenamientos');
GO

-- USUARIO
INSERT INTO USUARIO (id_rol, nombres, apellidos, correo, password_hash, telefono, estado) VALUES
(1, 'Marco', 'Villca', 'marco.admin@escuela.com', 'hash1', '70011122', 'ACTIVO'),
(2, 'Carla', 'Rojas', 'carla.secretaria@escuela.com', 'hash2', '70022233', 'ACTIVO'),
(2, 'Diego', 'Flores', 'diego.secretaria@escuela.com', 'hash3', '70033344', 'ACTIVO');
GO

-- TUTOR (25)
INSERT INTO TUTOR (nombres, apellidos, ci, telefono, whatsapp, correo, direccion) VALUES
('Mateo', 'Perez', '4500001', '71100001', '71100001', 'mateo.perez1@mail.com', 'Zona 1, Calle 1'),
('Nicolas', 'Gutierrez', '4500002', '71100002', '71100002', 'nicolas.gutierrez2@mail.com', 'Zona 2, Calle 2'),
('Sebastian', 'Mamani', '4500003', '71100003', '71100003', 'sebastian.mamani3@mail.com', 'Zona 3, Calle 3'),
('Diego', 'Choque', '4500004', '71100004', '71100004', 'diego.choque4@mail.com', 'Zona 4, Calle 4'),
('Santiago', 'Vargas', '4500005', '71100005', '71100005', 'santiago.vargas5@mail.com', 'Zona 5, Calle 5'),
('Mathias', 'Quispe', '4500006', '71100006', '71100006', 'mathias.quispe6@mail.com', 'Zona 6, Calle 6'),
('Benjamin', 'Rojas', '4500007', '71100007', '71100007', 'benjamin.rojas7@mail.com', 'Zona 7, Calle 7'),
('Joaquin', 'Flores', '4500008', '71100008', '71100008', 'joaquin.flores8@mail.com', 'Zona 8, Calle 8'),
('Gabriel', 'Condori', '4500009', '71100009', '71100009', 'gabriel.condori9@mail.com', 'Zona 9, Calle 9'),
('Adrian', 'Aguilar', '4500010', '71100010', '71100010', 'adrian.aguilar10@mail.com', 'Zona 10, Calle 10'),
('Emilio', 'Villca', '4500011', '71100011', '71100011', 'emilio.villca11@mail.com', 'Zona 11, Calle 11'),
('Ivan', 'Rivera', '4500012', '71100012', '71100012', 'ivan.rivera12@mail.com', 'Zona 12, Calle 12'),
('Rodrigo', 'Guzman', '4500013', '71100013', '71100013', 'rodrigo.guzman13@mail.com', 'Zona 13, Calle 13'),
('Andres', 'Salazar', '4500014', '71100014', '71100014', 'andres.salazar14@mail.com', 'Zona 14, Calle 14'),
('Marcelo', 'Torrez', '4500015', '71100015', '71100015', 'marcelo.torrez15@mail.com', 'Zona 15, Calle 15'),
('Fabian', 'Montano', '4500016', '71100016', '71100016', 'fabian.montano16@mail.com', 'Zona 16, Calle 16'),
('Ismael', 'Zambrana', '4500017', '71100017', '71100017', 'ismael.zambrana17@mail.com', 'Zona 17, Calle 17'),
('Bruno', 'Rocha', '4500018', '71100018', '71100018', 'bruno.rocha18@mail.com', 'Zona 18, Calle 18'),
('Franco', 'Cardenas', '4500019', '71100019', '71100019', 'franco.cardenas19@mail.com', 'Zona 19, Calle 19'),
('Leonel', 'Ledezma', '4500020', '71100020', '71100020', 'leonel.ledezma20@mail.com', 'Zona 20, Calle 20'),
('Cristian', 'Colque', '4500021', '71100021', '71100021', 'cristian.colque21@mail.com', 'Zona 21, Calle 1'),
('Alvaro', 'Apaza', '4500022', '71100022', '71100022', 'alvaro.apaza22@mail.com', 'Zona 22, Calle 2'),
('Erick', 'Fernandez', '4500023', '71100023', '71100023', 'erick.fernandez23@mail.com', 'Zona 23, Calle 3'),
('Ronald', 'Chura', '4500024', '71100024', '71100024', 'ronald.chura24@mail.com', 'Zona 24, Calle 4'),
('Denis', 'Mendoza', '4500025', '71100025', '71100025', 'denis.mendoza25@mail.com', 'Zona 25, Calle 5');
GO

-- ENTRENADOR (6)
INSERT INTO ENTRENADOR (nombres, apellidos, ci, telefono, correo, especialidad, estado) VALUES
('Carlos', 'Montano', '3311221', '72200001', 'carlos.montano@escuela.com', 'Futbol infantil', 'ACTIVO'),
('Pedro', 'Salazar', '3322332', '72200002', 'pedro.salazar@escuela.com', 'Futbol juvenil', 'ACTIVO'),
('Miguel', 'Torrez', '3333443', '72200003', 'miguel.torrez@escuela.com', 'Futbol formativo', 'ACTIVO'),
('Sandra', 'Quiroga', '3344554', '72200004', 'sandra.quiroga@escuela.com', 'Preparacion fisica', 'ACTIVO'),
('Ruben', 'Villca', '3355665', '72200005', 'ruben.villca@escuela.com', 'Futbol base', 'ACTIVO'),
('Gabriela', 'Rocha', '3366776', '72200006', 'gabriela.rocha@escuela.com', 'Arqueros', 'ACTIVO');
GO

-- CATEGORIA (5)
INSERT INTO CATEGORIA (nombre, edad_minima, edad_maxima, estado) VALUES
('Sub-8', 6, 8, 'ACTIVA'),
('Sub-10', 9, 10, 'ACTIVA'),
('Sub-12', 11, 12, 'ACTIVA'),
('Sub-14', 13, 14, 'ACTIVA'),
('Sub-16', 15, 16, 'ACTIVA');
GO

-- GRUPO (6)
INSERT INTO GRUPO (id_categoria, id_entrenador, nombre, cupo_maximo, precio_mensual, estado) VALUES
(2, 1, 'Sub-10 A', 20, 220.00, 'ACTIVO'),
(3, 2, 'Sub-12 A', 25, 250.00, 'ACTIVO'),
(3, 3, 'Sub-12 B', 20, 250.00, 'ACTIVO'),
(4, 4, 'Sub-14 A', 25, 280.00, 'ACTIVO'),
(5, 5, 'Sub-16 A', 22, 300.00, 'ACTIVO'),
(1, 6, 'Sub-8 A', 18, 200.00, 'ACTIVO');
GO

-- HORARIO (12)
INSERT INTO HORARIO (id_grupo, dia_semana, hora_inicio, hora_fin, lugar, estado) VALUES
(1, 'Lunes', '15:00', '16:30', 'Cancha 1', 'ACTIVO'),
(1, 'Miercoles', '15:00', '16:30', 'Cancha 1', 'ACTIVO'),
(2, 'Martes', '15:00', '16:30', 'Cancha 2', 'ACTIVO'),
(2, 'Jueves', '15:00', '16:30', 'Cancha 2', 'ACTIVO'),
(3, 'Miercoles', '15:00', '16:30', 'Cancha 3', 'ACTIVO'),
(3, 'Viernes', '15:00', '16:30', 'Cancha 3', 'ACTIVO'),
(4, 'Jueves', '15:00', '16:30', 'Cancha 1', 'ACTIVO'),
(4, 'Lunes', '15:00', '16:30', 'Cancha 1', 'ACTIVO'),
(5, 'Viernes', '15:00', '16:30', 'Cancha 2', 'ACTIVO'),
(5, 'Martes', '15:00', '16:30', 'Cancha 2', 'ACTIVO'),
(6, 'Lunes', '15:00', '16:30', 'Cancha 3', 'ACTIVO'),
(6, 'Miercoles', '15:00', '16:30', 'Cancha 3', 'ACTIVO');
GO

-- ALUMNO (50)
INSERT INTO ALUMNO (id_tutor, codigo, nombres, apellidos, fecha_nacimiento, sexo, direccion, estado) VALUES
(1, 'AL-001', 'Mateo', 'Mamani', '2011-08-06', 'M', 'Zona 1, Calle 1', 'ACTIVO'),
(2, 'AL-002', 'Valentina', 'Quispe', '2012-03-11', 'F', 'Zona 2, Calle 2', 'ACTIVO'),
(3, 'AL-003', 'Sebastian', 'Condori', '2013-10-16', 'M', 'Zona 3, Calle 3', 'ACTIVO'),
(4, 'AL-004', 'Renata', 'Rivera', '2014-05-21', 'F', 'Zona 4, Calle 4', 'ACTIVO'),
(5, 'AL-005', 'Santiago', 'Torrez', '2015-12-26', 'M', 'Zona 5, Calle 5', 'ACTIVO'),
(6, 'AL-006', 'Emilia', 'Rocha', '2016-07-04', 'F', 'Zona 6, Calle 6', 'ACTIVO'),
(7, 'AL-007', 'Benjamin', 'Colque', '2017-02-09', 'M', 'Zona 7, Calle 7', 'ACTIVO'),
(8, 'AL-008', 'Antonella', 'Chura', '2018-09-14', 'F', 'Zona 8, Calle 8', 'ACTIVO'),
(9, 'AL-009', 'Gabriel', 'Gutierrez', '2019-04-19', 'M', 'Zona 9, Calle 9', 'ACTIVO'),
(10, 'AL-010', 'Fernanda', 'Vargas', '2010-11-24', 'F', 'Zona 10, Calle 10', 'ACTIVO'),
(11, 'AL-011', 'Emilio', 'Flores', '2011-06-02', 'M', 'Zona 11, Calle 11', 'ACTIVO'),
(12, 'AL-012', 'Carla', 'Villca', '2012-01-07', 'F', 'Zona 12, Calle 12', 'ACTIVO'),
(13, 'AL-013', 'Rodrigo', 'Salazar', '2013-08-12', 'M', 'Zona 13, Calle 13', 'ACTIVO'),
(14, 'AL-014', 'Andrea', 'Zambrana', '2014-03-17', 'F', 'Zona 14, Calle 14', 'ACTIVO'),
(15, 'AL-015', 'Marcelo', 'Ledezma', '2015-10-22', 'M', 'Zona 15, Calle 15', 'ACTIVO'),
(16, 'AL-016', 'Gabriela', 'Fernandez', '2016-05-27', 'F', 'Zona 16, Calle 16', 'ACTIVO'),
(17, 'AL-017', 'Ismael', 'Perez', '2017-12-05', 'M', 'Zona 17, Calle 17', 'ACTIVO'),
(18, 'AL-018', 'Ximena', 'Choque', '2018-07-10', 'F', 'Zona 18, Calle 18', 'ACTIVO'),
(19, 'AL-019', 'Franco', 'Rojas', '2019-02-15', 'M', 'Zona 19, Calle 19', 'ACTIVO'),
(20, 'AL-020', 'Brenda', 'Aguilar', '2010-09-20', 'F', 'Zona 20, Calle 20', 'ACTIVO'),
(21, 'AL-021', 'Cristian', 'Guzman', '2011-04-25', 'M', 'Zona 21, Calle 1', 'ACTIVO'),
(22, 'AL-022', 'Noelia', 'Montano', '2012-11-03', 'F', 'Zona 22, Calle 2', 'ACTIVO'),
(23, 'AL-023', 'Erick', 'Cardenas', '2013-06-08', 'M', 'Zona 23, Calle 3', 'ACTIVO'),
(24, 'AL-024', 'Zoe', 'Apaza', '2014-01-13', 'F', 'Zona 24, Calle 4', 'ACTIVO'),
(25, 'AL-025', 'Denis', 'Mendoza', '2015-08-18', 'M', 'Zona 25, Calle 5', 'ACTIVO'),
(1, 'AL-026', 'Sofia', 'Mamani', '2016-03-23', 'F', 'Zona 1, Calle 6', 'ACTIVO'),
(2, 'AL-027', 'Nicolas', 'Quispe', '2017-10-01', 'M', 'Zona 2, Calle 7', 'ACTIVO'),
(3, 'AL-028', 'Camila', 'Condori', '2018-05-06', 'F', 'Zona 3, Calle 8', 'ACTIVO'),
(4, 'AL-029', 'Diego', 'Rivera', '2019-12-11', 'M', 'Zona 4, Calle 9', 'ACTIVO'),
(5, 'AL-030', 'Isabella', 'Torrez', '2010-07-16', 'F', 'Zona 5, Calle 10', 'ACTIVO'),
(6, 'AL-031', 'Mathias', 'Rocha', '2011-02-21', 'M', 'Zona 6, Calle 11', 'ACTIVO'),
(7, 'AL-032', 'Martina', 'Colque', '2012-09-26', 'F', 'Zona 7, Calle 12', 'ACTIVO'),
(8, 'AL-033', 'Joaquin', 'Chura', '2013-04-04', 'M', 'Zona 8, Calle 13', 'ACTIVO'),
(9, 'AL-034', 'Luciana', 'Gutierrez', '2014-11-09', 'F', 'Zona 9, Calle 14', 'ACTIVO'),
(10, 'AL-035', 'Adrian', 'Vargas', '2015-06-14', 'M', 'Zona 10, Calle 15', 'ACTIVO'),
(11, 'AL-036', 'Daniela', 'Flores', '2016-01-19', 'F', 'Zona 11, Calle 16', 'ACTIVO'),
(12, 'AL-037', 'Ivan', 'Villca', '2017-08-24', 'M', 'Zona 12, Calle 17', 'ACTIVO'),
(13, 'AL-038', 'Paola', 'Salazar', '2018-03-02', 'F', 'Zona 13, Calle 18', 'ACTIVO'),
(14, 'AL-039', 'Andres', 'Zambrana', '2019-10-07', 'M', 'Zona 14, Calle 19', 'ACTIVO'),
(15, 'AL-040', 'Vanessa', 'Ledezma', '2010-05-12', 'F', 'Zona 15, Calle 20', 'ACTIVO'),
(16, 'AL-041', 'Fabian', 'Fernandez', '2011-12-17', 'M', 'Zona 16, Calle 1', 'ACTIVO'),
(17, 'AL-042', 'Melissa', 'Perez', '2012-07-22', 'F', 'Zona 17, Calle 2', 'ACTIVO'),
(18, 'AL-043', 'Bruno', 'Choque', '2013-02-27', 'M', 'Zona 18, Calle 3', 'ACTIVO'),
(19, 'AL-044', 'Yolanda', 'Rojas', '2014-09-05', 'F', 'Zona 19, Calle 4', 'ACTIVO'),
(20, 'AL-045', 'Leonel', 'Aguilar', '2015-04-10', 'M', 'Zona 20, Calle 5', 'ACTIVO'),
(21, 'AL-046', 'Karen', 'Guzman', '2016-11-15', 'F', 'Zona 21, Calle 6', 'ACTIVO'),
(22, 'AL-047', 'Alvaro', 'Montano', '2017-06-20', 'M', 'Zona 22, Calle 7', 'ACTIVO'),
(23, 'AL-048', 'Alison', 'Cardenas', '2018-01-25', 'F', 'Zona 23, Calle 8', 'ACTIVO'),
(24, 'AL-049', 'Ronald', 'Apaza', '2019-08-03', 'M', 'Zona 24, Calle 9', 'ACTIVO'),
(25, 'AL-050', 'Abril', 'Mendoza', '2010-03-08', 'F', 'Zona 25, Calle 10', 'ACTIVO');
GO

-- INSCRIPCION (50)
INSERT INTO INSCRIPCION (id_alumno, id_grupo, fecha_inscripcion, estado) VALUES
(1, 1, '2026-02-03', 'ACTIVA'),
(2, 2, '2026-02-05', 'ACTIVA'),
(3, 3, '2026-02-07', 'ACTIVA'),
(4, 4, '2026-02-09', 'ACTIVA'),
(5, 5, '2026-02-11', 'ACTIVA'),
(6, 6, '2026-02-13', 'ACTIVA'),
(7, 1, '2026-02-15', 'ACTIVA'),
(8, 2, '2026-02-17', 'ACTIVA'),
(9, 3, '2026-02-19', 'ACTIVA'),
(10, 4, '2026-02-21', 'ACTIVA'),
(11, 5, '2026-02-23', 'ACTIVA'),
(12, 6, '2026-02-25', 'ACTIVA'),
(13, 1, '2026-02-02', 'ACTIVA'),
(14, 2, '2026-02-04', 'ACTIVA'),
(15, 3, '2026-02-06', 'ACTIVA'),
(16, 4, '2026-02-08', 'ACTIVA'),
(17, 5, '2026-02-10', 'ACTIVA'),
(18, 6, '2026-02-12', 'ACTIVA'),
(19, 1, '2026-02-14', 'ACTIVA'),
(20, 2, '2026-02-16', 'ACTIVA'),
(21, 3, '2026-02-18', 'ACTIVA'),
(22, 4, '2026-02-20', 'ACTIVA'),
(23, 5, '2026-02-22', 'ACTIVA'),
(24, 6, '2026-02-24', 'ACTIVA'),
(25, 1, '2026-02-01', 'ACTIVA'),
(26, 2, '2026-02-03', 'ACTIVA'),
(27, 3, '2026-02-05', 'ACTIVA'),
(28, 4, '2026-02-07', 'ACTIVA'),
(29, 5, '2026-02-09', 'ACTIVA'),
(30, 6, '2026-02-11', 'ACTIVA'),
(31, 1, '2026-02-13', 'ACTIVA'),
(32, 2, '2026-02-15', 'ACTIVA'),
(33, 3, '2026-02-17', 'ACTIVA'),
(34, 4, '2026-02-19', 'ACTIVA'),
(35, 5, '2026-02-21', 'ACTIVA'),
(36, 6, '2026-02-23', 'ACTIVA'),
(37, 1, '2026-02-25', 'ACTIVA'),
(38, 2, '2026-02-02', 'ACTIVA'),
(39, 3, '2026-02-04', 'ACTIVA'),
(40, 4, '2026-02-06', 'ACTIVA'),
(41, 5, '2026-02-08', 'ACTIVA'),
(42, 6, '2026-02-10', 'ACTIVA'),
(43, 1, '2026-02-12', 'ACTIVA'),
(44, 2, '2026-02-14', 'ACTIVA'),
(45, 3, '2026-02-16', 'ACTIVA'),
(46, 4, '2026-02-18', 'ACTIVA'),
(47, 5, '2026-02-20', 'ACTIVA'),
(48, 6, '2026-02-22', 'ACTIVA'),
(49, 1, '2026-02-24', 'ACTIVA'),
(50, 2, '2026-02-01', 'ACTIVA');
GO

-- MENSUALIDAD (300)
INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado) VALUES
(1, '2026-04', '2026-04-01', '2026-04-10', 220.00, 'PENDIENTE'),
(1, '2026-05', '2026-05-01', '2026-05-10', 220.00, 'PENDIENTE'),
(1, '2026-06', '2026-06-01', '2026-06-10', 220.00, 'PENDIENTE'),
(1, '2026-07', '2026-07-01', '2026-07-10', 220.00, 'PENDIENTE'),
(1, '2026-08', '2026-08-01', '2026-08-10', 220.00, 'PENDIENTE'),
(1, '2026-09', '2026-09-01', '2026-09-10', 220.00, 'PENDIENTE'),
(2, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(2, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(2, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(2, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(2, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(2, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(3, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(3, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(3, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(3, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(3, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(3, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(4, '2026-04', '2026-04-01', '2026-04-10', 280.00, 'PENDIENTE'),
(4, '2026-05', '2026-05-01', '2026-05-10', 280.00, 'PENDIENTE'),
(4, '2026-06', '2026-06-01', '2026-06-10', 280.00, 'PENDIENTE'),
(4, '2026-07', '2026-07-01', '2026-07-10', 280.00, 'PENDIENTE'),
(4, '2026-08', '2026-08-01', '2026-08-10', 280.00, 'PENDIENTE'),
(4, '2026-09', '2026-09-01', '2026-09-10', 280.00, 'PENDIENTE'),
(5, '2026-04', '2026-04-01', '2026-04-10', 300.00, 'PENDIENTE'),
(5, '2026-05', '2026-05-01', '2026-05-10', 300.00, 'PENDIENTE'),
(5, '2026-06', '2026-06-01', '2026-06-10', 300.00, 'PENDIENTE'),
(5, '2026-07', '2026-07-01', '2026-07-10', 300.00, 'PENDIENTE'),
(5, '2026-08', '2026-08-01', '2026-08-10', 300.00, 'PENDIENTE'),
(5, '2026-09', '2026-09-01', '2026-09-10', 300.00, 'PENDIENTE'),
(6, '2026-04', '2026-04-01', '2026-04-10', 200.00, 'PENDIENTE'),
(6, '2026-05', '2026-05-01', '2026-05-10', 200.00, 'PENDIENTE'),
(6, '2026-06', '2026-06-01', '2026-06-10', 200.00, 'PENDIENTE'),
(6, '2026-07', '2026-07-01', '2026-07-10', 200.00, 'PENDIENTE'),
(6, '2026-08', '2026-08-01', '2026-08-10', 200.00, 'PENDIENTE'),
(6, '2026-09', '2026-09-01', '2026-09-10', 200.00, 'PENDIENTE'),
(7, '2026-04', '2026-04-01', '2026-04-10', 220.00, 'PENDIENTE'),
(7, '2026-05', '2026-05-01', '2026-05-10', 220.00, 'PENDIENTE'),
(7, '2026-06', '2026-06-01', '2026-06-10', 220.00, 'PENDIENTE'),
(7, '2026-07', '2026-07-01', '2026-07-10', 220.00, 'PENDIENTE'),
(7, '2026-08', '2026-08-01', '2026-08-10', 220.00, 'PENDIENTE'),
(7, '2026-09', '2026-09-01', '2026-09-10', 220.00, 'PENDIENTE'),
(8, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(8, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(8, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(8, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(8, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(8, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(9, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(9, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(9, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(9, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(9, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(9, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(10, '2026-04', '2026-04-01', '2026-04-10', 280.00, 'PENDIENTE'),
(10, '2026-05', '2026-05-01', '2026-05-10', 280.00, 'PENDIENTE'),
(10, '2026-06', '2026-06-01', '2026-06-10', 280.00, 'PENDIENTE'),
(10, '2026-07', '2026-07-01', '2026-07-10', 280.00, 'PENDIENTE'),
(10, '2026-08', '2026-08-01', '2026-08-10', 280.00, 'PENDIENTE'),
(10, '2026-09', '2026-09-01', '2026-09-10', 280.00, 'PENDIENTE'),
(11, '2026-04', '2026-04-01', '2026-04-10', 300.00, 'PENDIENTE'),
(11, '2026-05', '2026-05-01', '2026-05-10', 300.00, 'PENDIENTE'),
(11, '2026-06', '2026-06-01', '2026-06-10', 300.00, 'PENDIENTE'),
(11, '2026-07', '2026-07-01', '2026-07-10', 300.00, 'PENDIENTE'),
(11, '2026-08', '2026-08-01', '2026-08-10', 300.00, 'PENDIENTE'),
(11, '2026-09', '2026-09-01', '2026-09-10', 300.00, 'PENDIENTE'),
(12, '2026-04', '2026-04-01', '2026-04-10', 200.00, 'PENDIENTE'),
(12, '2026-05', '2026-05-01', '2026-05-10', 200.00, 'PENDIENTE'),
(12, '2026-06', '2026-06-01', '2026-06-10', 200.00, 'PENDIENTE'),
(12, '2026-07', '2026-07-01', '2026-07-10', 200.00, 'PENDIENTE'),
(12, '2026-08', '2026-08-01', '2026-08-10', 200.00, 'PENDIENTE'),
(12, '2026-09', '2026-09-01', '2026-09-10', 200.00, 'PENDIENTE'),
(13, '2026-04', '2026-04-01', '2026-04-10', 220.00, 'PENDIENTE'),
(13, '2026-05', '2026-05-01', '2026-05-10', 220.00, 'PENDIENTE'),
(13, '2026-06', '2026-06-01', '2026-06-10', 220.00, 'PENDIENTE'),
(13, '2026-07', '2026-07-01', '2026-07-10', 220.00, 'PENDIENTE'),
(13, '2026-08', '2026-08-01', '2026-08-10', 220.00, 'PENDIENTE'),
(13, '2026-09', '2026-09-01', '2026-09-10', 220.00, 'PENDIENTE'),
(14, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(14, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(14, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(14, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(14, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(14, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(15, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(15, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(15, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(15, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(15, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(15, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(16, '2026-04', '2026-04-01', '2026-04-10', 280.00, 'PENDIENTE'),
(16, '2026-05', '2026-05-01', '2026-05-10', 280.00, 'PENDIENTE'),
(16, '2026-06', '2026-06-01', '2026-06-10', 280.00, 'PENDIENTE'),
(16, '2026-07', '2026-07-01', '2026-07-10', 280.00, 'PENDIENTE'),
(16, '2026-08', '2026-08-01', '2026-08-10', 280.00, 'PENDIENTE'),
(16, '2026-09', '2026-09-01', '2026-09-10', 280.00, 'PENDIENTE'),
(17, '2026-04', '2026-04-01', '2026-04-10', 300.00, 'PENDIENTE'),
(17, '2026-05', '2026-05-01', '2026-05-10', 300.00, 'PENDIENTE'),
(17, '2026-06', '2026-06-01', '2026-06-10', 300.00, 'PENDIENTE'),
(17, '2026-07', '2026-07-01', '2026-07-10', 300.00, 'PENDIENTE');
GO

INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado) VALUES
(17, '2026-08', '2026-08-01', '2026-08-10', 300.00, 'PENDIENTE'),
(17, '2026-09', '2026-09-01', '2026-09-10', 300.00, 'PENDIENTE'),
(18, '2026-04', '2026-04-01', '2026-04-10', 200.00, 'PENDIENTE'),
(18, '2026-05', '2026-05-01', '2026-05-10', 200.00, 'PENDIENTE'),
(18, '2026-06', '2026-06-01', '2026-06-10', 200.00, 'PENDIENTE'),
(18, '2026-07', '2026-07-01', '2026-07-10', 200.00, 'PENDIENTE'),
(18, '2026-08', '2026-08-01', '2026-08-10', 200.00, 'PENDIENTE'),
(18, '2026-09', '2026-09-01', '2026-09-10', 200.00, 'PENDIENTE'),
(19, '2026-04', '2026-04-01', '2026-04-10', 220.00, 'PENDIENTE'),
(19, '2026-05', '2026-05-01', '2026-05-10', 220.00, 'PENDIENTE'),
(19, '2026-06', '2026-06-01', '2026-06-10', 220.00, 'PENDIENTE'),
(19, '2026-07', '2026-07-01', '2026-07-10', 220.00, 'PENDIENTE'),
(19, '2026-08', '2026-08-01', '2026-08-10', 220.00, 'PENDIENTE'),
(19, '2026-09', '2026-09-01', '2026-09-10', 220.00, 'PENDIENTE'),
(20, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(20, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(20, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(20, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(20, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(20, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(21, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(21, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(21, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(21, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(21, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(21, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(22, '2026-04', '2026-04-01', '2026-04-10', 280.00, 'PENDIENTE'),
(22, '2026-05', '2026-05-01', '2026-05-10', 280.00, 'PENDIENTE'),
(22, '2026-06', '2026-06-01', '2026-06-10', 280.00, 'PENDIENTE'),
(22, '2026-07', '2026-07-01', '2026-07-10', 280.00, 'PENDIENTE'),
(22, '2026-08', '2026-08-01', '2026-08-10', 280.00, 'PENDIENTE'),
(22, '2026-09', '2026-09-01', '2026-09-10', 280.00, 'PENDIENTE'),
(23, '2026-04', '2026-04-01', '2026-04-10', 300.00, 'PENDIENTE'),
(23, '2026-05', '2026-05-01', '2026-05-10', 300.00, 'PENDIENTE'),
(23, '2026-06', '2026-06-01', '2026-06-10', 300.00, 'PENDIENTE'),
(23, '2026-07', '2026-07-01', '2026-07-10', 300.00, 'PENDIENTE'),
(23, '2026-08', '2026-08-01', '2026-08-10', 300.00, 'PENDIENTE'),
(23, '2026-09', '2026-09-01', '2026-09-10', 300.00, 'PENDIENTE'),
(24, '2026-04', '2026-04-01', '2026-04-10', 200.00, 'PENDIENTE'),
(24, '2026-05', '2026-05-01', '2026-05-10', 200.00, 'PENDIENTE'),
(24, '2026-06', '2026-06-01', '2026-06-10', 200.00, 'PENDIENTE'),
(24, '2026-07', '2026-07-01', '2026-07-10', 200.00, 'PENDIENTE'),
(24, '2026-08', '2026-08-01', '2026-08-10', 200.00, 'PENDIENTE'),
(24, '2026-09', '2026-09-01', '2026-09-10', 200.00, 'PENDIENTE'),
(25, '2026-04', '2026-04-01', '2026-04-10', 220.00, 'PENDIENTE'),
(25, '2026-05', '2026-05-01', '2026-05-10', 220.00, 'PENDIENTE'),
(25, '2026-06', '2026-06-01', '2026-06-10', 220.00, 'PENDIENTE'),
(25, '2026-07', '2026-07-01', '2026-07-10', 220.00, 'PENDIENTE'),
(25, '2026-08', '2026-08-01', '2026-08-10', 220.00, 'PENDIENTE'),
(25, '2026-09', '2026-09-01', '2026-09-10', 220.00, 'PENDIENTE'),
(26, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(26, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(26, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(26, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(26, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(26, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(27, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(27, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(27, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(27, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(27, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(27, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(28, '2026-04', '2026-04-01', '2026-04-10', 280.00, 'PENDIENTE'),
(28, '2026-05', '2026-05-01', '2026-05-10', 280.00, 'PENDIENTE'),
(28, '2026-06', '2026-06-01', '2026-06-10', 280.00, 'PENDIENTE'),
(28, '2026-07', '2026-07-01', '2026-07-10', 280.00, 'PENDIENTE'),
(28, '2026-08', '2026-08-01', '2026-08-10', 280.00, 'PENDIENTE'),
(28, '2026-09', '2026-09-01', '2026-09-10', 280.00, 'PENDIENTE'),
(29, '2026-04', '2026-04-01', '2026-04-10', 300.00, 'PENDIENTE'),
(29, '2026-05', '2026-05-01', '2026-05-10', 300.00, 'PENDIENTE'),
(29, '2026-06', '2026-06-01', '2026-06-10', 300.00, 'PENDIENTE'),
(29, '2026-07', '2026-07-01', '2026-07-10', 300.00, 'PENDIENTE'),
(29, '2026-08', '2026-08-01', '2026-08-10', 300.00, 'PENDIENTE'),
(29, '2026-09', '2026-09-01', '2026-09-10', 300.00, 'PENDIENTE'),
(30, '2026-04', '2026-04-01', '2026-04-10', 200.00, 'PENDIENTE'),
(30, '2026-05', '2026-05-01', '2026-05-10', 200.00, 'PENDIENTE'),
(30, '2026-06', '2026-06-01', '2026-06-10', 200.00, 'PENDIENTE'),
(30, '2026-07', '2026-07-01', '2026-07-10', 200.00, 'PENDIENTE'),
(30, '2026-08', '2026-08-01', '2026-08-10', 200.00, 'PENDIENTE'),
(30, '2026-09', '2026-09-01', '2026-09-10', 200.00, 'PENDIENTE'),
(31, '2026-04', '2026-04-01', '2026-04-10', 220.00, 'PENDIENTE'),
(31, '2026-05', '2026-05-01', '2026-05-10', 220.00, 'PENDIENTE'),
(31, '2026-06', '2026-06-01', '2026-06-10', 220.00, 'PENDIENTE'),
(31, '2026-07', '2026-07-01', '2026-07-10', 220.00, 'PENDIENTE'),
(31, '2026-08', '2026-08-01', '2026-08-10', 220.00, 'PENDIENTE'),
(31, '2026-09', '2026-09-01', '2026-09-10', 220.00, 'PENDIENTE'),
(32, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(32, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(32, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(32, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(32, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(32, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(33, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(33, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(33, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(33, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(33, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(33, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(34, '2026-04', '2026-04-01', '2026-04-10', 280.00, 'PENDIENTE'),
(34, '2026-05', '2026-05-01', '2026-05-10', 280.00, 'PENDIENTE');
GO

INSERT INTO MENSUALIDAD (id_inscripcion, periodo, fecha_emision, fecha_vencimiento, monto, estado) VALUES
(34, '2026-06', '2026-06-01', '2026-06-10', 280.00, 'PENDIENTE'),
(34, '2026-07', '2026-07-01', '2026-07-10', 280.00, 'PENDIENTE'),
(34, '2026-08', '2026-08-01', '2026-08-10', 280.00, 'PENDIENTE'),
(34, '2026-09', '2026-09-01', '2026-09-10', 280.00, 'PENDIENTE'),
(35, '2026-04', '2026-04-01', '2026-04-10', 300.00, 'PENDIENTE'),
(35, '2026-05', '2026-05-01', '2026-05-10', 300.00, 'PENDIENTE'),
(35, '2026-06', '2026-06-01', '2026-06-10', 300.00, 'PENDIENTE'),
(35, '2026-07', '2026-07-01', '2026-07-10', 300.00, 'PENDIENTE'),
(35, '2026-08', '2026-08-01', '2026-08-10', 300.00, 'PENDIENTE'),
(35, '2026-09', '2026-09-01', '2026-09-10', 300.00, 'PENDIENTE'),
(36, '2026-04', '2026-04-01', '2026-04-10', 200.00, 'PENDIENTE'),
(36, '2026-05', '2026-05-01', '2026-05-10', 200.00, 'PENDIENTE'),
(36, '2026-06', '2026-06-01', '2026-06-10', 200.00, 'PENDIENTE'),
(36, '2026-07', '2026-07-01', '2026-07-10', 200.00, 'PENDIENTE'),
(36, '2026-08', '2026-08-01', '2026-08-10', 200.00, 'PENDIENTE'),
(36, '2026-09', '2026-09-01', '2026-09-10', 200.00, 'PENDIENTE'),
(37, '2026-04', '2026-04-01', '2026-04-10', 220.00, 'PENDIENTE'),
(37, '2026-05', '2026-05-01', '2026-05-10', 220.00, 'PENDIENTE'),
(37, '2026-06', '2026-06-01', '2026-06-10', 220.00, 'PENDIENTE'),
(37, '2026-07', '2026-07-01', '2026-07-10', 220.00, 'PENDIENTE'),
(37, '2026-08', '2026-08-01', '2026-08-10', 220.00, 'PENDIENTE'),
(37, '2026-09', '2026-09-01', '2026-09-10', 220.00, 'PENDIENTE'),
(38, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(38, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(38, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(38, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(38, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(38, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(39, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(39, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(39, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(39, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(39, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(39, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(40, '2026-04', '2026-04-01', '2026-04-10', 280.00, 'PENDIENTE'),
(40, '2026-05', '2026-05-01', '2026-05-10', 280.00, 'PENDIENTE'),
(40, '2026-06', '2026-06-01', '2026-06-10', 280.00, 'PENDIENTE'),
(40, '2026-07', '2026-07-01', '2026-07-10', 280.00, 'PENDIENTE'),
(40, '2026-08', '2026-08-01', '2026-08-10', 280.00, 'PENDIENTE'),
(40, '2026-09', '2026-09-01', '2026-09-10', 280.00, 'PENDIENTE'),
(41, '2026-04', '2026-04-01', '2026-04-10', 300.00, 'PENDIENTE'),
(41, '2026-05', '2026-05-01', '2026-05-10', 300.00, 'PENDIENTE'),
(41, '2026-06', '2026-06-01', '2026-06-10', 300.00, 'PENDIENTE'),
(41, '2026-07', '2026-07-01', '2026-07-10', 300.00, 'PENDIENTE'),
(41, '2026-08', '2026-08-01', '2026-08-10', 300.00, 'PENDIENTE'),
(41, '2026-09', '2026-09-01', '2026-09-10', 300.00, 'PENDIENTE'),
(42, '2026-04', '2026-04-01', '2026-04-10', 200.00, 'PENDIENTE'),
(42, '2026-05', '2026-05-01', '2026-05-10', 200.00, 'PENDIENTE'),
(42, '2026-06', '2026-06-01', '2026-06-10', 200.00, 'PENDIENTE'),
(42, '2026-07', '2026-07-01', '2026-07-10', 200.00, 'PENDIENTE'),
(42, '2026-08', '2026-08-01', '2026-08-10', 200.00, 'PENDIENTE'),
(42, '2026-09', '2026-09-01', '2026-09-10', 200.00, 'PENDIENTE'),
(43, '2026-04', '2026-04-01', '2026-04-10', 220.00, 'PENDIENTE'),
(43, '2026-05', '2026-05-01', '2026-05-10', 220.00, 'PENDIENTE'),
(43, '2026-06', '2026-06-01', '2026-06-10', 220.00, 'PENDIENTE'),
(43, '2026-07', '2026-07-01', '2026-07-10', 220.00, 'PENDIENTE'),
(43, '2026-08', '2026-08-01', '2026-08-10', 220.00, 'PENDIENTE'),
(43, '2026-09', '2026-09-01', '2026-09-10', 220.00, 'PENDIENTE'),
(44, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(44, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(44, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(44, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(44, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(44, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(45, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(45, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(45, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(45, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(45, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(45, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE'),
(46, '2026-04', '2026-04-01', '2026-04-10', 280.00, 'PENDIENTE'),
(46, '2026-05', '2026-05-01', '2026-05-10', 280.00, 'PENDIENTE'),
(46, '2026-06', '2026-06-01', '2026-06-10', 280.00, 'PENDIENTE'),
(46, '2026-07', '2026-07-01', '2026-07-10', 280.00, 'PENDIENTE'),
(46, '2026-08', '2026-08-01', '2026-08-10', 280.00, 'PENDIENTE'),
(46, '2026-09', '2026-09-01', '2026-09-10', 280.00, 'PENDIENTE'),
(47, '2026-04', '2026-04-01', '2026-04-10', 300.00, 'PENDIENTE'),
(47, '2026-05', '2026-05-01', '2026-05-10', 300.00, 'PENDIENTE'),
(47, '2026-06', '2026-06-01', '2026-06-10', 300.00, 'PENDIENTE'),
(47, '2026-07', '2026-07-01', '2026-07-10', 300.00, 'PENDIENTE'),
(47, '2026-08', '2026-08-01', '2026-08-10', 300.00, 'PENDIENTE'),
(47, '2026-09', '2026-09-01', '2026-09-10', 300.00, 'PENDIENTE'),
(48, '2026-04', '2026-04-01', '2026-04-10', 200.00, 'PENDIENTE'),
(48, '2026-05', '2026-05-01', '2026-05-10', 200.00, 'PENDIENTE'),
(48, '2026-06', '2026-06-01', '2026-06-10', 200.00, 'PENDIENTE'),
(48, '2026-07', '2026-07-01', '2026-07-10', 200.00, 'PENDIENTE'),
(48, '2026-08', '2026-08-01', '2026-08-10', 200.00, 'PENDIENTE'),
(48, '2026-09', '2026-09-01', '2026-09-10', 200.00, 'PENDIENTE'),
(49, '2026-04', '2026-04-01', '2026-04-10', 220.00, 'PENDIENTE'),
(49, '2026-05', '2026-05-01', '2026-05-10', 220.00, 'PENDIENTE'),
(49, '2026-06', '2026-06-01', '2026-06-10', 220.00, 'PENDIENTE'),
(49, '2026-07', '2026-07-01', '2026-07-10', 220.00, 'PENDIENTE'),
(49, '2026-08', '2026-08-01', '2026-08-10', 220.00, 'PENDIENTE'),
(49, '2026-09', '2026-09-01', '2026-09-10', 220.00, 'PENDIENTE'),
(50, '2026-04', '2026-04-01', '2026-04-10', 250.00, 'PENDIENTE'),
(50, '2026-05', '2026-05-01', '2026-05-10', 250.00, 'PENDIENTE'),
(50, '2026-06', '2026-06-01', '2026-06-10', 250.00, 'PENDIENTE'),
(50, '2026-07', '2026-07-01', '2026-07-10', 250.00, 'PENDIENTE'),
(50, '2026-08', '2026-08-01', '2026-08-10', 250.00, 'PENDIENTE'),
(50, '2026-09', '2026-09-01', '2026-09-10', 250.00, 'PENDIENTE');
GO

-- METODO_PAGO
INSERT INTO METODO_PAGO (nombre, estado) VALUES
('Efectivo', 'ACTIVO'),
('Transferencia', 'ACTIVO'),
('QR', 'ACTIVO'),
('Tarjeta', 'ACTIVO');
GO

-- ESTADO_PAGO
INSERT INTO ESTADO_PAGO (nombre) VALUES
('Confirmado'),
('Parcial'),
('Anulado');
GO

-- PAGO (300)
INSERT INTO PAGO (id_mensualidad, id_usuario, id_metodo_pago, id_estado_pago, numero_recibo, fecha_pago, monto, observaciones) VALUES
(1, 2, 1, 1, 'REC-0001', '2026-04-08', 220.00, NULL),
(2, 2, 2, 1, 'REC-0002', '2026-05-09', 220.00, NULL),
(3, 3, 3, 1, 'REC-0003', '2026-06-10', 220.00, NULL),
(4, 2, 4, 1, 'REC-0004', '2026-07-11', 220.00, NULL),
(5, 2, 1, 1, 'REC-0005', '2026-08-12', 220.00, NULL),
(6, 3, 2, 1, 'REC-0006', '2026-09-13', 220.00, NULL),
(7, 2, 3, 1, 'REC-0007', '2026-04-07', 250.00, NULL),
(8, 2, 4, 2, 'REC-0008', '2026-05-08', 150.00, 'Pago parcial'),
(9, 3, 1, 1, 'REC-0009', '2026-06-09', 250.00, NULL),
(10, 2, 2, 1, 'REC-0010', '2026-07-10', 250.00, NULL),
(11, 2, 3, 1, 'REC-0011', '2026-08-11', 250.00, NULL),
(12, 3, 4, 1, 'REC-0012', '2026-09-12', 250.00, NULL),
(13, 2, 1, 1, 'REC-0013', '2026-04-13', 250.00, NULL),
(14, 2, 2, 1, 'REC-0014', '2026-05-07', 250.00, NULL),
(15, 3, 3, 1, 'REC-0015', '2026-06-08', 250.00, NULL),
(16, 2, 4, 2, 'REC-0016', '2026-07-09', 150.00, 'Pago parcial'),
(17, 2, 1, 1, 'REC-0017', '2026-08-10', 250.00, NULL),
(18, 3, 2, 1, 'REC-0018', '2026-09-11', 250.00, NULL),
(19, 2, 3, 1, 'REC-0019', '2026-04-12', 280.00, NULL),
(20, 2, 4, 1, 'REC-0020', '2026-05-13', 280.00, NULL),
(21, 3, 1, 1, 'REC-0021', '2026-06-07', 280.00, NULL),
(22, 2, 2, 1, 'REC-0022', '2026-07-08', 280.00, NULL),
(23, 2, 3, 1, 'REC-0023', '2026-08-09', 280.00, NULL),
(24, 3, 4, 2, 'REC-0024', '2026-09-10', 168.00, 'Pago parcial'),
(25, 2, 1, 1, 'REC-0025', '2026-04-11', 300.00, NULL),
(26, 2, 2, 1, 'REC-0026', '2026-05-12', 300.00, NULL),
(27, 3, 3, 1, 'REC-0027', '2026-06-13', 300.00, NULL),
(28, 2, 4, 1, 'REC-0028', '2026-07-07', 300.00, NULL),
(29, 2, 1, 1, 'REC-0029', '2026-08-08', 300.00, NULL),
(30, 3, 2, 1, 'REC-0030', '2026-09-09', 300.00, NULL),
(31, 2, 3, 1, 'REC-0031', '2026-04-10', 200.00, NULL),
(32, 2, 4, 2, 'REC-0032', '2026-05-11', 120.00, 'Pago parcial'),
(33, 3, 1, 1, 'REC-0033', '2026-06-12', 200.00, NULL),
(34, 2, 2, 1, 'REC-0034', '2026-07-13', 200.00, NULL),
(35, 2, 3, 1, 'REC-0035', '2026-08-07', 200.00, NULL),
(36, 3, 4, 1, 'REC-0036', '2026-09-08', 200.00, NULL),
(37, 2, 1, 1, 'REC-0037', '2026-04-09', 220.00, NULL),
(38, 2, 2, 1, 'REC-0038', '2026-05-10', 220.00, NULL),
(39, 3, 3, 1, 'REC-0039', '2026-06-11', 220.00, NULL),
(40, 2, 4, 2, 'REC-0040', '2026-07-12', 132.00, 'Pago parcial'),
(41, 2, 1, 1, 'REC-0041', '2026-08-13', 220.00, NULL),
(42, 3, 2, 1, 'REC-0042', '2026-09-07', 220.00, NULL),
(43, 2, 3, 1, 'REC-0043', '2026-04-08', 250.00, NULL),
(44, 2, 4, 1, 'REC-0044', '2026-05-09', 250.00, NULL),
(45, 3, 1, 1, 'REC-0045', '2026-06-10', 250.00, NULL),
(46, 2, 2, 1, 'REC-0046', '2026-07-11', 250.00, NULL),
(47, 2, 3, 1, 'REC-0047', '2026-08-12', 250.00, NULL),
(48, 3, 4, 2, 'REC-0048', '2026-09-13', 150.00, 'Pago parcial'),
(49, 2, 1, 1, 'REC-0049', '2026-04-07', 250.00, NULL),
(50, 2, 2, 1, 'REC-0050', '2026-05-08', 250.00, NULL),
(51, 3, 3, 1, 'REC-0051', '2026-06-09', 250.00, NULL),
(52, 2, 4, 1, 'REC-0052', '2026-07-10', 250.00, NULL),
(53, 2, 1, 1, 'REC-0053', '2026-08-11', 250.00, NULL),
(54, 3, 2, 1, 'REC-0054', '2026-09-12', 250.00, NULL),
(55, 2, 3, 1, 'REC-0055', '2026-04-13', 280.00, NULL),
(56, 2, 4, 2, 'REC-0056', '2026-05-07', 168.00, 'Pago parcial'),
(57, 3, 1, 1, 'REC-0057', '2026-06-08', 280.00, NULL),
(58, 2, 2, 1, 'REC-0058', '2026-07-09', 280.00, NULL),
(59, 2, 3, 1, 'REC-0059', '2026-08-10', 280.00, NULL),
(60, 3, 4, 1, 'REC-0060', '2026-09-11', 280.00, NULL),
(61, 2, 1, 1, 'REC-0061', '2026-04-12', 300.00, NULL),
(62, 2, 2, 1, 'REC-0062', '2026-05-13', 300.00, NULL),
(63, 3, 3, 1, 'REC-0063', '2026-06-07', 300.00, NULL),
(64, 2, 4, 2, 'REC-0064', '2026-07-08', 180.00, 'Pago parcial'),
(65, 2, 1, 1, 'REC-0065', '2026-08-09', 300.00, NULL),
(66, 3, 2, 1, 'REC-0066', '2026-09-10', 300.00, NULL),
(67, 2, 3, 1, 'REC-0067', '2026-04-11', 200.00, NULL),
(68, 2, 4, 1, 'REC-0068', '2026-05-12', 200.00, NULL),
(69, 3, 1, 1, 'REC-0069', '2026-06-13', 200.00, NULL),
(70, 2, 2, 1, 'REC-0070', '2026-07-07', 200.00, NULL),
(71, 2, 3, 1, 'REC-0071', '2026-08-08', 200.00, NULL),
(72, 3, 4, 2, 'REC-0072', '2026-09-09', 120.00, 'Pago parcial'),
(73, 2, 1, 1, 'REC-0073', '2026-04-10', 220.00, NULL),
(74, 2, 2, 1, 'REC-0074', '2026-05-11', 220.00, NULL),
(75, 3, 3, 1, 'REC-0075', '2026-06-12', 220.00, NULL),
(76, 2, 4, 1, 'REC-0076', '2026-07-13', 220.00, NULL),
(77, 2, 1, 1, 'REC-0077', '2026-08-07', 220.00, NULL),
(78, 3, 2, 1, 'REC-0078', '2026-09-08', 220.00, NULL),
(79, 2, 3, 1, 'REC-0079', '2026-04-09', 250.00, NULL),
(80, 2, 4, 2, 'REC-0080', '2026-05-10', 150.00, 'Pago parcial'),
(81, 3, 1, 1, 'REC-0081', '2026-06-11', 250.00, NULL),
(82, 2, 2, 1, 'REC-0082', '2026-07-12', 250.00, NULL),
(83, 2, 3, 1, 'REC-0083', '2026-08-13', 250.00, NULL),
(84, 3, 4, 1, 'REC-0084', '2026-09-07', 250.00, NULL),
(85, 2, 1, 1, 'REC-0085', '2026-04-08', 250.00, NULL),
(86, 2, 2, 1, 'REC-0086', '2026-05-09', 250.00, NULL),
(87, 3, 3, 1, 'REC-0087', '2026-06-10', 250.00, NULL),
(88, 2, 4, 2, 'REC-0088', '2026-07-11', 150.00, 'Pago parcial'),
(89, 2, 1, 1, 'REC-0089', '2026-08-12', 250.00, NULL),
(90, 3, 2, 1, 'REC-0090', '2026-09-13', 250.00, NULL),
(91, 2, 3, 1, 'REC-0091', '2026-04-07', 280.00, NULL),
(92, 2, 4, 1, 'REC-0092', '2026-05-08', 280.00, NULL),
(93, 3, 1, 1, 'REC-0093', '2026-06-09', 280.00, NULL),
(94, 2, 2, 1, 'REC-0094', '2026-07-10', 280.00, NULL),
(95, 2, 3, 1, 'REC-0095', '2026-08-11', 280.00, NULL),
(96, 3, 4, 2, 'REC-0096', '2026-09-12', 168.00, 'Pago parcial'),
(97, 2, 1, 1, 'REC-0097', '2026-04-13', 300.00, NULL),
(98, 2, 2, 1, 'REC-0098', '2026-05-07', 300.00, NULL),
(99, 3, 3, 1, 'REC-0099', '2026-06-08', 300.00, NULL),
(100, 2, 4, 1, 'REC-0100', '2026-07-09', 300.00, NULL);
GO

INSERT INTO PAGO (id_mensualidad, id_usuario, id_metodo_pago, id_estado_pago, numero_recibo, fecha_pago, monto, observaciones) VALUES
(101, 2, 1, 1, 'REC-0101', '2026-08-10', 300.00, NULL),
(102, 3, 2, 1, 'REC-0102', '2026-09-11', 300.00, NULL),
(103, 2, 3, 1, 'REC-0103', '2026-04-12', 200.00, NULL),
(104, 2, 4, 2, 'REC-0104', '2026-05-13', 120.00, 'Pago parcial'),
(105, 3, 1, 1, 'REC-0105', '2026-06-07', 200.00, NULL),
(106, 2, 2, 1, 'REC-0106', '2026-07-08', 200.00, NULL),
(107, 2, 3, 1, 'REC-0107', '2026-08-09', 200.00, NULL),
(108, 3, 4, 1, 'REC-0108', '2026-09-10', 200.00, NULL),
(109, 2, 1, 1, 'REC-0109', '2026-04-11', 220.00, NULL),
(110, 2, 2, 1, 'REC-0110', '2026-05-12', 220.00, NULL),
(111, 3, 3, 1, 'REC-0111', '2026-06-13', 220.00, NULL),
(112, 2, 4, 2, 'REC-0112', '2026-07-07', 132.00, 'Pago parcial'),
(113, 2, 1, 1, 'REC-0113', '2026-08-08', 220.00, NULL),
(114, 3, 2, 1, 'REC-0114', '2026-09-09', 220.00, NULL),
(115, 2, 3, 1, 'REC-0115', '2026-04-10', 250.00, NULL),
(116, 2, 4, 1, 'REC-0116', '2026-05-11', 250.00, NULL),
(117, 3, 1, 1, 'REC-0117', '2026-06-12', 250.00, NULL),
(118, 2, 2, 1, 'REC-0118', '2026-07-13', 250.00, NULL),
(119, 2, 3, 1, 'REC-0119', '2026-08-07', 250.00, NULL),
(120, 3, 4, 2, 'REC-0120', '2026-09-08', 150.00, 'Pago parcial'),
(121, 2, 1, 1, 'REC-0121', '2026-04-09', 250.00, NULL),
(122, 2, 2, 1, 'REC-0122', '2026-05-10', 250.00, NULL),
(123, 3, 3, 1, 'REC-0123', '2026-06-11', 250.00, NULL),
(124, 2, 4, 1, 'REC-0124', '2026-07-12', 250.00, NULL),
(125, 2, 1, 1, 'REC-0125', '2026-08-13', 250.00, NULL),
(126, 3, 2, 1, 'REC-0126', '2026-09-07', 250.00, NULL),
(127, 2, 3, 1, 'REC-0127', '2026-04-08', 280.00, NULL),
(128, 2, 4, 2, 'REC-0128', '2026-05-09', 168.00, 'Pago parcial'),
(129, 3, 1, 1, 'REC-0129', '2026-06-10', 280.00, NULL),
(130, 2, 2, 1, 'REC-0130', '2026-07-11', 280.00, NULL),
(131, 2, 3, 1, 'REC-0131', '2026-08-12', 280.00, NULL),
(132, 3, 4, 1, 'REC-0132', '2026-09-13', 280.00, NULL),
(133, 2, 1, 1, 'REC-0133', '2026-04-07', 300.00, NULL),
(134, 2, 2, 1, 'REC-0134', '2026-05-08', 300.00, NULL),
(135, 3, 3, 1, 'REC-0135', '2026-06-09', 300.00, NULL),
(136, 2, 4, 2, 'REC-0136', '2026-07-10', 180.00, 'Pago parcial'),
(137, 2, 1, 1, 'REC-0137', '2026-08-11', 300.00, NULL),
(138, 3, 2, 1, 'REC-0138', '2026-09-12', 300.00, NULL),
(139, 2, 3, 1, 'REC-0139', '2026-04-13', 200.00, NULL),
(140, 2, 4, 1, 'REC-0140', '2026-05-07', 200.00, NULL),
(141, 3, 1, 1, 'REC-0141', '2026-06-08', 200.00, NULL),
(142, 2, 2, 1, 'REC-0142', '2026-07-09', 200.00, NULL),
(143, 2, 3, 1, 'REC-0143', '2026-08-10', 200.00, NULL),
(144, 3, 4, 2, 'REC-0144', '2026-09-11', 120.00, 'Pago parcial'),
(145, 2, 1, 1, 'REC-0145', '2026-04-12', 220.00, NULL),
(146, 2, 2, 1, 'REC-0146', '2026-05-13', 220.00, NULL),
(147, 3, 3, 1, 'REC-0147', '2026-06-07', 220.00, NULL),
(148, 2, 4, 1, 'REC-0148', '2026-07-08', 220.00, NULL),
(149, 2, 1, 1, 'REC-0149', '2026-08-09', 220.00, NULL),
(150, 3, 2, 1, 'REC-0150', '2026-09-10', 220.00, NULL),
(151, 2, 3, 1, 'REC-0151', '2026-04-11', 250.00, NULL),
(152, 2, 4, 2, 'REC-0152', '2026-05-12', 150.00, 'Pago parcial'),
(153, 3, 1, 1, 'REC-0153', '2026-06-13', 250.00, NULL),
(154, 2, 2, 1, 'REC-0154', '2026-07-07', 250.00, NULL),
(155, 2, 3, 1, 'REC-0155', '2026-08-08', 250.00, NULL),
(156, 3, 4, 1, 'REC-0156', '2026-09-09', 250.00, NULL),
(157, 2, 1, 1, 'REC-0157', '2026-04-10', 250.00, NULL),
(158, 2, 2, 1, 'REC-0158', '2026-05-11', 250.00, NULL),
(159, 3, 3, 1, 'REC-0159', '2026-06-12', 250.00, NULL),
(160, 2, 4, 2, 'REC-0160', '2026-07-13', 150.00, 'Pago parcial'),
(161, 2, 1, 1, 'REC-0161', '2026-08-07', 250.00, NULL),
(162, 3, 2, 1, 'REC-0162', '2026-09-08', 250.00, NULL),
(163, 2, 3, 1, 'REC-0163', '2026-04-09', 280.00, NULL),
(164, 2, 4, 1, 'REC-0164', '2026-05-10', 280.00, NULL),
(165, 3, 1, 1, 'REC-0165', '2026-06-11', 280.00, NULL),
(166, 2, 2, 1, 'REC-0166', '2026-07-12', 280.00, NULL),
(167, 2, 3, 1, 'REC-0167', '2026-08-13', 280.00, NULL),
(168, 3, 4, 2, 'REC-0168', '2026-09-07', 168.00, 'Pago parcial'),
(169, 2, 1, 1, 'REC-0169', '2026-04-08', 300.00, NULL),
(170, 2, 2, 1, 'REC-0170', '2026-05-09', 300.00, NULL),
(171, 3, 3, 1, 'REC-0171', '2026-06-10', 300.00, NULL),
(172, 2, 4, 1, 'REC-0172', '2026-07-11', 300.00, NULL),
(173, 2, 1, 1, 'REC-0173', '2026-08-12', 300.00, NULL),
(174, 3, 2, 1, 'REC-0174', '2026-09-13', 300.00, NULL),
(175, 2, 3, 1, 'REC-0175', '2026-04-07', 200.00, NULL),
(176, 2, 4, 2, 'REC-0176', '2026-05-08', 120.00, 'Pago parcial'),
(177, 3, 1, 1, 'REC-0177', '2026-06-09', 200.00, NULL),
(178, 2, 2, 1, 'REC-0178', '2026-07-10', 200.00, NULL),
(179, 2, 3, 1, 'REC-0179', '2026-08-11', 200.00, NULL),
(180, 3, 4, 1, 'REC-0180', '2026-09-12', 200.00, NULL),
(181, 2, 1, 1, 'REC-0181', '2026-04-13', 220.00, NULL),
(182, 2, 2, 1, 'REC-0182', '2026-05-07', 220.00, NULL),
(183, 3, 3, 1, 'REC-0183', '2026-06-08', 220.00, NULL),
(184, 2, 4, 2, 'REC-0184', '2026-07-09', 132.00, 'Pago parcial'),
(185, 2, 1, 1, 'REC-0185', '2026-08-10', 220.00, NULL),
(186, 3, 2, 1, 'REC-0186', '2026-09-11', 220.00, NULL),
(187, 2, 3, 1, 'REC-0187', '2026-04-12', 250.00, NULL),
(188, 2, 4, 1, 'REC-0188', '2026-05-13', 250.00, NULL),
(189, 3, 1, 1, 'REC-0189', '2026-06-07', 250.00, NULL),
(190, 2, 2, 1, 'REC-0190', '2026-07-08', 250.00, NULL),
(191, 2, 3, 1, 'REC-0191', '2026-08-09', 250.00, NULL),
(192, 3, 4, 2, 'REC-0192', '2026-09-10', 150.00, 'Pago parcial'),
(193, 2, 1, 1, 'REC-0193', '2026-04-11', 250.00, NULL),
(194, 2, 2, 1, 'REC-0194', '2026-05-12', 250.00, NULL),
(195, 3, 3, 1, 'REC-0195', '2026-06-13', 250.00, NULL),
(196, 2, 4, 1, 'REC-0196', '2026-07-07', 250.00, NULL),
(197, 2, 1, 1, 'REC-0197', '2026-08-08', 250.00, NULL),
(198, 3, 2, 1, 'REC-0198', '2026-09-09', 250.00, NULL),
(199, 2, 3, 1, 'REC-0199', '2026-04-10', 280.00, NULL),
(200, 2, 4, 2, 'REC-0200', '2026-05-11', 168.00, 'Pago parcial');
GO

INSERT INTO PAGO (id_mensualidad, id_usuario, id_metodo_pago, id_estado_pago, numero_recibo, fecha_pago, monto, observaciones) VALUES
(201, 3, 1, 1, 'REC-0201', '2026-06-12', 280.00, NULL),
(202, 2, 2, 1, 'REC-0202', '2026-07-13', 280.00, NULL),
(203, 2, 3, 1, 'REC-0203', '2026-08-07', 280.00, NULL),
(204, 3, 4, 1, 'REC-0204', '2026-09-08', 280.00, NULL),
(205, 2, 1, 1, 'REC-0205', '2026-04-09', 300.00, NULL),
(206, 2, 2, 1, 'REC-0206', '2026-05-10', 300.00, NULL),
(207, 3, 3, 1, 'REC-0207', '2026-06-11', 300.00, NULL),
(208, 2, 4, 2, 'REC-0208', '2026-07-12', 180.00, 'Pago parcial'),
(209, 2, 1, 1, 'REC-0209', '2026-08-13', 300.00, NULL),
(210, 3, 2, 1, 'REC-0210', '2026-09-07', 300.00, NULL),
(211, 2, 3, 1, 'REC-0211', '2026-04-08', 200.00, NULL),
(212, 2, 4, 1, 'REC-0212', '2026-05-09', 200.00, NULL),
(213, 3, 1, 1, 'REC-0213', '2026-06-10', 200.00, NULL),
(214, 2, 2, 1, 'REC-0214', '2026-07-11', 200.00, NULL),
(215, 2, 3, 1, 'REC-0215', '2026-08-12', 200.00, NULL),
(216, 3, 4, 2, 'REC-0216', '2026-09-13', 120.00, 'Pago parcial'),
(217, 2, 1, 1, 'REC-0217', '2026-04-07', 220.00, NULL),
(218, 2, 2, 1, 'REC-0218', '2026-05-08', 220.00, NULL),
(219, 3, 3, 1, 'REC-0219', '2026-06-09', 220.00, NULL),
(220, 2, 4, 1, 'REC-0220', '2026-07-10', 220.00, NULL),
(221, 2, 1, 1, 'REC-0221', '2026-08-11', 220.00, NULL),
(222, 3, 2, 1, 'REC-0222', '2026-09-12', 220.00, NULL),
(223, 2, 3, 1, 'REC-0223', '2026-04-13', 250.00, NULL),
(224, 2, 4, 2, 'REC-0224', '2026-05-07', 150.00, 'Pago parcial'),
(225, 3, 1, 1, 'REC-0225', '2026-06-08', 250.00, NULL),
(226, 2, 2, 1, 'REC-0226', '2026-07-09', 250.00, NULL),
(227, 2, 3, 1, 'REC-0227', '2026-08-10', 250.00, NULL),
(228, 3, 4, 1, 'REC-0228', '2026-09-11', 250.00, NULL),
(229, 2, 1, 1, 'REC-0229', '2026-04-12', 250.00, NULL),
(230, 2, 2, 1, 'REC-0230', '2026-05-13', 250.00, NULL),
(231, 3, 3, 1, 'REC-0231', '2026-06-07', 250.00, NULL),
(232, 2, 4, 2, 'REC-0232', '2026-07-08', 150.00, 'Pago parcial'),
(233, 2, 1, 1, 'REC-0233', '2026-08-09', 250.00, NULL),
(234, 3, 2, 1, 'REC-0234', '2026-09-10', 250.00, NULL),
(235, 2, 3, 1, 'REC-0235', '2026-04-11', 280.00, NULL),
(236, 2, 4, 1, 'REC-0236', '2026-05-12', 280.00, NULL),
(237, 3, 1, 1, 'REC-0237', '2026-06-13', 280.00, NULL),
(238, 2, 2, 1, 'REC-0238', '2026-07-07', 280.00, NULL),
(239, 2, 3, 1, 'REC-0239', '2026-08-08', 280.00, NULL),
(240, 3, 4, 2, 'REC-0240', '2026-09-09', 168.00, 'Pago parcial'),
(241, 2, 1, 1, 'REC-0241', '2026-04-10', 300.00, NULL),
(242, 2, 2, 1, 'REC-0242', '2026-05-11', 300.00, NULL),
(243, 3, 3, 1, 'REC-0243', '2026-06-12', 300.00, NULL),
(244, 2, 4, 1, 'REC-0244', '2026-07-13', 300.00, NULL),
(245, 2, 1, 1, 'REC-0245', '2026-08-07', 300.00, NULL),
(246, 3, 2, 1, 'REC-0246', '2026-09-08', 300.00, NULL),
(247, 2, 3, 1, 'REC-0247', '2026-04-09', 200.00, NULL),
(248, 2, 4, 2, 'REC-0248', '2026-05-10', 120.00, 'Pago parcial'),
(249, 3, 1, 1, 'REC-0249', '2026-06-11', 200.00, NULL),
(250, 2, 2, 1, 'REC-0250', '2026-07-12', 200.00, NULL),
(251, 2, 3, 1, 'REC-0251', '2026-08-13', 200.00, NULL),
(252, 3, 4, 1, 'REC-0252', '2026-09-07', 200.00, NULL),
(253, 2, 1, 1, 'REC-0253', '2026-04-08', 220.00, NULL),
(254, 2, 2, 1, 'REC-0254', '2026-05-09', 220.00, NULL),
(255, 3, 3, 1, 'REC-0255', '2026-06-10', 220.00, NULL),
(256, 2, 4, 2, 'REC-0256', '2026-07-11', 132.00, 'Pago parcial'),
(257, 2, 1, 1, 'REC-0257', '2026-08-12', 220.00, NULL),
(258, 3, 2, 1, 'REC-0258', '2026-09-13', 220.00, NULL),
(259, 2, 3, 1, 'REC-0259', '2026-04-07', 250.00, NULL),
(260, 2, 4, 1, 'REC-0260', '2026-05-08', 250.00, NULL),
(261, 3, 1, 1, 'REC-0261', '2026-06-09', 250.00, NULL),
(262, 2, 2, 1, 'REC-0262', '2026-07-10', 250.00, NULL),
(263, 2, 3, 1, 'REC-0263', '2026-08-11', 250.00, NULL),
(264, 3, 4, 2, 'REC-0264', '2026-09-12', 150.00, 'Pago parcial'),
(265, 2, 1, 1, 'REC-0265', '2026-04-13', 250.00, NULL),
(266, 2, 2, 1, 'REC-0266', '2026-05-07', 250.00, NULL),
(267, 3, 3, 1, 'REC-0267', '2026-06-08', 250.00, NULL),
(268, 2, 4, 1, 'REC-0268', '2026-07-09', 250.00, NULL),
(269, 2, 1, 1, 'REC-0269', '2026-08-10', 250.00, NULL),
(270, 3, 2, 1, 'REC-0270', '2026-09-11', 250.00, NULL),
(271, 2, 3, 1, 'REC-0271', '2026-04-12', 280.00, NULL),
(272, 2, 4, 2, 'REC-0272', '2026-05-13', 168.00, 'Pago parcial'),
(273, 3, 1, 1, 'REC-0273', '2026-06-07', 280.00, NULL),
(274, 2, 2, 1, 'REC-0274', '2026-07-08', 280.00, NULL),
(275, 2, 3, 1, 'REC-0275', '2026-08-09', 280.00, NULL),
(276, 3, 4, 1, 'REC-0276', '2026-09-10', 280.00, NULL),
(277, 2, 1, 1, 'REC-0277', '2026-04-11', 300.00, NULL),
(278, 2, 2, 1, 'REC-0278', '2026-05-12', 300.00, NULL),
(279, 3, 3, 1, 'REC-0279', '2026-06-13', 300.00, NULL),
(280, 2, 4, 2, 'REC-0280', '2026-07-07', 180.00, 'Pago parcial'),
(281, 2, 1, 1, 'REC-0281', '2026-08-08', 300.00, NULL),
(282, 3, 2, 1, 'REC-0282', '2026-09-09', 300.00, NULL),
(283, 2, 3, 1, 'REC-0283', '2026-04-10', 200.00, NULL),
(284, 2, 4, 1, 'REC-0284', '2026-05-11', 200.00, NULL),
(285, 3, 1, 1, 'REC-0285', '2026-06-12', 200.00, NULL),
(286, 2, 2, 1, 'REC-0286', '2026-07-13', 200.00, NULL),
(287, 2, 3, 1, 'REC-0287', '2026-08-07', 200.00, NULL),
(288, 3, 4, 2, 'REC-0288', '2026-09-08', 120.00, 'Pago parcial'),
(289, 2, 1, 1, 'REC-0289', '2026-04-09', 220.00, NULL),
(290, 2, 2, 1, 'REC-0290', '2026-05-10', 220.00, NULL),
(291, 3, 3, 1, 'REC-0291', '2026-06-11', 220.00, NULL),
(292, 2, 4, 1, 'REC-0292', '2026-07-12', 220.00, NULL),
(293, 2, 1, 1, 'REC-0293', '2026-08-13', 220.00, NULL),
(294, 3, 2, 1, 'REC-0294', '2026-09-07', 220.00, NULL),
(295, 2, 3, 1, 'REC-0295', '2026-04-08', 250.00, NULL),
(296, 2, 4, 2, 'REC-0296', '2026-05-09', 150.00, 'Pago parcial'),
(297, 3, 1, 1, 'REC-0297', '2026-06-10', 250.00, NULL),
(298, 2, 2, 1, 'REC-0298', '2026-07-11', 250.00, NULL),
(299, 2, 3, 1, 'REC-0299', '2026-08-12', 250.00, NULL),
(300, 3, 4, 1, 'REC-0300', '2026-09-13', 250.00, NULL);
GO

/* ============================================================
   VERIFICACION: conteo de filas por tabla
   Esperado: ROL=3, USUARIO=3, TUTOR=25, ENTRENADOR=6,
   CATEGORIA=5, GRUPO=6, HORARIO=12, ALUMNO=50, INSCRIPCION=50,
   MENSUALIDAD=300, METODO_PAGO=4, ESTADO_PAGO=3, PAGO=300,
   AUDITORIA_PAGO=0
   ============================================================ */
SELECT 'ROL' AS Tabla, COUNT(*) AS Total FROM ROL
UNION ALL SELECT 'USUARIO', COUNT(*) FROM USUARIO
UNION ALL SELECT 'TUTOR', COUNT(*) FROM TUTOR
UNION ALL SELECT 'ENTRENADOR', COUNT(*) FROM ENTRENADOR
UNION ALL SELECT 'CATEGORIA', COUNT(*) FROM CATEGORIA
UNION ALL SELECT 'GRUPO', COUNT(*) FROM GRUPO
UNION ALL SELECT 'HORARIO', COUNT(*) FROM HORARIO
UNION ALL SELECT 'ALUMNO', COUNT(*) FROM ALUMNO
UNION ALL SELECT 'INSCRIPCION', COUNT(*) FROM INSCRIPCION
UNION ALL SELECT 'MENSUALIDAD', COUNT(*) FROM MENSUALIDAD
UNION ALL SELECT 'METODO_PAGO', COUNT(*) FROM METODO_PAGO
UNION ALL SELECT 'ESTADO_PAGO', COUNT(*) FROM ESTADO_PAGO
UNION ALL SELECT 'PAGO', COUNT(*) FROM PAGO
UNION ALL SELECT 'AUDITORIA_PAGO', COUNT(*) FROM AUDITORIA_PAGO;
GO
