from supabase import create_client, Client
from datetime import datetime, timedelta

# Credenciales del entorno de pruebas
SUPABASE_URL = "https://tmimwpzxmtezopieqzcl.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRtaW13cHp4bXRlem9waWVxemNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzY4NTI5NzQsImV4cCI6MjA1MjQyODk3NH0."
    "tTrdPaiPAkQbF_JlfOOWTQwSs3C_zBbFDZECYzPP-Ho"
)

# Definir la fecha de filtro para todos los cálculos
fecha_filtro = "2025-02-14"
fecha_obj = datetime.strptime(fecha_filtro, "%Y-%m-%d").date()

# Variable para los BRS restantes del día anterior (modifícala según corresponda)
brs_restantes_dia_anterior = 0


def calcular_pedidos():
    """
    Para la tabla 'pedidos' (filtrando por fecha = fecha_filtro y excluyendo cliente DETAL):
      - brs_vendidos: suma de la columna 'brs'
      - tasa_compra_ponderada: sum((brs / brs_vendidos) * tasa) / 1,000,000
      - venta_en_clp: suma de la columna 'clp'
    """
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    # Se excluyen filas donde el cliente sea "DETAL"
    response = (
        supabase.table("pedidos")
        .select("*")
        .eq("fecha", fecha_filtro)
        .neq("cliente", "DETAL")
        .execute()
    )
    if response.data is None or len(response.data) == 0:
        print("No se obtuvieron datos para el día", fecha_filtro, "en la tabla 'pedidos'")
        return None

    rows = response.data
    brs_vendidos = sum(row.get("brs", 0) for row in rows)

    if brs_vendidos != 0:
        suma_operaciones = sum(
            (row.get("brs", 0) / brs_vendidos) * row.get("tasa", 0) for row in rows
        )
        tasa_compra_ponderada = suma_operaciones / 1_000_000
    else:
        tasa_compra_ponderada = None

    venta_en_clp = sum(row.get("clp", 0) for row in rows)

    print("Resultados para la tabla 'pedidos' en el día", fecha_filtro)
    print(f"brs_vendidos: {int(brs_vendidos):,}")
    if tasa_compra_ponderada is not None:
        print(f"tasa_compra_ponderada: {tasa_compra_ponderada:.6f}")
    else:
        print("tasa_compra_ponderada: No aplica")
    print(f"venta_en_clp: {int(venta_en_clp):,}")
    print("-" * 40)

    return {
        "brs_vendidos": brs_vendidos,
        "tasa_compra_ponderada": tasa_compra_ponderada,
        "venta_en_clp": venta_en_clp,
    }


