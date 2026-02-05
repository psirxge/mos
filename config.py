import os
from dotenv import load_dotenv

# Загрузка переменных из .env файла
load_dotenv()

# Google Sheets конфигурация
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '1IPSrwsLZvL8vqwW_Hk5cv0rUl6mAtLMzdhGShaLGYaw')
GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')

# MOEX конфигурация
MOEX_URL = os.getenv('MOEX_URL', 'https://www.moex.com/')
UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', '600'))  # 10 минут в секундах

# Logging конфигурация
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'bonds_parser.log')

# Заголовки для HTTP запросов
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Названия столбцов в Google Sheets
SHEET_COLUMNS = [
    'Котировка',
    'Название',
    'Дата погашения',
    'Дата выплаты купона',
    'Сумма купона',
    'НКД',
    'Периодичность выплаты купонов',
    'Номинал',
    'Статус (Рейтинг)',
    'Дата оферты',
    'Текущая стоимость',
    'Последнее обновление'
]
