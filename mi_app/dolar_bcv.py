#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot de Telegram para enviar el valor del dólar de Venezuela al grupo cuando se reciba el comando /dolarve,
manteniéndose constantemente a la espera de comandos.
"""

import telebot
import requests
from bs4 import BeautifulSoup
import re
import urllib3

# Desactivar las advertencias de certificados inseguros
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Token del bot y chat id del grupo (se trabaja en un entorno seguro)
TOKEN = "7503093829:AAGzK60nUU6w4HtBSM8XVeIk9uK5JonjfHI"
GROUP_CHAT_ID = -4090514300

bot = telebot.TeleBot(TOKEN)


def obtener_valor_dolar():
    """
    Realiza scraping en la web del BCV para extraer el valor del dólar usando el selector:
    "#dolar > div > div > div.col-sm-6.col-xs-6.centrado".
    Convierte el valor extraído a float, lo redondea a dos decimales y lo retorna como cadena.
    """
    url = 'https://www.bcv.org.ve'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error al acceder a la página: {e}")
        return None

    # Parsear el contenido HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    # Utilizar el selector CSS proporcionado para ubicar el contenedor
    container = soup.select_one("#dolar > div > div > div.col-sm-6.col-xs-6.centrado")

    if container:
        # Buscar la etiqueta <strong> que contiene el valor
        strong_tag = container.find("strong")
        if strong_tag:
            valor_str = strong_tag.get_text(strip=True)
            # Validar el formato (ejemplo: "58,44370000")
            if re.match(r'^\d+,\d+$', valor_str):
                try:
                    # Convertir la cadena a float (reemplazando la coma por punto)
                    valor_float = float(valor_str.replace(',', '.'))
                    # Aproximar a dos decimales
                    valor_aproximado = round(valor_float, 2)
                    return f"{valor_aproximado:.2f}"
                except ValueError as e:
                    print(f"Error al convertir el valor a número: {e}")
                    return None
            else:
                print("El valor obtenido no coincide con el formato numérico esperado.")
                return None
        else:
            print("No se encontró la etiqueta <strong> dentro del contenedor especificado.")
            return None
    else:
        print("No se encontró el contenedor con el selector especificado.")
        return None


@bot.message_handler(commands=['dolarve'])
def enviar_valor_dolar(message):
    """
    Al recibir el comando /dolarve, extrae el valor del dólar y lo envía al grupo de Telegram.
    """
    valor = obtener_valor_dolar()
    if valor:
        texto = f"Dolar BCV: {valor}"
    else:
        texto = "No se pudo obtener el valor del dólar."

    bot.send_message(GROUP_CHAT_ID, texto)


if __name__ == '__main__':
    print("Bot iniciado. Esperando comandos...")
    # Se utiliza infinity_polling para que el bot esté constantemente a la escucha
    bot.infinity_polling()
