# blueprints/margen.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from functools import wraps

# Decorador para requerir que el usuario haya iniciado sesión
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Por favor, inicia sesión.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# Decorador para verificar permisos de usuario (puedes ampliar esta validación si lo requieres)
def user_allowed(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("email"):
            flash("Debes iniciar sesión.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

# Se crea el blueprint llamado "margen" y se especifica la carpeta de templates
margen_bp = Blueprint("margen", __name__, template_folder="../templates")

@margen_bp.route("/margen", methods=["GET"])
@login_required
@user_allowed
def margen():
    return render_template("margen.html", active_page="admin")

@margen_bp.route("/calcular_margen", methods=["GET"])
@login_required
@user_allowed
def calcular_margen():
    fecha = request.args.get("fecha")
    if not fecha:
        flash("Debe seleccionar una fecha para calcular el margen.", "warning")
        return redirect(url_for("margen.margen"))
    # Lógica para calcular el margen (valor de ejemplo)
    margen_calculado = 1234.56
    return render_template("margen_resultado.html", active_page="admin", fecha=fecha, margin=margen_calculado)