def calcular_compras_ves():
    """
    Para la tabla 'compras' filtrando por fiat = 'VES' y por createtime en el día fecha_filtro:
      - usdt_vendidos: suma de la columna 'costo_real'
      - tasa_ponderada_venta_usdt: sum((costo_real / usdt_vendidos) * tasa)
      - brs_comprados: suma de la columna 'totalprice'
    """
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    fecha_inicio = f"{fecha_filtro}T00:00:00"
    fecha_fin = (
        datetime.strptime(fecha_filtro, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%dT00:00:00")

    response = (
        supabase.table("compras")
        .select("*")
        .eq("fiat", "VES")
        .gte("createtime", fecha_inicio)
        .lt("createtime", fecha_fin)
        .execute()
    )

    if response.data is None or len(response.data) == 0:
        print(
            "No se obtuvieron datos para fiat = VES y createtime entre",
            fecha_inicio,
            "y",
            fecha_fin,
            "en la tabla 'compras'",
        )
        return None

    rows = response.data
    usdt_vendidos = sum(row.get("costo_real", 0) for row in rows)
    if usdt_vendidos != 0:
        tasa_ponderada_venta_usdt = sum(
            (row.get("costo_real", 0) / usdt_vendidos) * row.get("tasa", 0)
            for row in rows
        )
    else:
        tasa_ponderada_venta_usdt = None

    brs_comprados = sum(row.get("totalprice", 0) for row in rows)

    print("Resultados para la tabla 'compras' con fiat = VES y createtime en el día", fecha_filtro)
    print(f"usdt_vendidos: {int(usdt_vendidos):,}")
    if tasa_ponderada_venta_usdt is not None:
        print(f"tasa_ponderada_venta_usdt: {tasa_ponderada_venta_usdt:.6f}")
    else:
        print("tasa_ponderada_venta_usdt: No aplica")
    print(f"brs_comprados: {int(brs_comprados):,}")
    print("-" * 40)

    return {
        "usdt_vendidos": usdt_vendidos,
        "tasa_ponderada_venta_usdt": tasa_ponderada_venta_usdt,
        "brs_comprados": brs_comprados,
    }


def calcular_compras_clp():
    """
    Para la tabla 'compras' filtrando por fiat = 'CLP' y por createtime en el día fecha_filtro:
      - usdt_comprados: suma de la columna 'amount'
      - tasa_ponderada_usdt_clp: se calcula a partir de la suma de "totalprice" y "amount"

    Nota: A partir de ahora, el valor de total_clp_invertido se calculará en main utilizando la fórmula:
          total_clp_invertido = usdt_vendidos (de FIAT=VES) * tasa_ponderada_usdt_clp
    """
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    fecha_inicio = f"{fecha_filtro}T00:00:00"
    fecha_fin = (
        datetime.strptime(fecha_filtro, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%dT00:00:00")

    response = (
        supabase.table("compras")
        .select("*")
        .eq("fiat", "CLP")
        .gte("createtime", fecha_inicio)
        .lt("createtime", fecha_fin)
        .execute()
    )

    if response.data is None or len(response.data) == 0:
        print(
            "No se obtuvieron datos para fiat = CLP y createtime entre",
            fecha_inicio,
            "y",
            fecha_fin,
            "en la tabla 'compras'",
        )
        return None

    rows = response.data
    # Se calcula el total original para obtener la tasa ponderada,
    # aunque no se utilizará directamente para total_clp_invertido
    total_clp_invertido_original = sum(row.get("totalprice", 0) for row in rows)
    usdt_comprados = sum(row.get("amount", 0) for row in rows)
    if usdt_comprados != 0:
        tasa_ponderada_usdt_clp = total_clp_invertido_original / usdt_comprados
    else:
        tasa_ponderada_usdt_clp = None

    print("Resultados para la tabla 'compras' con fiat = CLP y createtime en el día", fecha_filtro)
    print(f"usdt_comprados: {int(usdt_comprados):,}")
    if tasa_ponderada_usdt_clp is not None:
        print(f"tasa_ponderada_usdt_clp: {tasa_ponderada_usdt_clp:.6f}")
    else:
        print("tasa_ponderada_usdt_clp: No aplica")
    print("-" * 40)

    return {
        "usdt_comprados": usdt_comprados,
        "tasa_ponderada_usdt_clp": tasa_ponderada_usdt_clp,
    }


def insertar_resultados(resultados):
    """
    Inserta los resultados en la tabla 'margen' de Supabase.
    La columna 'fecha' es llave única.
    """
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    response = supabase.table("margen").insert(resultados).execute()
    if response.data:
        print("Resultados insertados correctamente en la tabla 'margen'.")
    else:
        print("Error al insertar los resultados:", response.error)


def main():
    result_pedidos = calcular_pedidos()
    result_compras_ves = calcular_compras_ves()
    result_compras_clp = calcular_compras_clp()

    # Calcular usdt_invertidos_exacto = brs_vendidos / tasa_ponderada_venta_usdt (usando FIAT = VES)
    if result_pedidos is not None and result_compras_ves is not None:
        brs_vendidos = result_pedidos.get("brs_vendidos", 0)
        tasa_ponderada_venta_usdt = result_compras_ves.get("tasa_ponderada_venta_usdt", 0)
        if tasa_ponderada_venta_usdt and tasa_ponderada_venta_usdt != 0:
            usdt_invertidos_exacto = brs_vendidos / tasa_ponderada_venta_usdt
            print("usdt_invertidos_exacto:", f"{usdt_invertidos_exacto:.6f}")
        else:
            usdt_invertidos_exacto = None
            print("usdt_invertidos_exacto: No aplica (tasa_ponderada_venta_usdt es 0 o None)")
    else:
        usdt_invertidos_exacto = None

    # Calcular clp_invertidos_exacto = usdt_invertidos_exacto * tasa_ponderada_usdt_clp (usando FIAT = CLP)
    if usdt_invertidos_exacto is not None and result_compras_clp is not None:
        tasa_ponderada_usdt_clp = result_compras_clp.get("tasa_ponderada_usdt_clp", 0)
        if tasa_ponderada_usdt_clp is not None:
            clp_invertidos_exacto = usdt_invertidos_exacto * tasa_ponderada_usdt_clp
            print("clp_invertidos_exacto:", f"{clp_invertidos_exacto:,.0f}")
        else:
            clp_invertidos_exacto = None
            print("clp_invertidos_exacto: No aplica (tasa_ponderada_usdt_clp es 0 o None)")
    else:
        clp_invertidos_exacto = None

    # Calcular margen mayor y margen mayor porcentaje
    if result_pedidos is not None:
        venta_en_clp = result_pedidos.get("venta_en_clp", 0)
        if clp_invertidos_exacto is not None and venta_en_clp != 0:
            margen_mayor = venta_en_clp - clp_invertidos_exacto
            margen_mayor_porcentaje = 1 - (clp_invertidos_exacto / venta_en_clp)
            print("margen_mayor:", f"{margen_mayor:,.0f}")
            print("margen_mayor_porcentaje:", f"{margen_mayor_porcentaje:.6f}")
        else:
            margen_mayor = None
            margen_mayor_porcentaje = None
            print("No se pueden calcular margen mayor y porcentaje (clp_invertidos_exacto o venta_en_clp es 0)")
    else:
        margen_mayor = None
        margen_mayor_porcentaje = None

    print("-" * 40)

    # Calcular brs_restantes:
    # brs_restantes = brs_comprados (de FIAT=VES) + brs_restantes_dia_anterior - brs_vendidos
    if result_compras_ves is not None and result_pedidos is not None:
        brs_comprados = result_compras_ves.get("brs_comprados", 0)
        brs_restantes = brs_comprados + brs_restantes_dia_anterior - result_pedidos.get("brs_vendidos", 0)
        print("brs_restantes:", f"{brs_restantes:,.0f}")
    else:
        brs_restantes = None

    # Calcular usdt_restantes = usdt_comprados (de FIAT=CLP) - usdt_invertidos_exacto
    if result_compras_clp is not None and usdt_invertidos_exacto is not None:
        usdt_comprados = result_compras_clp.get("usdt_comprados", 0)
        usdt_restantes = usdt_comprados - usdt_invertidos_exacto
        print("usdt_restantes:", f"{usdt_restantes:,.0f}")
    else:
        usdt_restantes = None

    # Calcular total_clp_invertido utilizando la segunda forma:
    # total_clp_invertido = usdt_vendidos (de FIAT=VES) * tasa_ponderada_usdt_clp (de FIAT=CLP)
    if result_compras_ves is not None and result_compras_clp is not None:
        tasa_ponderada_usdt_clp = result_compras_clp.get("tasa_ponderada_usdt_clp", None)
        if tasa_ponderada_usdt_clp is not None:
            total_clp_invertido = result_compras_ves.get("usdt_vendidos", 0) * tasa_ponderada_usdt_clp
            print("total_clp_invertido (nuevo):", f"{int(total_clp_invertido):,}")
        else:
            total_clp_invertido = None
            print("total_clp_invertido: No aplica (tasa_ponderada_usdt_clp es None)")
    else:
        total_clp_invertido = None

    # Preparar los datos para insertar en la tabla 'margen'
    resultados = {
        "fecha": str(fecha_obj),  # Formato YYYY-MM-DD
        "brs_vendidos": result_pedidos.get("brs_vendidos", None) if result_pedidos else None,
        "tasa_compra_ponderada": result_pedidos.get("tasa_compra_ponderada", None) if result_pedidos else None,
        "venta_en_clp": result_pedidos.get("venta_en_clp", None) if result_pedidos else None,
        "usdt_vendidos": result_compras_ves.get("usdt_vendidos", None) if result_compras_ves else None,
        "tasa_ponderada_venta_usdt": result_compras_ves.get("tasa_ponderada_venta_usdt", None)
        if result_compras_ves
        else None,
        "brs_comprados": result_compras_ves.get("brs_comprados", None) if result_compras_ves else None,
        "total_clp_invertido": total_clp_invertido,
        "usdt_comprados": result_compras_clp.get("usdt_comprados", None) if result_compras_clp else None,
        "tasa_ponderada_usdt_clp": result_compras_clp.get("tasa_ponderada_usdt_clp", None)
        if result_compras_clp
        else None,
        "usdt_invertidos_exacto": usdt_invertidos_exacto,
        "clp_invertidos_exacto": clp_invertidos_exacto,
        "margen_mayor": margen_mayor,
        "margen_mayor_porcentaje": margen_mayor_porcentaje,
        "usdt_restantes": usdt_restantes,
        "brs_restantes": brs_restantes,
    }

    insertar_resultados(resultados)

    print("-" * 40)
    print("¿Qué podemos hacer con los USDT y BRS que sobran?")
    print(
        "Se pueden reinvertir en nuevas operaciones, diversificar en otros activos o mantenerlos como reserva para aprovechar futuras oportunidades del mercado."
    )


if __name__ == "__main__":
    main()
