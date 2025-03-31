import requests
import logging
import hashlib
import hmac
import time
import re
import asyncio
import aiohttp
from dolar_online import obtener_precio_usd_clp
from telebot.async_telebot import AsyncTeleBot
import ssl
import certifi

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constantes
SELL_API_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
UPDATE_URL = "https://api.binance.com/sapi/v1/c2c/ads/update"
TRANS_AMOUNT = 3000000
LIMITE = 0
TIEMPO_ACTUALIZACION = 5  # Tiempo en segundos para actualizar precios
API_KEY = "i1RfFPH1JZemkq6puhp0fcMlrlb2FUGqcretupTWllY8h5lOCU1eKWrXyKcyYcDT"
API_SECRET = "qXU3owKPuSkx3dGnfMBMrzs0d422HabjtsBUd2ZASPhfUSHqcoFn6zTc9BCOsylk"
AD_NUMBER = "12725913569863766016"
TELEGRAM_BOT_TOKEN = '7717562245:AAGdLPawHTxX228otTjkn3L4f3DgrUwmAz4'
TELEGRAM_CHAT_ID = '-4280089421'
COMISION_FACTOR = 1.0016
OTC_INCREMENTO = 15
LIMITE_FACTOR = 1 - 0.0016
USDT_INCREMENTO = 0.013
UMBRAL_CAMBIO_PRECIO = 0.01
INTERVALO_USD = 5  # Intervalo en segundos para actualizar el precio USD
POLLING_INTERVAL = 5  # Intervalo para polling de Telegram

# Inicialización
bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
ejecucion_activa = False
ultimo_precio = None
ultimo_precio_usd = None
ultimo_tiempo_usd = 0

async def obtener_precios_usdt_clp_sell(session):
    try:
        data = {'proMerchantAds': False, 'page': 1, 'transAmount': TRANS_AMOUNT, 'rows': 20, 'asset': 'USDT', 'fiat': 'CLP', 'tradeType': 'SELL'}
        async with session.post(SELL_API_URL, json=data, timeout=aiohttp.ClientTimeout(total=5)) as response:
            response.raise_for_status()
            json_response = await response.json()
            if 'data' in json_response and json_response['data']:
                return [float(a['adv']['price']) for a in json_response['data']
                        if a['advertiser']['userType'] == 'merchant' and a['adv']['advNo'] != AD_NUMBER]
            logging.warning("No se encontraron datos en la respuesta de Binance.")
            return []
    except Exception as e:
        logging.error(f"Error al obtener precios USDT/CLP: {e}")
        return []

async def obtener_precio_usd():
    global ultimo_precio_usd, ultimo_tiempo_usd
    tiempo_actual = time.time()
    if ultimo_precio_usd is None or (tiempo_actual - ultimo_tiempo_usd) > INTERVALO_USD:
        try:
            ultimo_precio_usd = obtener_precio_usd_clp()
            ultimo_tiempo_usd = tiempo_actual
        except Exception as e:
            logging.error(f"Error al obtener el precio del USD/CLP: {e}")
            return ultimo_precio_usd
    return ultimo_precio_usd

