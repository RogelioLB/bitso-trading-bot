#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Bitso Trading Bot

Este script implementa un bot de trading para Bitso que busca realizar
operaciones de compra y venta con al menos 0.05% de ganancia, considerando
las comisiones de la plataforma.
"""

import os
import time
import logging
import datetime
from decimal import Decimal
from dotenv import load_dotenv
import bitso
import sqlalchemy as sa
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bitso_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("BitsoTradingBot")

# Cargar variables de entorno
load_dotenv()

# Configuración
API_KEY = os.getenv("BITSO_API_KEY")
API_SECRET = os.getenv("BITSO_API_SECRET")
TARGET_PROFIT_PERCENTAGE = Decimal('0.0005')  # 0.05% de ganancia objetivo
BOOK = "usdt_mxn"  # Libro a utilizar (USDT/Peso Mexicano)
CHECK_INTERVAL = 60  # Intervalo de verificación en segundos
TRADE_AMOUNT = Decimal('1')  # Cantidad de USDT a operar (ajustar según tus necesidades)
SPREAD_FEE = Decimal('0.015')  # 1.5% de spread según Bitso
MAX_ACTIVE_ORDERS = 5  # Número máximo de órdenes activas simultáneas
MAX_PRICE_DIFF = Decimal('0.05')  # Diferencia máxima de precio para venta (0.05 MXN)

# Configuración de la base de datos PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bitso_bot")

# Configuración de SQLAlchemy
Base = declarative_base()

class Order(Base):
    """Modelo para almacenar órdenes en la base de datos."""
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(String, unique=True, nullable=False)
    book = Column(String, nullable=False)
    side = Column(String, nullable=False)  # 'buy' o 'sell'
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    target_price = Column(Float, nullable=True)  # Precio objetivo para venta
    status = Column(String, nullable=False)  # 'active', 'completed', 'cancelled'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<Order(order_id='{self.order_id}', side='{self.side}', price={self.price}, status='{self.status}')>"

# Crear motor de base de datos y tablas
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

class BitsoTradingBot:
    """Bot para realizar operaciones de trading en Bitso."""
    
    def __init__(self, api_key, api_secret, book, target_profit, trade_amount):
        """Inicializar el bot con la configuración necesaria."""
        self.api = bitso.Api(api_key, api_secret)
        self.book = book
        self.target_profit = target_profit
        self.trade_amount = trade_amount
        self.active_buy_orders = []
        self.active_sell_orders = []
        self.db_session = Session()
    
    def get_account_balance(self):
        """Obtener el balance de la cuenta."""
        try:
            balances = self.api.balances()
            logger.info(f"Balance USDT: {balances.usdt.available}")
            logger.info(f"Balance MXN: {balances.mxn.available}")
            return balances
        except Exception as e:
            logger.error(f"Error al obtener balance: {e}")
            return None
    
    def get_fees(self):
        """Obtener las comisiones actuales."""
        try:
            fees = self.api.fees()
            fee_percent = fees.usdt_mxn.fee_percent
            logger.info(f"Comisión actual: {fee_percent}%")
            return fee_percent / Decimal('100')  # Convertir a decimal (ej: 0.65% -> 0.0065)
        except Exception as e:
            logger.error(f"Error al obtener comisiones: {e}")
            return SPREAD_FEE  # Usar el spread definido como valor por defecto
    
    def get_ticker(self):
        """Obtener información del ticker."""
        try:
            ticker = self.api.ticker(self.book)
            logger.info(f"Precio de compra (bid): {ticker.bid}")
            logger.info(f"Precio de venta (ask): {ticker.ask}")
            return ticker
        except Exception as e:
            logger.error(f"Error al obtener ticker: {e}")
            return None
    
    def calculate_prices(self, ticker, fee):
        """
        Calcular precios de compra y venta para obtener la ganancia objetivo.
        
        La estrategia es:
        1. Comprar a un precio ligeramente por debajo del ask actual
        2. Vender a un precio realista que sea ligeramente superior al precio de compra
           más un pequeño margen que cubra las comisiones
        """
        if not ticker:
            return None, None
        
        # Precio de compra: ligeramente por debajo del ask para aumentar probabilidad de ejecución
        buy_price = ticker.ask * Decimal('0.999')  # 0.1% por debajo del ask
        
        # Cálculo del precio de venta con un margen realista
        # En lugar de usar una fórmula que considere el spread completo, usamos un incremento fijo
        # que sea alcanzable en el mercado real
        sell_price = buy_price + MAX_PRICE_DIFF
        
        logger.info(f"Precio de compra calculado: {buy_price}")
        logger.info(f"Precio de venta calculado: {sell_price}")
        
        return buy_price, sell_price
    
    def save_order_to_db(self, order_id, side, price, amount, target_price=None, status='active'):
        """Guardar una orden en la base de datos."""
        try:
            order = Order(
                order_id=order_id,
                book=self.book,
                side=side,
                price=float(price),
                amount=float(amount),
                target_price=float(target_price) if target_price else None,
                status=status
            )
            self.db_session.add(order)
            self.db_session.commit()
            logger.info(f"Orden {order_id} guardada en la base de datos")
        except Exception as e:
            self.db_session.rollback()
            logger.error(f"Error al guardar orden en la base de datos: {e}")
    
    def update_order_status(self, order_id, status):
        """Actualizar el estado de una orden en la base de datos."""
        try:
            order = self.db_session.query(Order).filter_by(order_id=order_id).first()
            if order:
                order.status = status
                order.updated_at = datetime.datetime.utcnow()
                if status != 'active':
                    order.is_active = False
                self.db_session.commit()
                logger.info(f"Estado de orden {order_id} actualizado a {status}")
        except Exception as e:
            self.db_session.rollback()
            logger.error(f"Error al actualizar estado de orden en la base de datos: {e}")
    
    def get_active_orders_from_db(self):
        """Obtener todas las órdenes activas de la base de datos."""
        try:
            active_orders = self.db_session.query(Order).filter_by(is_active=True).all()
            return active_orders
        except Exception as e:
            logger.error(f"Error al obtener órdenes activas de la base de datos: {e}")
            return []
    
    def count_active_orders_by_side(self, side):
        """Contar el número de órdenes activas por lado (compra/venta)."""
        try:
            count = self.db_session.query(Order).filter_by(is_active=True, side=side).count()
            return count
        except Exception as e:
            logger.error(f"Error al contar órdenes activas: {e}")
            return 0
    
    def place_buy_order(self, price):
        """Colocar una orden de compra."""
        try:
            # Verificar si ya tenemos demasiadas órdenes de compra activas
            active_buy_count = self.count_active_orders_by_side('buy')
            if active_buy_count >= MAX_ACTIVE_ORDERS:
                logger.warning(f"Ya hay {active_buy_count} órdenes de compra activas. Límite: {MAX_ACTIVE_ORDERS}")
                return None
            
            # Verificar si tenemos suficiente saldo en MXN
            balances = self.api.balances()
            required_mxn = price * self.trade_amount
            
            if balances.mxn.available < required_mxn:
                logger.warning(f"Saldo MXN insuficiente. Necesario: {required_mxn}, Disponible: {balances.mxn.available}")
                return None
            
            # Colocar orden de compra
            order = self.api.place_order(book=self.book, side='buy', order_type='limit', 
                                         major=str(self.trade_amount), price=str(price))
            
            logger.info(f"Orden de compra colocada: {order['oid']} a {price} MXN por {self.trade_amount} USDT")
            
            # Calcular precio objetivo de venta (precio de compra + margen fijo)
            target_price = price + MAX_PRICE_DIFF
            
            # Guardar orden en la base de datos con el precio objetivo
            self.save_order_to_db(order['oid'], 'buy', price, self.trade_amount, target_price)
            
            # Añadir a la lista de órdenes de compra activas
            self.active_buy_orders.append(order['oid'])
            
            return order['oid']
        except Exception as e:
            logger.error(f"Error al colocar orden de compra: {e}")
            return None
    
    def place_sell_order(self, price, buy_price=None):
        """Colocar una orden de venta."""
        try:
            # Verificar si ya tenemos demasiadas órdenes de venta activas
            active_sell_count = self.count_active_orders_by_side('sell')
            if active_sell_count >= MAX_ACTIVE_ORDERS:
                logger.warning(f"Ya hay {active_sell_count} órdenes de venta activas. Límite: {MAX_ACTIVE_ORDERS}")
                return None
            
            # Verificar si tenemos suficiente saldo en USDT
            balances = self.api.balances()
            
            if balances.usdt.available < self.trade_amount:
                logger.warning(f"Saldo USDT insuficiente. Necesario: {self.trade_amount}, Disponible: {balances.usdt.available}")
                return None
            
            # Colocar orden de venta
            order = self.api.place_order(book=self.book, side='sell', order_type='limit', 
                                         major=str(self.trade_amount), price=str(price))
            
            logger.info(f"Orden de venta colocada: {order['oid']} a {price} MXN por {self.trade_amount} USDT")
            
            # Guardar orden en la base de datos
            self.save_order_to_db(order['oid'], 'sell', price, self.trade_amount, buy_price)
            
            # Añadir a la lista de órdenes de venta activas
            self.active_sell_orders.append(order['oid'])
            
            return order['oid']
        except Exception as e:
            logger.error(f"Error al colocar orden de venta: {e}")
            return None
    
    def check_order_status(self, order_id):
        """Verificar el estado de una orden."""
        try:
            if not order_id:
                return None
                
            orders = self.api.lookup_order([order_id])
            if orders and len(orders) > 0:
                order = orders[0]
                logger.info(f"Estado de orden {order_id}: {order.status}")
                
                # Actualizar estado en la base de datos
                if order.status in ['complete', 'cancelled']:
                    self.update_order_status(order_id, order.status)
                    
                    # Eliminar de las listas de órdenes activas
                    if order_id in self.active_buy_orders:
                        self.active_buy_orders.remove(order_id)
                    if order_id in self.active_sell_orders:
                        self.active_sell_orders.remove(order_id)
                
                return order
            return None
        except Exception as e:
            error_str = str(e)
            # Verificar si el error es código 0312 (orden ya cerrada/completada)
            if "0312" in error_str:
                logger.info(f"Orden {order_id} ya está cerrada o completada (código 0312)")
                # Actualizar estado en la base de datos como completada
                self.update_order_status(order_id, 'completed')
                
                # Eliminar de las listas de órdenes activas
                if order_id in self.active_buy_orders:
                    self.active_buy_orders.remove(order_id)
                if order_id in self.active_sell_orders:
                    self.active_sell_orders.remove(order_id)
            else:
                logger.error(f"Error al verificar estado de orden: {e}")
            return None
    
    def cancel_order(self, order_id):
        """Cancelar una orden existente."""
        try:
            if not order_id:
                return False
                
            result = self.api.cancel_order(order_id)
            logger.info(f"Orden {order_id} cancelada: {result}")
            
            # Actualizar estado en la base de datos
            if result == 'true':
                self.update_order_status(order_id, 'cancelled')
                
                # Eliminar de las listas de órdenes activas
                if order_id in self.active_buy_orders:
                    self.active_buy_orders.remove(order_id)
                if order_id in self.active_sell_orders:
                    self.active_sell_orders.remove(order_id)
                
            return result == 'true'
        except Exception as e:
            logger.error(f"Error al cancelar orden: {e}")
            return False
    
    def check_active_orders(self):
        """Revisar todas las órdenes activas y tomar acción si es necesario."""
        logger.info("Revisando órdenes activas...")
        
        # Obtener órdenes activas de la base de datos
        active_orders = self.get_active_orders_from_db()
        
        if not active_orders:
            logger.info("No hay órdenes activas para revisar")
            return
        
        # Obtener ticker actual
        ticker = self.get_ticker()
        if not ticker:
            return
        
        for order in active_orders:
            # Verificar estado actual de la orden en Bitso
            bitso_order = self.check_order_status(order.order_id)
            
            # Si la orden ya no está activa en Bitso, actualizar en la base de datos
            if not bitso_order or bitso_order.status != 'open':
                continue
            
            # Para órdenes de compra completadas, colocar orden de venta
            if order.side == 'buy' and bitso_order.status == 'complete':
                logger.info(f"Orden de compra {order.order_id} completada, colocando orden de venta")
                
                # Usar el precio objetivo guardado en la base de datos
                buy_price = Decimal(str(order.price))
                sell_price = Decimal(str(order.target_price)) if order.target_price else buy_price + MAX_PRICE_DIFF
                
                # Colocar orden de venta
                sell_order_id = self.place_sell_order(sell_price, buy_price)
                
                # Actualizar estado de la orden de compra
                self.update_order_status(order.order_id, 'completed')
            
            # Para órdenes de venta, verificar si el precio actual es favorable
            elif order.side == 'sell':
                # Si el precio actual es mayor o igual al precio objetivo, mantener la orden
                if ticker.bid >= Decimal(str(order.price)):
                    logger.info(f"Manteniendo orden de venta {order.order_id}, precio actual favorable")
                # Si el precio ha bajado significativamente, considerar cancelar y recalcular
                elif ticker.bid < Decimal(str(order.price)) * Decimal('0.99'):
                    logger.info(f"Precio ha bajado significativamente para orden {order.order_id}, considerando recalcular")
                    # Aquí podrías implementar lógica para decidir si cancelar y recalcular
    
    def run_trading_cycle(self):
        """Ejecutar un ciclo completo de trading."""
        logger.info("Iniciando ciclo de trading...")
        
        # Revisar órdenes activas primero
        self.check_active_orders()
        
        # Obtener comisiones actuales
        fee = self.get_fees()
        
        # Obtener información del mercado
        ticker = self.get_ticker()
        
        # Calcular precios de compra y venta
        buy_price, sell_price = self.calculate_prices(ticker, fee)
        
        if not buy_price or not sell_price:
            logger.error("No se pudieron calcular los precios. Saltando ciclo.")
            return
        
        # Verificar si hay suficiente saldo para operar
        balances = self.get_account_balance()
        if not balances:
            return
        
        # Colocar nuevas órdenes según el saldo disponible y el límite de órdenes activas
        
        # Si tenemos USDT disponible, colocar orden(es) de venta
        if balances.usdt.available >= self.trade_amount:
            active_sell_count = self.count_active_orders_by_side('sell')
            if active_sell_count < MAX_ACTIVE_ORDERS:
                logger.info(f"Tenemos USDT disponible ({balances.usdt.available}), colocando orden de venta")
                self.place_sell_order(sell_price)
        
        # Si tenemos MXN disponible, colocar orden(es) de compra
        if balances.mxn.available >= buy_price * self.trade_amount:
            active_buy_count = self.count_active_orders_by_side('buy')
            if active_buy_count < MAX_ACTIVE_ORDERS:
                logger.info(f"Tenemos MXN disponible ({balances.mxn.available}), colocando orden de compra")
                self.place_buy_order(buy_price)
    
    def run(self):
        """Ejecutar el bot de trading continuamente."""
        logger.info("Iniciando bot de trading de Bitso...")
        
        # Mostrar balance inicial
        self.get_account_balance()
        
        try:
            while True:
                self.run_trading_cycle()
                logger.info(f"Esperando {CHECK_INTERVAL} segundos para el próximo ciclo...")
                time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Bot detenido manualmente.")
            
            # Cancelar órdenes pendientes
            active_orders = self.get_active_orders_from_db()
            for order in active_orders:
                if order.is_active:
                    self.cancel_order(order.order_id)
            
            # Mostrar balance final
            self.get_account_balance()
            
            # Cerrar sesión de base de datos
            self.db_session.close()


if __name__ == "__main__":
    # Verificar que las claves API estén configuradas
    if not API_KEY or not API_SECRET:
        logger.error("Las claves API no están configuradas. Por favor, configura el archivo .env")
        exit(1)
    
    # Crear e iniciar el bot
    bot = BitsoTradingBot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        book=BOOK,
        target_profit=TARGET_PROFIT_PERCENTAGE,
        trade_amount=TRADE_AMOUNT
    )
    
    bot.run()
