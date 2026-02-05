import logging
import schedule
import time
import sys
from datetime import datetime
from typing import Optional

from config import UPDATE_INTERVAL, LOG_LEVEL, LOG_FILE, GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE, SHEET_COLUMNS
from parser import MOEXBondsParser
from sheets_handler import GoogleSheetsHandler

# Настройка логирования с поддержкой UTF-8
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Устанавливаем UTF-8 для консоли на Windows
if sys.platform == 'win32':
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'

logger = logging.getLogger(__name__)


class BondsUpdater:
    """Основной класс для управления обновлением данных об облигациях"""

    def __init__(self):
        """Инициализация обновителя"""
        self.parser = MOEXBondsParser()
        self.sheets_handler: Optional[GoogleSheetsHandler] = None
        self.initialized = False
        self.sheet_name = 'Облигации'

    def initialize(self) -> bool:
        """
        Инициализация всех компонентов
        
        Returns:
            bool: True если инициализация успешна
        """
        try:
            logger.info('=== Инициализация парсера облигаций ===')
            
            # Проверка параметров Google Sheets
            if not GOOGLE_SHEET_ID:
                logger.error('GOOGLE_SHEET_ID не установлен в .env файле')
                return False

            # Инициализация Google Sheets handler
            self.sheets_handler = GoogleSheetsHandler(GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID)

            if not self.sheets_handler.is_authenticated():
                logger.error('Не удалось аутентифицироваться в Google Sheets')
                return False

            # Создание листа если его нет
            self.sheets_handler.create_sheet(self.sheet_name)
            
            # Запись заголовков
            if not self.sheets_handler.write_header(self.sheet_name, SHEET_COLUMNS):
                logger.warning('Не удалось записать заголовки')

            self.initialized = True
            logger.info('Инициализация завершена успешно')
            return True

        except Exception as e:
            logger.error(f'Ошибка инициализации: {e}')
            return False

    def update_bonds(self) -> bool:
        """
        Обновление данных об облигациях
        
        Returns:
            bool: True если обновление успешно
        """
        if not self.initialized:
            logger.error('Система не инициализирована')
            return False

        try:
            logger.info('--- Начало обновления данных об облигациях ---')
            
            # Получение данных с MOEX
            bonds = self.parser.fetch_bonds_data()
            
            if not bonds:
                logger.warning('Не получены данные об облигациях')
                return False

            logger.info(f'Получено {len(bonds)} облигаций')

            # Конвертирование данных в формат Google Sheets
            rows = self.sheets_handler.convert_bonds_to_rows(bonds, SHEET_COLUMNS)

            # Обновление данных в Google Sheets
            if self.sheets_handler.update_data(self.sheet_name, rows):
                logger.info(f'✓ Данные успешно обновлены ({len(rows)} облигаций)')
                return True
            else:
                logger.error('Не удалось обновить данные в Google Sheets')
                return False

        except Exception as e:
            logger.error(f'Ошибка при обновлении данных: {e}')
            return False

    def schedule_updates(self):
        """Планирование периодических обновлений"""
        try:
            logger.info(f'Планирование обновлений каждые {UPDATE_INTERVAL // 60} минут(ы)')
            
            # Планирование обновления
            schedule.every(UPDATE_INTERVAL).seconds.do(self.update_bonds)
            
            # Первое обновление сразу
            logger.info('Выполнение первоначального обновления...')
            self.update_bonds()
            
            logger.info('=== Парсер запущен ===')
            logger.info('Нажмите Ctrl+C для остановки')

            # Основной цикл
            while True:
                schedule.run_pending()
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info('Парсер остановлен пользователем')
            sys.exit(0)
        except Exception as e:
            logger.error(f'Ошибка в цикле обновлений: {e}')
            sys.exit(1)


def main():
    """Главная функция"""
    try:
        updater = BondsUpdater()
        
        if not updater.initialize():
            logger.error('Ошибка инициализации. Проверьте конфигурацию.')
            logger.info('\nДля корректной работы требуется:')
            logger.info('1. Создать проект в Google Cloud Console')
            logger.info('2. Включить Google Sheets API')
            logger.info('3. Создать Service Account и скачать credentials.json')
            logger.info('4. Заполнить переменные в файле .env:')
            logger.info('   - GOOGLE_SHEET_ID: ID вашей таблицы Google Sheets')
            logger.info('   - GOOGLE_CREDENTIALS_FILE: путь к credentials.json')
            sys.exit(1)
        
        updater.schedule_updates()

    except KeyboardInterrupt:
        logger.info('\nПрограмма остановлена пользователем')
        sys.exit(0)
    except Exception as e:
        logger.critical(f'Критическая ошибка: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
