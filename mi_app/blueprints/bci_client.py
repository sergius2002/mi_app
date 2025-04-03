import os
import json
import jwt
import time
import uuid
import logging
from datetime import datetime, timedelta
from urllib.parse import quote
import requests
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class BCIClient:
    def __init__(self):
        self.client_id = os.getenv('BCI_CLIENT_ID')
        self.client_secret = os.getenv('BCI_CLIENT_SECRET')
        self.redirect_uri = os.getenv('BCI_REDIRECT_URI')
        self.api_base_url = os.getenv('BCI_API_BASE_URL')
        self.token = None
        self.token_expiry = None
        self.logger = logging.getLogger(__name__)

    def generate_jwt(self):
        """Genera un JWT para la autenticación con BCI"""
        try:
            # Crear el payload del JWT
            current_time = int(time.time())
            payload = {
                "iss": self.client_id,
                "sub": self.client_id,
                "aud": f"{self.api_base_url}/v1/api-oauth/token",
                "iat": current_time,
                "exp": current_time + 300,  # 5 minutos de validez
                "jti": str(uuid.uuid4()),
                "scope": "customers accounts transactions payments"
            }

            # Generar el JWT
            token = jwt.encode(
                payload,
                self.client_secret,
                algorithm='HS256',
                headers={
                    "typ": "JWT",
                    "alg": "HS256",
                    "kid": self.client_id,
                    "x5t": self.client_id
                }
            )

            self.logger.info("JWT generado correctamente")
            self.logger.info(f"Payload del JWT: {json.dumps(payload)}")
            return token
        except Exception as e:
            self.logger.error(f"Error al generar JWT: {str(e)}", exc_info=True)
            raise

    def get_token(self):
        """Obtiene un token de acceso de BCI"""
        try:
            # Verificar si ya tenemos un token válido
            if self.token and self.token_expiry and datetime.now() < self.token_expiry:
                return self.token

            # Generar el JWT
            jwt_token = self.generate_jwt()

            # Preparar los datos para la solicitud
            data = {
                "grant_type": "client_credentials",
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": jwt_token,
                "scope": "customers accounts transactions payments"
            }

            # Hacer la solicitud
            response = requests.post(
                f"{self.api_base_url}/v1/api-oauth/token",
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                }
            )

            # Verificar la respuesta
            if response.status_code == 200:
                token_data = response.json()
                self.token = token_data.get('access_token')
                expires_in = token_data.get('expires_in', 3600)
                self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
                self.logger.info("Token obtenido correctamente")
                return self.token
            else:
                self.logger.error(f"Error al obtener token: {response.status_code} - {response.text}")
                raise Exception(f"Error al obtener token: {response.text}")

        except Exception as e:
            self.logger.error(f"Error en get_token: {str(e)}", exc_info=True)
            raise

    def get_accounts(self):
        """Obtiene las cuentas del usuario"""
        try:
            token = self.get_token()
            response = requests.get(
                f"{self.api_base_url}/v1/accounts",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
            return response.json()
        except Exception as e:
            self.logger.error(f"Error al obtener cuentas: {str(e)}", exc_info=True)
            raise 