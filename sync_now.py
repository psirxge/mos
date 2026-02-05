#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Быстрая синхронизация облигаций с Google Sheets
Использование: python sync_now.py
"""

import sys
import os
import logging

# Добавляем текущую директорию в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser import MOEXBondsParser
from sheets_handler import GoogleSheetsHandler
from config import GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE, SHEET_COLUMNS

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Основная функция синхронизации"""
    try:
        logger.info("=" * 50)
        logger.info("Начало синхронизации облигаций с Google Sheets")
        logger.info("=" * 50)
        
        # Шаг 1: Получение данных с MOEX
        logger.info("\n[1/3] Получение данных об облигациях с MOEX...")
        parser = MOEXBondsParser()
        bonds = parser.fetch_bonds_data()
        
        if not bonds:
            logger.error("✗ Не получены данные об облигациях")
            return False
        
        logger.info(f"✓ Получено {len(bonds)} облигаций")
        
        # Шаг 2: Инициализация Google Sheets
        logger.info("\n[2/3] Подключение к Google Sheets...")
        sheets_handler = GoogleSheetsHandler(GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID)
        
        if not sheets_handler.is_authenticated():
            logger.error("✗ Не удалось подключиться к Google Sheets")
            return False
        
        logger.info("✓ Успешное подключение к Google Sheets")
        
        # Шаг 3: Обновление данных
        logger.info("\n[3/3] Обновление данных в Google Sheets...")
        rows = sheets_handler.convert_bonds_to_rows(bonds, SHEET_COLUMNS)
        
        if sheets_handler.update_data('Облигации', rows):
            logger.info(f"✓ Успешно обновлено {len(rows)} облигаций")
            logger.info("\n" + "=" * 50)
            logger.info("✓ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
            logger.info("=" * 50)
            
            # Вывод статистики
            currencies = {}
            for bond in bonds:
                currency = bond.get('Валюта', 'Неизвестно').split()[0]
                currencies[currency] = currencies.get(currency, 0) + 1
            
            logger.info("\nСтатистика по валютам:")
            for currency in sorted(currencies.keys()):
                count = currencies[currency]
                percentage = round(count / len(bonds) * 100, 1)
                logger.info(f"  {currency}: {count} облигаций ({percentage}%)")
            
            return True
        else:
            logger.error("✗ Ошибка при обновлении данных")
            return False
        
    except Exception as e:
        logger.error(f"✗ Критическая ошибка: {e}")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