async def actualizar_precio_anuncio(session, api_key, api_secret, ad_number, nuevo_precio):
    global ultimo_precio
    if ultimo_precio is None or abs(nuevo_precio - ultimo_precio) > UMBRAL_CAMBIO_PRECIO:
        timestamp = str(int(time.time() * 1000))
        query_string = f"timestamp={timestamp}"
        signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
        payload = {"advNo": ad_number, "price": nuevo_precio, "asset": "USDT", "priceType": 0, "fiatUnit": "CLP"}
        headers = {"X-MBX-APIKEY": api_key}
        params = {"timestamp": timestamp, "signature": signature}
        try:
            async with session.post(UPDATE_URL, json=payload, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    logging.error(f"Error al actualizar el precio del anuncio {ad_number}: {await response.text()}")
                else:
                    ultimo_precio = nuevo_precio
        except Exception as e:
            logging.error(f"Error al actualizar el precio del anuncio: {e}")

def escapar_markdown_v2(texto):
    caracteres_especiales = r'[\_\*\[\]\(\)\~\>\#\+\-\=\|\{\}\.\!]'
    return re.sub(caracteres_especiales, r'\\\g<0>', texto)

async def enviar_mensaje_telegram(mensaje):
    mensaje_escapado = escapar_markdown_v2(mensaje)
    try:
        await bot.send_message(TELEGRAM_CHAT_ID, mensaje_escapado, parse_mode="MarkdownV2")
    except Exception as e:
        logging.error(f"Error al enviar mensaje a Telegram: {e}")

async def actualizar_precio(session):
    global ejecucion_activa
    while ejecucion_activa:
        precios, precio_usd_clp = await asyncio.gather(obtener_precios_usdt_clp_sell(session), obtener_precio_usd())
        if precio_usd_clp is not None:
            USDT_1 = precio_usd_clp + LIMITE
            filtered_prices = [p for p in precios if p <= USDT_1]
            USDT_2 = max(filtered_prices, default=None)
            USDT_3 = (USDT_2 + USDT_INCREMENTO) if USDT_2 is not None else USDT_1
            comision = USDT_3 * COMISION_FACTOR
            otc = precio_usd_clp + OTC_INCREMENTO
            limite_max = otc * LIMITE_FACTOR
            if USDT_3 > limite_max:
                mensaje = f"```\nUSDT    : {USDT_3:.2f} (supera el límite máximo de {limite_max:.2f})\nComisión: {comision:.2f}\nDólar   : {precio_usd_clp:.2f}\nOTC     : {otc:.2f}\nLímite  : {limite_max:.2f}\n```"
            else:
                await actualizar_precio_anuncio(session, API_KEY, API_SECRET, AD_NUMBER, USDT_3)
                mensaje = f"```\nUSDT    : {USDT_3:.2f}\nComisión: {comision:.2f}\nDólar   : {precio_usd_clp:.2f}\nOTC     : {otc:.2f}\nLímite  : {limite_max:.2f}\n```"
            logging.info(mensaje)
            await enviar_mensaje_telegram(mensaje)
        else:
            logging.warning("No se pudo obtener el precio del USD/CLP.")
        await asyncio.sleep(TIEMPO_ACTUALIZACION)

@bot.message_handler(commands=['stop'])
async def detener_actualizacion(message):
    global ejecucion_activa
    if ejecucion_activa:
        ejecucion_activa = False
        await bot.reply_to(message, 'Proceso de actualización detenido.')
    else:
        await bot.reply_to(message, 'El proceso ya está detenido.')

@bot.message_handler(commands=['ini'])
async def iniciar_actualizacion(message):
    global ejecucion_activa
    if not ejecucion_activa:
        # Paso 1: Crear el contexto SSL usando certifi
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            ejecucion_activa = True
            asyncio.create_task(actualizar_precio(session))
            await bot.reply_to(message, 'Proceso de actualización iniciado.')
    else:
        await bot.reply_to(message, 'El proceso de actualización ya está en ejecución.')

@bot.message_handler(commands=['time'])
async def cambiar_tiempo(message):
    global TIEMPO_ACTUALIZACION
    try:
        parts = message.text.split()
        nuevo_tiempo = int(parts[1])
        if nuevo_tiempo < 10:  # Límite mínimo para evitar abuso de CPU
            nuevo_tiempo = 10
        TIEMPO_ACTUALIZACION = nuevo_tiempo
        await bot.reply_to(message, f'Tiempo de actualización cambiado a {nuevo_tiempo} segundos.')
    except (IndexError, ValueError):
        await bot.reply_to(message, 'Por favor, proporciona un tiempo válido en segundos. Uso: /time <segundos>')

@bot.message_handler(commands=['mon'])
async def cambiar_monto(message):
    global TRANS_AMOUNT
    try:
        parts = message.text.split()
        nuevo_monto = int(parts[1])
        TRANS_AMOUNT = nuevo_monto
        await bot.reply_to(message, f'Monto mínimo cambiado a {nuevo_monto} CLP.')
    except (IndexError, ValueError):
        await bot.reply_to(message, 'Por favor, proporciona un monto válido en CLP. Uso: /mon <monto>')

@bot.message_handler(commands=['lim'])
async def cambiar_limite(message):
    global LIMITE
    try:
        parts = message.text.split()
        nuevo_limite = float(parts[1])
        LIMITE = nuevo_limite
        await bot.reply_to(message, f'Límite cambiado a {nuevo_limite}.')
    except (IndexError, ValueError):
        await bot.reply_to(message, 'Por favor, proporciona un límite válido. Uso: /lim <valor>')

async def main():
    global ejecucion_activa
    # Paso 1: Crear el contexto SSL usando certifi para el main
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        ejecucion_activa = True
        asyncio.create_task(actualizar_precio(session))
        logging.info("Iniciando bot de Telebot en polling...")
        await bot.polling(none_stop=True, interval=POLLING_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())