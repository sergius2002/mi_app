import asyncio
import aiohttp
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from datetime import datetime
import csv
import logging
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
from threading import Thread

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SELL_API_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
DATA_FILE = "data_tasas.csv"  # Archivo para almacenar el historial de datos

# Inicializar listas para almacenar datos del gráfico
tiempos = []
precios_banesco = []
precios_bank_transfer = []

# Variable global para registrar la última fecha de reinicio
last_reset_date = None

# Crear/Inicializar el archivo CSV con encabezados
with open(DATA_FILE, mode="w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["Tiempo", "Precio_Banesco", "Precio_Bank_Transfer"])

# Función para guardar datos en un archivo CSV
def guardar_datos_csv(tiempo, precio_banesco, precio_bank_transfer):
    with open(DATA_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([tiempo, precio_banesco, precio_bank_transfer])

# Función para obtener la tasa de USDT/VES
async def obtener_tasa_usdt_ves(bancos):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/json",
    }

    payload = {
        'proMerchantAds': False,
        'page': 1,
        'transAmount': 100000,
        'rows': 20,
        'payTypes': bancos,
        'publisherType': 'merchant',
        'asset': 'USDT',
        'fiat': 'VES',
        'tradeType': 'SELL'
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(SELL_API_URL, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if "data" in data and data["data"]:
                        return float(data["data"][0]["adv"]["price"])
                    else:
                        logging.warning("No se encontraron datos en la respuesta.")
                        return None
                else:
                    logging.error(f"Error en la solicitud: {response.status}, {await response.text()}")
                    return None
        except Exception as e:
            logging.error(f"Error al obtener tasa USDT/VES: {e}")
            return None

def reiniciar_datos_diarios():
    """
    Esta función se encarga de reiniciar las listas y
    el archivo CSV a las 8:00 am de cada día.
    """
    global last_reset_date, tiempos, precios_banesco, precios_bank_transfer

    now = datetime.now()
    # Verificamos si es la hora (08:XX) y no se ha reiniciado hoy
    if now.hour == 8 and (last_reset_date is None or last_reset_date != now.date()):
        logging.info("Reiniciando datos del gráfico y archivo CSV a las 8:00 am...")

        # Limpiar listas
        tiempos.clear()
        precios_banesco.clear()
        precios_bank_transfer.clear()

        # Reiniciar archivo CSV
        with open(DATA_FILE, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Tiempo", "Precio_Banesco", "Precio_Bank_Transfer"])

        # Actualizar última fecha de reinicio
        last_reset_date = now.date()

# Función para obtener los datos de manera síncrona y actualizar las listas
def actualizar_datos():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    precio_banesco = loop.run_until_complete(obtener_tasa_usdt_ves(["Banesco"]))
    precio_bank_transfer = loop.run_until_complete(obtener_tasa_usdt_ves(["BANK"]))
    tiempo = datetime.now().strftime('%H:%M\n%d - %b')

    # Actualizamos las listas de precios
    tiempos.append(tiempo)
    precios_banesco.append(
        precio_banesco if precio_banesco is not None
        else (precios_banesco[-1] if precios_banesco else 0)
    )
    precios_bank_transfer.append(
        precio_bank_transfer if precio_bank_transfer is not None
        else (precios_bank_transfer[-1] if precios_bank_transfer else 0)
    )

    # Guardamos los datos en el CSV
    guardar_datos_csv(tiempo, precios_banesco[-1], precios_bank_transfer[-1])

# Configuración de Dash
app = dash.Dash(__name__)

# Función para actualizar el gráfico
@app.callback(
    Output('live-graph', 'figure'),
    Input('interval-component', 'n_intervals')
)
def actualizar_grafico(n):
    reiniciar_datos_diarios()  # Verificar si es hora de reiniciar los datos
    # Ejecutamos la actualización de los datos en segundo plano
    Thread(target=actualizar_datos).start()  # Ejecutar actualización en un hilo separado

    # Actualizamos el gráfico con los nuevos datos
    return {
        'data': [
            go.Scatter(
                x=tiempos,
                y=precios_banesco,
                mode='lines',
                name='Banesco',
                line=dict(color='blue')
            ),
            go.Scatter(
                x=tiempos,
                y=precios_bank_transfer,
                mode='lines',
                name='Venezuela',
                line=dict(color='orange')
            )
        ],
        'layout': go.Layout(
            title='Precios USDT/VES en Tiempo Real',
            xaxis=dict(title='Tiempo'),
            yaxis=dict(title='Precio (VES)'),
        )
    }

# Configuración del layout de la aplicación web con Dash
app.layout = html.Div([
    html.H1("Gráfico en Tiempo Real de Precios USDT/VES"),
    dcc.Graph(id='live-graph'),
    dcc.Interval(
        id='interval-component',
        interval=3000,  # Intervalo de 5 segundos
        n_intervals=0
    ),
])

if __name__ == '__main__':
    app.run_server(debug=True)
