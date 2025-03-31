# blueprints/utilidades.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import logging
from supabase import create_client, Client
from datetime import datetime
import hashlib
from functools import wraps

# -----------------------------------------------------------------------------
# Definición del Blueprint
# -----------------------------------------------------------------------------
utilidades_bp = Blueprint('utilidades', __name__, url_prefix='/utilidades')

# -----------------------------------------------------------------------------
# Configuración de Supabase
# -----------------------------------------------------------------------------
SUPABASE_URL = "https://tmimwpzxmtezopieqzcl.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRtaW13cHp4bXRlem9waWVxemNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzY4NTI5NzQsImV4cCI6MjA1MjQyODk3NH0."
    "tTrdPaiPAkQbF_JlfOOWTQwSs3C_zBbFDZECYzPP-Ho"
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# -----------------------------------------------------------------------------
# Decorador de login (puedes reutilizar el que ya tienes)
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
# Rutas del Módulo de Utilidades
# -----------------------------------------------------------------------------

@utilidades_bp.route("/")
@login_required
def index():
    # Vista principal del módulo de utilidades
    return render_template("utilidades/utilidades.html", active_page="utilidades")


@utilidades_bp.route("/compras", methods=["GET", "POST"])
@login_required
def compras():
    """
    Permite seleccionar una fecha para filtrar la tabla "compras" en Supabase.
    Se filtra por:
      - fiat = 'VES'
      - tradetype = 'SELL'
    Se suma la columna "totalprice" de los registros correspondientes al día seleccionado
    y se formatea el resultado con separador de miles y sin decimales.
    """
    if request.method == "POST":
        # Recibimos la fecha seleccionada y redirigimos usando query string
        fecha = request.form.get("fecha")
        return redirect(url_for("utilidades.compras", fecha=fecha))

    # Para el método GET, se obtiene la fecha del query string (si existe)
    fecha = request.args.get("fecha")

    # Preparamos la consulta filtrando por fiat y tradetype
    query = supabase.table("compras") \
        .select("totalprice") \
        .eq("fiat", "VES") \
        .eq("tradetype", "SELL")

    # Si se ha seleccionado una fecha, filtramos también por el campo "createtime"
    if fecha:
        # Asumimos que "createtime" almacena la fecha y hora en formato ISO (YYYY-MM-DDThh:mm:ss)
        inicio = fecha + "T00:00:00"
        fin = fecha + "T23:59:59"
        query = query.gte("createtime", inicio).lte("createtime", fin)

    response = query.execute()
    total = sum(item.get("totalprice", 0) for item in response.data) if response.data is not None else 0
    # Formatear el total: separador de miles y sin decimales (ej. 1234567 se mostrará como "1.234.567")
    formatted_total = format(total, ",.0f").replace(",", ".")

    return render_template("utilidades/compras_resultado.html", total=formatted_total, fecha=fecha,
                           active_page="utilidades")
