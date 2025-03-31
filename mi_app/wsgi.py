import sys
import os

# Agregar el directorio del proyecto al path de Python
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.append(path)

# Importar la aplicación Flask
from app import app as application 