#!/usr/bin/env python3
import warnings
# Suprime los avisos FutureWarning (por ejemplo, el de .dt.floor('S'))
warnings.filterwarnings("ignore", category=FutureWarning)

import os
import time
os.environ['TZ'] = 'America/Argentina/Buenos_Aires'
time.tzset()

import pytz
local_tz = pytz.timezone('America/Argentina/Buenos_Aires')

from binance.client import Client
import pandas as pd
from datetime import datetime, timedelta
import logging
from supabase import create_client
from postgrest.exceptions import APIError  # Para manejo específico de errores de Supabase

# Configuración de logging para mostrar información relevante
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Reducir mensajes de módulos externos que generan logs informativos
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)

def ejecutar_escaneo_binance(fecha_escaneo=None):
    # Configuración de Binance (credenciales de pruebas)
    api_key = 'Ds4W6XojH4dvM8eCre4U5rVBZpn03e8wM3POSOHHuDajdL33Cjg99JbLQ62n4Uti'
    api_secret = 'ljnha3p0yTg5tKpWm41sZMAH79LOsuwSiL7he6lU9ovUEM0D4e1AaeYkT1TFWo2A'
    client = Client(api_key, api_secret)

    # Configuración de Supabase (credenciales de pruebas)
    supabase_url = "https://tmimwpzxmtezopieqzcl.supabase.co"
    supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRtaW13cHp4bXRlem9waWVxemNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzY4NTI5NzQsImV4cCI6MjA1MjQyODk3NH0.tTrdPaiPAkQbF_JlfOOWTQwSs3C_zBbFDZECYzPP-Ho"
    supabase = create_client(supabase_url, supabase_key)

    # Si no se proporciona una fecha, se usa la fecha actual (en zona local)
    if fecha_escaneo is None:
        fecha_escaneo = datetime.now(local_tz).strftime("%Y-%m-%d")
    fecha_escaneo_dt = datetime.strptime(fecha_escaneo, "%Y-%m-%d")

    def llamada_binance():
        ad_params = {"asset": 'USDT'}
        try:
            result = client.get_c2c_trade_history(**ad_params)
            # Depuración: imprimir estructura de result['data']
            logging.debug(f"Resultado completo de Binance: {result}")

            data = result.get('data', [])
            if isinstance(data, dict):
                lengths = [len(v) for v in data.values() if isinstance(v, list)]
                if lengths and len(set(lengths)) != 1:
                    logging.error("Las listas en result['data'] tienen longitudes diferentes.")
                    return pd.DataFrame()
                df = pd.DataFrame(data)
            elif isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                logging.error("El formato de result['data'] no es ni lista ni diccionario.")
                return pd.DataFrame()

            # Verificar si la columna 'orderNumber' existe
            if 'orderNumber' in df.columns:
                logging.info("La columna 'orderNumber' está presente y se utilizará como identificador único.")
            else:
                if 'tradeType' in df.columns and 'createTime' in df.columns:
                    df['orderNumber'] = df.apply(lambda row: f"{row['tradeType']}_{row['createTime']}", axis=1)
                    logging.info("La columna 'orderNumber' no estaba presente. Se ha generado un identificador único.")
                else:
                    logging.error("Faltan columnas necesarias para generar 'orderNumber'.")
                    return pd.DataFrame()

            # Convertir 'createTime' a datetime: se asume que viene en milisegundos en UTC,
            # se convierte a datetime con zona UTC y luego se transforma a la zona local.
            if 'createTime' in df.columns:
                df['createTime'] = pd.to_datetime(df['createTime'], unit='ms', errors='coerce', utc=True)
                df['createTime'] = df['createTime'].dt.tz_convert('America/Argentina/Buenos_Aires')
                df['createTime'] = df['createTime'].dt.floor('s')
            else:
                logging.error("La columna 'createTime' no existe en los datos.")
                return pd.DataFrame()

            # Definir las columnas que se convertirán a float
            cols_float = ['amount', 'totalPrice', 'unitPrice', 'commission', 'takerCommission']
            for col in cols_float:
                if col not in df.columns:
                    df[col] = 0.0
            df[cols_float] = df[cols_float].apply(pd.to_numeric, errors='coerce')

            # Seleccionar las columnas de interés (solo las que existan en el DataFrame)
            columnas = ['orderNumber', 'tradeType', 'asset', 'fiat', 'amount', 'totalPrice',
                        'unitPrice', 'commission', 'takerCommission', 'orderStatus',
                        'createTime', 'payMethodName']
            columnas_existentes = [col for col in columnas if col in df.columns]
            df = df[columnas_existentes]

            # Filtrar registros descartando aquellos con estados no válidos, si la columna existe
            if 'orderStatus' in df.columns:
                estados_invalidos = ['CANCELLED', 'CANCELLED_BY_SYSTEM', 'PENDING',
                                     'TRADING', 'PROCESSING', 'PARTIALLY_FILLED']
                df = df[~df['orderStatus'].isin(estados_invalidos)]

            # Filtrar registros por fecha (comparar solo la fecha, sin hora)
            df = df[df['createTime'].dt.date == fecha_escaneo_dt.date()]

            # Renombrar métodos de pago según corresponda, si la columna existe
            if 'payMethodName' in df.columns:
                df['payMethodName'] = df['payMethodName'].replace('SpecificBank', 'Venezuela')
                df['payMethodName'] = df['payMethodName'].replace('BANK', 'Venezuela')

            # Ajustar la comisión: usar 'takerCommission' si es distinto de cero y existe la columna
            if 'takerCommission' in df.columns and 'commission' in df.columns:
                df['commission'] = df.apply(
                    lambda row: row['takerCommission'] if pd.notnull(row['takerCommission']) and row['takerCommission'] != 0 else row['commission'], axis=1)
                df = df.drop(columns=['takerCommission'])
            else:
                logging.info("No se encontraron las columnas 'takerCommission' o 'commission' para ajustar la comisión.")

            logging.info("Datos procesados correctamente desde Binance.")
            return df
        except Exception as e:
            logging.error(f"Error en llamada_binance: {e}")
            return pd.DataFrame()

    def verificar_y_upsert(data, supabase):
        try:
            batch_size = 50
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                # Verificar si ya existen los datos antes de hacer el upsert
                existing_data = supabase.table('compras').select('*').in_('ordernumber',
                                                                          [item['ordernumber'] for item in batch]).execute()
                existing_order_numbers = [item['ordernumber'] for item in existing_data.data]
                records_to_upsert = [item for item in batch if item['ordernumber'] not in existing_order_numbers]
                if records_to_upsert:
                    logging.info(f"Realizando upsert de {len(records_to_upsert)} registros.")
                    supabase.table('compras').upsert(records_to_upsert, on_conflict='ordernumber').execute()
                else:
                    logging.info("No hay registros nuevos o actualizados.")
        except Exception as e:
            logging.error(f"Error al realizar el upsert en Supabase: {e}")

    while True:
        # Actualizar la fecha de escaneo si ha cambiado el día
        current_date_str = datetime.now(local_tz).strftime("%Y-%m-%d")
        if current_date_str != fecha_escaneo:
            fecha_escaneo = current_date_str
            fecha_escaneo_dt = datetime.strptime(fecha_escaneo, "%Y-%m-%d")
            logging.info(f"Se actualizó la fecha de escaneo a {fecha_escaneo}")

        df_completo = llamada_binance()
        if df_completo.empty:
            logging.info("No se obtuvieron datos nuevos desde Binance.")
        else:
            # Convertir 'createTime' a cadena con el formato "YYYY-MM-DD HH:MM:SS"
            df_completo['createTime'] = df_completo['createTime'].apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(x) else None
            )
            # Convertir los nombres de las columnas a minúsculas
            df_completo.columns = [col.lower() for col in df_completo.columns]
            # Convertir el DataFrame a una lista de diccionarios para la inserción en Supabase
            records = df_completo.to_dict(orient='records')
            try:
                verificar_y_upsert(records, supabase)
            except APIError as api_err:
                logging.error(f"APIError al realizar el upsert en Supabase: {api_err}")
            except Exception as e:
                logging.error(f"Error al realizar el upsert en Supabase: {e}")
        time.sleep(60)

if __name__ == "__main__":
    fecha_escaneo = None  # Puedes especificar una fecha en formato "YYYY-MM-DD" si lo deseas
    ejecutar_escaneo_binance(fecha_escaneo)
