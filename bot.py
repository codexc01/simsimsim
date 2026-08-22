"""
telegram-бот для круглосуточного мониторинга доступных номеров ucell.
поддержка встроенной нижней панели управления (replykeyboard).
"""

import asyncio
import logging
from typing import Dict, List, Set, Any
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

import config
from ucell import UcellClient, CATEGORIES, UcellNumber
from filters import (
    PRESET_PATTERNS,
    validate_pattern,
    check_number_match,
    MatchResult,
)
from database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

db = Database(config.DB_PATH)
router = Router()

UCELL_RESERVATION_URL = "https://ucell.uz/ru/services/reservation_numbers"


class AddPatternState(StatesGroup):
    waiting_for_pattern = State()


class SetIntervalState(StatesGroup):
    waiting_for_seconds = State()


# клавиатуры

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """постоянная нижняя панель управления внизу экрана telegram."""
    kb = [
        [KeyboardButton(text="📡 Мониторинг"), KeyboardButton(text="💎 Категории")],
        [KeyboardButton(text="🎯 Шаблоны"), KeyboardButton(text="⏱ Интервал")],
        [KeyboardButton(text="📊 Статус")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_main_menu_keyboard(is_monitoring: bool, check_interval: int) -> InlineKeyboardMarkup:
    status_icon = "🟢 Активен" if is_monitoring else "🔴 На паузе"
    kb = [
        [InlineKeyboardButton(text=f"📡 Мониторинг ({status_icon})", callback_data="toggle_monitoring")],
        [
            InlineKeyboardButton(text="💎 Категории", callback_data="menu_categories"),
            InlineKeyboardButton(text="🎯 Шаблоны", callback_data="menu_patterns"),
        ],
        [
            InlineKeyboardButton(text=f"⏱ Интервал ({check_interval}с)", callback_data="menu_interval"),
            InlineKeyboardButton(text="📊 Статус", callback_data="menu_status"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_categories_keyboard(enabled_cat_ids: List[int]) -> InlineKeyboardMarkup:
    kb = []
    for cat_id, cat_info in CATEGORIES.items():
        is_on = cat_id in enabled_cat_ids
        icon = "✅" if is_on else "❌"
        text = f"{icon} {cat_info['name']} ({cat_info['price_text']})"
        kb.append([InlineKeyboardButton(text=text, callback_data=f"cat_toggle_{cat_id}")])

    kb.append([
        InlineKeyboardButton(text="✅ Выбрать все", callback_data="cat_enable_all"),
        InlineKeyboardButton(text="❌ Отключить все", callback_data="cat_disable_all"),
    ])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_patterns_keyboard(
    enabled_patterns: List[str], custom_patterns: List[str]
) -> InlineKeyboardMarkup:
    kb = []
    all_patterns = list(dict.fromkeys(PRESET_PATTERNS + custom_patterns))

    for pat in all_patterns:
        is_on = pat in enabled_patterns
        icon = "✅" if is_on else "❌"
        kb.append([InlineKeyboardButton(text=f"{icon} {pat}", callback_data=f"pat_toggle_{pat}")])

    kb.append([
        InlineKeyboardButton(text="➕ Добавить шаблон", callback_data="pat_add"),
        InlineKeyboardButton(text="🗑 Очистить все", callback_data="pat_clear_all"),
    ])
    kb.append([
        InlineKeyboardButton(text="✅ Включить все", callback_data="pat_enable_all"),
        InlineKeyboardButton(text="❌ Отключить все", callback_data="pat_disable_all"),
    ])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_interval_keyboard(current_interval: int) -> InlineKeyboardMarkup:
    intervals = [30, 60, 120, 300, 600]
    row = []
    for sec in intervals:
        mark = "✅ " if sec == current_interval else ""
        text = f"{mark}{sec}с"
        row.append(InlineKeyboardButton(text=text, callback_data=f"set_int_{sec}"))
    
    kb = [
        row,
        [InlineKeyboardButton(text="✍️ Ввести своё значение (сек)", callback_data="custom_int")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_notification_keyboard() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text="🔗 Открыть Ucell", url=UCELL_RESERVATION_URL)]]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# команды и обработка нижней панели

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    inline_kb = get_main_menu_keyboard(settings["is_monitoring"], settings["check_interval"])
    reply_kb = get_main_reply_keyboard()

    await message.answer(
        "👋 **Мониторинг номеров Ucell**\n\n"
        "Панель управления закреплена внизу вашего экрана.\n"
        "Используйте кнопки ниже для быстрой настройки:",
        reply_markup=reply_kb,
        parse_mode=ParseMode.MARKDOWN,
    )
    await message.answer(
        "⚙️ **Меню настроек:**",
        reply_markup=inline_kb,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(F.text == "📡 Мониторинг")
async def btn_toggle_monitoring(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    new_state = not settings["is_monitoring"]
    await db.set_monitoring_state(user_id, new_state)

    status_text = "возобновлён 🟢" if new_state else "приостановлен 🔴"
    await message.answer(
        f"📡 **Статус мониторинга:** {status_text}",
        reply_markup=get_main_reply_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(F.text == "💎 Категории")
@router.message(Command("categories"))
async def cmd_categories(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_categories_keyboard(settings["enabled_categories"])
    await message.answer(
        "💎 **Категории номеров:**",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(F.text == "🎯 Шаблоны")
@router.message(Command("patterns"))
async def cmd_patterns(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_patterns_keyboard(settings["enabled_patterns"], settings["custom_patterns"])
    await message.answer(
        "🎯 **Шаблоны номеров:**\n"
        "_Добавляйте свои шаблоны с буквами (XXX AA XX) и конкретными цифрами (777 AA XX, 555 12 34)._",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(F.text == "⏱ Интервал")
async def btn_interval(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_interval_keyboard(settings["check_interval"])
    await message.answer(
        f"⏱ **Настройка интервала проверки:**\n\n"
        f"Текущий интервал: **{settings['check_interval']} секунд**.\n"
        "Выберите желаемый интервал из списка ниже или введите своё значение:",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(F.text == "📊 Статус")
@router.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)

    status_str = "🟢 Активен" if settings["is_monitoring"] else "🔴 На паузе"
    cat_count = len(settings["enabled_categories"])
    pat_count = len(settings["enabled_patterns"])

    msg_text = (
        "📊 **Статус вашей системы:**\n\n"
        f"• **Мониторинг:** {status_str}\n"
        f"• **Интервал:** {settings['check_interval']} сек.\n"
        f"• **Включено категорий:** {cat_count} из {len(CATEGORIES)}\n"
        f"• **Активных шаблонов:** {pat_count}\n"
    )
    await message.answer(
        msg_text,
        reply_markup=get_main_reply_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("pause"))
async def cmd_pause(message: Message):
    await db.set_monitoring_state(message.from_user.id, False)
    await message.answer("⏸ Мониторинг приостановлен.")


@router.message(Command("resume"))
async def cmd_resume(message: Message):
    await db.set_monitoring_state(message.from_user.id, True)
    await message.answer("▶️ Мониторинг возобновлён!")


# callback-обработчики

@router.callback_query(F.data == "menu_main")
async def cb_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_main_menu_keyboard(settings["is_monitoring"], settings["check_interval"])
    await callback.message.edit_text(
        "👋 **Главное меню:**",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )
    await callback.answer()


@router.callback_query(F.data == "toggle_monitoring")
async def cb_toggle_monitoring(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    new_state = not settings["is_monitoring"]
    await db.set_monitoring_state(user_id, new_state)

    kb = get_main_menu_keyboard(new_state, settings["check_interval"])
    await callback.message.edit_reply_markup(reply_markup=kb)
    status_text = "возобновлён 🟢" if new_state else "приостановлен 🔴"
    await callback.answer(f"Мониторинг {status_text}")


@router.callback_query(F.data == "menu_categories")
async def cb_menu_categories(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_categories_keyboard(settings["enabled_categories"])
    await callback.message.edit_text(
        "💎 **Категории номеров:**",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat_toggle_"))
async def cb_cat_toggle(callback: CallbackQuery):
    user_id = callback.from_user.id
    cat_id = int(callback.data.split("_")[-1])
    await db.toggle_category(user_id, cat_id)

    settings = await db.get_settings(user_id)
    kb = get_categories_keyboard(settings["enabled_categories"])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "cat_enable_all")
async def cb_cat_enable_all(callback: CallbackQuery):
    user_id = callback.from_user.id
    await db.enable_all_categories(user_id, list(CATEGORIES.keys()))

    settings = await db.get_settings(user_id)
    kb = get_categories_keyboard(settings["enabled_categories"])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Все категории включены ✅")


@router.callback_query(F.data == "cat_disable_all")
async def cb_cat_disable_all(callback: CallbackQuery):
    user_id = callback.from_user.id
    await db.disable_all_categories(user_id)

    settings = await db.get_settings(user_id)
    kb = get_categories_keyboard(settings["enabled_categories"])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Все категории отключены ❌")


@router.callback_query(F.data == "menu_patterns")
async def cb_menu_patterns(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_patterns_keyboard(settings["enabled_patterns"], settings["custom_patterns"])
    await callback.message.edit_text(
        "🎯 **Шаблоны номеров:**\n"
        "_Добавляйте свои шаблоны с буквами (XXX AA XX) и конкретными цифрами (777 AA XX, 555 12 34)._",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pat_toggle_"))
async def cb_pat_toggle(callback: CallbackQuery):
    user_id = callback.from_user.id
    pat = callback.data.replace("pat_toggle_", "")
    await db.toggle_pattern(user_id, pat)

    settings = await db.get_settings(user_id)
    kb = get_patterns_keyboard(settings["enabled_patterns"], settings["custom_patterns"])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "pat_enable_all")
async def cb_pat_enable_all(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    all_pats = list(dict.fromkeys(PRESET_PATTERNS + settings["custom_patterns"]))
    await db.enable_all_patterns(user_id, all_pats)

    settings = await db.get_settings(user_id)
    kb = get_patterns_keyboard(settings["enabled_patterns"], settings["custom_patterns"])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Все шаблоны включены ✅")


@router.callback_query(F.data == "pat_disable_all")
async def cb_pat_disable_all(callback: CallbackQuery):
    user_id = callback.from_user.id
    await db.disable_all_patterns(user_id)

    settings = await db.get_settings(user_id)
    kb = get_patterns_keyboard(settings["enabled_patterns"], settings["custom_patterns"])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Все шаблоны отключены ❌")


@router.callback_query(F.data == "pat_clear_all")
async def cb_pat_clear_all(callback: CallbackQuery):
    user_id = callback.from_user.id
    await db.clear_all_patterns(user_id)

    settings = await db.get_settings(user_id)
    kb = get_patterns_keyboard(settings["enabled_patterns"], settings["custom_patterns"])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Список шаблонов очищен 🗑")


@router.callback_query(F.data == "pat_add")
async def cb_pat_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPatternState.waiting_for_pattern)
    await callback.message.answer(
        "✍️ **Отправьте шаблон в чат:**\n\n"
        "Вы можете использовать как буквы, так и точные цифры:\n"
        "• `XXX AA XX` (любые комбинации букв)\n"
        "• `777 AA XX` (начинается на 777)\n"
        "• `555 XX 55` (начинается и заканчивается на 555/55)\n"
        "• `777 55 77` (точный фрагмент)\n"
        "• `AB AB AB`\n\n"
        "_Буквы задают связи (одинаковые буквы = одинаковые цифры), а цифры требуют точного совпадения._",
        parse_mode=ParseMode.MARKDOWN,
    )
    await callback.answer()


@router.message(AddPatternState.waiting_for_pattern)
async def process_add_pattern(message: Message, state: FSMContext):
    pattern_input = message.text.strip().upper()
    if not validate_pattern(pattern_input):
        await message.answer(
            "❌ **Некорректный шаблон!**\n"
            "Шаблон должен содержать от 2 до 12 символов (буквы A-Z, цифры, пробелы).\n"
            "Попробуйте ещё раз:"
        )
        return

    user_id = message.from_user.id
    await db.add_custom_pattern(user_id, pattern_input)
    await state.clear()

    settings = await db.get_settings(user_id)
    kb = get_patterns_keyboard(settings["enabled_patterns"], settings["custom_patterns"])
    await message.answer(
        f"✅ Шаблон **{pattern_input}** добавлен и активирован!",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )


# настройка интервала

@router.callback_query(F.data == "menu_interval")
async def cb_menu_interval(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_interval_keyboard(settings["check_interval"])
    await callback.message.edit_text(
        f"⏱ **Настройка интервала проверки:**\n\n"
        f"Текущий интервал: **{settings['check_interval']} секунд**.\n"
        "Выберите желаемый интервал из списка ниже или введите своё значение:",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_int_"))
async def cb_set_int(callback: CallbackQuery):
    user_id = callback.from_user.id
    sec = int(callback.data.split("_")[-1])
    await db.set_check_interval(user_id, sec)

    kb = get_interval_keyboard(sec)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer(f"Интервал установлен: {sec} сек.")


@router.callback_query(F.data == "custom_int")
async def cb_custom_int(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SetIntervalState.waiting_for_seconds)
    await callback.message.answer(
        "⏱ **Введите интервал проверки в секундах (например: 45, 120, 300):**\n"
        "_Минимальный интервал — 10 секунд._"
    )
    await callback.answer()


@router.message(SetIntervalState.waiting_for_seconds)
async def process_custom_int(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or int(text) < 10:
        await message.answer("❌ Введите число секунд (не менее 10):")
        return

    sec = int(text)
    user_id = message.from_user.id
    await db.set_check_interval(user_id, sec)
    await state.clear()

    settings = await db.get_settings(user_id)
    kb = get_main_menu_keyboard(settings["is_monitoring"], settings["check_interval"])
    await message.answer(
        f"✅ Интервал проверки сохранён: **{sec} сек.**",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data == "menu_status")
async def cb_menu_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)

    status_str = "🟢 Активен" if settings["is_monitoring"] else "🔴 На паузе"
    cat_count = len(settings["enabled_categories"])
    pat_count = len(settings["enabled_patterns"])

    msg_text = (
        "📊 **Статус вашей системы:**\n\n"
        f"• **Мониторинг:** {status_str}\n"
        f"• **Интервал:** {settings['check_interval']} сек.\n"
        f"• **Включено категорий:** {cat_count} из {len(CATEGORIES)}\n"
        f"• **Активных шаблонов:** {pat_count}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")]
    ])
    await callback.message.edit_text(msg_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@router.callback_query(F.data == "ignore")
async def cb_ignore(callback: CallbackQuery):
    await callback.answer()


# фоновая задача мониторинга

async def monitoring_task(bot: Bot):
    logger.info("Запуск фоновой задачи мониторинга...")
    client = UcellClient()

    last_user_checks: Dict[int, float] = {}

    while True:
        try:
            active_users = await db.get_all_active_users()
            now = asyncio.get_event_loop().time()

            due_users = []
            for user in active_users:
                uid = user["user_id"]
                interval = user.get("check_interval", 120)
                last_time = last_user_checks.get(uid, 0)
                if now - last_time >= interval:
                    due_users.append(user)

            if due_users:
                all_needed_cats: Set[int] = set()
                for user in due_users:
                    all_needed_cats.update(user.get("enabled_categories", []))

                if all_needed_cats:
                    fetched_by_cat: Dict[int, List[UcellNumber]] = {}
                    all_available_raw: Set[str] = set()

                    for cat_id in all_needed_cats:
                        numbers = await client.fetch_numbers(category_id=cat_id, page_size=100)
                        fetched_by_cat[cat_id] = numbers
                        for num in numbers:
                            all_available_raw.add(num.raw_number)

                    await db.update_seen_numbers(all_available_raw)

                    for user in due_users:
                        user_id = user["user_id"]
                        last_user_checks[user_id] = now
                        user_cats = set(user.get("enabled_categories", []))
                        user_pats = user.get("enabled_patterns", [])

                        if not user_cats or not user_pats:
                            continue

                        for cat_id in user_cats:
                            for num in fetched_by_cat.get(cat_id, []):
                                match_res: MatchResult = check_number_match(
                                    num.raw_number, enabled_patterns=user_pats, check_auto=True
                                )

                                if match_res.matched:
                                    if await db.should_notify(user_id, num.raw_number):
                                        notification_text = (
                                            "🔥 **Найден красивый номер!**\n\n"
                                            f"📱 `{num.formatted_number}`\n"
                                            f"💎 **Категория:** {num.category_name}\n"
                                            f"💰 **Цена:** {num.price_text}\n"
                                            f"🎯 **Шаблон:** {match_res.reason}\n"
                                        )
                                        try:
                                            await bot.send_message(
                                                chat_id=user_id,
                                                text=notification_text,
                                                reply_markup=get_notification_keyboard(),
                                                parse_mode=ParseMode.MARKDOWN,
                                            )
                                            logger.info(f"Уведомление отправлено {user_id}: {num.formatted_number}")
                                            await db.record_notification(
                                                user_id,
                                                num.raw_number,
                                                num.msisdn_id,
                                                num.category_id,
                                                num.formatted_number,
                                                num.price_text,
                                            )
                                        except Exception as send_err:
                                            logger.error(f"Ошибка отправки пользователю {user_id}: {send_err}")

        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)

        await asyncio.sleep(10)


# точка входа

async def main():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN не задан в файле .env!")
        return

    await db.init_db()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(router)

    asyncio.create_task(monitoring_task(bot))

    logger.info("Бот успешно запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
