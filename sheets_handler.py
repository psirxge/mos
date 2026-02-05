import logging
import traceback
from typing import List, Dict, Optional
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.auth.exceptions import DefaultCredentialsError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import json

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


class GoogleSheetsHandler:
    """Обработчик для работы с Google Sheets"""

    def __init__(self, credentials_file: str, sheet_id: str):
        """
        Инициализация обработчика Google Sheets
        
        Args:
            credentials_file: Путь к файлу с учетными данными
            sheet_id: ID Google Sheet
        """
        self.credentials_file = credentials_file
        self.sheet_id = sheet_id
        self.service = None
        self._authenticate()

    def _authenticate(self) -> bool:
        """
        Аутентификация в Google API
        
        Returns:
            bool: True если аутентификация успешна
        """
        try:
            if not os.path.exists(self.credentials_file):
                logger.error(f'Файл учетных данных не найден: {self.credentials_file}')
                logger.info('Пожалуйста, получите credentials.json через Google Cloud Console')
                return False

            credentials = Credentials.from_service_account_file(
                self.credentials_file, scopes=SCOPES
            )
            self.service = build('sheets', 'v4', credentials=credentials)
            logger.info('Успешная аутентификация в Google Sheets API')
            return True

        except Exception as e:
            logger.error(f'Ошибка аутентификации: {e}')
            return False

    def create_sheet(self, title: str) -> bool:
        """
        Создание нового листа в таблице
        
        Args:
            title: Название листа
            
        Returns:
            bool: True если лист создан успешно или уже существует
        """
        if not self.service:
            logger.error('Сервис не инициализирован')
            return False

        try:
            body = {
                'requests': [
                    {
                        'addSheet': {
                            'properties': {
                                'title': title,
                                'gridProperties': {
                                    'rowCount': 1000,
                                    'columnCount': 15
                                }
                            }
                        }
                    }
                ]
            }

            result = self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=body
            ).execute()

            logger.info(f'Лист "{title}" создан успешно')
            return True

        except HttpError as e:
            error_content = e.content.decode('utf-8') if hasattr(e.content, 'decode') else str(e.content)
            error_msg = str(e)
            
            # Если лист уже существует (ошибка 400), это нормально
            if 'Duplicate sheet name' in str(e) or 'already exists' in error_content or e.resp.status == 400:
                logger.info(f'Лист "{title}" уже существует')
                return True
            elif e.resp.status == 403:
                logger.error(f'Ошибка доступа при создании листа: {error_msg}')
                logger.error('Убедитесь, что сервисный аккаунт имеет доступ к таблице Google Sheets')
                return False
            else:
                logger.error(f'Ошибка при создании листа (статус {e.resp.status}): {error_msg}')
                logger.debug(f'Полный текст ошибки: {error_content}')
                return False
        except Exception as e:
            logger.error(f'Неожиданная ошибка при создании листа: {type(e).__name__}: {e}')
            import traceback
            logger.debug(f'Traceback: {traceback.format_exc()}')
            return False

    def write_header(self, sheet_name: str, headers: List[str]) -> bool:
        """
        Запись заголовков в первую строку
        
        Args:
            sheet_name: Название листа
            headers: Список названий столбцов
            
        Returns:
            bool: True если заголовки записаны успешно
        """
        if not self.service:
            logger.error('Сервис не инициализирован')
            return False

        try:
            range_name = f'{sheet_name}!A1'
            body = {
                'values': [headers]
            }

            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()

            logger.info(f'Заголовки записаны в лист "{sheet_name}"')
            return True

        except HttpError as e:
            logger.warning(f'Ошибка при записи заголовков (возможно, они уже существуют): {e}')
            return True  # Возвращаем True, так как это некритичная ошибка
        except Exception as e:
            logger.error(f'Неожиданная ошибка при записи заголовков: {e}')
            return False

    def append_data(self, sheet_name: str, data: List[List]) -> bool:
        """
        Добавление данных в таблицу
        
        Args:
            sheet_name: Название листа
            data: Список списков с данными
            
        Returns:
            bool: True если данные добавлены успешно
        """
        if not self.service:
            logger.error('Сервис не инициализирован')
            return False

        try:
            range_name = f'{sheet_name}!A2'
            body = {
                'values': data
            }

            self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()

            logger.info(f'Добавлено {len(data)} строк в лист "{sheet_name}"')
            return True

        except HttpError as e:
            logger.error(f'Ошибка при добавлении данных: {e}')
            return False

    def update_data(self, sheet_name: str, data: List[List]) -> bool:
        """
        Обновление данных в таблице (перезапись)
        
        Args:
            sheet_name: Название листа
            data: Список списков с данными
            
        Returns:
            bool: True если данные обновлены успешно
        """
        if not self.service:
            logger.error('Сервис не инициализирован')
            return False

        try:
            range_name = f'{sheet_name}!A2'
            body = {
                'values': data
            }

            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()

            logger.info(f'Обновлено {len(data)} строк в листе "{sheet_name}"')
            return True

        except HttpError as e:
            logger.error(f'Ошибка при обновлении данных: {e}')
            return False

    def clear_sheet(self, sheet_name: str) -> bool:
        """
        Очистка листа
        
        Args:
            sheet_name: Название листа
            
        Returns:
            bool: True если лист очищен успешно
        """
        if not self.service:
            logger.error('Сервис не инициализирован')
            return False

        try:
            range_name = f'{sheet_name}!A:Z'
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()

            logger.info(f'Лист "{sheet_name}" очищен')
            return True

        except HttpError as e:
            logger.error(f'Ошибка при очистке листа: {e}')
            return False

    def read_data(self, sheet_name: str, range_name: str = 'A:Z') -> List[List]:
        """
        Чтение данных из таблицы
        
        Args:
            sheet_name: Название листа
            range_name: Диапазон для чтения
            
        Returns:
            List[List]: Список списков с данными
        """
        if not self.service:
            logger.error('Сервис не инициализирован')
            return []

        try:
            full_range = f'{sheet_name}!{range_name}'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=full_range
            ).execute()

            return result.get('values', [])

        except HttpError as e:
            logger.error(f'Ошибка при чтении данных: {e}')
            return []

    def convert_bonds_to_rows(self, bonds: List[Dict], columns: List[str]) -> List[List]:
        """
        Конвертирование данных об облигациях в строки для Google Sheets
        
        Args:
            bonds: Список словарей с данными об облигациях
            columns: Список названий столбцов
            
        Returns:
            List[List]: Список списков для записи в таблицу
        """
        rows = []
        for bond in bonds:
            row = [bond.get(col, '') for col in columns]
            rows.append(row)
        return rows

    def is_authenticated(self) -> bool:
        """
        Проверка аутентификации
        
        Returns:
            bool: True если аутентификация успешна
        """
        return self.service is not None
