import re
import logging
import cloudscraper
from bs4 import BeautifulSoup


def obtener_precio_usd_clp():
    """
    Esta función realiza una petición a la página de Investing.com
    para extraer el valor del dólar en pesos chilenos (USD/CLP).

    Se basa en la estructura HTML actual, donde el precio puede aparecer:
    - en un <div data-test="instrument-price-last">, o
    - en un <span id="last_last">.

    Utiliza cloudscraper para evadir el escudo de Cloudflare.
    Retorna un float con el precio o None en caso de error.
    """

    # URL de la página principal de USD/CLP (más confiable que la de chart)
    url = "https://www.investing.com/currencies/usd-clp"

    # Encabezados simulando un navegador actualizado
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/90.0.4430.93 Safari/537.36"
        ),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://www.investing.com/"
    }

    # Se crea un objeto scraper usando cloudscraper
    scraper = cloudscraper.create_scraper()

    try:
        # Realiza la petición GET con los encabezados
        response = scraper.get(url, headers=headers)
        response.raise_for_status()

        # Crea el objeto BeautifulSoup para parsear el HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Intentamos primero buscar el elemento con data-test="instrument-price-last"
        price_element = soup.find("div", {"data-test": "instrument-price-last"})

        # Si no se encuentra, se intenta buscar con id "last_last"
        if not price_element:
            logging.info(
                "No se encontró el elemento con data-test='instrument-price-last', intentando con id 'last_last'.")
            price_element = soup.find("span", {"id": "last_last"})

        # Si aún no se encuentra, se registra un error y se finaliza la función
        if not price_element:
            logging.error(
                "No se encontró el elemento que contiene el precio. Verifica la estructura HTML de la página.")
            # Opcional: guarda el HTML en un archivo para depuración
            # with open("html_investing.html", "w", encoding="utf-8") as f:
            #     f.write(response.text)
            return None

        # Obtiene el texto del elemento, por ejemplo "996.27"
        price_text = price_element.get_text(strip=True)

        # Limpia el texto para conservar solo números y puntos decimales
        price_text = re.sub(r'[^\d\.]', '', price_text)

        # Convierte la cadena a float
        price = float(price_text)

    except Exception as e:
        logging.error(f"Error al obtener el precio USD/CLP: {e}")
        return None

    return price


# Bloque principal de pruebas
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    precio_usd_clp = obtener_precio_usd_clp()
    if precio_usd_clp is not None:
        print(f"Precio USD/CLP: {precio_usd_clp}")
    else:
        print("No se pudo obtener el precio USD/CLP.")
