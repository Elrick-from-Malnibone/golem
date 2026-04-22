import config
from database import db

def is_technical(text):
    """Проверяет, является ли сообщение техническим вопросом"""
    keywords = [
        "код", "ошибка", "баг", "функция", "класс", "скрипт", "бот", 
        "python", "питон", "сортировка", "алгоритм", "api", "json", 
        "библиотека", "установить", "import", "def", "async", "помоги",
        "как", "почему", "не работает", "поломалось"
    ]
    text_lower = text.lower()
    return any(k in text_lower for k in keywords) or "```" in text

async def handle_group(client, event, llm, user_id, text):
    """Обработчик сообщений в твоём чате"""
    
    # Получаем username бота
    bot_username = (await client.get_me()).username
    
    # Проверяем режим чата
    mode = db.get_chat_mode(config.GROUP_CHAT_ID) if config.GROUP_CHAT_ID else "normal"
    
    # В normal режиме отвечаем только на явный вызов
    if mode == "normal":
        if f"@{bot_username}" not in text and not text.startswith("/ask"):
            return
    # В demo режиме отвечаем на технические вопросы
    elif mode == "demo":
        if f"@{bot_username}" not in text and not text.startswith("/ask") and not is_technical(text):
            return
    
    # Проверка на бан
    if db.is_banned(user_id, config.GROUP_CHAT_ID):
        await event.reply("🚫 Ты в бане. Жди.")
        return
    
    # Проверка rate limit для чата
    requests_count = db.get_requests_last_minute(0, config.GROUP_CHAT_ID)
    if requests_count >= config.RATE_LIMIT_GROUP:
        await event.reply("📛 Чат перегружен. Подожди немного.")
        return
    
    # Добавляем запрос
    db.add_request(0, config.GROUP_CHAT_ID)
    
    # Очищаем текст от упоминания бота
    clean_text = text.replace(f"@{bot_username}", "").strip()
    if clean_text.startswith("/ask"):
        clean_text = clean_text[4:].strip()
    
    # Получаем историю чата (последние 10 для скорости)
    history = db.get_history(config.GROUP_CHAT_ID, limit=10)
    
    # Формируем сообщения для DeepSeek
    messages = []

# Добавляем историю
    for msg in history:
        messages.append({"role": "user", "content": msg})

# Добавляем текущее сообщение с указанием автора
    if user_id == config.OWNER_ID:
        messages.append({"role": "user", "content": f"[ХОЗЯИН] {clean_text}"})
    else:
        messages.append({"role": "user", "content": f"[ПОЛЬЗОВАТЕЛЬ] {clean_text}"})
    
    # Отправляем в DeepSeek
    response = llm.ask(messages)
    
    # Сохраняем в историю
    db.add_to_history(config.GROUP_CHAT_ID, user_id, clean_text)
    db.add_to_history(config.GROUP_CHAT_ID, 0, response)
    
    # Отправляем ответ
    if len(response) > 4096:
        await event.reply(response[:4096] + "\n\n... (обрезано)")
    else:
        await event.reply(response)