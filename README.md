# Ucell Number Monitor Bot

Асинхронный Telegram-бот на Python (aiogram 3) для 24/7 мониторинга свободных красивых номеров Ucell

## Возможности

- Работает напрямую через веб-API Ucell без браузеров и Selenium
- Поиск по структуре номера (XXX AA XX, AB AB AB, ABC ABC, ABCCBA) и точным цифрам (777 AA XX, 555 12 34)
- Авто-детекция палиндромов, последовательностей (1234, 9876) и повторов (000, 777, 1111)
- Выбор категорий номеров (Simple, Steel, Bronze, Silver, Gold, Platinum, Vip, Lux)
- Индивидуальная настройка интервала проверки для каждого пользователя
- База данных SQLite (aiosqlite) для отслеживания повторных уведомлений

## Запуск

1. Перейти в папку проекта:
```bash
cd ucell_monitor
```

2. Установить зависимости:
```bash
pip install -r requirements.txt
```

3. Создать файл `.env` и указать токен бота:
```env
BOT_TOKEN=ваш_токен_бота
CHECK_INTERVAL=120
```

4. Запустить бота:
```bash
python3 bot.py
```
