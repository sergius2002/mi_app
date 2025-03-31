#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import threading
import telebot
import requests
from bs4 import BeautifulSoup

# Inicializar el bot con el token proporcionado
bot = telebot.TeleBot('7442937067:AAEK2y8mULc6FAM4CTyuyrUM0hySZNdq5EY')
default_chat_id = '-4090514300'

# Diccionario para almacenar los valores anteriores
previous_values = {
    'minimos_inferior': None,
    'minimos_superior': None,
    'banesco_inferior': None,
    'venezuela_inferior': None,
    'banesco_superior': None,
    'venezuela_superior': None
}

monitoring = False
monitoring_task = None

def has_changed(current_values):
    global previous_values
    changes = []
    for key, current_value in current_values.items():
        if previous_values[key] is None or previous_values[key] != current_value:
            changes.append((key, previous_values[key], current_value))
    return changes

def update_previous_values(current_values):
    global previous_values
    previous_values.update(current_values)

def get_stored_values():
    global previous_values
    if all(v is None for v in previous_values.values()):
        return "❌ No hay valores almacenados. Usa /monitor para iniciar el monitoreo."
    resultado = (
        "<pre>"
        "📊 Valores Almacenados:\n\n"
        "{:<22} : {}\n".format("Mínimos ", previous_values['minimos_inferior'] or "N/A") +
        "{:<22} : {}\n".format("Banesco ", previous_values['banesco_inferior'] or "N/A") +
        "{:<22} : {}\n\n".format("Venezuela ", previous_values['venezuela_inferior'] or "N/A") +
        "{:<22} : {}\n".format("Mínimos ", previous_values['minimos_superior'] or "N/A") +
        "{:<22} : {}\n".format("Banesco ", previous_values['banesco_superior'] or "N/A") +
        "{:<22} : {}".format("Venezuela ", previous_values['venezuela_superior'] or "N/A") +
        "</pre>"
    )
    return resultado

