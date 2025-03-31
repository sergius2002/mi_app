# Sistema de Gestión de Tasas USDT/VES

Sistema web para monitorear y gestionar tasas de cambio USDT/VES en tiempo real, con soporte para múltiples bancos venezolanos.

## Características

- Monitoreo en tiempo real de tasas USDT/VES para:
  - Banesco
  - Venezuela (BANK)
  - Mercantil
  - Provincial
- Gráficos interactivos con actualización automática
- Sistema de autenticación de usuarios
- Panel de administración
- Gestión de transferencias y pedidos
- Dashboard con métricas en tiempo real

## Requisitos

- Python 3.8+
- Flask
- Supabase
- Matplotlib
- Otras dependencias listadas en `requirements.txt`

## Configuración

1. Clonar el repositorio:
```bash
git clone https://github.com/tu-usuario/mi_app.git
cd mi_app
```

2. Crear y activar entorno virtual:
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Crear archivo `.env` con las siguientes variables:
```
SUPABASE_URL=tu_url_supabase
SUPABASE_KEY=tu_key_supabase
SECRET_KEY=tu_clave_secreta
TZ=America/Argentina/Buenos_Aires
```

5. Ejecutar la aplicación:
```bash
python app.py
```

## Estructura del Proyecto

```
mi_app/
├── app.py              # Aplicación principal
├── requirements.txt    # Dependencias
├── .env               # Variables de entorno
├── data_tasas.csv     # Datos históricos
├── templates/         # Plantillas HTML
└── blueprints/        # Módulos de la aplicación
```

## Uso

1. Acceder a la aplicación en `http://localhost:5001`
2. Iniciar sesión con credenciales autorizadas
3. Navegar por las diferentes secciones:
   - Gráfico: Monitoreo en tiempo real de tasas
   - Transferencias: Gestión de transferencias
   - Pedidos: Gestión de pedidos
   - Dashboard: Métricas y estadísticas
   - Admin: Panel de administración

## Contribuir

1. Fork el repositorio
2. Crear una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir un Pull Request

## Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles. 