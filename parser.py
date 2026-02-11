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
        self.currency_cache = {}  # Кэш валют для облигаций
        self.exchange_rates = {}  # Кэш валютных курсов (USD, EUR и т.д. к RUB)

    def fetch_bonds_data(self) -> List[Dict]:
        """
        Получение данных об облигациях с MOEX
        
        Returns:
            List[Dict]: Список словарей с данными об облигациях
        """
        try:
            # Получаем актуальные валютные курсы перед парсингом
            self._fetch_exchange_rates()
            
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

    def _fetch_exchange_rates(self):
        """
        Получение актуальных валютных курсов с MOEX и CBRF
        Загружаем курсы основных валют (USD, EUR, CNY, JPY, CHF, GBP) к RUB
        """
        try:
            # Загружаем курсы валют через MOEX ISS API (статистика ЦБ РФ)
            url = 'https://iss.moex.com/iss/statistics/engines/currency/markets/selt/rates.json'
            
            response = requests.get(url, params={'iss.meta': 'off'}, headers=HEADERS, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            # Обработаем данные от CBRF (Центральный Банк РФ)
            if 'cbrf' in data:
                cbrf_data = data['cbrf']
                if 'data' in cbrf_data and 'columns' in cbrf_data:
                    cols = cbrf_data['columns']
                    rows = cbrf_data['data']
                    
                    if rows:
                        row = rows[0]  # Берём последние данные (первая строка)
                        row_dict = dict(zip(cols, row))
                        
                        # Ищем курсы по стандартным колонкам CBRF
                        currency_fields = {
                            'CBRF_USD_LAST': 'USD',
                            'CBRF_EUR_LAST': 'EUR',
                        }
                        
                        for field, currency in currency_fields.items():
                            rate = row_dict.get(field)
                            if rate:
                                try:
                                    rate_value = float(rate)
                                    if rate_value > 0:
                                        self.exchange_rates[currency] = rate_value
                                        logger.debug(f'Получен курс {currency}/RUB от CBRF: {rate_value}')
                                except (ValueError, TypeError):
                                    pass
            
            # Получаем курсы для CNY, JPY, CHF, GBP с MOEX через отдельные запросы
            logger.debug('Начинаю получение дополнительных курсов валют...')
            self._fetch_additional_exchange_rates()
            logger.debug(f'После дополнительных запросов: {self.exchange_rates}')
            
            # Используем дефолтные курсы если не получили основные (USD, EUR)
            if 'USD' not in self.exchange_rates or 'EUR' not in self.exchange_rates:
                raise Exception("Не получены основные валютные курсы")
            
            logger.info(f'Загружены актуальные валютные курсы: {self.exchange_rates}')
            
        except Exception as e:
            logger.error(f'Критическая ошибка при получении курсов: {e}')
            logger.warning('Программа продолжит работу')

    def _fetch_additional_exchange_rates(self):
        """
        Получение курсов для дополнительных валют (CNY, JPY, CHF, GBP) через разные источники
        """
        # Попытка 1: Попробуем получить из API по курс ЦБ РФ через другой эндпоинт
        cbrf_url = 'https://www.cbr-xml-daily.ru/daily_json.js'
        try:
            response = requests.get(cbrf_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'Valute' in data:
                    currency_map = {
                        'CNY': 'CNY',
                        'JPY': 'JPY',
                        'CHF': 'CHF',
                        'GBP': 'GBP',
                    }
                    
                    for api_code, currency in currency_map.items():
                        if currency in self.exchange_rates:
                            continue
                        
                        if api_code in data['Valute']:
                            rate_data = data['Valute'][api_code]
                            rate = rate_data.get('Value')
                            nominal = rate_data.get('Nominal', 1)
                            
                            if rate and nominal:
                                try:
                                    rate_value = float(rate) / float(nominal)
                                    if rate_value > 0:
                                        self.exchange_rates[currency] = rate_value
                                        logger.info(f'Получен курс {currency}/RUB от ЦБ РФ: {rate_value}')
                                except (ValueError, TypeError):
                                    pass
        except Exception as e:
            logger.debug(f'Не удалось получить курсы от ЦБ РФ: {e}')
        
        # Попытка 2: Используем MOEX данные если ЦБ не сработал
        currency_pairs = {
            'CNYRUB': 'CNY',
            'JPYRUB': 'JPY',
            'CHFRUB': 'CHF',
            'GBPRUB': 'GBP',
        }
        
        for pair, currency in currency_pairs.items():
            if currency in self.exchange_rates:
                continue
                
            try:
                url = f'https://iss.moex.com/iss/engines/currency/markets/selt/securities/{pair}.json'
                response = requests.get(url, params={'iss.meta': 'off'}, headers=HEADERS, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Попробуем использовать данные из securities если marketdata пуста
                    if 'securities' in data and 'data' in data['securities'] and data['securities']['data']:
                        sec_data = data['securities']['data']
                        cols = data['securities'].get('columns', [])
                        
                        if sec_data and cols:
                            sec_row = sec_data[0]
                            sec_dict = dict(zip(cols, sec_row))
                            
                            # Пытаемся получить цену
                            for price_field in ['PREVWAPRICE', 'PREVPRICE', 'WAPRICE']:
                                if price_field in sec_dict:
                                    price = sec_dict[price_field]
                                    if price and price not in ('', None, 0, '0'):
                                        try:
                                            rate_value = float(price)
                                            if rate_value > 0:
                                                self.exchange_rates[currency] = rate_value
                                                logger.debug(f'Получен курс {currency}/RUB от MOEX (securities): {rate_value}')
                                                break
                                        except (ValueError, TypeError):
                                            continue
            except Exception as e:
                logger.debug(f'Не удалось получить курс для {currency} из MOEX: {e}')

    def _get_currency_from_moex(self, secid: str) -> Optional[str]:
        """
        Получение информации о валюте облигации с MOEX через отдельный запрос
        
        Args:
            secid: Идентификатор ценной бумаги
            
        Returns:
            Optional[str]: Код валюты (USD, EUR, RUB и т.д.) или None
        """
        try:
            # Проверяем кэш
            if secid in self.currency_cache:
                return self.currency_cache[secid]
            
            # Запрос информации о конкретной облигации
            url = f'https://iss.moex.com/iss/securities/{secid}.json'
            
            params = {
                'iss.meta': 'off',
            }
            
            response = requests.get(url, params=params, headers=HEADERS, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if 'securities' in data and data['securities']['data']:
                sec_data = data['securities']['data'][0]
                sec_cols = data['securities']['columns']
                sec_dict = dict(zip(sec_cols, sec_data))
                
                # Проверяем несколько полей в порядке приоритета
                # 1. ISIN код
                isin = (sec_dict.get('ISIN') or '').strip().upper()
                if isin:
                    if isin.startswith('XS'):
                        return 'EUR'
                    elif isin.startswith('US'):
                        return 'USD'
                    elif isin.startswith('RU'):
                        return 'RUB'
                    elif isin.startswith('CH'):
                        return 'CNY'
                    elif isin.startswith('JP'):
                        return 'JPY'
                
                # 2. SECNAME (название)
                secname = (sec_dict.get('SECNAME') or '').upper()
                if 'USD' in secname or 'ДОЛЛАР' in secname:
                    return 'USD'
                elif 'EUR' in secname or 'ЕВРО' in secname:
                    return 'EUR'
                
                # 3. CURRENCYID
                currency = (sec_dict.get('CURRENCYID') or '').strip().upper()
                if currency:
                    if currency in ('SUR', 'RUR'):
                        return 'RUB'
                    return currency
                
                return None
            
            return None
            
        except requests.exceptions.Timeout:
            logger.debug(f'Timeout при получении валюты для {secid}')
            return None
        except requests.exceptions.RequestException as e:
            logger.debug(f'Ошибка при получении валюты для {secid}: {e}')
            return None
        except Exception as e:
            logger.debug(f'Неожиданная ошибка при обработке валюты {secid}: {e}')
            return None

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

            # Валюта облигации - приоритет: FACEUNIT > SECNAME (точные паттерны) > ISIN (XS) > отдельный запрос > RUB
            currency = ''
            currency_source = ''
            
            # Попытка 1: Использовать FACEUNIT (валюта номинала) - САМЫЙ НАДЕЖНЫЙ ИСТОЧНИК!
            # Это официальное поле на MOEX, показывает реальную валюту номинала облигации
            faceunit = (sec_dict.get('FACEUNIT') or '').strip().upper()
            if faceunit and faceunit not in ('', 'RUB', 'SUR', 'RUR'):
                # FACEUNIT содержит реальный код валюты (USD, EUR, GBP, JPY, CNY)
                currency = faceunit
                currency_source = 'FACEUNIT (валюта номинала)'
            elif faceunit in ('RUB', 'SUR', 'RUR'):
                # Явно указана рубль
                currency = 'RUB'
                currency_source = 'FACEUNIT (рубль)'
            
            # Попытка 2: Извлечь валюту из SECNAME (полного названия облигации)
            # На MOEX RU* ISINs используются для любых валют, поэтому SECNAME дополнительный способ
            # НО: нужно быть осторожнее - "Европлан" и "ЕвроТранс" - это названия компаний, не валюты!
            if not currency:
                name_upper = name.upper()
                
                # Проверяем точные паттерны валют в названии
                if 'USD' in name_upper or '-USD' in name_upper or 'USDRUR' in name_upper:
                    currency = 'USD'
                    currency_source = 'SECNAME'
                elif 'EUR' in name_upper or '-EUR' in name_upper or 'EURUR' in name_upper:
                    currency = 'EUR'
                    currency_source = 'SECNAME'
                elif 'GBP' in name_upper or 'ФУНТ' in name_upper:
                    currency = 'GBP'
                    currency_source = 'SECNAME'
                elif 'JPY' in name_upper or 'ЙЕН' in name_upper:
                    currency = 'JPY'
                    currency_source = 'SECNAME'
                elif 'CNY' in name_upper or 'ЮАНЬ' in name_upper or '-CNY' in name_upper:
                    currency = 'CNY'
                    currency_source = 'SECNAME'
            
            # Попытка 3: Проверка XS ISINs для EUR (если SECNAME не дал результат)
            if not currency:
                isin = (sec_dict.get('ISIN') or '').strip().upper()
                if isin and isin.startswith('XS'):
                    currency = 'EUR'
                    currency_source = 'ISIN (XS prefix)'
            
            # Попытка 4: Отдельный запрос к MOEX API для конкретной облигации
            if not currency:
                currency = self._get_currency_from_moex(secid)
                if currency:
                    currency_source = 'отдельный запрос MOEX'
            
            # Попытка 6: По умолчанию RUB если ничего не помогло
            if not currency:
                currency = 'RUB'
                currency_source = 'по умолчанию'
                logger.warning(f"Валюта не определена для облигации {secid} ({name}), используется RUB по умолчанию")

            currency_symbols = {
                'RUB': '₽',
                'RUR': '₽',
                'SUR': '₽',
                'USD': '$',
                'EUR': '€',
                'JPY': '¥',
                'CNY': '¥',
                'GBP': '£',
            }
            
            # Выводим валюту с символом
            currency_symbol = currency_symbols.get(currency, currency)
            currency_display = f'{currency} {currency_symbol}' if currency else 'Не определена'
            
            # Логирование для отладки с полной информацией
            logger.debug(f'Облигация {secid} ({name}): валюта={currency} {currency_symbol}, источник={currency_source}')

            # Статус (Рейтинг) — попробуем несколько полей
            status = sec_dict.get('RATINGOFDB', '')
            if not status:
                status = sec_dict.get('REGNUMBER', '')

            # Дата оферты
            offerdate = sec_dict.get('OFFERDATE', '')

            # Текущая стоимость (цена из marketdata с приоритетной цепочкой)
            # Приоритет: PRICE > LAST > PREVPRICE > (BID+OFFER)/2 > OPEN > HIGH > LOW > номинал (100%)
            current_price = None
            price_source = ''
            
            # Пытаемся получить текущую цену в разном порядке
            for price_field in ['PRICE', 'LAST', 'PREVPRICE', 'OPEN', 'HIGH', 'LOW']:
                price_value = market_dict.get(price_field)
                if price_value and price_value not in ('', None, 0, '0'):
                    try:
                        current_price = float(price_value)
                        price_source = price_field
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Если основные цены не найдены, пытаемся использовать среднее BID/OFFER
            if current_price is None:
                bid = market_dict.get('BID')
                offer = market_dict.get('OFFER')
                try:
                    bid_val = float(bid) if bid and bid not in ('', None, 0, '0') else None
                    offer_val = float(offer) if offer and offer not in ('', None, 0, '0') else None
                    if bid_val and offer_val:
                        current_price = (bid_val + offer_val) / 2
                        price_source = 'BID/OFFER avg'
                    elif bid_val:
                        current_price = bid_val
                        price_source = 'BID'
                    elif offer_val:
                        current_price = offer_val
                        price_source = 'OFFER'
                except (ValueError, TypeError):
                    pass
            
            # Если цена не найдена, оставляем пустую ячейку
            if current_price is None:
                current_price_display = ''
            else:
                current_price_display = round(current_price, 2)
            
            # Логирование для отладки
            if secid == 'BYM000002402':
                logger.debug(f'Облигация {secid}: текущая стоимость={current_price_display}% (источник: {price_source}), номинал={face_value}')

            # Стоимость в валюте (конвертирование в рубли с учётом курса)
            value_str = ''
            if current_price is not None:
                try:
                    price_percent = float(current_price)
                    face = float(face_value) if face_value else 1.0
                    if face == 0:
                        face = 100.0
                    
                    # Вычисляем абсолютную стоимость в валюте облигации
                    value_in_currency = face * price_percent / 100
                    
                    # Конвертируем в рубли если это не RUB
                    if currency and currency != 'RUB':
                        exchange_rate = self.exchange_rates.get(currency)
                        if exchange_rate and exchange_rate > 0:
                            value_in_rub = value_in_currency * exchange_rate
                            value_str = f"{round(value_in_rub, 2)} ₽"
                            logger.debug(f'{secid}: {value_in_currency:.2f} {currency} * {exchange_rate} = {value_in_rub:.2f} ₽')
                        else:
                            # Если курс не получен, показываем в исходной валюте
                            currency_symbol = {'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥', 'CNY': '¥'}.get(currency, currency)
                            value_str = f"{round(value_in_currency, 2)} {currency_symbol}"
                            logger.warning(f'{secid}: курс {currency} не найден, выводим в {currency_symbol}')
                    else:
                        # RUB - выводим сразу
                        value_str = f"{round(value_in_currency, 2)} ₽"
                except (ValueError, TypeError) as e:
                    logger.debug(f'Ошибка при вычислении стоимости {secid}: {e}')
                    value_str = ''

            # Последнее обновление
            last_update = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Количество выпущенных облигаций
            issue_size = sec_dict.get('ISSUESIZE', '')
            if not issue_size:
                issue_size = sec_dict.get('FACESIZE', '')
            if not issue_size:
                issue_size = sec_dict.get('ISSUE_SIZE', '')
            if not issue_size:
                issue_size = sec_dict.get('QUANTITY', '')
            # Форматирование количества
            if issue_size:
                try:
                    issue_num = float(issue_size)
                    # Форматируем число с разделителями
                    if issue_num == int(issue_num):
                        issue_size = f'{int(issue_num):,}'.replace(',', ' ')
                    else:
                        issue_size = f'{issue_num:,.2f}'.replace(',', ' ')
                except (ValueError, TypeError):
                    issue_size = str(issue_size) if issue_size else ''

            bond = {
                'Котировка': secid,
                'Название': name,
                'Дата погашения': self._format_date(mat_date),
                'Дата выплаты купона': self._format_date(coupon_date),
                'Дата следующей выплаты купона': self._format_date(sec_dict.get('NEXTCOUPON', '')),
                'Сумма купона': coupon_value,
                'НКД': accruedint,
                'Периодичность выплаты купонов': self._format_coupon_frequency(coupon_freq),
                'Номинал': face_value,
                'Валюта': currency_display,
                'Статус (Рейтинг)': status,
                'Дата оферты': self._format_date(offerdate),
                'Текущая стоимость': current_price_display,
                'Стоимость в валюте': value_str,
                'Количество выпущенных облигаций': issue_size,
                'Последнее обновление': last_update,
                'Ссылка на страницу MOEX': 'https://www.moex.com/ru/issue.aspx?board=TQCB&code='+secid
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
