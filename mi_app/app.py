import os
import time
from dotenv import load_dotenv
import ssl
import shutil
import requests
import json
import urllib.parse

# Cargar variables de entorno
load_dotenv()

# Debug prints
print("SUPABASE_URL:", os.getenv('SUPABASE_URL'))
print("SUPABASE_KEY:", os.getenv('SUPABASE_KEY'))
print("BCI_CLIENT_ID:", os.getenv('BCI_CLIENT_ID'))
print("BCI_CLIENT_SECRET:", os.getenv('BCI_CLIENT_SECRET'))

# Configurar el backend de Matplotlib sin interfaz
os.environ['MPLBACKEND'] = 'Agg'
os.environ['TZ'] = 'America/Argentina/Buenos_Aires'  # Forzar zona horaria
time.tzset()

import pytz
local_tz = pytz.timezone('America/Argentina/Buenos_Aires')  # Forzar zona horaria

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Blueprint, current_app, send_file
from supabase import create_client, Client
from datetime import datetime, timedelta

from flask_caching import Cache
import hashlib
from functools import wraps
from usdt_ves import obtener_valor_usdt_por_banco
import asyncio
import aiohttp
import csv
import logging
import io

# Configuración de Matplotlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.ioff()

from blueprints.utilidades import utilidades_bp
from blueprints.margen import margen_bp
from blueprints.bci import bci_bp

# -----------------------------------------------------------------------------
# Configuración de logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -----------------------------------------------------------------------------
# Inicialización de la aplicación y cache
# -----------------------------------------------------------------------------
app = Flask(__name__)
print("Rutas de templates:", app.jinja_loader.searchpath)
app.secret_key = os.getenv('SECRET_KEY', 'mi_clave_secreta')
cache = Cache(app, config={
    "CACHE_TYPE": os.getenv('CACHE_TYPE', 'SimpleCache'),
    "CACHE_DEFAULT_TIMEOUT": int(os.getenv('CACHE_DEFAULT_TIMEOUT', 300))
})

# -----------------------------------------------------------------------------
# Registro de blueprints
# -----------------------------------------------------------------------------
app.register_blueprint(utilidades_bp)
app.register_blueprint(margen_bp)
app.register_blueprint(bci_bp, url_prefix='/bci')

# -----------------------------------------------------------------------------
# Decorador login_required
# -----------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Por favor, inicia sesión.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# -----------------------------------------------------------------------------
# Configuración de Supabase
# -----------------------------------------------------------------------------
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------------------------------------------------------
# Procesador de contexto para verificar si el usuario es admin
# -----------------------------------------------------------------------------
@app.context_processor
def inject_user_permissions():
    is_admin = False
    if "email" in session:
        try:
            response = supabase.table("allowed_users").select("email").eq("email", session["email"]).execute()
            is_admin = bool(response.data)  # True si el email está en allowed_users
        except Exception as e:
            logging.error("Error al verificar permisos de usuario: %s", e)
    return dict(is_admin=is_admin)

# -----------------------------------------------------------------------------
# Blueprint: GRÁFICO (Real Time)
# -----------------------------------------------------------------------------
grafico_bp = Blueprint("grafico", __name__, template_folder="templates")

SELL_API_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
DATA_FILE = "data_tasas.csv"  # Archivo para almacenar el historial de datos

# Variables globales para el gráfico
tiempos = []
precios_banesco = []
precios_bank_transfer = []
precios_mercantil = []
precios_provincial = []
last_reset_date = None

def cargar_datos_historicos():
    global tiempos, precios_banesco, precios_bank_transfer, precios_mercantil, precios_provincial
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, mode="r", newline="") as file:
                reader = csv.reader(file)
                next(reader)  # Saltar encabezados
                for row in reader:
                    if len(row) >= 5:  # Asegurarse de que la fila tiene todos los datos
                        tiempo, banesco, bank, mercantil, provincial = row
                        tiempos.append(tiempo)
                        precios_banesco.append(float(banesco) if banesco else 0)
                        precios_bank_transfer.append(float(bank) if bank else 0)
                        precios_mercantil.append(float(mercantil) if mercantil else 0)
                        precios_provincial.append(float(provincial) if provincial else 0)
            logging.info(f"Datos históricos cargados: {len(tiempos)} registros")
    except Exception as e:
        logging.error(f"Error al cargar datos históricos: {e}")

