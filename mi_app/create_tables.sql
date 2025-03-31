-- Crear tabla de pedidos
CREATE TABLE IF NOT EXISTS public.pedidos (
    id SERIAL PRIMARY KEY,
    cliente VARCHAR(255) NOT NULL,
    fecha DATE NOT NULL,
    brs DECIMAL(15,2) NOT NULL,
    tasa DECIMAL(15,6) NOT NULL,
    clp DECIMAL(15,2) NOT NULL,
    usuario VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear tabla de deuda_anterior
CREATE TABLE IF NOT EXISTS public.deuda_anterior (
    id SERIAL PRIMARY KEY,
    cliente VARCHAR(255) NOT NULL,
    deuda DECIMAL(15,2) NOT NULL,
    fecha DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear tabla de pagos_procesados
CREATE TABLE IF NOT EXISTS public.pagos_procesados (
    id SERIAL PRIMARY KEY,
    transferencia_id INTEGER NOT NULL,
    hash VARCHAR(255) NOT NULL UNIQUE,
    fecha_procesada DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear tabla de compras
CREATE TABLE IF NOT EXISTS public.compras (
    id SERIAL PRIMARY KEY,
    totalprice DECIMAL(15,2) NOT NULL,
    unitprice DECIMAL(15,6) NOT NULL,
    tradetype VARCHAR(10) NOT NULL,
    fiat VARCHAR(10) NOT NULL,
    asset VARCHAR(10) NOT NULL,
    amount DECIMAL(15,6) NOT NULL,
    costo_real DECIMAL(15,6) NOT NULL,
    commission DECIMAL(15,6) NOT NULL,
    paymethodname VARCHAR(50) NOT NULL,
    createtime TIMESTAMP WITH TIME ZONE NOT NULL,
    orderstatus VARCHAR(20) NOT NULL,
    ordernumber VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear tabla de pedidos_log
CREATE TABLE IF NOT EXISTS public.pedidos_log (
    id SERIAL PRIMARY KEY,
    pedido_id INTEGER NOT NULL,
    usuario VARCHAR(255) NOT NULL,
    cambios TEXT NOT NULL,
    fecha TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear tabla de pagadores
CREATE TABLE IF NOT EXISTS public.pagadores (
    id SERIAL PRIMARY KEY,
    cliente VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear vista para compras FIFO
CREATE OR REPLACE VIEW public.vista_compras_fifo AS
WITH compras_ordenadas AS (
    SELECT 
        id,
        totalprice,
        unitprice,
        amount,
        createtime,
        fiat,
        tradetype,
        SUM(amount) OVER (ORDER BY createtime) as stock_acumulado,
        SUM(totalprice) OVER (ORDER BY createtime) as costo_acumulado
    FROM public.compras
    WHERE fiat = 'VES' AND tradetype = 'BUY'
),
costos_promedio AS (
    SELECT 
        id,
        totalprice,
        unitprice,
        amount,
        createtime,
        fiat,
        tradetype,
        stock_acumulado,
        costo_acumulado,
        CASE 
            WHEN stock_acumulado > 0 THEN costo_acumulado / stock_acumulado
            ELSE 0
        END as costo_promedio
    FROM compras_ordenadas
)
SELECT 
    id,
    totalprice,
    unitprice,
    amount,
    createtime,
    fiat,
    tradetype,
    stock_acumulado as stock_usdt,
    costo_promedio as costo_no_vendido
FROM costos_promedio;

-- Crear índices para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_pedidos_cliente ON public.pedidos(cliente);
CREATE INDEX IF NOT EXISTS idx_pedidos_fecha ON public.pedidos(fecha);
CREATE INDEX IF NOT EXISTS idx_deuda_anterior_cliente ON public.deuda_anterior(cliente);
CREATE INDEX IF NOT EXISTS idx_deuda_anterior_fecha ON public.deuda_anterior(fecha);
CREATE INDEX IF NOT EXISTS idx_compras_createtime ON public.compras(createtime);
CREATE INDEX IF NOT EXISTS idx_compras_fiat ON public.compras(fiat);
CREATE INDEX IF NOT EXISTS idx_compras_tradetype ON public.compras(tradetype); 