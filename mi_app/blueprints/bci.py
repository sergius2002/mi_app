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
import jwt
import time
import base64

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

def generate_jwt():
    """Genera un token JWT para la autenticación con BCI"""
    try:
        # Crear el payload del JWT
        payload = {
            'iss': os.getenv('BCI_CLIENT_ID'),
            'sub': os.getenv('BCI_CLIENT_ID'),
            'aud': os.getenv('BCI_API_BASE_URL'),
            'exp': int(time.time()) + 300,  # 5 minutos de expiración
            'iat': int(time.time()),
            'jti': str(uuid.uuid4())
        }
        
        # Crear el header del JWT
        headers = {
            'alg': 'RS256',
            'typ': 'JWT',
            'kid': os.getenv('BCI_CLIENT_ID')
        }
        
        # Obtener la clave privada
        private_key_path = os.path.join(os.path.dirname(__file__), 'bci_private_key.pem')
        with open(private_key_path, 'r') as key_file:
            private_key = key_file.read()
        
        # Generar el token JWT
        token = jwt.encode(
            payload,
            private_key,
            algorithm='RS256',
            headers=headers
        )
        
        logger.info("Token JWT generado correctamente")
        logger.info(f"Token JWT: {token}")
        return token
        
    except Exception as e:
        logger.error(f"Error al generar JWT: {str(e)}")
        raise

@bci_bp.route("/auth")
def auth():
    """Inicia el proceso de autorización OAuth con BCI"""
    try:
        logger.info("Iniciando proceso de autorización BCI")
        
        # Verificar variables de entorno
        required_vars = ['BCI_API_BASE_URL', 'BCI_CLIENT_ID', 'BCI_REDIRECT_URI', 'BCI_CLIENT_SECRET']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            error_msg = f"Faltan variables de entorno requeridas: {', '.join(missing_vars)}"
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 500
            
        logger.info("Variables de entorno verificadas correctamente")
        logger.info(f"BCI_API_BASE_URL: {os.getenv('BCI_API_BASE_URL')}")
        logger.info(f"BCI_CLIENT_ID: {os.getenv('BCI_CLIENT_ID')}")
        logger.info(f"BCI_REDIRECT_URI: {os.getenv('BCI_REDIRECT_URI')}")

        # Paso 1: Obtener token de acceso
        token_url = f"{os.getenv('BCI_API_BASE_URL')}/v1/api-oauth/token"
        token_data = {
            'grant_type': 'client_credentials',
            'redirect_uri': os.getenv('BCI_REDIRECT_URI'),
            'scope': 'access-requests',
            'client_assertion': generate_jwt()  # JWT con iss y credentials
        }
        
        logger.info("Solicitando token de acceso...")
        token_response = requests.post(
            token_url,
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if token_response.status_code != 200:
            logger.error(f"Error al obtener token de acceso: {token_response.text}")
            return jsonify({'error': f"Error al obtener token de acceso: {token_response.text}"}), token_response.status_code
            
        access_token = token_response.json().get('access_token')
        logger.info("Token de acceso obtenido correctamente")
        
        # Paso 2: Solicitar AccessRequest
        access_request_url = f"{os.getenv('BCI_API_BASE_URL')}/v1/api-access-requests/requests"
        access_request_data = {
            "Data": {
                "TppId": os.getenv('BCI_CLIENT_ID'),
                "Scope": "customers"
            }
        }
        
        logger.info("Solicitando AccessRequest...")
        access_request_response = requests.post(
            access_request_url,
            json=access_request_data,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
        )
        
        if access_request_response.status_code != 200:
            logger.error(f"Error al solicitar AccessRequest: {access_request_response.text}")
            return jsonify({'error': f"Error al solicitar AccessRequest: {access_request_response.text}"}), access_request_response.status_code
            
        request_id = access_request_response.json()['Request']['RequestId']
        logger.info(f"AccessRequest obtenido correctamente. RequestId: {request_id}")
        
        # Paso 3: Llamada a OAuth Authorize
        state = str(uuid.uuid1())
        nonce = str(uuid.uuid4())
        
        # Crear objeto request para el JWT de autorización
        request_obj = {
            "iss": "https://api.openbank.com",
            "response_type": "code",
            "client_id": os.getenv('BCI_CLIENT_ID'),
            "redirect_uri": os.getenv('BCI_REDIRECT_URI'),
            "scope": "customers",
            "state": state,
            "nonce": nonce,
            "claims": {
                "id_token": {
                    "openbanking_intent_id": {
                        "value": f"urn:openbanking:intent:customers:{request_id}",
                        "essential": True
                    },
                    "acr": {
                        "essential": True
                    }
                }
            }
        }
        
        # Generar JWT para autorización
        auth_jwt = generate_auth_jwt(request_obj)
        
        # Generar URL de autorización
        auth_url = (
            f"{os.getenv('BCI_API_BASE_URL')}/v1/api-oauth/authorize"
            f"?response_type=code"
            f"&client_id={os.getenv('BCI_CLIENT_ID')}"
            f"&redirect_uri={quote(os.getenv('BCI_REDIRECT_URI'))}"
            f"&scope=customers"
            f"&state={state}"
            f"&nonce={nonce}"
            f"&request={quote(auth_jwt)}"
        )
        
        logger.info(f"URL de autorización generada: {auth_url}")
        
        # Hacer la solicitud de autorización
        headers = {
            'Content-Type': 'application/json',
            'x-apikey': os.getenv('BCI_CLIENT_ID')
        }
        
        logger.info("Realizando solicitud de autorización...")
        response = requests.post(auth_url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Error en la solicitud de autorización: {response.status_code} - {response.text}")
            return jsonify({'error': f"Error en la solicitud de autorización: {response.text}"}), response.status_code
            
        # Si la respuesta es exitosa, redirigir a la URL de autorización
        return redirect(auth_url)
        
    except Exception as e:
        logger.error(f"Error en auth: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def generate_auth_jwt(payload):
    """Genera un JWT para la autorización OAuth"""
    try:
        # Obtener la clave privada
        private_key_path = os.path.join(os.path.dirname(__file__), 'bci_private_key.pem')
        with open(private_key_path, 'r') as key_file:
            private_key = key_file.read()
            
        # Crear el header del JWT
        header = {
            'alg': 'RS256',
            'typ': 'JWT'
        }
        
        # Generar el JWT
        token = jwt.encode(
            payload,
            private_key,
            algorithm='RS256',
            headers=header
        )
        
        logger.info("JWT de autorización generado correctamente")
        return token
        
    except Exception as e:
        logger.error(f"Error generando JWT de autorización: {str(e)}", exc_info=True)
        raise

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
        
        # Paso 4: Obtención del Authorization Token
        token_url = f"{os.getenv('BCI_API_BASE_URL')}/v1/api-oauth/token"
        
        # Generar JWT para client_assertion
        client_assertion = generate_jwt()
        
        token_data = {
            'grant_type': 'authorization_code',
            'redirect_uri': os.getenv('BCI_REDIRECT_URI'),
            'client_id': os.getenv('BCI_CLIENT_ID'),
            'code': auth_code,
            'scope': 'customers',
            'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
            'client_assertion': client_assertion
        }
        
        logging.info("Solicitando token de acceso...")
        response = requests.post(
            token_url, 
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
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