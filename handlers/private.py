import config
from database import db

async def handle_private(client, event, llm, user_id, text):
    """Обработчик личных сообщений"""
    
    # 1. Проверка на бан
    if db.is_banned(user_id, user_id):
        await event.reply("🚫 Ты в бане. Жди.")
        return
    
    # 2. Проверка rate limit (сколько запросов за минуту)
    requests_count = db.get_requests_last_minute(user_id, user_id)
    if requests_count >= config.RATE_LIMIT_PRIVATE:
        await event.reply("Не гони так братишечка. Повремени...")
        return
    
    # 3. Добавляем запрос в базу (для счётчика)
    db.add_request(user_id, user_id)
    
    # 4. Получаем историю диалога (чтобы Голем помнил контекст)
    history = db.get_history(user_id, limit=config.MAX_HISTORY)
    
    # 5. Формируем сообщения для DeepSeek
    messages = []
    
    # Добавляем историю
    for msg in history:
        messages.append({"role": "user", "content": msg})
    
    # Добавляем текущий вопрос
    messages.append({"role": "user", "content": text})
    
    # 6. Отправляем в DeepSeek
    response = llm.ask(messages)
    
    # 7. Сохраняем вопрос и ответ в историю
    db.add_to_history(user_id, user_id, text)
    db.add_to_history(user_id, user_id, response)
    
    # 8. Отправляем ответ (если длинный — режем)
    if len(response) > 4096:
        await event.reply(response[:4096] + "\n\n... (обрезано)")
    else:
        await event.reply(response)