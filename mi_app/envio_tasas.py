#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para responder a los comandos /tasa y /compras en Telegram usando telebot,
obteniendo datos de Supabase, calculando tasas y enviando el resultado como
una tabla dibujada con Pillow (con estilo similar a una tabla de Excel y mayor nitidez)
para mayor legibilidad.
"""

import os
import time
import pytz
import asyncio
import logging
from datetime import datetime
from io import BytesIO

from supabase import create_client, Client
from usdt_ves import obtener_valor_usdt_por_banco
from telebot.async_telebot import AsyncTeleBot
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# Zona horaria
local_tz = pytz.timezone('America/Santiago')

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Credenciales y variables de entorno
CHAT_ID_TELEGRAM = -4090514300
TOKEN_TELEGRAM = '6962665881:AAG7e9l9rRtcnWyyia8i9jR5aLiU4ldlTzI'

SUPABASE_URL = "https://tmimwpzxmtezopieqzcl.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRtaW13cHp4bXRlem9waWVxemNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzY4NTI5NzQsImV4cCI6MjA1MjQyODk3NH0.tTrdPaiPAkQbF_JlfOOWTQwSs3C_zBbFDZECYzPP-Ho"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = AsyncTeleBot(TOKEN_TELEGRAM)

# Configuraciones de tabla/imagen con estilo Excel
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # Ajusta según tu sistema
FONT_SIZE = 50
PADDING = 20         # Margen externo reducido para simular Excel
COL_SPACING = 0      # Sin espacio horizontal extra entre columnas
ROW_SPACING = 0      # Sin espacio vertical extra entre filas

def create_table_image(table_data, font_path=FONT_PATH, font_size=FONT_SIZE,
                       padding=PADDING, col_spacing=COL_SPACING, row_spacing=ROW_SPACING,
                       header_bg_color="#4F81BD", header_text_color="white",
                       even_row_bg_color="white", odd_row_bg_color="#DCE6F1",
                       cell_border_color="#A6A6A6", border_width=1, sharpness_factor=2.0):
    """
    Crea una imagen con formato de tabla a partir de table_data (lista de listas),
    aplicando un estilo similar a una tabla de Excel: encabezado con fondo azul,
    filas alternadas en blanco y celeste, bordes en cada celda y texto centrado.
    Se aplica un factor de nitidez para mejorar la claridad de la imagen.
    """
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception as e:
        logger.error(f"Error cargando la fuente '{font_path}': {e}")
        font = ImageFont.load_default()

    num_rows = len(table_data)
    if num_rows == 0:
        return None
    num_cols = len(table_data[0])

    # Determinar el ancho de cada columna y la altura de cada fila
    col_widths = [0] * num_cols
    row_heights = [0] * num_rows
    temp_image = Image.new("RGB", (1, 1))
    draw_temp = ImageDraw.Draw(temp_image)

    for r in range(num_rows):
        for c in range(num_cols):
            cell_text = str(table_data[r][c])
            bbox = draw_temp.textbbox((0, 0), cell_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            if text_width > col_widths[c]:
                col_widths[c] = text_width
            if text_height > row_heights[r]:
                row_heights[r] = text_height

    # Relleno interno para cada celda
    cell_padding = 10
    col_widths = [w + 2 * cell_padding for w in col_widths]
    row_heights = [h + 2 * cell_padding for h in row_heights]

    # Calcular dimensiones totales de la imagen
    table_width = sum(col_widths) + (col_spacing * (num_cols - 1)) + (2 * padding)
    table_height = sum(row_heights) + (row_spacing * (num_rows - 1)) + (2 * padding)

    # Crear imagen final
    image = Image.new("RGB", (table_width, table_height), color="white")
    draw = ImageDraw.Draw(image)

    y_offset = padding
    for r in range(num_rows):
        x_offset = padding
        # Definir color de fondo y color de texto según la fila
        if r == 0:
            row_bg_color = header_bg_color
            text_color = header_text_color
        else:
            row_bg_color = even_row_bg_color if r % 2 == 0 else odd_row_bg_color
            text_color = "black"

        for c in range(num_cols):
            cell_text = str(table_data[r][c])
            cell_width = col_widths[c]
            cell_height = row_heights[r]

            # Dibujar fondo de la celda
            draw.rectangle(
                [x_offset, y_offset, x_offset + cell_width, y_offset + cell_height],
                fill=row_bg_color
            )

            # Dibujar borde de la celda (simulando el grid de Excel)
            draw.rectangle(
                [x_offset, y_offset, x_offset + cell_width, y_offset + cell_height],
                outline=cell_border_color, width=border_width
            )

            # Calcular posición para centrar el texto
            bbox = draw.textbbox((0, 0), cell_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x_offset + (cell_width - text_width) / 2
            text_y = y_offset + (cell_height - text_height) / 2

            draw.text((text_x, text_y), cell_text, font=font, fill=text_color)
            x_offset += cell_width + col_spacing
        y_offset += row_heights[r] + row_spacing

    # Aplicar mejora de nitidez para evitar imagen borrosa
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(sharpness_factor)

    return image


async def send_table_as_image(chat_id, table_data):
    """
    Crea una imagen a partir de table_data (lista de listas) y la envía al chat.
    """
    image = create_table_image(table_data)
    if image is None:
        await bot.send_message(chat_id, "No hay datos para mostrar en tabla.")
        return

    bio = BytesIO()
    bio.name = 'tabla.png'
    image.save(bio, 'PNG')
    bio.seek(0)
    await bot.send_photo(chat_id, bio)


# ---------------------------------------------------------------------
# Comando /tasa
# ---------------------------------------------------------------------
@bot.message_handler(commands=['tasa'])
async def manejar_tasa(message):
    try:
        if message.chat.id != CHAT_ID_TELEGRAM:
            await bot.send_message(message.chat.id, "No tienes permiso para usar este comando.")
            return

        response = supabase.table("vista_compras_fifo") \
            .select("costo_no_vendido") \
            .order("id", desc=True) \
            .limit(1) \
            .execute()

        if not response.data or len(response.data) == 0:
            await bot.send_message(message.chat.id, "No se encontró información en la tabla vista_compras_fifo.")
            return

        costo_no_vendido = response.data[0]["costo_no_vendido"]
        if costo_no_vendido == 0:
            await bot.send_message(
                message.chat.id,
                "El valor de costo_no_vendido es 0, no se puede realizar la división."
            )
            return

        banesco_val = await obtener_valor_usdt_por_banco("Banesco")
        bank_val = await obtener_valor_usdt_por_banco("BANK")

        tasa_banesco = banesco_val / costo_no_vendido
        tasa_venezuela = bank_val / costo_no_vendido

        # Construimos la tabla
        table_data = [
            ["Banco", "Tasa"],  # Encabezados
            ["Banesco", f"{tasa_banesco:.6f}"],
            ["Venezuela", f"{tasa_venezuela:.6f}"]
        ]

        await send_table_as_image(message.chat.id, table_data)

    except Exception as e:
        logger.error(f"Error en el comando /tasa: {e}")
        await bot.send_message(message.chat.id, "Ha ocurrido un error al procesar la solicitud.")


# ---------------------------------------------------------------------
# Comando /compras
# ---------------------------------------------------------------------
@bot.message_handler(commands=['compras'])
async def manejar_compras(message):
    try:
        if message.chat.id != CHAT_ID_TELEGRAM:
            await bot.send_message(message.chat.id, "No tienes permiso para usar este comando.")
            return

        parts = message.text.split()
        if len(parts) > 1:
            fecha = parts[1]
        else:
            fecha = adjust_datetime(datetime.now(local_tz)).strftime("%Y-%m-%d")

        inicio = f"{fecha}T00:00:00"
        fin = f"{fecha}T23:59:59"

        response = supabase.table("vista_compras_fifo") \
            .select("totalprice, paymethodname, createtime, unitprice, costo_no_vendido") \
            .eq("fiat", "VES") \
            .gte("createtime", inicio) \
            .lte("createtime", fin) \
            .execute()

        compras_data = response.data if response.data else []
        compras_data.sort(key=lambda row: row.get("createtime", ""), reverse=True)

        if not compras_data:
            await bot.send_message(message.chat.id, f"No se encontraron transacciones para la fecha {fecha}.")
            return

        # Construimos la tabla
        table_data = []
        table_data.append(["Hora", "Banco", "Brs", "Tasa"])  # Encabezados

        for row in compras_data:
            costo = row.get('costo_no_vendido')
            if costo and costo != 0:
                tasa = round(row['unitprice'] / costo, 6)
            else:
                tasa = 0
            createtime = row.get('createtime', '')
            hora = createtime.split("T")[1][:5] if "T" in createtime else createtime
            banco = row.get('paymethodname', '')
            brs = row.get('totalprice', 0)

            table_data.append([
                hora,
                banco,
                f"{brs:,.0f}",
                f"{tasa:.6f}"
            ])

        await send_table_as_image(message.chat.id, table_data)

    except Exception as e:
        logger.error(f"Error en el comando /compras: {e}")
        await bot.send_message(message.chat.id, "Ha ocurrido un error al obtener los datos de compras.")


# ---------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------
async def main():
    logger.info("Bot iniciado. Esperando comandos...")
    await bot.polling()


if __name__ == '__main__':
    asyncio.run(main())
