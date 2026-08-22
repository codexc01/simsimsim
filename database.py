"""
модуль работы с sqlite базами данных.
оптимизирован с помощью wal режима, кэширования и индексов.
"""

from datetime import datetime
import json
import logging
from typing import Dict, List, Optional, Set, Any
import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = "bot_data.db"


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        """инициализация базы данных, включение wal и создание индексов."""
        async with aiosqlite.connect(self.db_path) as db:
            # настройки быстродействия и минимального потребления памяти
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA synchronous = NORMAL;")
            await db.execute("PRAGMA temp_store = MEMORY;")
            await db.execute("PRAGMA cache_size = -2000;")

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    is_monitoring INTEGER DEFAULT 1,
                    check_interval INTEGER DEFAULT 120,
                    enabled_categories TEXT DEFAULT '[]',
                    enabled_patterns TEXT DEFAULT '[]',
                    custom_patterns TEXT DEFAULT '[]'
                )
                """
            )

            # миграция структуры
            async with db.execute("PRAGMA table_info(user_settings)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
                if "check_interval" not in columns:
                    await db.execute("ALTER TABLE user_settings ADD COLUMN check_interval INTEGER DEFAULT 120")

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sent_numbers (
                    user_id INTEGER,
                    raw_number TEXT,
                    msisdn_id INTEGER,
                    category_id INTEGER,
                    formatted_number TEXT,
                    price_text TEXT,
                    notified_at TIMESTAMP,
                    last_seen_at TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, raw_number)
                )
                """
            )

            # индексы для мгновенного поиска
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sent_active ON sent_numbers(is_active);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sent_user_raw ON sent_numbers(user_id, raw_number);")

            await db.commit()

    async def get_settings(self, user_id: int) -> Dict[str, Any]:
        """получает настройки пользователя. если их нет — создаёт дефолтные."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT is_monitoring, check_interval, enabled_categories, enabled_patterns, custom_patterns FROM user_settings WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "user_id": user_id,
                        "is_monitoring": bool(row[0]),
                        "check_interval": row[1] or 120,
                        "enabled_categories": json.loads(row[2] or "[]"),
                        "enabled_patterns": json.loads(row[3] or "[]"),
                        "custom_patterns": json.loads(row[4] or "[]"),
                    }

            # настройки по умолчанию для нового пользователя
            default_categories = [1, 111, 109, 108, 107, 106, 105, 104]
            default_interval = 120
            default_patterns: List[str] = []
            default_custom: List[str] = []

            await db.execute(
                """
                INSERT OR REPLACE INTO user_settings 
                (user_id, is_monitoring, check_interval, enabled_categories, enabled_patterns, custom_patterns) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    1,
                    default_interval,
                    json.dumps(default_categories),
                    json.dumps(default_patterns),
                    json.dumps(default_custom),
                ),
            )
            await db.commit()

            return {
                "user_id": user_id,
                "is_monitoring": True,
                "check_interval": default_interval,
                "enabled_categories": default_categories,
                "enabled_patterns": default_patterns,
                "custom_patterns": default_custom,
            }

    async def get_all_active_users(self) -> List[Dict[str, Any]]:
        """возвращает список всех активных пользователей с включённым мониторингом."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT user_id, is_monitoring, check_interval, enabled_categories, enabled_patterns, custom_patterns FROM user_settings WHERE is_monitoring = 1"
            ) as cursor:
                rows = await cursor.fetchall()
                result = []
                for row in rows:
                    result.append({
                        "user_id": row[0],
                        "is_monitoring": bool(row[1]),
                        "check_interval": row[2] or 120,
                        "enabled_categories": json.loads(row[3] or "[]"),
                        "enabled_patterns": json.loads(row[4] or "[]"),
                        "custom_patterns": json.loads(row[5] or "[]"),
                    })
                return result

    async def save_settings(self, user_id: int, settings: Dict[str, Any]):
        """сохраняет настройки пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO user_settings 
                (user_id, is_monitoring, check_interval, enabled_categories, enabled_patterns, custom_patterns)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    1 if settings.get("is_monitoring", True) else 0,
                    settings.get("check_interval", 120),
                    json.dumps(settings.get("enabled_categories", [])),
                    json.dumps(settings.get("enabled_patterns", [])),
                    json.dumps(settings.get("custom_patterns", [])),
                ),
            )
            await db.commit()

    async def set_monitoring_state(self, user_id: int, is_active: bool):
        settings = await self.get_settings(user_id)
        settings["is_monitoring"] = is_active
        await self.save_settings(user_id, settings)

    async def set_check_interval(self, user_id: int, interval_seconds: int):
        settings = await self.get_settings(user_id)
        settings["check_interval"] = max(10, interval_seconds)
        await self.save_settings(user_id, settings)

    async def toggle_category(self, user_id: int, category_id: int) -> bool:
        settings = await self.get_settings(user_id)
        cats: List[int] = settings.get("enabled_categories", [])
        if category_id in cats:
            cats.remove(category_id)
            enabled = False
        else:
            cats.append(category_id)
            enabled = True
        settings["enabled_categories"] = cats
        await self.save_settings(user_id, settings)
        return enabled

    async def enable_all_categories(self, user_id: int, all_cat_ids: List[int]):
        settings = await self.get_settings(user_id)
        settings["enabled_categories"] = list(set(all_cat_ids))
        await self.save_settings(user_id, settings)

    async def disable_all_categories(self, user_id: int):
        settings = await self.get_settings(user_id)
        settings["enabled_categories"] = []
        await self.save_settings(user_id, settings)

    async def toggle_pattern(self, user_id: int, pattern: str) -> bool:
        settings = await self.get_settings(user_id)
        pats: List[str] = settings.get("enabled_patterns", [])
        if pattern in pats:
            pats.remove(pattern)
            enabled = False
        else:
            pats.append(pattern)
            enabled = True
        settings["enabled_patterns"] = pats
        await self.save_settings(user_id, settings)
        return enabled

    async def add_custom_pattern(self, user_id: int, pattern: str) -> bool:
        settings = await self.get_settings(user_id)
        customs: List[str] = settings.get("custom_patterns", [])
        pats: List[str] = settings.get("enabled_patterns", [])

        if pattern not in customs:
            customs.append(pattern)
        if pattern not in pats:
            pats.append(pattern)

        settings["custom_patterns"] = customs
        settings["enabled_patterns"] = pats
        await self.save_settings(user_id, settings)
        return True

    async def remove_custom_pattern(self, user_id: int, pattern: str) -> bool:
        settings = await self.get_settings(user_id)
        customs: List[str] = settings.get("custom_patterns", [])
        pats: List[str] = settings.get("enabled_patterns", [])

        if pattern in customs:
            customs.remove(pattern)
        if pattern in pats:
            pats.remove(pattern)

        settings["custom_patterns"] = customs
        settings["enabled_patterns"] = pats
        await self.save_settings(user_id, settings)
        return True

    async def enable_all_patterns(self, user_id: int, all_patterns: List[str]):
        settings = await self.get_settings(user_id)
        settings["enabled_patterns"] = list(set(all_patterns))
        await self.save_settings(user_id, settings)

    async def disable_all_patterns(self, user_id: int):
        settings = await self.get_settings(user_id)
        settings["enabled_patterns"] = []
        await self.save_settings(user_id, settings)

    async def clear_all_patterns(self, user_id: int):
        """полная очистка всех шаблонов пользователя."""
        settings = await self.get_settings(user_id)
        settings["custom_patterns"] = []
        settings["enabled_patterns"] = []
        await self.save_settings(user_id, settings)

    async def should_notify(self, user_id: int, raw_number: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT is_active FROM sent_numbers WHERE user_id = ? AND raw_number = ?",
                (user_id, raw_number),
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return True
                return row[0] == 0

    async def record_notification(
        self,
        user_id: int,
        raw_number: str,
        msisdn_id: int,
        category_id: int,
        formatted_number: str,
        price_text: str,
    ):
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO sent_numbers 
                (user_id, raw_number, msisdn_id, category_id, formatted_number, price_text, notified_at, last_seen_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    user_id,
                    raw_number,
                    msisdn_id,
                    category_id,
                    formatted_number,
                    price_text,
                    now,
                    now,
                ),
            )
            await db.commit()

    async def update_seen_numbers(self, currently_available_raw: Set[str]):
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT DISTINCT raw_number FROM sent_numbers WHERE is_active = 1") as cursor:
                rows = await cursor.fetchall()
                active_in_db = {row[0] for row in rows}

            disappeared = active_in_db - currently_available_raw
            if disappeared:
                await db.executemany(
                    "UPDATE sent_numbers SET is_active = 0 WHERE raw_number = ?",
                    [(raw_num,) for raw_num in disappeared],
                )

            if currently_available_raw:
                await db.executemany(
                    "UPDATE sent_numbers SET last_seen_at = ?, is_active = 1 WHERE raw_number = ?",
                    [(now, raw_num) for raw_num in currently_available_raw],
                )

            await db.commit()