def reiniciar_datos_diarios():
    global last_reset_date, tiempos, precios_banesco, precios_bank_transfer, precios_mercantil, precios_provincial
    now = datetime.now(local_tz)
    
    # Solo reiniciar si:
    # 1. Es la primera vez (last_reset_date es None)
    # 2. Es un nuevo día y son las 8:00 am
    if last_reset_date is None or (now.hour == 8 and now.date() > last_reset_date):
        logging.info(f"Reiniciando datos del gráfico y CSV a las {now.strftime('%Y-%m-%d %H:%M:%S')}...")
        
        # Guardar una copia de respaldo antes de reiniciar
        if os.path.exists(DATA_FILE):
            backup_file = f"{DATA_FILE}.{now.strftime('%Y%m%d')}.bak"
            try:
                shutil.copy2(DATA_FILE, backup_file)
                logging.info(f"Backup creado: {backup_file}")
            except Exception as e:
                logging.error(f"Error al crear backup: {e}")
        
        # Reiniciar las listas
        tiempos.clear()
        precios_banesco.clear()
        precios_bank_transfer.clear()
        precios_mercantil.clear()
        precios_provincial.clear()
        
        # Crear nuevo archivo CSV
        with open(DATA_FILE, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Tiempo", "Precio_Banesco", "Precio_Bank_Transfer", "Precio_Mercantil", "Precio_Provincial"])
        
        last_reset_date = now.date()
        logging.info("Reinicio completado")

def guardar_datos_csv(tiempo, banesco, bank, mercantil, provincial):
    try:
        with open(DATA_FILE, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([tiempo, banesco, bank, mercantil, provincial])
    except Exception as e:
        logging.error(f"Error al guardar datos en CSV: {e}")

# Cargar datos históricos al inicio
cargar_datos_historicos()

async def obtener_tasa_usdt_ves(bancos):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
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
    
    # Configurar SSL context para ignorar verificación de certificados
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(connector=connector) as session:
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
                    logging.error(f"Error en la solicitud: {response.status}")
                    return None
        except Exception as e:
            logging.error(f"Error al obtener tasa USDT/VES: {e}")
            return None

def actualizar_datos():
    global tiempos, precios_banesco, precios_bank_transfer, precios_mercantil, precios_provincial
    reiniciar_datos_diarios()  # Esto asegura el reinicio a las 8:00 am
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    precio_banesco_actualizado = loop.run_until_complete(obtener_tasa_usdt_ves(["Banesco"]))
    precio_bank_transfer_actualizado = loop.run_until_complete(obtener_tasa_usdt_ves(["BANK"]))
    precio_mercantil_actualizado = loop.run_until_complete(obtener_tasa_usdt_ves(["Mercantil"]))
    precio_provincial_actualizado = loop.run_until_complete(obtener_tasa_usdt_ves(["Provincial"]))
    loop.close()

    # Usar la zona horaria local para el tiempo actual
    tiempo_actual = datetime.now(local_tz)
    tiempo_str = tiempo_actual.strftime('%H:%M\n%d - %b')
    tiempos.append(tiempo_str)

    if precio_banesco_actualizado is not None:
        precios_banesco.append(precio_banesco_actualizado)
    else:
        precios_banesco.append(precios_banesco[-1] if precios_banesco else 0)

    if precio_bank_transfer_actualizado is not None:
        precios_bank_transfer.append(precio_bank_transfer_actualizado)
    else:
        precios_bank_transfer.append(precios_bank_transfer[-1] if precios_bank_transfer else 0)

    if precio_mercantil_actualizado is not None:
        precios_mercantil.append(precio_mercantil_actualizado)
    else:
        precios_mercantil.append(precios_mercantil[-1] if precios_mercantil else 0)

    if precio_provincial_actualizado is not None:
        precios_provincial.append(precio_provincial_actualizado)
    else:
        precios_provincial.append(precios_provincial[-1] if precios_provincial else 0)

    # Guardar datos con la hora local
    guardar_datos_csv(tiempo_str, precios_banesco[-1], precios_bank_transfer[-1], 
                     precios_mercantil[-1], precios_provincial[-1])

def generar_grafico():
    try:
        actualizar_datos()
        fig, ax = plt.subplots(figsize=(12, 6))
        fig.patch.set_facecolor('none')  # Fondo transparente
        ax.set_facecolor('none')  # Fondo del eje transparente

        # Graficar líneas
        ax.plot(tiempos, precios_banesco, label='Banesco', color='blue')
        ax.plot(tiempos, precios_bank_transfer, label='Venezuela', color='orange')
        ax.plot(tiempos, precios_mercantil, label='Mercantil', color='green')
        ax.plot(tiempos, precios_provincial, label='Provincial', color='red')

        # Añadir etiquetas de datos
        if precios_banesco:
            ax.annotate(f'{precios_banesco[-1]:.2f}', xy=(tiempos[-1], precios_banesco[-1]),
                        xytext=(5, 0), textcoords='offset points', color='blue', va='bottom', fontsize=10)
        if precios_bank_transfer:
            ax.annotate(f'{precios_bank_transfer[-1]:.2f}', xy=(tiempos[-1], precios_bank_transfer[-1]),
                        xytext=(5, 0), textcoords='offset points', color='orange', va='bottom', fontsize=10)
        if precios_mercantil:
            ax.annotate(f'{precios_mercantil[-1]:.2f}', xy=(tiempos[-1], precios_mercantil[-1]),
                        xytext=(5, 0), textcoords='offset points', color='green', va='bottom', fontsize=10)
        if precios_provincial:
            ax.annotate(f'{precios_provincial[-1]:.2f}', xy=(tiempos[-1], precios_provincial[-1]),
                        xytext=(5, 0), textcoords='offset points', color='red', va='bottom', fontsize=10)

        # Configurar etiquetas y leyenda
        ax.set_xlabel('Hora', fontsize=12)
        ax.set_ylabel('Precio (VES)', fontsize=12)
        ax.legend(loc='upper left', fontsize=10)

        # Configurar ticks
        if len(tiempos) > 1:
            ax.set_xticks([tiempos[0], tiempos[-1]])
        else:
            ax.set_xticks(tiempos)
        ax.tick_params(axis='x', rotation=45, labelsize=10)

        plt.tight_layout()
        return fig
    except Exception as e:
        logging.error(f"Error al generar el gráfico: {e}")
        raise  # Relanzar para depuración

@grafico_bp.route("/plot.png")
@login_required
def plot_png():
    try:
        fig = generar_grafico()
        # Convertir la figura a una imagen
        img = io.BytesIO()
        fig.savefig(img, format='png', bbox_inches='tight')
        img.seek(0)
        return send_file(img, mimetype='image/png')
    except Exception as e:
        logging.error(f"Error al generar el gráfico: {e}")
        return "Error al generar el gráfico", 500

@grafico_bp.route("/")
@login_required
def index():
    try:
        actualizar_datos()
        return render_template("grafico.html", active_page="grafico")
    except Exception as e:
        logging.error(f"Error al generar el gráfico: {e}")
        return "Error al generar el gráfico", 500

# -----------------------------------------------------------------------------
# Función para generar hash único para cada transferencia
# -----------------------------------------------------------------------------
def generar_hash_transferencia(transferencia):
    data = f"{transferencia.get('id')}-{transferencia.get('fecha')}-{transferencia.get('monto')}"
    return hashlib.sha256(data.encode('utf-8')).hexdigest()

# -----------------------------------------------------------------------------
# Decorador para módulos restringidos
# -----------------------------------------------------------------------------
def user_allowed(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        email = session.get("email")
        if not email:
            flash("Debes iniciar sesión.")
            return redirect(url_for("login"))
        try:
            response = supabase.table("allowed_users").select("email").eq("email", email).execute()
            if not response.data:
                flash("No tienes permisos para acceder a este módulo.")
                return redirect(url_for("index"))
        except Exception as e:
            logging.error("Error al verificar usuario permitido: %s", e)
            flash("Error interno al verificar permisos.")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper

# -----------------------------------------------------------------------------
# Filtros personalizados para Jinja2
# -----------------------------------------------------------------------------
def format_monto(value):
    try:
        return "{:,.0f}".format(value).replace(",", ".")
    except Exception:
        return value

def format_date(value):
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.strftime("%d-%m")
    except Exception:
        return value

def format_time(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%H:%M:%S")
    except Exception:
        return value

app.jinja_env.filters['format_time'] = format_time

@app.template_filter("format_fecha_detec")
def format_fecha_detec(value):
    if not value:
        return ""
    try:
        if isinstance(value, str):
            # Si es una cadena ISO, convertirla a datetime
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            # Convertir a zona horaria local
            dt = dt.astimezone(local_tz)
            # Formatear la fecha
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(value, datetime):
            # Si ya es datetime, asegurarse de que tenga zona horaria
            if value.tzinfo is None:
                value = local_tz.localize(value)
            return value.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")
        return str(value)
    except Exception as e:
        logging.error(f"Error formateando fecha_detec: {e}, valor: {value}")
        return str(value)

def format_clp(value):
    try:
        number = int(abs(float(value)))
        return "{:,.0f}".format(number).replace(",", ".")
    except Exception:
        return value

def format_int(value):
    try:
        return "{:,.0f}".format(int(float(value))).replace(",", ".")
    except Exception:
        return value

def format_datetime(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d-%m-%Y %H:%M:%S")
    except Exception:
        return value

def format_decimal(value, decimals=3):
    try:
        return f"{float(value):.{decimals}f}"
    except Exception:
        return value

app.jinja_env.filters['format_monto'] = format_monto
app.jinja_env.filters['format_date'] = format_date
app.jinja_env.filters['format_clp'] = format_clp
app.jinja_env.filters['format_int'] = format_int
app.jinja_env.filters['format_datetime'] = format_datetime
app.jinja_env.filters['format_decimal'] = format_decimal

# -----------------------------------------------------------------------------
# Funciones helper para filtrar y ordenar consultas
# -----------------------------------------------------------------------------
def filter_transferencias(query):
    cliente = request.args.get("cliente")
    if cliente:
        if cliente == "Desconocido":
            query = query.is_("cliente", "null")
        else:
            query = query.ilike("cliente", f"%{cliente}%")
    rut = request.args.get("rut")
    if rut:
        query = query.ilike("rut", f"%{rut}%")
    monto = request.args.get("monto", "").replace(".", "").strip()
    if monto:
        try:
            query = query.eq("monto", int(monto))
        except ValueError:
            logging.warning("Valor de monto no válido: %s", monto)
    verificada = request.args.get("verificada")
    if verificada == "true":
        query = query.eq("verificada", True)
    elif verificada == "false":
        query = query.eq("verificada", False)
    empresas = request.args.getlist("empresa")
    if empresas:
        query = query.in_("empresa", empresas)
    return query

def filter_pedidos(query):
    cliente = request.args.get("cliente")
    if cliente:
        query = query.ilike("cliente", f"%{cliente}%")
    fecha = request.args.get("fecha")
    if not fecha:
        fecha = datetime.now(local_tz).strftime("%Y-%m-%d")
    query = query.eq("fecha", fecha)
    brs = request.args.get("brs", "").strip()
    if brs:
        try:
            query = query.eq("brs", float(brs))
        except ValueError:
            logging.warning("Valor de BRS no válido: %s", brs)
    clp = request.args.get("clp", "").replace(".", "").strip()
    if clp:
        try:
            query = query.eq("clp", int(clp))
        except ValueError:
            logging.warning("Valor de CLP no válido: %s", clp)
    return query

def apply_ordering(query, sort_params):
    for sort_field, order in sort_params:
        if sort_field:
            query = query.order(sort_field, desc=(order == "desc"))
    return query

# -----------------------------------------------------------------------------
# Blueprints y rutas
# -----------------------------------------------------------------------------

# Blueprint para Transferencias
transferencias_bp = Blueprint("transferencias", __name__)

@transferencias_bp.route("/")
@login_required
def index():
    try:
        # Iniciar la consulta base
        query = supabase.table("transferencias").select(
            "id, cliente, empresa, rut, monto, fecha, fecha_detec, verificada, manual"
        )

        # Aplicar filtros
        cliente = request.args.get("cliente")
        if cliente:
            query = query.eq("cliente", cliente)

        rut = request.args.get("rut")
        if rut:
            query = query.ilike("rut", f"%{rut}%")

        monto = request.args.get("monto", "").replace(".", "").strip()
        if monto:
            try:
                query = query.eq("monto", int(monto))
            except ValueError:
                logging.warning("Valor de monto no válido: %s", monto)

        verificada = request.args.get("verificada")
        if verificada == "true":
            query = query.eq("verificada", True)
        elif verificada == "false":
            query = query.eq("verificada", False)

        empresas = request.args.getlist("empresa")
        if empresas:
            query = query.in_("empresa", empresas)

        # Aplicar ordenamiento
        sort_fields = []
        for i in range(1, 4):  # Para sort1, sort2, sort3
            sort = request.args.get(f"sort{i}")
            order = request.args.get(f"order{i}", "asc")
            if sort:
                query = query.order(sort, desc=(order == "desc"))

        # Si no hay ordenamiento específico, ordenar por fecha_detec descendente
        if not any(request.args.get(f"sort{i}") for i in range(1, 4)):
            query = query.order("fecha_detec", desc=True)

        # Ejecutar la consulta
        response_transfers = query.execute()

        transfers_data = []
        if response_transfers.data:
            for transfer in response_transfers.data:
                # Convertir los datos a su tipo correcto y manejar valores nulos
                transfer_processed = {
                    'id': transfer.get('id'),
                    'cliente': transfer.get('cliente') if transfer.get('cliente') is not None else 'Desconocido',
                    'empresa': transfer.get('empresa') if transfer.get('empresa') is not None else '',
                    'rut': transfer.get('rut') if transfer.get('rut') is not None else '',
                    'monto': float(transfer.get('monto', 0)),
                    'fecha': transfer.get('fecha') if transfer.get('fecha') is not None else '',
                    'fecha_detec': transfer.get('fecha_detec') if transfer.get('fecha_detec') is not None else '',
                    'verificada': bool(transfer.get('verificada', False)),
                    'manual': bool(transfer.get('manual', False))
                }
                transfers_data.append(transfer_processed)

        # Obtener lista única de clientes y empresas
        response_pagadores = supabase.table("pagadores").select("cliente").execute()
        clientes = sorted(set(p["cliente"] for p in response_pagadores.data)) if response_pagadores.data else []
        
        # Obtener lista única de empresas de la tabla transferencias
        response_empresas = supabase.table("transferencias").select("empresa").execute()
        empresas = sorted(set(e["empresa"] for e in response_empresas.data if e["empresa"] is not None)) if response_empresas.data else []
        empresas = ["Todas"] + empresas  # Agregar opción "Todas" al inicio

        return render_template(
            "transferencias.html",
            transfers=transfers_data,
            cliente=clientes,
            empresas=empresas,
            active_page="transferencias"
        )
    except Exception as e:
        logging.error(f"Error al obtener transferencias: {e}")
        flash("Error al cargar los datos de transferencias", "error")
        return render_template(
            "transferencias.html",
            transfers=[],
            cliente=[],
            empresas=[],
            active_page="transferencias"
        )

@transferencias_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    if request.method == "POST":
        try:
            cliente = request.form.get("cliente")
            empresa = request.form.get("empresa")
            rut = request.form.get("rut")
            monto = int(float(request.form.get("monto")))
            fecha = request.form.get("fecha")
            verificada = True if request.form.get("verificada") == "on" else False
            fecha_detec = datetime.now(local_tz).isoformat()
            data = f"{cliente}-{empresa}-{rut}-{monto}-{fecha}-{verificada}"
            hash_value = hashlib.sha256(data.encode('utf-8')).hexdigest()
            supabase.table("transferencias").insert({
                "cliente": cliente,
                "empresa": empresa,
                "rut": rut,
                "monto": monto,
                "fecha": fecha,
                "fecha_detec": fecha_detec,
                "verificada": verificada,
                "hash": hash_value,
                "manual": True
            }).execute()
            flash("Transferencia ingresada con éxito.")
            return redirect(url_for("transferencias.nuevo"))
        except Exception as e:
            logging.error("Error al insertar transferencia: %s", e)
            flash("Error al ingresar la transferencia: " + str(e))
            return redirect(url_for("transferencias.nuevo"))
    current_date = datetime.now(local_tz).strftime("%Y-%m-%d")
    try:
        response_pagadores = supabase.table("pagadores").select("cliente").execute()
        cliente_pagadores = [p["cliente"] for p in response_pagadores.data] if response_pagadores.data else []
    except Exception as e:
        logging.error("Error al obtener clientes para transferencia: %s", e)
        cliente_pagadores = []
    empresa_options = ["Caja Vecina", "Depósito en efectivo", "Otro"]
    return render_template("nuevo_transferencia.html", current_date=current_date, active_page="transferencias",
                           cliente_pagadores=cliente_pagadores, empresa_options=empresa_options)

@transferencias_bp.route("/editar/<transfer_id>", methods=["GET", "POST"])
@login_required
def editar_transferencia(transfer_id):
    try:
        response = supabase.table("transferencias").select("*").eq("id", transfer_id).execute()
        if not response.data:
            flash("Transferencia no encontrada.")
            return redirect(url_for("transferencias.index"))
        transferencia = response.data[0]
    except Exception as e:
        logging.error("Error al obtener la transferencia: %s", e)
        flash("Error al obtener la transferencia: " + str(e))
        return redirect(url_for("transferencias.index"))
    if not transferencia.get("manual", False):
        flash("Esta transferencia no puede ser editada porque no fue ingresada manualmente.")
        return redirect(url_for("transferencias.index"))
    if request.method == "POST":
        try:
            cliente = request.form.get("cliente")
            empresa = request.form.get("empresa")
            rut = request.form.get("rut")
            monto = int(float(request.form.get("monto")))
            fecha = request.form.get("fecha")
            verificada = True if request.form.get("verificada") == "on" else False
            data = f"{cliente}-{empresa}-{rut}-{monto}-{fecha}-{verificada}"
            hash_value = hashlib.sha256(data.encode('utf-8')).hexdigest()
            supabase.table("transferencias").update({
                "cliente": cliente,
                "empresa": empresa,
                "rut": rut,
                "monto": monto,
                "fecha": fecha,
                "verificada": verificada,
                "hash": hash_value
            }).eq("id", transfer_id).execute()
            flash("Transferencia actualizada con éxito.")
            return redirect(url_for("transferencias.index"))
        except Exception as e:
            logging.error("Error al actualizar la transferencia: %s", e)
            flash("Error al actualizar la transferencia: " + str(e))
            return redirect(url_for("transferencias.editar_transferencia", transfer_id=transfer_id))
    current_date = transferencia.get("fecha", datetime.now(local_tz).strftime("%Y-%m-%d"))
    try:
        response_pagadores = supabase.table("pagadores").select("cliente").execute()
        cliente_pagadores = [p["cliente"] for p in response_pagadores.data] if response_pagadores.data else []
    except Exception as e:
        logging.error("Error al obtener clientes para transferencia: %s", e)
        cliente_pagadores = []
    empresa_options = ["Caja Vecina", "Depósito en efectivo", "Otro"]
    return render_template(
        "editar_transferencia.html",
        transferencia=transferencia,
        current_date=current_date,
        cliente_pagadores=cliente_pagadores,
        empresa_options=empresa_options,
        active_page="transferencias"
    )

# Blueprint para Pedidos
pedidos_bp = Blueprint("pedidos", __name__)

@pedidos_bp.route("/")
@login_required
def index():
    try:
        query = supabase.table("pedidos").select("id, cliente, fecha, brs, tasa, clp")
        query = filter_pedidos(query)
        query = query.order("fecha", desc=False)
        response = query.execute()
        pedidos_data = response.data if response.data is not None else []
        clientes = sorted({p["cliente"] for p in pedidos_data if p.get("cliente")})
    except Exception as e:
        logging.error("Error al cargar los pedidos: %s", e)
        flash("Error al cargar los pedidos: " + str(e))
        pedidos_data, clientes = [], []
    current_date = datetime.now(local_tz).strftime("%Y-%m-%d")
    return render_template("pedidos.html", pedidos=pedidos_data, cliente=clientes, active_page="pedidos",
                           current_date=current_date)

@pedidos_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    try:
        response_pagadores = supabase.table("pagadores").select("cliente").execute()
        cliente_pagadores = [p["cliente"] for p in response_pagadores.data] if response_pagadores.data else []
    except Exception as e:
        logging.error("Error al obtener cliente de pagadores: %s", e)
        cliente_pagadores = []
    if request.method == "POST":
        try:
            cliente = request.form.get("cliente")
            brs = int(float(request.form.get("brs")))
            tasa = float(request.form.get("tasa"))
            fecha = request.form.get("fecha")
            usuario = session.get("email")
            supabase.table("pedidos").insert({
                "cliente": cliente, "brs": brs, "tasa": tasa, "fecha": fecha, "usuario": usuario
            }).execute()
            flash("Pedido ingresado con éxito.")
            return redirect(url_for("pedidos.nuevo"))
        except Exception as e:
            logging.error("Error al insertar pedido: %s", e)
            flash("Error al insertar pedido: " + str(e))
            return redirect(url_for("pedidos.nuevo"))
    current_date = datetime.now(local_tz).strftime("%Y-%m-%d")
    return render_template("nuevo_pedido.html", cliente_pagadores=cliente_pagadores, current_date=current_date,
                           active_page="pedidos")

@pedidos_bp.route("/editar/<pedido_id>", methods=["GET", "POST"])
@login_required
def editar(pedido_id):
    try:
        response_pagadores = supabase.table("pagadores").select("cliente").execute()
        cliente_pagadores = [p["cliente"] for p in response_pagadores.data] if response_pagadores.data else []
    except Exception as e:
        logging.error("Error al obtener cliente de pagadores: %s", e)
        cliente_pagadores = []
    try:
        pedido_response = supabase.table("pedidos").select("id, cliente, fecha, brs, tasa, clp").eq("id", pedido_id).execute()
        if not pedido_response.data:
            flash("Pedido no encontrado.")
            return redirect(url_for("pedidos.index"))
        pedido = pedido_response.data[0]
    except Exception as e:
        logging.error("Error al obtener pedido: %s", e)
        flash("Error al obtener pedido: " + str(e))
        return redirect(url_for("pedidos.index"))
    logs = []
    try:
        logs_response = supabase.table("pedidos_log").select("*").eq("pedido_id", pedido_id).order("fecha", desc=True).execute()
        logs = logs_response.data if logs_response.data is not None else []
    except Exception as e:
        logging.error("Error al obtener historial de cambios: %s", e)
    if request.method == "POST":
        try:
            nuevo_cliente = request.form.get("cliente")
            nuevo_brs = int(float(request.form.get("brs")))
            nuevo_tasa = float(request.form.get("tasa"))
            nuevo_fecha = request.form.get("fecha")
            cambios = []
            if pedido["cliente"] != nuevo_cliente:
                cambios.append(f"cliente: {pedido['cliente']} -> {nuevo_cliente}")
            if int(pedido["brs"]) != nuevo_brs:
                cambios.append(f"brs: {pedido['brs']} -> {nuevo_brs}")
            if float(pedido["tasa"]) != nuevo_tasa:
                cambios.append(f"tasa: {pedido['tasa']} -> {nuevo_tasa}")
            if pedido["fecha"] != nuevo_fecha:
                cambios.append(f"fecha: {pedido['fecha']} -> {nuevo_fecha}")
            supabase.table("pedidos").update({
                "cliente": nuevo_cliente, "brs": nuevo_brs, "tasa": nuevo_tasa, "fecha": nuevo_fecha
            }).eq("id", pedido_id).execute()
            if cambios:
                cambios_str = "; ".join(cambios)
                try:
                    supabase.table("pedidos_log").insert({
                        "pedido_id": pedido_id, "usuario": session.get("email"), "cambios": cambios_str,
                        "fecha": datetime.now(local_tz).isoformat()
                    }).execute()
                except Exception as log_error:
                    logging.error("Error al insertar en el log de cambios: %s", log_error)
                    flash("Error al registrar el historial de cambios: " + str(log_error))
            flash("Pedido actualizado con éxito.")
            return redirect(url_for("pedidos.index"))
        except Exception as e:
            logging.error("Error al actualizar pedido: %s", e)
            flash("Error al actualizar pedido: " + str(e))
            return redirect(url_for("pedidos.editar", pedido_id=pedido_id))
    return render_template("editar_pedido.html", pedido=pedido, cliente_pagadores=cliente_pagadores, logs=logs,
                           active_page="pedidos")

# Blueprint para Dashboard
dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
@login_required
@cache.cached(timeout=60, query_string=True)
def index():
    try:
        current_date = datetime.now(local_tz).strftime("%Y-%m-%d")
        fecha_inicio = request.args.get("fecha_inicio", current_date)
        fecha_fin = request.args.get("fecha_fin", current_date)
        rpc_response = supabase.rpc("get_dashboard_aggregates",
                                    {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin}).execute()
        dashboard_list = rpc_response.data if rpc_response.data is not None else []
        dashboard_list = sorted(dashboard_list, key=lambda item: item.get("cliente", "").lower())
        global_total_brs = sum(item.get("total_brs", 0) for item in dashboard_list)
        global_total_clp = sum(item.get("total_clp", 0) for item in dashboard_list)
        global_total_pagos = sum(item.get("total_pagos", 0) for item in dashboard_list)
        deuda_response = supabase.table("deuda_anterior").select("cliente, deuda").execute()
        deuda_data = deuda_response.data if deuda_response.data is not None else []
        deuda_dict = {d["cliente"]: float(d["deuda"]) for d in deuda_data}
        for item in dashboard_list:
            deuda_cliente = deuda_dict.get(item["cliente"], 0)
            item["saldo"] = item.get("total_clp", 0) - item.get("total_pagos", 0) + deuda_cliente
        global_total_saldo = sum(item["saldo"] for item in dashboard_list)
    except Exception as e:
        logging.error("Error al generar el dashboard: %s", e)
        flash("Error al generar el dashboard: " + str(e))
        dashboard_list = []
        global_total_brs = global_total_clp = global_total_pagos = global_total_saldo = 0
        current_date = datetime.now(local_tz).strftime("%Y-%m-%d")
    return render_template("dashboard.html", dashboard_list=dashboard_list, current_date=current_date,
                           global_total_brs=global_total_brs, global_total_clp=global_total_clp,
                           global_total_pagos=global_total_pagos, global_total_saldo=global_total_saldo,
                           active_page="dashboard")

@dashboard_bp.route("/detalle/<cliente>")
@login_required
@cache.cached(timeout=60, query_string=True)
def detalle(cliente):
    try:
        current_date = datetime.now(local_tz).strftime("%Y-%m-%d")
        fecha_inicio = request.args.get("fecha_inicio", current_date)
        fecha_fin = request.args.get("fecha_fin", current_date)
        try:
            page = int(request.args.get("page", 1))
        except ValueError:
            page = 1
        per_page = 10
        query = supabase.table("pedidos").select("id, cliente, fecha, brs, tasa, clp") \
            .eq("cliente", cliente) \
            .gte("fecha", fecha_inicio) \
            .lte("fecha", fecha_fin)
        query = query.range((page - 1) * per_page, page * per_page - 1)
        response = query.execute()
        pedidos_data = response.data if response.data is not None else []
        count_response = supabase.table("pedidos").select("id", count="exact") \
            .eq("cliente", cliente) \
            .gte("fecha", fecha_inicio) \
            .lte("fecha", fecha_fin).execute()
        total_count = count_response.count if count_response.count is not None else 0
        total_pages = (total_count + per_page - 1) // per_page
    except Exception as e:
        logging.error("Error al obtener el detalle para el cliente %s: %s", cliente, e)
        flash("Error al obtener el detalle: " + str(e))
        pedidos_data = []
        total_pages = 0
        page = 1
        fecha_inicio = fecha_fin = current_date
    return render_template("dashboard_detalle.html", pedidos=pedidos_data, cliente=cliente, fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin, page=page, total_pages=total_pages)

# Blueprint para el módulo restringido (admin)
admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/")
@login_required
@user_allowed
def index():
    return redirect(url_for('admin.tasa_compras'))

@admin_bp.route("/calcular_margen", methods=["GET"])
@login_required
@user_allowed
def calcular_margen():
    fecha = request.args.get("fecha")
    if not fecha:
        flash("Debe seleccionar una fecha para calcular el margen.", "warning")
        return redirect(url_for("admin.margen"))
    margen_calculado = 1234.56  # Placeholder, reemplaza con lógica real si aplica
    return render_template("margen_resultado.html", active_page="admin", fecha=fecha, margin=margen_calculado)

@admin_bp.route("/tasa_compras", methods=["GET"])
@login_required
@user_allowed
def tasa_compras():
    fecha = request.args.get("fecha")
    if not fecha:
        fecha = datetime.now(local_tz).strftime("%Y-%m-%d")
    inicio = fecha + "T00:00:00"
    fin = fecha + "T23:59:59"
    try:
        response = supabase.table("vista_compras_fifo") \
            .select("totalprice, paymethodname, createtime, unitprice, costo_no_vendido") \
            .eq("fiat", "VES") \
            .gte("createtime", inicio) \
            .lte("createtime", fin) \
            .execute()
        compras_data = response.data if response.data else []
        query = supabase.table("vista_compras_fifo").select("costo_no_vendido") \
            .eq("fiat", "VES") \
            .gte("createtime", inicio) \
            .lte("createtime", fin) \
            .order("createtime", desc=True) \
            .limit(1) \
            .execute()
        if query.data:
            costo_no_vendido = query.data[0]["costo_no_vendido"]
        else:
            costo_no_vendido = None
        for row in compras_data:
            if costo_no_vendido:
                row['tasa'] = round(row['unitprice'] / costo_no_vendido, 6)
    except Exception as e:
        logging.error("Error al obtener los datos: %s", e)
        compras_data = []
    return render_template("tasa_compras.html", active_page="admin",
                           compras_data=compras_data, fecha=fecha)

@admin_bp.route("/ingresar_usdt", methods=["GET", "POST"])
@login_required
@user_allowed
def ingresar_usdt():
    if request.method == "POST":
        try:
            totalprice_str = request.form.get("totalprice", "")
            if not totalprice_str:
                flash("El campo Total Price es requerido.")
                return redirect(url_for("admin.ingresar_usdt"))
            
            totalprice = float(totalprice_str.replace(".", "").replace(",", ".").strip())
            tasa_str = request.form.get("tasa")
            tasa = float(tasa_str)
            tradetype = request.form.get("tradetype")
            fiat = request.form.get("fiat")
            asset = "USDT"
            paymethodname = "OTC"
            orderstatus = "COMPLETED"
            amount = totalprice / tasa
            costo_real = amount
            commission = 0
            createtime = request.form.get("createtime")
            # Asegurarse de que la fecha está en la zona horaria correcta
            dt_createtime = datetime.strptime(createtime, "%Y-%m-%dT%H:%M")
            dt_createtime = local_tz.localize(dt_createtime)
            createtime = dt_createtime.isoformat()
            hash_input = f"{totalprice}{tasa}{tradetype}{fiat}{asset}{createtime}"
            ordernumber = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:20]
            response = supabase.table("compras").insert({
                "totalprice": totalprice,
                "unitprice": tasa,
                "tradetype": tradetype,
                "fiat": fiat,
                "asset": asset,
                "amount": amount,
                "costo_real": costo_real,
                "commission": commission,
                "paymethodname": paymethodname,
                "createtime": createtime,
                "orderstatus": orderstatus,
                "ordernumber": ordernumber
            }).execute()
            flash("Compra de USDT ingresada con éxito.")
            return redirect(url_for("admin.ingresar_usdt"))
        except Exception as e:
            logging.error("Error al ingresar compra de USDT: %s", e)
            flash("Error al ingresar la compra de USDT: " + str(e))
            return redirect(url_for("admin.ingresar_usdt"))
    
    # Asegurarse de que la fecha actual está en la zona horaria correcta
    current_datetime = datetime.now(local_tz).strftime("%Y-%m-%dT%H:%M")
    tradetype_options = ["BUY", "SELL"]
    fiat_options = ["CLP", "VES", "USD"]
    
    # Renderizar el template sin valor por defecto para totalprice
    return render_template("ingresar_usdt.html", 
                         active_page="admin", 
                         current_datetime=current_datetime,
                         tradetype_options=tradetype_options, 
                         fiat_options=fiat_options,
                         totalprice="")  # Enviamos un string vacío explícitamente

@admin_bp.route("/tasa_actual", methods=["GET"])
@login_required
@user_allowed
def tasa_actual():
    try:
        query = supabase.table("vista_compras_fifo").select("costo_no_vendido, createtime, stock_usdt") \
            .order("createtime", desc=True) \
            .limit(1)
        response = query.execute()
        if response.data and len(response.data) > 0:
            record = response.data[0]
            costo_no_vendido = record.get("costo_no_vendido")
            stock_usdt = record.get("stock_usdt")
        else:
            costo_no_vendido = None
            stock_usdt = None
            flash("No se encontró ningún registro.", "warning")
    except Exception as e:
        logging.error("Error al obtener la tasa actual desde Supabase: %s", e)
        flash("Error al obtener la tasa actual: " + str(e), "danger")
        costo_no_vendido = None
        stock_usdt = None

    resultado_banesco = None
    resultado_bank = None

    if costo_no_vendido is not None:
        try:
            async def obtener_valores():
                logging.info("Intentando obtener valor de Banesco...")
                banesco_val = await obtener_valor_usdt_por_banco("Banesco")
                logging.info(f"Valor de Banesco obtenido: {banesco_val}")
                
                logging.info("Intentando obtener valor de BANK...")
                bank_val = await obtener_valor_usdt_por_banco("BANK")
                logging.info(f"Valor de BANK obtenido: {bank_val}")
                
                return banesco_val, bank_val
            banesco_val, bank_val = asyncio.run(obtener_valores())
            if banesco_val and bank_val:
                resultado_banesco = round(float(banesco_val) / float(costo_no_vendido), 6)
                resultado_bank = round(float(bank_val) / float(costo_no_vendido), 6)
                logging.info(f"Tasas calculadas - Banesco: {resultado_banesco}, Venezuela: {resultado_bank}")
            else:
                logging.warning("No se pudieron obtener los valores de los bancos")
                flash("No se pudieron obtener las tasas de conversión de Banesco y BANK.", "warning")
        except Exception as e:
            logging.error("Error al obtener valores USDT/VES: %s", e)
            flash("Error al obtener valores USDT/VES: " + str(e), "danger")

    return render_template(
        "tasa_actual.html",
        active_page="admin",
        costo_no_vendido=costo_no_vendido,
        stock_usdt=stock_usdt,
        resultado_banesco=resultado_banesco,
        resultado_bank=resultado_bank
    )

@admin_bp.route("/cierre_dia", methods=["GET", "POST"])
@login_required
@user_allowed
def cierre_dia():
    if request.method == "POST":
        fecha = request.form.get("fecha")
        try:
            pedidos_response = supabase.table("pedidos").select("cliente, clp").eq("fecha", fecha).execute()
            pedidos_data = pedidos_response.data if pedidos_response.data is not None else []
            pedidos_totales = {}
            for p in pedidos_data:
                pedidos_totales[p["cliente"]] = pedidos_totales.get(p["cliente"], 0) + p["clp"]

            filtrar_verificadas = True
            pagos_query = supabase.table("transferencias").select("id, cliente, monto, fecha").eq("fecha", fecha)
            if filtrar_verificadas:
                pagos_query = pagos_query.eq("verificada", True)
            pagos_response = pagos_query.execute()
            pagos_data = pagos_response.data if pagos_response.data is not None else []
            pagos_totales = {}
            for p in pagos_data:
                hash_actual = generar_hash_transferencia(p)
                check_resp = supabase.table("pagos_procesados").select("*").eq("hash", hash_actual).execute()
                if not check_resp.data:
                    pagos_totales[p["cliente"]] = pagos_totales.get(p["cliente"], 0) + p["monto"]
                    supabase.table("pagos_procesados").insert({
                        "transferencia_id": p["id"],
                        "hash": hash_actual,
                        "fecha_procesada": datetime.now(local_tz).strftime("%Y-%m-%d")
                    }).execute()
            clientes = set(list(pedidos_totales.keys()) + list(pagos_totales.keys()))
            for cliente in clientes:
                total_pedidos = pedidos_totales.get(cliente, 0)
                total_pagos = pagos_totales.get(cliente, 0)
                deuda_resp = supabase.table("deuda_anterior").select("deuda").eq("cliente", cliente).execute()
                deuda_anterior = deuda_resp.data[0]["deuda"] if deuda_resp.data else 0
                saldo_final = total_pedidos - total_pagos + deuda_anterior
                fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")
                nueva_fecha = (fecha_obj + timedelta(days=1)).strftime("%Y-%m-%d")
                check_resp = supabase.table("deuda_anterior").select("*").eq("cliente", cliente).eq("fecha", nueva_fecha).execute()
                if check_resp.data:
                    supabase.table("deuda_anterior").update({"deuda": saldo_final}).eq("cliente", cliente).eq("fecha", nueva_fecha).execute()
                else:
                    supabase.table("deuda_anterior").insert(
                        {"cliente": cliente, "deuda": saldo_final, "fecha": nueva_fecha}).execute()
            flash("Cierre de día realizado con éxito para la fecha " + fecha)
        except Exception as e:
            logging.error("Error en el cierre de día: %s", e)
            flash("Error en el cierre de día: " + str(e))
        return redirect(url_for("admin.index"))
    return render_template("cierre_dia.html", active_page="admin")

@admin_bp.route("/margen", methods=["GET"])
@login_required
@user_allowed
def margen():
    return render_template("margen.html", active_page="admin")

@admin_bp.route("/resumen_compras_usdt", methods=["GET"])
@login_required
@user_allowed
def resumen_compras_usdt():
    fecha = request.args.get("fecha")
    if not fecha:
        fecha = datetime.now(local_tz).strftime("%Y-%m-%d")
    
    inicio = fecha + "T00:00:00"
    fin = fecha + "T23:59:59"
    
    try:
        response = supabase.table("compras") \
            .select("*") \
            .eq("fiat", "CLP") \
            .eq("tradetype", "BUY") \
            .gte("createtime", inicio) \
            .lte("createtime", fin) \
            .execute()
        
        compras_data = response.data if response.data else []
        compras_data.sort(key=lambda x: x.get("createtime", ""), reverse=True)
        
        # Calcular totales
        total_clp = sum(compra.get("totalprice", 0) for compra in compras_data)
        total_usdt = sum(compra.get("amount", 0) for compra in compras_data)
        tasa_promedio = total_clp / total_usdt if total_usdt > 0 else 0
        
        return render_template(
            "admin/resumen_compras_usdt.html",
            active_page="admin",
            compras_data=compras_data,
            total_clp=total_clp,
            total_usdt=total_usdt,
            tasa_promedio=tasa_promedio,
            fecha=fecha
        )
    except Exception as e:
        logging.error("Error al obtener resumen de compras USDT: %s", e)
        flash("Error al obtener el resumen de compras USDT.")
        return redirect(url_for("admin.index"))

# Rutas generales
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("transferencias.index"))
    else:
        return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        try:
            auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as e:
            logging.error("Error al iniciar sesión: %s", e)
            flash("Error al iniciar sesión: " + str(e))
            return redirect(url_for("login"))
        if auth_response.session:
            session["user_id"] = auth_response.user.id
            session["email"] = auth_response.user.email
            flash("¡Sesión iniciada con éxito!")
            return redirect(url_for("transferencias.index"))
        else:
            flash("Credenciales incorrectas.")
            return redirect(url_for("login"))
    return render_template("login.html", title="Iniciar Sesión", active_page="")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Sesión cerrada.")
    return redirect(url_for("login"))

@app.route("/update/<transfer_id>", methods=["POST"])
@login_required
def update_transfer(transfer_id):
    nuevo_valor = request.form.get("nuevo_valor")
    try:
        nuevo_valor = bool(int(nuevo_valor))
    except Exception as e:
        logging.error("Error al convertir nuevo_valor: %s", e)
        nuevo_valor = False
    try:
        result = supabase.table("transferencias").update({"verificada": nuevo_valor}).eq("id", transfer_id).execute()
        if result.data and len(result.data) > 0:
            flash(f"Registro actualizado (ID = {transfer_id}).")
        else:
            flash("No se encontró el registro para actualizar. Verifica las políticas de seguridad.")
    except Exception as e:
        logging.error("Error al actualizar el registro: %s", e)
        flash("Error al actualizar el registro: " + str(e))
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(success=True)
    return redirect(request.referrer or url_for("transferencias.index"))

# Rutas para BCI
@app.route('/auth')
@login_required
def auth():
    """Redirige a la página de autorización de BCI"""
    return redirect(url_for('bci.auth'))

@app.route("/bci/callback")
@login_required
def bci_callback():
    """Maneja la respuesta de autorización de BCI"""
    try:
        # Obtener el código de autorización
        auth_code = request.args.get('code')
        if not auth_code:
            error = request.args.get('error')
            error_description = request.args.get('error_description')
            flash(f"Error en la autorización de BCI: {error} - {error_description}")
            return redirect(url_for("index"))
        
        # Intercambiar el código por un token de acceso
        token_url = "https://apiprogram.bci.cl/sandbox/v1/api-oauth/token"
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": "https://sancristobalspa.eu.pythonanywhere.com/bci/callback",
            "client_id": os.getenv('BCI_CLIENT_ID'),
            "client_secret": os.getenv('BCI_CLIENT_SECRET')
        }
        
        # Hacer la solicitud para obtener el token
        response = requests.post(token_url, data=token_data)
        if response.status_code != 200:
            flash("Error al obtener el token de acceso de BCI")
            return redirect(url_for("index"))
        
        # Guardar el token en la sesión
        token_data = response.json()
        session['bci_access_token'] = token_data.get('access_token')
        session['bci_refresh_token'] = token_data.get('refresh_token')
        session['bci_token_expires_in'] = token_data.get('expires_in')
        
        flash("Autorización con BCI completada exitosamente")
        return redirect(url_for("index"))
        
    except Exception as e:
        logging.error(f"Error en bci_callback: {e}")
        flash("Error al procesar la respuesta de BCI")
        return redirect(url_for("index"))

@app.route("/bci/accounts")
@login_required
def bci_accounts():
    """Obtiene las cuentas del usuario desde BCI"""
    try:
        access_token = session.get('bci_access_token')
        if not access_token:
            flash("No hay token de acceso de BCI. Por favor, autoriza primero.")
            return redirect(url_for("bci_auth"))
        
        # Hacer la solicitud a la API de BCI
        accounts_url = "https://apiprogram.bci.cl/sandbox/v1/api-accounts/accounts"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(accounts_url, headers=headers)
        if response.status_code != 200:
            flash("Error al obtener las cuentas de BCI")
            return redirect(url_for("index"))
        
        accounts = response.json()
        return render_template("bci_accounts.html", accounts=accounts, active_page="bci")
        
    except Exception as e:
        logging.error(f"Error en bci_accounts: {e}")
        flash("Error al obtener las cuentas de BCI")
        return redirect(url_for("index"))

# Registro de blueprints
app.register_blueprint(transferencias_bp, url_prefix="/transferencias")
app.register_blueprint(pedidos_bp, url_prefix="/pedidos")
app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(grafico_bp, url_prefix="/grafico")

def get_current_datetime():
    """Helper function to get current datetime in local timezone"""
    return datetime.now(local_tz)

def format_datetime_with_timezone(dt):
    """Helper function to format datetime with timezone"""
    if dt is None:
        return ""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = local_tz.localize(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")

# Agregar filtro para formatear moneda
@app.template_filter('format_currency')
def format_currency(value):
    if value is None:
        return ""
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return str(value)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)