from flask import Blueprint, render_template, redirect, url_for, request, session, flash
import requests
import urllib.parse
import os
import logging
from functools import wraps
import json

bci_bp = Blueprint('bci', __name__, template_folder='../templates')

def bci_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'bci_access_token' not in session:
            flash('Por favor, autoriza primero con BCI', 'warning')
            return redirect(url_for('bci.auth'))
        return f(*args, **kwargs)
    return decorated_function

@bci_bp.route('/auth')
def auth():
    """Inicia el proceso de autorización con BCI"""
    try:
        # Parámetros requeridos para la autorización
        auth_params = {
            'response_type': 'code',
            'client_id': os.getenv('BCI_CLIENT_ID'),
            'redirect_uri': os.getenv('BCI_REDIRECT_URI'),
            'scope': 'customers accounts transactions payments',
            'state': 'bci_auth',
            'nonce': 'bci_nonce',
            'request': json.dumps({
                'client_id': os.getenv('BCI_CLIENT_ID'),
                'redirect_uri': os.getenv('BCI_REDIRECT_URI'),
                'response_type': 'code',
                'scope': 'customers accounts transactions payments',
                'state': 'bci_auth',
                'nonce': 'bci_nonce'
            })
        }
        
        # Logging de los parámetros (sin información sensible)
        logging.info(f"Parámetros de autorización: {auth_params}")
        
        # Construir URL de autorización
        auth_url = f"{os.getenv('BCI_API_BASE_URL')}/api-oauth/authorize?{urllib.parse.urlencode(auth_params)}"
        logging.info(f"URL de autorización: {auth_url}")
        
        return redirect(auth_url)
    except Exception as e:
        logging.error(f"Error en bci_auth: {str(e)}")
        flash('Error al iniciar la autorización con BCI', 'error')
        return redirect(url_for('index'))

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