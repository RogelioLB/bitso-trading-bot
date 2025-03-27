# Bitso Trading Bot

Este proyecto implementa un bot de trading para Bitso que busca realizar operaciones de compra y venta con criptomonedas, considerando las comisiones de la plataforma y utilizando una base de datos PostgreSQL para gestionar las órdenes.

## Características

- Utiliza USDT (Tether) como criptomoneda principal para reducir la volatilidad
- Permite colocar múltiples órdenes simultáneas (hasta 5 de compra y 5 de venta)
- Calcula precios de venta realistas con un incremento fijo sobre el precio de compra
- Considera el spread del 1.5% de Bitso en las operaciones
- Almacena y gestiona órdenes en una base de datos PostgreSQL
- Obtiene información en tiempo real de la API de Bitso
- Monitorea y ajusta órdenes según las condiciones del mercado
- Registra todas las operaciones y eventos en un archivo de log

## Requisitos

- Python 3.6 o superior
- Cuenta en Bitso con API Key y API Secret
- Base de datos PostgreSQL (puede ser local o en Railway)
- Saldo suficiente en la cuenta para realizar operaciones

## Instalación

1. Clona este repositorio:
```
git clone https://github.com/tu-usuario/bitso-trading-bot.git
cd bitso-trading-bot
```

2. Instala las dependencias:
```
pip install -r requirements.txt
```

3. Configura tus credenciales de API y base de datos:
   - Crea un archivo `.env` en el directorio raíz
   - Añade tus claves API y configuración de base de datos:
   ```
   BITSO_API_KEY=your_api_key_here
   BITSO_API_SECRET=your_api_secret_here
   DATABASE_URL=postgresql://usuario:contraseña@host:puerto/nombre_db
   ```

## Configuración

Puedes ajustar los siguientes parámetros en el archivo `bitso_trading_bot.py`:

- `TARGET_PROFIT_PERCENTAGE`: Porcentaje de ganancia objetivo (por defecto 0.05%)
- `BOOK`: Par de trading a utilizar (por defecto "usdt_mxn")
- `CHECK_INTERVAL`: Intervalo de verificación en segundos (por defecto 60)
- `TRADE_AMOUNT`: Cantidad de USDT a operar (por defecto 5 USDT)
- `MAX_ACTIVE_ORDERS`: Número máximo de órdenes activas simultáneas (por defecto 5)
- `MAX_PRICE_DIFF`: Diferencia máxima de precio para venta (por defecto 0.05 MXN)

## Uso

Para ejecutar el bot:

```
python bitso_trading_bot.py
```

Para detener el bot, presiona `Ctrl+C`. El bot cancelará cualquier orden pendiente antes de finalizar.

## Funcionamiento

El bot opera siguiendo esta estrategia:

1. Revisa todas las órdenes activas en la base de datos
2. Obtiene las comisiones actuales de la plataforma
3. Consulta el estado actual del mercado (ticker)
4. Calcula un precio de compra ligeramente por debajo del ask actual
5. Calcula un precio de venta con un incremento fijo sobre el precio de compra
6. Coloca múltiples órdenes de compra y venta según el saldo disponible
7. Monitorea continuamente las órdenes y coloca nuevas cuando se completan las existentes

## Despliegue en Railway

Este bot está diseñado para ser desplegado fácilmente en Railway:

1. Crea una nueva aplicación en Railway
2. Conecta tu repositorio de GitHub
3. Configura las variables de entorno (BITSO_API_KEY, BITSO_API_SECRET)
4. Añade un servicio de PostgreSQL desde el marketplace de Railway
5. Railway proporcionará automáticamente la variable DATABASE_URL

## Advertencia

El trading de criptomonedas implica riesgos. Este bot es una herramienta educativa y no garantiza ganancias. Úsalo bajo tu propia responsabilidad y solo con fondos que estés dispuesto a arriesgar.

## Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo LICENSE para más detalles.
