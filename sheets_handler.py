import logging
from typing import List, Dict, Optional
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleSheetsHandler:
    """Обработчик для работы с Google Sheets API"""

    def __init__(self, credentials_file: str, sheet_id: str):
        """
        Инициализация Google Sheets handler
        
        Args:
            credentials_file: Путь к файлу с учетными данными
            sheet_id: ID таблицы Google Sheets
        """
        self.sheet_id = sheet_id
        self.service = None
        self.credentials_file = credentials_file
        self._authenticate()

    def _authenticate(self) -> bool:
        """
        Аутентификация в Google Sheets API
        
        Returns:
            bool: True если аутентификация успешна
        """
        try:
            credentials = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets',
                        'https://www.googleapis.com/auth/drive']
            )
            self.service = build('sheets', 'v4', credentials=credentials)
            logger.info('Успешная аутентификация в Google Sheets API')
            return True
        except Exception as e:
            logger.error(f'Ошибка аутентификации: {e}')
            return False

    def is_authenticated(self) -> bool:
        """
        Проверка аутентификации
        
        Returns:
            bool: True если сервис инициализирован
        """
        return self.service is not None

    def create_sheet(self, sheet_name: str) -> bool:
        """
        Создание листа в таблице Google Sheets
        
        Args:
            sheet_name: Название листа
            
        Returns:
            bool: True если операция успешна
        """
        try:
            # Получаем список листов
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            
            sheets = spreadsheet.get('sheets', [])
            sheet_titles = [sheet['properties']['title'] for sheet in sheets]
            
            # Если лист с таким названием уже существует, не создаем
            if sheet_name in sheet_titles:
                logger.info(f'Лист "{sheet_name}" уже существует')
                return True
            
            # Создаем новый лист
            request_body = {
                'requests': [
                    {
                        'addSheet': {
                            'properties': {
                                'title': sheet_name
                            }
                        }
                    }
                ]
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=request_body
            ).execute()
            
            logger.info(f'Лист "{sheet_name}" создан успешно')
            return True
            
        except HttpError as error:
            logger.error(f'Ошибка при создании листа: {error}')
            return False
        except Exception as e:
            logger.error(f'Неожиданная ошибка при создании листа: {e}')
            return False

    def write_header(self, sheet_name: str, columns: List[str]) -> bool:
        """
        Запись заголовков столбцов
        
        Args:
            sheet_name: Название листа
            columns: Список названий столбцов
            
        Returns:
            bool: True если операция успешна
        """
        try:
            range_name = f'{sheet_name}!A1'
            values = [columns]
            
            body = {
                'values': values
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logger.info(f'Заголовки записаны в лист "{sheet_name}"')
            return True
            
        except HttpError as error:
            logger.error(f'Ошибка при записи заголовков: {error}')
            return False
        except Exception as e:
            logger.error(f'Неожиданная ошибка при записи заголовков: {e}')
            return False

    def update_data(self, sheet_name: str, rows: List[List]) -> bool:
        """
        Обновление данных в листе
        
        Args:
            sheet_name: Название листа
            rows: Список строк (каждая строка - список значений)
            
        Returns:
            bool: True если операция успешна
        """
        try:
            range_name = f'{sheet_name}!A2'
            
            body = {
                'values': rows
            }
            
            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            updated_rows = result.get('updatedRows', 0)
            logger.info(f'Обновлено {updated_rows} строк в листе "{sheet_name}"')
            return True
            
        except HttpError as error:
            logger.error(f'Ошибка при обновлении данных: {error}')
            return False
        except Exception as e:
            logger.error(f'Неожиданная ошибка при обновлении данных: {e}')
            return False

    def convert_bonds_to_rows(self, bonds: List[Dict], columns: List[str]) -> List[List]:
        """
        Конвертирование данных об облигациях в формат для Google Sheets
        
        Args:
            bonds: Список словарей с данными об облигациях
            columns: Список названий столбцов
            
        Returns:
            List[List]: Список строк для записи в таблицу
        """
        rows = []
        
        try:
            for bond in bonds:
                if bond is None:
                    continue
                    
                row = []
                for column in columns:
                    value = bond.get(column, '')
                    # Конвертируем значение в строку
                    if value is None:
                        value = ''
                    else:
                        value = str(value)
                    row.append(value)
                
                rows.append(row)
            
            logger.debug(f'Конвертировано {len(rows)} облигаций в формат Google Sheets')
            return rows
            
        except Exception as e:
            logger.error(f'Ошибка при конвертировании данных: {e}')
            return []

    def get_data(self, sheet_name: str, range_name: Optional[str] = None) -> List[List]:
        """
        Получение данных из листа
        
        Args:
            sheet_name: Название листа
            range_name: Диапазон (опционально, по умолчанию весь лист)
            
        Returns:
            List[List]: Список строк с данными
        """
        try:
            if range_name is None:
                range_name = sheet_name
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            logger.debug(f'Получено {len(values)} строк из листа "{sheet_name}"')
            return values
            
        except HttpError as error:
            logger.error(f'Ошибка при получении данных: {error}')
            return []
        except Exception as e:
            logger.error(f'Неожиданная ошибка при получении данных: {e}')
            return []

    def clear_sheet(self, sheet_name: str) -> bool:
        """
        Очистка листа (удаление всех данных)
        
        Args:
            sheet_name: Название листа
            
        Returns:
            bool: True если операция успешна
        """
        try:
            # Получаем ID листа
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            
            sheets = spreadsheet.get('sheets', [])
            sheet_id = None
            for sheet in sheets:
                if sheet['properties']['title'] == sheet_name:
                    sheet_id = sheet['properties']['sheetId']
                    break
            
            if sheet_id is None:
                logger.error(f'Лист "{sheet_name}" не найден')
                return False
            
            # Очищаем лист
            request_body = {
                'requests': [
                    {
                        'deleteRange': {
                            'range': {
                                'sheetId': sheet_id
                            },
                            'shiftDimension': 'ROWS'
                        }
                    }
                ]
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=request_body
            ).execute()
            
            logger.info(f'Лист "{sheet_name}" очищен')
            return True
            
        except HttpError as error:
            logger.error(f'Ошибка при очистке листа: {error}')
            return False
        except Exception as e:
            logger.error(f'Неожиданная ошибка при очистке листа: {e}')
            return False
