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

# Configuración de BCI
os.environ['BCI_CLIENT_ID'] = 'XO1F0IQsd5iJHEA0pJTGmAQGAjSGa1k3'
os.environ['BCI_CLIENT_SECRET'] = 'wmcgXFQYAHmnuNJm'
os.environ['BCI_REDIRECT_URI'] = 'https://sancristobalspa.eu.pythonanywhere.com/bci/callback'
os.environ['BCI_API_BASE_URL'] = 'https://apiprogram.bci.cl/sandbox/v1'

# Importar la aplicación
from app import app as application 