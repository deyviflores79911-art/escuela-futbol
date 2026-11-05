/* ============================================================
   DATA WAREHOUSE: DW_EscuelasDeportivas
   Esquema estrella para UNA SOLA escuela de futbol (un unico
   cliente). Por eso no hay D_ESCUELA: al ser una sola, no
   aporta nada como dimension analitica (siempre seria 1 fila
   y no filtrarias ni compararias nada con ella).

   GRANO DEL HECHO: un registro de H_PAGOS = un pago (fila de
   la tabla transaccional PAGO), no una mensualidad ni una
   inscripcion. Asi cada pago recibido (incluidos los parciales)
   queda como un evento independiente.

   ORIGEN DE CADA COLUMNA (para el Origen OLE DB en SSIS):
   PAGO
     -> MENSUALIDAD -> INSCRIPCION -> GRUPO -> CATEGORIA  => D_CATEGORIA
                     -> INSCRIPCION -> ALUMNO              => D_ALUMNO
     -> METODO_PAGO                                        => D_METODO_PAGO
     -> ESTADO_PAGO                                         => D_ESTADO_PAGO
     -> fecha_pago                                          => D_TIEMPO
   ============================================================ */

IF DB_ID('DW_EscuelasDeportivas') IS NOT NULL
BEGIN
    ALTER DATABASE DW_EscuelasDeportivas SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE DW_EscuelasDeportivas;
END
GO

CREATE DATABASE DW_EscuelasDeportivas;
GO

USE DW_EscuelasDeportivas;
GO

/* ---------- D_ALUMNO ---------- */
CREATE TABLE D_ALUMNO (
    id_alumno        INT           NOT NULL,
    codigo_alumno    NVARCHAR(20)  NULL,
    nombre_alumno    NVARCHAR(100) NOT NULL,
    apellido_alumno  NVARCHAR(100) NULL,
    sexo             NVARCHAR(10)  NULL,
    fecha_nacimiento DATE          NULL,
    estado_alumno    NVARCHAR(20)  NULL,
    CONSTRAINT PK_D_ALUMNO PRIMARY KEY (id_alumno)
);
GO

/* ---------- D_CATEGORIA ---------- */
CREATE TABLE D_CATEGORIA (
    id_categoria     INT           NOT NULL,
    nombre_categoria NVARCHAR(50)  NOT NULL,
    edad_minima      INT           NULL,
    edad_maxima      INT           NULL,
    CONSTRAINT PK_D_CATEGORIA PRIMARY KEY (id_categoria)
);
GO

/* ---------- D_METODO_PAGO ---------- */
CREATE TABLE D_METODO_PAGO (
    id_metodo_pago     INT          NOT NULL,
    nombre_metodo_pago NVARCHAR(50) NOT NULL,
    CONSTRAINT PK_D_METODO_PAGO PRIMARY KEY (id_metodo_pago)
);
GO

/* ---------- D_ESTADO_PAGO ---------- */
CREATE TABLE D_ESTADO_PAGO (
    id_estado_pago     INT          NOT NULL,
    nombre_estado_pago NVARCHAR(50) NOT NULL,
    CONSTRAINT PK_D_ESTADO_PAGO PRIMARY KEY (id_estado_pago)
);
GO

/* ---------- D_TIEMPO ---------- */
CREATE TABLE D_TIEMPO (
    id_tiempo  INT IDENTITY(1,1) NOT NULL,
    fecha      DATE         NOT NULL,
    dia        INT          NOT NULL,
    mes        INT          NOT NULL,
    nombre_mes NVARCHAR(20) NULL,
    trimestre  INT          NOT NULL,
    anio       INT          NOT NULL,
    CONSTRAINT PK_D_TIEMPO PRIMARY KEY (id_tiempo)
);
GO

/* ---------- H_PAGOS ---------- */
CREATE TABLE H_PAGOS (
    id_hecho          INT IDENTITY(1,1) NOT NULL,
    id_alumno         INT NOT NULL,
    id_categoria      INT NOT NULL,
    id_metodo_pago    INT NOT NULL,
    id_estado_pago    INT NOT NULL,
    id_tiempo         INT NOT NULL,
    numero_recibo     NVARCHAR(30)  NULL,
    monto_mensualidad DECIMAL(10,2) NULL,  -- lo que se debia ese mes
    monto_pagado      DECIMAL(10,2) NOT NULL,
    saldo_pendiente   DECIMAL(10,2) NULL,  -- monto_mensualidad - suma pagada a la fecha
    dias_atraso       INT NULL,            -- fecha_pago - fecha_vencimiento (si es > 0)
    pago_atrasado     BIT NULL,            -- 1 si dias_atraso > 0
    CONSTRAINT PK_H_PAGOS PRIMARY KEY (id_hecho),
    CONSTRAINT FK_HP_ALUMNO FOREIGN KEY (id_alumno) REFERENCES D_ALUMNO (id_alumno),
    CONSTRAINT FK_HP_CATEGORIA FOREIGN KEY (id_categoria) REFERENCES D_CATEGORIA (id_categoria),
    CONSTRAINT FK_HP_METODO FOREIGN KEY (id_metodo_pago) REFERENCES D_METODO_PAGO (id_metodo_pago),
    CONSTRAINT FK_HP_ESTADO FOREIGN KEY (id_estado_pago) REFERENCES D_ESTADO_PAGO (id_estado_pago),
    CONSTRAINT FK_HP_TIEMPO FOREIGN KEY (id_tiempo) REFERENCES D_TIEMPO (id_tiempo)
);
GO

/* Verificacion: deberian aparecer 5 tablas */
SELECT TABLE_NAME
FROM DW_EscuelasDeportivas.INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
GO
