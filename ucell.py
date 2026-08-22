"""
ucell api module for fetching available phone numbers.
optimized for high performance and minimal memory footprint.
"""

from dataclasses import dataclass
import logging
import asyncio
import re
from typing import List, Dict, Optional, Any, Tuple
import aiohttp

logger = logging.getLogger(__name__)

API_URL = "https://cw-corn00.ucell.uz/api/v1/phone_number/search-mask"

# предкомпилированные регулярные выражения для максимального ускорения
RE_DIGITS = re.compile(r"\D")

CATEGORIES: Dict[int, Dict[str, Any]] = {
    1: {"name": "Simple", "price_text": "0 сум", "price": 0},
    111: {"name": "Steel", "price_text": "10 000 сум", "price": 10000},
    109: {"name": "Bronze", "price_text": "50 000 сум", "price": 50000},
    108: {"name": "Silver", "price_text": "100 000 сум", "price": 100000},
    107: {"name": "Gold", "price_text": "250 000 сум", "price": 250000},
    106: {"name": "Platinum", "price_text": "500 000 сум", "price": 500000},
    105: {"name": "Vip", "price_text": "1 000 000 сум", "price": 1000000},
    104: {"name": "Lux", "price_text": "3 000 000 сум", "price": 3000000},
    101: {"name": "Privilege", "price_text": "20 000 000 сум", "price": 20000000},
    112: {"name": "Diamond", "price_text": "50 000 000 сум", "price": 50000000},
    114: {"name": "Elite", "price_text": "100 000 000 сум", "price": 100000000},
    115: {"name": "Luxury", "price_text": "300 000 000 сум", "price": 300000000},
    116: {"name": "Exclusive", "price_text": "500 000 000 сум", "price": 500000000},
}


@dataclass
class UcellNumber:
    msisdn_id: int
    raw_number: str       # e.g. "998501527854"
    formatted_number: str # e.g. "+998 50 152 78 54"
    category_id: int      # e.g. 1
    category_name: str    # e.g. "Simple"
    price: int            # e.g. 0
    price_text: str       # e.g. "0 сум"


def normalize_number(phone_str: str) -> Tuple[str, str]:
    """быстрая нормализация номера в цифры и красивый формат."""
    digits = RE_DIGITS.sub("", phone_str)
    if digits.startswith("80") and len(digits) == 11:
        digits = "998" + digits[1:]
    elif not digits.startswith("998") and len(digits) == 9:
        digits = "998" + digits

    if len(digits) == 12 and digits.startswith("998"):
        formatted = f"+998 {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"
    else:
        formatted = f"+{digits}" if digits else phone_str

    return digits, formatted


class UcellClient:
    """оптимизированный асинхронный клиент ucell api с пулом соединений."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=20, keepalive_timeout=30)
            self._session = aiohttp.ClientSession(
                connector=connector,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                },
            )
            self._owns_session = True
        return self._session

    async def close(self):
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def fetch_numbers(
        self,
        category_id: int = 0,
        page_num: int = 1,
        page_size: int = 100,
        timeout: float = 8.0,
        max_retries: int = 2,
    ) -> List[UcellNumber]:
        session = await self._get_session()
        payload = {
            "pager": {"pageNum": page_num, "pageSize": page_size},
            "filter": {
                "msisdn_type": category_id,
                "search_type": 2,
                "query": "",
                "lang": "ru",
            },
        }

        for attempt in range(1, max_retries + 1):
            try:
                async with session.post(
                    API_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        if attempt == max_retries:
                            return []
                        await asyncio.sleep(0.5)
                        continue

                    data = await response.json()
                    items = data.get("data", [])
                    if not items:
                        return []

                    result = []
                    cat_info = CATEGORIES.get(category_id, {})
                    default_cat_name = cat_info.get("name", "Unknown")
                    default_price = cat_info.get("price", 0)
                    default_price_text = cat_info.get("price_text", "0 сум")

                    for item in items:
                        msisdn_id = item.get("msisdn_id", 0)
                        raw_input = item.get("msisdn") or item.get("phone_number", "")
                        raw_num, formatted_num = normalize_number(str(raw_input))
                        cat_id = item.get("msisdn_type", category_id)

                        cat_name = item.get("type_name") or default_cat_name
                        price = item.get("price", default_price)
                        price_text = item.get("price_text") or default_price_text

                        result.append(
                            UcellNumber(
                                msisdn_id=msisdn_id,
                                raw_number=raw_num,
                                formatted_number=formatted_num,
                                category_id=cat_id,
                                category_name=cat_name,
                                price=price,
                                price_text=price_text,
                            )
                        )
                    return result

            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt == max_retries:
                    return []
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"ошибка получения номеров ucell: {e}")
                return []

        return []
