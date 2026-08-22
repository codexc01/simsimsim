"""
Telegram bot for Ucell beautiful numbers monitoring (aiogram 3).
Multi-user support enabled.
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize database
db = Database(config.DB_PATH)
router = Router()

UCELL_RESERVATION_URL = "https://ucell.uz/ru/services/reservation_numbers"


class AddPatternState(StatesGroup):
    waiting_for_pattern = State()


# --- Keyboards ---

def get_main_menu_keyboard(is_monitoring: bool) -> InlineKeyboardMarkup:
    status_icon = "🟢 Активен" if is_monitoring else "🔴 На паузе"
    btn_text = f"📡 Мониторинг ({status_icon})"
    kb = [
        [InlineKeyboardButton(text=btn_text, callback_data="toggle_monitoring")],
        [
            InlineKeyboardButton(text="💎 Категории", callback_data="menu_categories"),
            InlineKeyboardButton(text="🎯 Шаблоны", callback_data="menu_patterns"),
        ],
        [InlineKeyboardButton(text="📊 Статус", callback_data="menu_status")],
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
        InlineKeyboardButton(text="🗑 Мои шаблоны", callback_data="pat_my_list"),
    ])
    kb.append([
        InlineKeyboardButton(text="✅ Включить все", callback_data="pat_enable_all"),
        InlineKeyboardButton(text="❌ Отключить все", callback_data="pat_disable_all"),
    ])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_my_patterns_keyboard(custom_patterns: List[str]) -> InlineKeyboardMarkup:
    kb = []
    for pat in custom_patterns:
        kb.append([
            InlineKeyboardButton(text=f"📌 {pat}", callback_data="ignore"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"pat_del_{pat}"),
        ])
    kb.append([InlineKeyboardButton(text="⬅️ Назад к шаблонам", callback_data="menu_patterns")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_notification_keyboard() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text="🔗 Открыть Ucell", url=UCELL_RESERVATION_URL)]]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- Command Handlers ---

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_main_menu_keyboard(settings["is_monitoring"])
    await message.answer(
        "👋 **Вас приветствует бот мониторинга номеров Ucell!**\n\n"
        "Выберите нужный раздел в меню ниже:",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("categories"))
async def cmd_categories(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_categories_keyboard(settings["enabled_categories"])
    await message.answer("💎 **Настройка категорий номеров:**", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("patterns"))
async def cmd_patterns(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_patterns_keyboard(settings["enabled_patterns"], settings["custom_patterns"])
    await message.answer("🎯 **Настройка шаблонов красивых номеров:**", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    settings = await db.get_settings(user_id)

    status_str = "🟢 Активен (24/7)" if settings["is_monitoring"] else "🔴 На паузе"
    cat_count = len(settings["enabled_categories"])
    pat_count = len(settings["enabled_patterns"])
    custom_count = len(settings["custom_patterns"])

    msg_text = (
        "📊 **Статус вашей системы:**\n\n"
        f"• **Мониторинг:** {status_str}\n"
        f"• **Интервал проверки:** {config.CHECK_INTERVAL} сек.\n"
        f"• **Включено категорий:** {cat_count} из {len(CATEGORIES)}\n"
        f"• **Включено шаблонов:** {pat_count}\n"
        f"• **Пользовательских шаблонов:** {custom_count}\n"
    )
    await message.answer(msg_text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("pause"))
async def cmd_pause(message: Message):
    user_id = message.from_user.id
    await db.set_monitoring_state(user_id, False)
    await message.answer("⏸ Мониторинг временно приостановлен.")


@router.message(Command("resume"))
async def cmd_resume(message: Message):
    user_id = message.from_user.id
    await db.set_monitoring_state(user_id, True)
    await message.answer("▶️ Мониторинг возобновлён!")


# --- Callback Query Handlers ---

@router.callback_query(F.data == "menu_main")
async def cb_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_main_menu_keyboard(settings["is_monitoring"])
    await callback.message.edit_text(
        "👋 **Главное меню мониторинга Ucell:**",
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

    kb = get_main_menu_keyboard(new_state)
    await callback.message.edit_reply_markup(reply_markup=kb)
    status_text = "возобновлён 🟢" if new_state else "приостановлен 🔴"
    await callback.answer(f"Мониторинг {status_text}")


@router.callback_query(F.data == "menu_categories")
async def cb_menu_categories(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    kb = get_categories_keyboard(settings["enabled_categories"])
    await callback.message.edit_text(
        "💎 **Настройка категорий номеров:**",
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
        "🎯 **Настройка шаблонов красивых номеров:**",
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


@router.callback_query(F.data == "pat_add")
async def cb_pat_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPatternState.waiting_for_pattern)
    await callback.message.answer(
        "✍️ **Введите ваш шаблон в чат:**\n\n"
        "Например:\n"
        "`XXX AA XX`\n"
        "`AB AB AB`\n"
        "`ABC ABC`\n\n"
        "_Символы обозначают отношения между цифрами (одинаковые буквы = одинаковые цифры)._",
        parse_mode=ParseMode.MARKDOWN,
    )
    await callback.answer()


@router.message(AddPatternState.waiting_for_pattern)
async def process_add_pattern(message: Message, state: FSMContext):
    pattern_input = message.text.strip().upper()
    if not validate_pattern(pattern_input):
        await message.answer(
            "❌ **Некорректный шаблон!**\n"
            "Шаблон должен содержать от 3 до 12 символов (буквы A-Z, цифры, пробелы).\n"
            "Попробуйте ещё раз:"
        )
        return

    user_id = message.from_user.id
    await db.add_custom_pattern(user_id, pattern_input)
    await state.clear()

    settings = await db.get_settings(user_id)
    kb = get_patterns_keyboard(settings["enabled_patterns"], settings["custom_patterns"])
    await message.answer(
        f"✅ Шаблон **{pattern_input}** успешно добавлен и включён!",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data == "pat_my_list")
async def cb_pat_my_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    customs = settings["custom_patterns"]

    if not customs:
        await callback.answer("У вас пока нет пользовательских шаблонов.", show_alert=True)
        return

    kb = get_my_patterns_keyboard(customs)
    await callback.message.edit_text(
        "🗑 **Мои пользовательские шаблоны:**",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pat_del_"))
async def cb_pat_delete(callback: CallbackQuery):
    user_id = callback.from_user.id
    pat = callback.data.replace("pat_del_", "")
    await db.remove_custom_pattern(user_id, pat)

    settings = await db.get_settings(user_id)
    customs = settings["custom_patterns"]
    if customs:
        kb = get_my_patterns_keyboard(customs)
        await callback.message.edit_reply_markup(reply_markup=kb)
    else:
        kb = get_patterns_keyboard(settings["enabled_patterns"], customs)
        await callback.message.edit_text(
            "🎯 **Настройка шаблонов красивых номеров:**",
            reply_markup=kb,
            parse_mode=ParseMode.MARKDOWN,
        )

    await callback.answer(f"Шаблон {pat} удалён")


@router.callback_query(F.data == "menu_status")
async def cb_menu_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)

    status_str = "🟢 Активен (24/7)" if settings["is_monitoring"] else "🔴 На паузе"
    cat_count = len(settings["enabled_categories"])
    pat_count = len(settings["enabled_patterns"])
    custom_count = len(settings["custom_patterns"])

    msg_text = (
        "📊 **Статус вашей системы:**\n\n"
        f"• **Мониторинг:** {status_str}\n"
        f"• **Интервал проверки:** {config.CHECK_INTERVAL} сек.\n"
        f"• **Включено категорий:** {cat_count} из {len(CATEGORIES)}\n"
        f"• **Включено шаблонов:** {pat_count}\n"
        f"• **Пользовательских шаблонов:** {custom_count}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_main")]
    ])
    await callback.message.edit_text(msg_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@router.callback_query(F.data == "ignore")
async def cb_ignore(callback: CallbackQuery):
    await callback.answer()


# --- Background Monitoring Task ---

async def monitoring_task(bot: Bot):
    """
    Background worker that runs continuously every CHECK_INTERVAL seconds.
    Fetches numbers from Ucell API and alerts active users based on their individual settings.
    """
    logger.info("Starting background monitoring task...")
    client = UcellClient()

    while True:
        try:
            active_users = await db.get_all_active_users()
            if not active_users:
                await asyncio.sleep(config.CHECK_INTERVAL)
                continue

            # Aggregate all categories needed across all active users
            all_needed_cats: Set[int] = set()
            for user in active_users:
                all_needed_cats.update(user.get("enabled_categories", []))

            if not all_needed_cats:
                await asyncio.sleep(config.CHECK_INTERVAL)
                continue

            # Fetch numbers grouped by category
            fetched_by_cat: Dict[int, List[UcellNumber]] = {}
            all_available_raw: Set[str] = set()

            for cat_id in all_needed_cats:
                numbers = await client.fetch_numbers(category_id=cat_id, page_size=100)
                fetched_by_cat[cat_id] = numbers
                for num in numbers:
                    all_available_raw.add(num.raw_number)

            # Update DB active status
            await db.update_seen_numbers(all_available_raw)

            # Check matches per user
            for user in active_users:
                user_id = user["user_id"]
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
                                    logger.info(f"Notified user {user_id} about number: {num.formatted_number}")
                                    await db.record_notification(
                                        user_id,
                                        num.raw_number,
                                        num.msisdn_id,
                                        num.category_id,
                                        num.formatted_number,
                                        num.price_text,
                                    )
                                except Exception as send_err:
                                    logger.error(f"Failed to send notification to user {user_id}: {send_err}")

        except Exception as e:
            logger.error(f"Error in background monitoring loop: {e}", exc_info=True)

        await asyncio.sleep(config.CHECK_INTERVAL)


# --- Main entry point ---

async def main():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN is missing! Please set it in .env file.")
        return

    # Initialize DB
    await db.init_db()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(router)

    # Start background task
    asyncio.create_task(monitoring_task(bot))

    logger.info("Bot starting polling for all users...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
