import requests
import json
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
from config import MOEX_URL, HEADERS

logger = logging.getLogger(__name__)


class MOEXBondsParser:
    """Парсер данных об облигациях с сайта Московской Биржи"""

    def __init__(self):
        self.base_url = MOEX_URL
        self.bonds_data = []

    def fetch_bonds_data(self) -> List[Dict]:
        """
        Получение данных об облигациях с MOEX
        
        Returns:
            List[Dict]: Список словарей с данными об облигациях
        """
        try:
            # Используем MOEX ISS API для получения данных об облигациях
            url = 'https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQCB/securities.json'
            
            params = {
                'iss.meta': 'off',
                'iss.only': 'securities,marketdata',
                'limit': '100'
            }
            
            response = requests.get(url, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            self.bonds_data = self._parse_bonds_response(data)
            
            # Попытка получить дополнительные данные по НКД и другим полям
            # через отдельный запрос к aggregates если необходимо
            self._enrich_bonds_data()
            
            logger.info(f'Успешно загружены данные об {len(self.bonds_data)} облигациях')
            return self.bonds_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f'Ошибка при получении данных с MOEX: {e}')
            return []
    
    def _enrich_bonds_data(self):
        """
        Попытка дополнить данные по облигациям доступной информацией
        (ACCRUEDINT может быть недоступен в некоторых запросах)
        """
        try:
            # Если НКД пустое, можно использовать расчет на основе купонного периода
            for bond in self.bonds_data:
                # Попытка заполнить периодичность на основе COUPONPERIOD если доступно
                if not bond.get('Периодичность выплаты купонов') or bond.get('Периодичность выплаты купонов') == '':
                    bond['Периодичность выплаты купонов'] = 'Не определена'
                
                # Попытка заполнить НКД если пусто
                if not bond.get('НКД') or bond.get('НКД') == '':
                    bond['НКД'] = 'Данные недоступны'
        except Exception as e:
            logger.warning(f'Ошибка при обогащении данных: {e}')

    def _parse_bonds_response(self, data: Dict) -> List[Dict]:
        """
        Парсирование ответа от MOEX ISS API
        
        Args:
            data: JSON ответ от API
            
        Returns:
            List[Dict]: Список обработанных данных об облигациях
        """
        bonds = []
        
        try:
            if 'securities' not in data or 'marketdata' not in data:
                logger.warning('Неполный ответ от API MOEX')
                return bonds

            securities = {item[0]: item for item in data['securities']['data']}
            market_data = {item[0]: item for item in data['marketdata']['data']}
            
            security_columns = data['securities']['columns']
            market_columns = data['marketdata']['columns']
            
            # Логирование доступных колонок для отладки
            logger.debug(f'Securities columns: {security_columns}')
            logger.debug(f'Market columns: {market_columns}')

            processed_count = 0
            for secid, sec_item in securities.items():
                if secid not in market_data:
                    continue

                market_item = market_data[secid]
                
                bond_data = self._extract_bond_info(
                    sec_item, security_columns,
                    market_item, market_columns
                )
                
                if bond_data:
                    bonds.append(bond_data)
                    processed_count += 1
                    # Логирование первой облигации для отладки
                    if processed_count == 1:
                        logger.debug(f'Пример облигации: {bond_data}')

        except (KeyError, IndexError) as e:
            logger.error(f'Ошибка при парсировании ответа MOEX: {e}')

        return bonds

    def _extract_bond_info(self, sec_item: List, sec_cols: List,
                          market_item: List, market_cols: List) -> Optional[Dict]:
        """
        Извлечение информации об одной облигации
        
        Args:
            sec_item: Данные из securities
            sec_cols: Названия колонок securities
            market_item: Данные из marketdata
            market_cols: Названия колонок marketdata
            
        Returns:
            Optional[Dict]: Словарь с информацией об облигации или None

        """
        try:
            sec_dict = dict(zip(sec_cols, sec_item))
            market_dict = dict(zip(market_cols, market_item))

            # Котировка
            secid = sec_dict.get('SECID', '')
            # Название
            name = sec_dict.get('SECNAME', '') or sec_dict.get('SHORTNAME', '')
            # Дата погашения
            mat_date = sec_dict.get('MATDATE', '')
            
            # Дата выплаты купона (попытка получить из разных источников)
            # Вариант 1: COUPONDATE из marketdata
            coupon_date = market_dict.get('COUPONDATE', '')
            # Вариант 2: NEXTCOUPON из securities
            if not coupon_date:
                coupon_date = sec_dict.get('NEXTCOUPON', '')
            # Вариант 3: COUPONDATE из securities
            if not coupon_date:
                coupon_date = sec_dict.get('COUPONDATE', '')
            
            # Сумма купона (COUPONVALUE из securities)
            coupon_value = sec_dict.get('COUPONVALUE', '')
            
            # НКД - накопленный купонный доход (несколько вариантов)
            accruedint = market_dict.get('ACCRUEDINT', '')
            if not accruedint:
                accruedint = market_dict.get('ACCINT', '')
            if not accruedint:
                accruedint = sec_dict.get('ACCINT', '')
            
            # Периодичность выплаты купонов (COUPONFREQUENCY из securities)
            coupon_freq = sec_dict.get('COUPONFREQUENCY', '')
            if not coupon_freq:
                coupon_freq = sec_dict.get('COUPONFREQ', '')
            # Попытка получить периодичность из COUPONPERIOD
            if not coupon_freq:
                coupon_period = sec_dict.get('COUPONPERIOD', '')
                if coupon_period:
                    coupon_freq = self._get_frequency_from_period(coupon_period)
            
            # Номинал облигации
            face_value = sec_dict.get('FACEVALUE', '')
            
            # Статус (Рейтинг) — попробуем несколько полей
            status = sec_dict.get('RATINGOFDB', '')
            if not status:
                status = sec_dict.get('REGNUMBER', '')
            
            # Дата оферты
            offerdate = sec_dict.get('OFFERDATE', '')
            
            # Текущая стоимость (цена из marketdata)
            current_price = market_dict.get('PRICE', '')
            if not current_price:
                current_price = market_dict.get('LAST', '')
            
            # Последнее обновление
            last_update = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            bond = {
                'Котировка': secid,
                'Название': name,
                'Дата погашения': self._format_date(mat_date),
                'Дата выплаты купона': self._format_date(coupon_date),
                'Сумма купона': coupon_value,
                'НКД': accruedint,
                'Периодичность выплаты купонов': self._format_coupon_frequency(coupon_freq),
                'Номинал': face_value,
                'Статус (Рейтинг)': status,
                'Дата оферты': self._format_date(offerdate),
                'Текущая стоимость': current_price,
                'Последнее обновление': last_update
            }
            return bond
        except Exception as e:
            logger.error(f'Ошибка при извлечении информации об облигации: {e}')
            return None

    @staticmethod
    def _format_date(date_str: str) -> str:
        """
        Форматирование даты в читаемый вид
        
        Args:
            date_str: Строка с датой
            
        Returns:
            str: Отформатированная дата
        """
        if not date_str:
            return ''
        
        try:
            # Предполагаем формат YYYY-MM-DD
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d.%m.%Y')
        except (ValueError, AttributeError):
            return date_str

    @staticmethod
    def _format_coupon_frequency(freq: str) -> str:
        """
        Преобразование кода периодичности выплаты купонов в понятный формат
        
        Args:
            freq: Код периодичности из API
            
        Returns:
            str: Периодичность в понятном виде
        """
        if not freq:
            return ''
        
        # Преобразование кодов MOEX в русский текст
        frequency_mapping = {
            '0': 'Ежегодно',
            '1': 'Полугодие',
            '2': 'Квартал',
            '3': 'Месяц',
            '4': 'Неделя',
            '5': 'День',
            '6': 'Единовременно',
        }
        
        # Если freq это число, преобразуем его
        try:
            return frequency_mapping.get(str(int(freq)), freq)
        except (ValueError, TypeError):
            return str(freq)
    
    @staticmethod
    def _get_frequency_from_period(period_days: str) -> str:
        """
        Расчет периодичности выплаты на основе количества дней между купонами
        
        Args:
            period_days: Количество дней между купонами
            
        Returns:
            str: Периодичность в понятном виде
        """
        try:
            days = int(period_days)
            if days <= 7:
                return '4'  # Неделя
            elif days <= 31:
                return '3'  # Месяц
            elif days <= 92:
                return '2'  # Квартал
            elif days <= 184:
                return '1'  # Полугодие
            else:
                return '0'  # Ежегодно
        except (ValueError, TypeError):
            return ''

    def get_bonds(self) -> List[Dict]:
        """
        Получение списка облигаций
        
        Returns:
            List[Dict]: Список облигаций
        """
        return self.bonds_data

    def clear_cache(self):
        """Очистка кэша данных"""
        self.bonds_data = []
