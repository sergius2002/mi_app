import sys
import os

# Agregar la ruta del entorno virtual
venv_path = '/home/sancristobalspa/mi_app/venv/lib/python3.10/site-packages'
if venv_path not in sys.path:
    sys.path.append(venv_path)

# Cambiar al directorio de la aplicación
app_path = '/home/sancristobalspa/mi_app'
if app_path not in sys.path:
    sys.path.append(app_path)
os.chdir(app_path)

# Importar la aplicación
from app import app as application 