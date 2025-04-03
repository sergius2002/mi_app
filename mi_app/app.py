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
app.register_blueprint(bci_bp)

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
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(SELL_API_URL, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data
            else:
                logging.error(f"Error al obtener tasas: {response.status}")
                return None

def actualizar_datos():
    global tiempos, precios_banesco, precios_bank_transfer, precios_mercantil, precios_provincial
    
    # Reiniciar datos diarios si es necesario
    reiniciar_datos_diarios()
    
    # Obtener la hora actual en la zona horaria local
    now = datetime.now(local_tz)
    tiempo_actual = now.strftime("%H:%M:%S")
    
    # Obtener tasas para cada banco
    bancos = ["Banesco", "Bank Transfer", "Mercantil", "Provincial"]
    tasas = asyncio.run(obtener_tasa_usdt_ves(bancos))
    
    if tasas:
        # Procesar datos para cada banco
        for banco in bancos:
            if banco == "Banesco":
                precios_banesco.append(tasas.get("Banesco", 0))
            elif banco == "Bank Transfer":
                precios_bank_transfer.append(tasas.get("Bank Transfer", 0))
            elif banco == "Mercantil":
                precios_mercantil.append(tasas.get("Mercantil", 0))
            elif banco == "Provincial":
                precios_provincial.append(tasas.get("Provincial", 0))
        
        # Añadir el tiempo actual
        tiempos.append(tiempo_actual)
        
        # Guardar en CSV
        guardar_datos_csv(
            tiempo_actual,
            precios_banesco[-1],
            precios_bank_transfer[-1],
            precios_mercantil[-1],
            precios_provincial[-1]
        )
        
        # Limitar el número de puntos en el gráfico
        max_points = 100
        if len(tiempos) > max_points:
            tiempos = tiempos[-max_points:]
            precios_banesco = precios_banesco[-max_points:]
            precios_bank_transfer = precios_bank_transfer[-max_points:]
            precios_mercantil = precios_mercantil[-max_points:]
            precios_provincial = precios_provincial[-max_points:]
        
        logging.info("Datos actualizados correctamente")
    else:
        logging.error("No se pudieron obtener las tasas")

def generar_grafico():
    plt.figure(figsize=(10, 6))
    
    # Asegurarse de que todos los arrays tengan la misma longitud
    min_len = min(len(tiempos), len(precios_banesco), len(precios_bank_transfer), len(precios_mercantil), len(precios_provincial))
    tiempos_plot = tiempos[-min_len:]
    precios_banesco_plot = precios_banesco[-min_len:]
    precios_bank_transfer_plot = precios_bank_transfer[-min_len:]
    precios_mercantil_plot = precios_mercantil[-min_len:]
    precios_provincial_plot = precios_provincial[-min_len:]
    
    # Graficar cada banco con un color diferente
    plt.plot(tiempos_plot, precios_banesco_plot, label='Banesco', color='blue')
    plt.plot(tiempos_plot, precios_bank_transfer_plot, label='Bank Transfer', color='green')
    plt.plot(tiempos_plot, precios_mercantil_plot, label='Mercantil', color='red')
    plt.plot(tiempos_plot, precios_provincial_plot, label='Provincial', color='purple')
    
    # Configurar el gráfico
    plt.title('Tasas de USDT a VES en tiempo real')
    plt.xlabel('Hora')
    plt.ylabel('Precio (VES)')
    plt.legend()
    plt.grid(True)
    
    # Rotar las etiquetas del eje x para mejor legibilidad
    plt.xticks(rotation=45)
    
    # Ajustar el layout para evitar que las etiquetas se corten
    plt.tight_layout()
    
    # Guardar el gráfico en un buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    
    return buf

@grafico_bp.route("/plot.png")
@login_required
def plot_png():
    actualizar_datos()
    buf = generar_grafico()
    return send_file(buf, mimetype='image/png')

@grafico_bp.route("/")
@login_required
def index():
    return render_template("grafico.html")

def generar_hash_transferencia(transferencia):
    """Genera un hash único para una transferencia basado en sus atributos"""
    hash_data = f"{transferencia['cliente']}{transferencia['empresa']}{transferencia['rut']}{transferencia['monto']}{transferencia['fecha']}"
    return hashlib.md5(hash_data.encode()).hexdigest()

def user_allowed(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "email" not in session:
            flash("Por favor, inicia sesión.")
            return redirect(url_for("login"))
            
        try:
            response = supabase.table("allowed_users").select("email").eq("email", session["email"]).execute()
            if not response.data:
                flash("No tienes permiso para acceder a esta sección.")
                return redirect(url_for("index"))
        except Exception as e:
            logging.error("Error al verificar permisos de usuario: %s", e)
            flash("Error al verificar permisos.")
            return redirect(url_for("index"))
            
        return f(*args, **kwargs)
    return wrapper

def format_monto(value):
    """Formatea un monto como moneda"""
    if value is None:
        return "0"
    return f"{value:,.0f}"

def format_date(value):
    """Formatea una fecha como dd/mm/yyyy"""
    if value is None:
        return ""
    return value.strftime("%d/%m/%Y")

def format_time(value):
    """Formatea una hora como HH:MM"""
    if value is None:
        return ""
    return value.strftime("%H:%M")

@app.template_filter("format_fecha_detec")
def format_fecha_detec(value):
    """Formatea una fecha de detección como dd/mm/yyyy HH:MM"""
    if value is None:
        return ""
    return value.strftime("%d/%m/%Y %H:%M")

def format_clp(value):
    """Formatea un monto en CLP"""
    if value is None:
        return "0"
    return f"${value:,.0f}"

def format_int(value):
    """Formatea un número como entero"""
    if value is None:
        return "0"
    return f"{value:,.0f}"

def format_datetime(value):
    """Formatea una fecha y hora como dd/mm/yyyy HH:MM"""
    if value is None:
        return ""
    return value.strftime("%d/%m/%Y %H:%M")

def format_decimal(value, decimals=3):
    """Formatea un número decimal con la cantidad especificada de decimales"""
    if value is None:
        return "0"
    return f"{value:,.{decimals}f}"

def filter_transferencias(query):
    """Aplica filtros a la consulta de transferencias"""
    # Filtro por cliente
    if "cliente" in request.args and request.args["cliente"]:
        query = query.eq("cliente", request.args["cliente"])
    
    # Filtro por empresa
    if "empresa" in request.args and request.args["empresa"]:
        empresas = request.args.getlist("empresa")
        if "Todas" not in empresas:
            query = query.in_("empresa", empresas)
    
    # Filtro por rut
    if "rut" in request.args and request.args["rut"]:
        query = query.eq("rut", request.args["rut"])
    
    # Filtro por monto
    if "monto" in request.args and request.args["monto"]:
        query = query.eq("monto", request.args["monto"])
    
    # Filtro por estado de verificación
    if "verificada" in request.args and request.args["verificada"] != "":
        query = query.eq("verificada", request.args["verificada"] == "true")
    
    return query

def filter_pedidos(query):
    """Aplica filtros a la consulta de pedidos"""
    # Filtro por cliente
    if "cliente" in request.args and request.args["cliente"]:
        query = query.eq("cliente", request.args["cliente"])
    
    # Filtro por estado
    if "estado" in request.args and request.args["estado"]:
        query = query.eq("estado", request.args["estado"])
    
    return query

def apply_ordering(query, sort_params):
    """Aplica ordenamiento a la consulta"""
    for sort_param in sort_params:
        if sort_param in request.args and request.args[sort_param]:
            order = request.args.get(f"order{sort_param[-1]}", "asc")
            query = query.order(request.args[sort_param], desc=(order == "desc"))
    return query

@transferencias_bp.route("/")
@login_required
def index():
    """Muestra la lista de transferencias"""
    try:
        # Obtener lista de clientes únicos
        clientes_response = supabase.table("transferencias").select("cliente").execute()
        clientes = sorted(list(set(t["cliente"] for t in clientes_response.data)))
        
        # Obtener lista de empresas únicas
        empresas_response = supabase.table("transferencias").select("empresa").execute()
        empresas = sorted(list(set(t["empresa"] for t in empresas_response.data)))
        empresas.insert(0, "Todas")
        
        # Construir la consulta base
        query = supabase.table("transferencias").select("*")
        
        # Aplicar filtros
        query = filter_transferencias(query)
        
        # Aplicar ordenamiento
        sort_params = ["sort1", "sort2", "sort3"]
        query = apply_ordering(query, sort_params)
        
        # Ejecutar la consulta
        response = query.execute()
        transferencias = response.data
        
        return render_template(
            "transferencias.html",
            transfers=transferencias,
            cliente=clientes,
            empresas=empresas,
            active_page="transferencias"
        )
    except Exception as e:
        logging.error(f"Error en index de transferencias: {str(e)}")
        flash("Error al cargar las transferencias", "error")
        return redirect(url_for("index"))

@transferencias_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    """Crea una nueva transferencia"""
    if request.method == "POST":
        try:
            data = {
                "cliente": request.form["cliente"],
                "empresa": request.form["empresa"],
                "rut": request.form["rut"],
                "monto": float(request.form["monto"]),
                "fecha": datetime.strptime(request.form["fecha"], "%Y-%m-%d"),
                "fecha_detec": datetime.now(),
                "verificada": False,
                "manual": True
            }
            
            response = supabase.table("transferencias").insert(data).execute()
            flash("Transferencia creada exitosamente", "success")
            return redirect(url_for("transferencias.index"))
        except Exception as e:
            logging.error(f"Error al crear transferencia: {str(e)}")
            flash("Error al crear la transferencia", "error")
            return redirect(url_for("transferencias.index"))
    
    return render_template("nuevo_transferencia.html", active_page="transferencias")

@transferencias_bp.route("/editar/<transfer_id>", methods=["GET", "POST"])
@login_required
def editar_transferencia(transfer_id):
    """Edita una transferencia existente"""
    if request.method == "POST":
        try:
            data = {
                "cliente": request.form["cliente"],
                "empresa": request.form["empresa"],
                "rut": request.form["rut"],
                "monto": float(request.form["monto"]),
                "fecha": datetime.strptime(request.form["fecha"], "%Y-%m-%d")
            }
            
            response = supabase.table("transferencias").update(data).eq("id", transfer_id).execute()
            flash("Transferencia actualizada exitosamente", "success")
            return redirect(url_for("transferencias.index"))
        except Exception as e:
            logging.error(f"Error al actualizar transferencia: {str(e)}")
            flash("Error al actualizar la transferencia", "error")
            return redirect(url_for("transferencias.index"))
    
    try:
        response = supabase.table("transferencias").select("*").eq("id", transfer_id).execute()
        transferencia = response.data[0]
        return render_template("editar_transferencia.html", transfer=transferencia, active_page="transferencias")
    except Exception as e:
        logging.error(f"Error al cargar transferencia: {str(e)}")
        flash("Error al cargar la transferencia", "error")
        return redirect(url_for("transferencias.index"))

@pedidos_bp.route("/")
@login_required
def index():
    """Muestra la lista de pedidos"""
    try:
        # Obtener lista de clientes únicos
        clientes_response = supabase.table("pedidos").select("cliente").execute()
        clientes = sorted(list(set(p["cliente"] for p in clientes_response.data)))
        
        # Construir la consulta base
        query = supabase.table("pedidos").select("*")
        
        # Aplicar filtros
        query = filter_pedidos(query)
        
        # Aplicar ordenamiento
        sort_params = ["sort1", "sort2", "sort3"]
        query = apply_ordering(query, sort_params)
        
        # Ejecutar la consulta
        response = query.execute()
        pedidos = response.data
        
        return render_template(
            "pedidos.html",
            pedidos=pedidos,
            clientes=clientes,
            active_page="pedidos"
        )
    except Exception as e:
        logging.error(f"Error en index de pedidos: {str(e)}")
        flash("Error al cargar los pedidos", "error")
        return redirect(url_for("index"))

@pedidos_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    """Crea un nuevo pedido"""
    if request.method == "POST":
        try:
            data = {
                "cliente": request.form["cliente"],
                "producto": request.form["producto"],
                "cantidad": int(request.form["cantidad"]),
                "precio": float(request.form["precio"]),
                "fecha": datetime.now(),
                "estado": "pendiente"
            }
            
            response = supabase.table("pedidos").insert(data).execute()
            flash("Pedido creado exitosamente", "success")
            return redirect(url_for("pedidos.index"))
        except Exception as e:
            logging.error(f"Error al crear pedido: {str(e)}")
            flash("Error al crear el pedido", "error")
            return redirect(url_for("pedidos.index"))
    
    return render_template("nuevo_pedido.html", active_page="pedidos")

@pedidos_bp.route("/editar/<pedido_id>", methods=["GET", "POST"])
@login_required
def editar(pedido_id):
    """Edita un pedido existente"""
    if request.method == "POST":
        try:
            data = {
                "cliente": request.form["cliente"],
                "producto": request.form["producto"],
                "cantidad": int(request.form["cantidad"]),
                "precio": float(request.form["precio"]),
                "estado": request.form["estado"]
            }
            
            response = supabase.table("pedidos").update(data).eq("id", pedido_id).execute()
            flash("Pedido actualizado exitosamente", "success")
            return redirect(url_for("pedidos.index"))
        except Exception as e:
            logging.error(f"Error al actualizar pedido: {str(e)}")
            flash("Error al actualizar el pedido", "error")
            return redirect(url_for("pedidos.index"))
    
    try:
        response = supabase.table("pedidos").select("*").eq("id", pedido_id).execute()
        pedido = response.data[0]
        return render_template("editar_pedido.html", pedido=pedido, active_page="pedidos")
    except Exception as e:
        logging.error(f"Error al cargar pedido: {str(e)}")
        flash("Error al cargar el pedido", "error")
        return redirect(url_for("pedidos.index"))

@dashboard_bp.route("/")
@login_required
@cache.cached(timeout=60, query_string=True)
def index():
    """Muestra el dashboard principal"""
    try:
        # Obtener datos de transferencias
        transferencias_response = supabase.table("transferencias").select("*").execute()
        transferencias = transferencias_response.data
        
        # Calcular totales
        total_transferencias = sum(t["monto"] for t in transferencias)
        total_verificadas = sum(t["monto"] for t in transferencias if t["verificada"])
        
        # Obtener datos de pedidos
        pedidos_response = supabase.table("pedidos").select("*").execute()
        pedidos = pedidos_response.data
        
        # Calcular totales de pedidos
        total_pedidos = len(pedidos)
        total_pendientes = len([p for p in pedidos if p["estado"] == "pendiente"])
        
        return render_template(
            "dashboard.html",
            total_transferencias=total_transferencias,
            total_verificadas=total_verificadas,
            total_pedidos=total_pedidos,
            total_pendientes=total_pendientes,
            active_page="dashboard"
        )
    except Exception as e:
        logging.error(f"Error en dashboard: {str(e)}")
        flash("Error al cargar el dashboard", "error")
        return redirect(url_for("index"))

@dashboard_bp.route("/detalle/<cliente>")
@login_required
@cache.cached(timeout=60, query_string=True)
def detalle(cliente):
    """Muestra el detalle de un cliente en el dashboard"""
    try:
        # Obtener transferencias del cliente
        transferencias_response = supabase.table("transferencias").select("*").eq("cliente", cliente).execute()
        transferencias = transferencias_response.data
        
        # Obtener pedidos del cliente
        pedidos_response = supabase.table("pedidos").select("*").eq("cliente", cliente).execute()
        pedidos = pedidos_response.data
        
        return render_template(
            "dashboard_detalle.html",
            cliente=cliente,
            transferencias=transferencias,
            pedidos=pedidos,
            active_page="dashboard"
        )
    except Exception as e:
        logging.error(f"Error en detalle de dashboard: {str(e)}")
        flash("Error al cargar el detalle del cliente", "error")
        return redirect(url_for("dashboard.index"))

@admin_bp.route("/")
@login_required
@user_allowed
def index():
    """Muestra la página principal del módulo de administración"""
    return render_template("admin.html", active_page="admin")

@admin_bp.route("/calcular_margen", methods=["GET"])
@login_required
@user_allowed
def calcular_margen():
    """Calcula el margen de ganancia"""
    try:
        # Obtener datos necesarios para el cálculo
        response = supabase.table("configuracion").select("*").execute()
        config = response.data[0]
        
        margen = (config["precio_venta"] - config["precio_compra"]) / config["precio_compra"] * 100
        
        return render_template("margen_resultado.html", margen=margen, active_page="admin")
    except Exception as e:
        logging.error(f"Error al calcular margen: {str(e)}")
        flash("Error al calcular el margen", "error")
        return redirect(url_for("admin.index"))

@admin_bp.route("/tasa_compras", methods=["GET"])
@login_required
@user_allowed
def tasa_compras():
    """Muestra la tasa de compras"""
    try:
        # Obtener datos de compras
        response = supabase.table("compras").select("*").execute()
        compras = response.data
        
        return render_template("tasa_compras.html", compras=compras, active_page="admin")
    except Exception as e:
        logging.error(f"Error al cargar tasa de compras: {str(e)}")
        flash("Error al cargar la tasa de compras", "error")
        return redirect(url_for("admin.index"))

@admin_bp.route("/ingresar_usdt", methods=["GET", "POST"])
@login_required
@user_allowed
def ingresar_usdt():
    """Permite ingresar USDT"""
    if request.method == "POST":
        try:
            data = {
                "cantidad": float(request.form["cantidad"]),
                "precio": float(request.form["precio"]),
                "fecha": datetime.now()
            }
            
            response = supabase.table("usdt").insert(data).execute()
            flash("USDT ingresado exitosamente", "success")
            return redirect(url_for("admin.index"))
        except Exception as e:
            logging.error(f"Error al ingresar USDT: {str(e)}")
            flash("Error al ingresar USDT", "error")
            return redirect(url_for("admin.index"))
    
    return render_template("ingresar_usdt.html", active_page="admin")

@admin_bp.route("/tasa_actual", methods=["GET"])
@login_required
@user_allowed
def tasa_actual():
    """Muestra la tasa actual"""
    try:
        # Obtener datos de tasas
        response = supabase.table("tasas").select("*").order("fecha", desc=True).limit(1).execute()
        tasa = response.data[0] if response.data else None
        
        return render_template("tasa_actual.html", tasa=tasa, active_page="admin")
    except Exception as e:
        logging.error(f"Error al cargar tasa actual: {str(e)}")
        flash("Error al cargar la tasa actual", "error")
        return redirect(url_for("admin.index"))

@admin_bp.route("/cierre_dia", methods=["GET", "POST"])
@login_required
@user_allowed
def cierre_dia():
    """Realiza el cierre del día"""
    if request.method == "POST":
        try:
            # Obtener datos del día
            fecha = datetime.now().strftime("%Y-%m-%d")
            transferencias_response = supabase.table("transferencias").select("*").eq("fecha", fecha).execute()
            transferencias = transferencias_response.data
            
            pedidos_response = supabase.table("pedidos").select("*").eq("fecha", fecha).execute()
            pedidos = pedidos_response.data
            
            # Calcular totales
            total_transferencias = sum(t["monto"] for t in transferencias)
            total_pedidos = sum(p["precio"] * p["cantidad"] for p in pedidos)
            
            # Guardar cierre
            data = {
                "fecha": fecha,
                "total_transferencias": total_transferencias,
                "total_pedidos": total_pedidos
            }
            
            response = supabase.table("cierre_dia").insert(data).execute()
            flash("Cierre del día realizado exitosamente", "success")
            return redirect(url_for("admin.index"))
        except Exception as e:
            logging.error(f"Error al realizar cierre del día: {str(e)}")
            flash("Error al realizar el cierre del día", "error")
            return redirect(url_for("admin.index"))
    
    return render_template("cierre_dia.html", active_page="admin")

@admin_bp.route("/margen", methods=["GET"])
@login_required
@user_allowed
def margen():
    """Muestra el margen de ganancia"""
    try:
        # Obtener datos de margen
        response = supabase.table("margen").select("*").order("fecha", desc=True).limit(1).execute()
        margen = response.data[0] if response.data else None
        
        return render_template("margen.html", margen=margen, active_page="admin")
    except Exception as e:
        logging.error(f"Error al cargar margen: {str(e)}")
        flash("Error al cargar el margen", "error")
        return redirect(url_for("admin.index"))

@admin_bp.route("/resumen_compras_usdt", methods=["GET"])
@login_required
@user_allowed
def resumen_compras_usdt():
    """Muestra el resumen de compras de USDT"""
    try:
        # Obtener datos de compras
        response = supabase.table("compras_usdt").select("*").execute()
        compras = response.data
        
        return render_template("compras_utilidades.html", compras=compras, active_page="admin")
    except Exception as e:
        logging.error(f"Error al cargar resumen de compras: {str(e)}")
        flash("Error al cargar el resumen de compras", "error")
        return redirect(url_for("admin.index"))

@app.route("/")
def index():
    """Muestra la página principal"""
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Maneja el inicio de sesión"""
    if request.method == "POST":
        try:
            email = request.form["email"]
            password = request.form["password"]
            
            # Verificar credenciales
            response = supabase.table("users").select("*").eq("email", email).eq("password", password).execute()
            if response.data:
                session["user_id"] = response.data[0]["id"]
                session["email"] = email
                flash("Inicio de sesión exitoso", "success")
                return redirect(url_for("index"))
            else:
                flash("Credenciales inválidas", "error")
        except Exception as e:
            logging.error(f"Error en login: {str(e)}")
            flash("Error al iniciar sesión", "error")
    
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    """Cierra la sesión del usuario"""
    session.clear()
    flash("Sesión cerrada exitosamente", "success")
    return redirect(url_for("login"))

@app.route("/update/<transfer_id>", methods=["POST"])
@login_required
def update_transfer(transfer_id):
    """Actualiza una transferencia"""
    try:
        nuevo_valor = request.form.get("nuevo_valor") == "1"
        response = supabase.table("transferencias").update({"verificada": nuevo_valor}).eq("id", transfer_id).execute()
        flash("Transferencia actualizada exitosamente", "success")
        return redirect(url_for("transferencias.index"))
    except Exception as e:
        logging.error(f"Error al actualizar transferencia: {str(e)}")
        flash("Error al actualizar la transferencia", "error")
        return redirect(url_for("transferencias.index"))

@app.template_filter('format_currency')
def format_currency(value):
    """Formatea un valor como moneda"""
    if value is None:
        return "0"
    return f"${value:,.0f}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)