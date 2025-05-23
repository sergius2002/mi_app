from flask import Blueprint, render_template, redirect, url_for, request, session, flash, jsonify
import requests
import urllib.parse
import os
import logging
from functools import wraps
import json
from datetime import datetime, timedelta
import uuid
from urllib.parse import quote

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('bci_blueprint')

bci_bp = Blueprint('bci', __name__, template_folder='../templates')

def bci_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'bci_access_token' not in session:
            flash('Por favor, autoriza primero con BCI', 'warning')
            return redirect(url_for('bci.auth'))
        return f(*args, **kwargs)
    return decorated_function

@bci_bp.route("/auth")
def auth():
    """Inicia el proceso de autorización OAuth con BCI"""
    try:
        logger.info("Iniciando proceso de autorización BCI")
        
        # Verificar variables de entorno
        required_vars = ['BCI_API_BASE_URL', 'BCI_CLIENT_ID', 'BCI_REDIRECT_URI', 'BCI_API_KEY']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            error_msg = f"Faltan variables de entorno requeridas: {', '.join(missing_vars)}"
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 500
            
        logger.info("Variables de entorno verificadas correctamente")
        logger.info(f"BCI_API_BASE_URL: {os.getenv('BCI_API_BASE_URL')}")
        logger.info(f"BCI_CLIENT_ID: {os.getenv('BCI_CLIENT_ID')}")
        logger.info(f"BCI_REDIRECT_URI: {os.getenv('BCI_REDIRECT_URI')}")
        logger.info(f"BCI_API_KEY: {os.getenv('BCI_API_KEY')}")

        # Crear objeto request
        request_obj = {
            "openbanking_intent_id": {
                "value": f"urn:openbank:intent:customers:{str(uuid.uuid4())}",
                "essential": True
            },
            "acr": {
                "essential": True,
                "values": ["urn:openbank:cds:2.0"]
            }
        }
        
        logger.info(f"Objeto request creado: {request_obj}")
        
        # Convertir a JSON y codificar
        request_json = json.dumps(request_obj)
        logger.info(f"JSON generado: {request_json}")
        
        request_encoded = quote(request_json)
        logger.info(f"JSON codificado: {request_encoded}")
        
        # Generar URL de autorización
        auth_url = (
            f"{os.getenv('BCI_API_BASE_URL')}/v1/api-oauth/authorize"
            f"?response_type=code"
            f"&client_id={os.getenv('BCI_CLIENT_ID')}"
            f"&redirect_uri={quote(os.getenv('BCI_REDIRECT_URI'))}"
            f"&scope=customers+accounts+transactions+payments"
            f"&state=bci_auth"
            f"&nonce=bci_nonce"
            f"&request={request_encoded}"
        )
        
        logger.info(f"URL de autorización generada: {auth_url}")
        
        # Verificar que la URL contiene el parámetro request
        if 'request=' not in auth_url:
            error_msg = "La URL de autorización no contiene el parámetro request"
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 500
            
        # Asegurarse de que la URL esté correctamente codificada
        auth_url = auth_url.replace(' ', '+')
        logger.info(f"URL de autorización final: {auth_url}")
        
        # Hacer la solicitud con el API Key
        headers = {
            'x-api-key': os.getenv('BCI_API_KEY'),
            'Content-Type': 'application/json'
        }
        
        # Hacer una solicitud GET a la URL de autorización
        response = requests.get(auth_url, headers=headers)
        logger.info(f"Respuesta de la API: {response.status_code} - {response.text}")
        
        if response.status_code == 200:
            return redirect(auth_url)
        else:
            error_msg = f"Error en la autorización: {response.status_code} - {response.text}"
            logger.error(error_msg)
            return jsonify({'error': error_msg}), response.status_code
            
    except Exception as e:
        logger.error(f"Error en auth: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@bci_bp.route('/callback')
def callback():
    """Maneja la respuesta de autorización de BCI"""
    try:
        auth_code = request.args.get('code')
        if not auth_code:
            error = request.args.get('error')
            error_description = request.args.get('error_description')
            logging.error(f"Error en callback: {error} - {error_description}")
            flash(f'Error en la autorización de BCI: {error} - {error_description}', 'error')
            return redirect(url_for('index'))
        
        token_url = f"{os.getenv('BCI_API_BASE_URL')}/api-oauth/token"
        token_data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': os.getenv('BCI_REDIRECT_URI'),
            'client_id': os.getenv('BCI_CLIENT_ID'),
            'client_secret': os.getenv('BCI_CLIENT_SECRET')
        }
        
        logging.info("Solicitando token de acceso...")
        response = requests.post(token_url, data=token_data)
        
        if response.status_code != 200:
            logging.error(f"Error al obtener token: {response.status_code} - {response.text}")
            flash('Error al obtener el token de acceso de BCI', 'error')
            return redirect(url_for('index'))
        
        token_data = response.json()
        session['bci_access_token'] = token_data.get('access_token')
        session['bci_refresh_token'] = token_data.get('refresh_token')
        session['bci_token_expires_in'] = token_data.get('expires_in')
        
        flash('Autorización con BCI completada exitosamente', 'success')
        return redirect(url_for('bci.accounts'))
        
    except Exception as e:
        logging.error(f"Error en bci_callback: {str(e)}")
        flash('Error al procesar la respuesta de BCI', 'error')
        return redirect(url_for('index'))

@bci_bp.route('/accounts')
@bci_required
def accounts():
    """Obtiene las cuentas del usuario desde BCI"""
    try:
        access_token = session.get('bci_access_token')
        accounts_url = f"{os.getenv('BCI_API_BASE_URL')}/api-accounts/accounts"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        logging.info("Solicitando cuentas...")
        response = requests.get(accounts_url, headers=headers)
        
        if response.status_code != 200:
            logging.error(f"Error al obtener cuentas: {response.status_code} - {response.text}")
            flash('Error al obtener las cuentas de BCI', 'error')
            return redirect(url_for('index'))
        
        accounts = response.json()
        return render_template('bci_accounts.html', accounts=accounts, active_page='bci')
        
    except Exception as e:
        logging.error(f"Error en bci_accounts: {str(e)}")
        flash('Error al obtener las cuentas de BCI', 'error')
        return redirect(url_for('index'))

@bci_bp.route('/transactions/<account_id>')
@bci_required
def transactions(account_id):
    """Obtiene las transacciones de una cuenta específica"""
    try:
        access_token = session.get('bci_access_token')
        transactions_url = f"{os.getenv('BCI_API_BASE_URL')}/api-accounts/accounts/{account_id}/transactions"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        logging.info(f"Solicitando transacciones para cuenta {account_id}...")
        response = requests.get(transactions_url, headers=headers)
        
        if response.status_code != 200:
            logging.error(f"Error al obtener transacciones: {response.status_code} - {response.text}")
            flash('Error al obtener las transacciones de BCI', 'error')
            return redirect(url_for('bci.accounts'))
        
        transactions = response.json()
        return render_template('bci_transactions.html', transactions=transactions, account_id=account_id, active_page='bci')
        
    except Exception as e:
        logging.error(f"Error en bci_transactions: {str(e)}")
        flash('Error al obtener las transacciones de BCI', 'error')
        return redirect(url_for('bci.accounts')) 