def extract_data():
    try:
        # Crear una sesión con un User-Agent personalizado
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        login_url = "https://www.aguacatewallet.com/auth/login"

        # Obtener la página de login para inspeccionar el formulario
        login_page = session.get(login_url)
        soup = BeautifulSoup(login_page.text, 'html.parser')

        # Buscar un token CSRF (ajusta el nombre del campo según el HTML real)
        csrf_token = soup.find('input', {'name': 'csrf_token'})  # Puede ser 'csrf_token', '_token', etc.
        if csrf_token:
            csrf_value = csrf_token['value']
            print(f"Token CSRF encontrado: {csrf_value}")
        else:
            csrf_value = None
            print("No se encontró un token CSRF en la página de login")

        # Preparar datos de login (ajusta los nombres de los campos según el formulario real)
        login_data = {
            "email": "sergio.plaza.altamirano@gmail.com",
            "password": "karjon-razHiv-puvru2"
        }
        if csrf_value:
            login_data["csrf_token"] = csrf_value  # Ajusta el nombre del campo al real

        # Enviar solicitud POST a la URL correcta (ajusta esta URL según el formulario)
        login_post_url = "https://www.aguacatewallet.com/auth/login"  # ¡Cambia esto por la URL real del POST!
        response = session.post(login_post_url, data=login_data, allow_redirects=True)
        if response.status_code != 200:
            bot.send_message(default_chat_id, f"❌ Error al iniciar sesión. Código: {response.status_code}")
            print(f"Respuesta del servidor: {response.text}")
            return

        # Verificar si el login fue exitoso
        if "auth/login" in response.url:
            bot.send_message(default_chat_id, "❌ Login fallido: Redirigido de vuelta a la página de login")
            print(f"URL después del login: {response.url}")
            return
        else:
            print(f"Login exitoso. Redirigido a: {response.url}")

        # Acceder a la página de remesas (ajusta esta URL según el sitio real)
        remesas_url = "https://www.aguacatewallet.com/remesas"  # Verifica esta URL manualmente
        response = session.get(remesas_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extraer datos (ajusta los selectores según el HTML real)
        minimos_inferior_elem = soup.select_one('h1.text-lg.my-7:nth-child(1)')
        minimos_superior_elem = soup.select_one('h1.text-lg.my-7:nth-child(2)')
        banesco_inferior_elem = soup.select_one('span.text-xl.font-bold:nth-child(1)')
        venezuela_inferior_elem = soup.select_one('span.text-xl.font-bold:nth-child(2)')
        banesco_superior_elem = soup.select_one('div.app-rate-value-card:nth-child(1) span')
        venezuela_superior_elem = soup.select_one('div.app-rate-value-card:nth-child(4) span')

        minimos_inferior = minimos_inferior_elem.text.strip().replace("Mínimo", "") if minimos_inferior_elem else "N/A"
        minimos_superior = minimos_superior_elem.text.strip().replace("Mínimo", "") if minimos_superior_elem else "N/A"
        banesco_inferior = banesco_inferior_elem.text.strip() if banesco_inferior_elem else "N/A"
        venezuela_inferior = venezuela_inferior_elem.text.strip() if venezuela_inferior_elem else "N/A"
        banesco_superior = banesco_superior_elem.text.strip() if banesco_superior_elem else "N/A"
        venezuela_superior = venezuela_superior_elem.text.strip() if venezuela_superior_elem else "N/A"

        current_values = {
            'minimos_inferior': minimos_inferior,
            'minimos_superior': minimos_superior,
            'banesco_inferior': banesco_inferior,
            'venezuela_inferior': venezuela_inferior,
            'banesco_superior': banesco_superior,
            'venezuela_superior': venezuela_superior
        }

        # Enviar datos iniciales o cambios
        if all(v is None for v in previous_values.values()):
            resultado = (
                "<pre>"
                "📊 Datos Extraídos:\n\n"
                "{:<22} : {}\n".format("Mínimos ", minimos_inferior) +
                "{:<22} : {}\n".format("Banesco ", banesco_inferior) +
                "{:<22} : {}\n\n".format("Venezuela ", venezuela_inferior) +
                "{:<22} : {}\n".format("Mínimos ", minimos_superior) +
                "{:<22} : {}\n".format("Banesco ", banesco_superior) +
                "{:<22} : {}".format("Venezuela ", venezuela_superior) +
                "</pre>"
            )
            bot.send_message(default_chat_id, resultado, parse_mode="HTML")
        else:
            changes = has_changed(current_values)
            if changes:
                mensaje_cambios = "<pre>🔄 Cambios Detectados:\n\n"
                for key, old_value, new_value in changes:
                    mensaje_cambios += f"{key.replace('_', ' ').title():<22} : {old_value} → {new_value}\n"
                mensaje_cambios += "</pre>"
                bot.send_message(default_chat_id, mensaje_cambios, parse_mode="HTML")

        update_previous_values(current_values)

    except Exception as e:
        bot.send_message(default_chat_id, f"❌ Error al extraer datos: {str(e)}")
        print(f"Error: {str(e)}")

def monitor_values(interval=10):
    bot.send_message(default_chat_id, f"🔍 Monitoreo iniciado, actualizando cada {interval} segundos...")
    global monitoring
    while monitoring:
        extract_data()
        time.sleep(interval)

def run_monitoring(interval=10):
    monitor_values(interval)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "¡Hola! El monitoreo ya está en marcha. Usa /agua para ver los valores almacenados.")

@bot.message_handler(commands=['agua'])
def handle_agua(message):
    resultado = get_stored_values()
    bot.send_message(message.chat.id, resultado, parse_mode="HTML")

@bot.message_handler(commands=['stop'])
def handle_stop(message):
    global monitoring, monitoring_task
    if monitoring:
        monitoring = False
        if monitoring_task:
            monitoring_task.join()
            monitoring_task = None
        bot.reply_to(message, "🛑 Monitoreo detenido.")
    else:
        bot.reply_to(message, "No hay monitoreo en ejecución.")

if __name__ == '__main__':
    print("Bot iniciado...")
    # Iniciar el monitoreo solo después de asegurarse de que no hay conflictos
    monitoring = True
    monitoring_task = threading.Thread(target=run_monitoring)
    monitoring_task.start()
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Error en polling: {str(e)}")
        monitoring = False  # Detener monitoreo si falla el polling