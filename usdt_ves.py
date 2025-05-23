import asyncio
import aiohttp
import logging
import warnings

warnings.filterwarnings("ignore")

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SELL_API_URL = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'


def obtener_headers_binance():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:102.0) Gecko/20100101 Firefox/102.0',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json;charset=UTF-8'
    }


async def obtener_valor_usdt_por_banco(banco: str) -> float:
    """
    Función que recibe como parámetro el banco (por ejemplo, "Banesco" o "BANK")
    y retorna el valor de USDT obtenido de la API.
    """
    payload = {
        'proMerchantAds': False,
        'page': 1,
        'transAmount': 100000,
        'rows': 20,
        'payTypes': [banco],
        'publisherType': 'merchant',
        'asset': 'USDT',
        'fiat': 'VES',
        'tradeType': 'SELL'
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(SELL_API_URL, json=payload, headers=obtener_headers_binance()) as response:
                if response.status == 200:
                    data = await response.json()
                    if "data" in data and data["data"]:
                        return float(data["data"][0]["adv"]["price"])
                    else:
                        # Si no se encuentran datos, se intenta sin el filtro "payTypes"
                        payload.pop("payTypes", None)
                        async with session.post(SELL_API_URL, json=payload,
                                                headers=obtener_headers_binance()) as alt_response:
                            if alt_response.status == 200:
                                alt_data = await alt_response.json()
                                if "data" in alt_data and alt_data["data"]:
                                    return float(alt_data["data"][0]["adv"]["price"])
                                else:
                                    logging.error("No se encontraron datos en la respuesta alternativa.")
                                    return None
                            else:
                                logging.error(f"Error en la solicitud alternativa: {alt_response.status}")
                                return None
                else:
                    logging.error(f"Error en la solicitud: {response.status}, {await response.text()}")
                    return None
        except Exception as e:
            logging.error(f"Error al obtener tasas USDT/VES: {e}")
            return None


# Ejemplo de uso
async def main():
    precio_banesco = await obtener_valor_usdt_por_banco("Banesco")
    precio_bank_transfer = await obtener_valor_usdt_por_banco("BANK")

    if precio_banesco is not None:
        print(precio_banesco)
    else:
        print("No se pudo obtener el valor para Banesco.")

    if precio_bank_transfer is not None:
        print(precio_bank_transfer)
    else:
        print("No se pudo obtener el valor para BANK.")


if __name__ == "__main__":
    asyncio.run(main())
