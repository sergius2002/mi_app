import os
import re
import pandas as pd
from datetime import datetime, timedelta
import telebot
from supabase import create_client, Client

# Token de Telegram
token_telegram = '7473214384:AAFbCAmg4TEDvnN5RfzUt9FbDED2QSPjRvc'

# Crear bot de Telebot
bot = telebot.TeleBot(token_telegram)

# Configuración de Supabase
SUPABASE_URL = "https://tmimwpzxmtezopieqzcl.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRtaW13cHp4bXRlem9waWVxemNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzY4NTI5NzQsImV4cCI6MjA1MjQyODk3NH0.tTrdPaiPAkQbF_JlfOOWTQwSs3C_zBbFDZECYzPP-Ho"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def obtener_compras_por_fecha(fecha_input: str):
    """
    Convierte la fecha ingresada (dd-mm) a un rango de tiempo y consulta la tabla 'compras'
    en Supabase filtrando por fiat = VES y por el campo 'createtime'.

    Se asume que el año es el actual. Se obtienen registros desde 'AAAA-MM-DDT00:00:00'
    hasta el inicio del día siguiente.
    """
    try:
        day, month = map(int, fecha_input.split('-'))
        year = datetime.now().year
        start_dt = datetime(year, month, day, 0, 0, 0)
        end_dt = start_dt + timedelta(days=1)
        start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception as e:
        return None, f"Error en el formato de fecha: {e}"

    response = supabase.table("compras") \
        .select("*") \
        .gte("createtime", start_str) \
        .lt("createtime", end_str) \
        .eq("fiat", "VES") \
        .execute()

    response_dict = response.dict()
    if response_dict.get("error"):
        return None, f"Error en la consulta a Supabase: {response_dict.get('error')}"

    data = response_dict.get("data")
    if not data:
        return None, f"No se encontraron registros para la fecha {fecha_input}"

    return data, None


@bot.message_handler(commands=['fecha'])
def handle_fecha(message):
    # Extraer argumento: se espera que el mensaje sea "/fecha dd-mm"
    parts = message.text.split()
    if len(parts) < 2:
        response = "<pre>Por favor, proporciona una fecha en el formato dd-mm. Ejemplo: /fecha 25-06</pre>"
        bot.send_message(message.chat.id, response, parse_mode='HTML')
        return

    fecha_input = parts[1]
    data, error = obtener_compras_por_fecha(fecha_input)
    if error:
        bot.send_message(message.chat.id, f"<pre>{error}</pre>", parse_mode='HTML')
        return
    else:
        df = pd.DataFrame(data)
        # Convertir nombres de columnas a minúsculas
        df.columns = [col.lower() for col in df.columns]
        if 'totalprice' not in df.columns or 'createtime' not in df.columns:
            response = "<pre>Los datos no contienen las columnas requeridas.</pre>"
            bot.send_message(message.chat.id, response, parse_mode='HTML')
            return
        # Convertir 'createtime' a datetime y ordenar los registros
        df['createtime'] = pd.to_datetime(df['createtime'])
        df.sort_values(by='createtime', inplace=True)
        # Extraer la hora en formato hh:mm
        df['Hora'] = df['createtime'].dt.strftime("%H:%M")
        # Crear la columna 'Brs': totalprice sin decimales y con separador de miles (puntos)
        df['Brs'] = df['totalprice'].apply(lambda x: f"{int(x):,}".replace(",", "."))
        # Seleccionar y ordenar las columnas a mostrar
        df_result = df[['Hora', 'Brs']]
        # Calcular el total de totalprice y formatearlo
        total_brs = df['totalprice'].sum()
        formatted_total = f"{int(total_brs):,}".replace(",", ".")
        # Convertir el DataFrame a string centrado
        table_str = df_result.to_string(index=False, justify="center")
        response = f"<pre>{table_str}\n\nTOTAL: {formatted_total}</pre>"
        bot.send_message(message.chat.id, response, parse_mode='HTML')


if __name__ == '__main__':
    bot.polling()