import logging
import hashlib
import asyncio
import shutil
import zipfile
import sqlite3
import os
import time
import httpx
import random
from telegram import LinkPreviewOptions
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import config
from database import db
from core.llm_client import LLMClient
from utils.config_validator import validate_config
from utils.markdown_cleaner import clean_markdown
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from blogger import Blogger
from config import YUMONEY_ACCESS_TOKEN
from handlers.channel import handle_channel_post
from datetime import datetime
from project_analyzer import analyze_project_from_zip, analyze_project_from_repo
from core.fixer import handle_fix, handle_download, GoFixer
from telegram.ext import CallbackQueryHandler
 


# Сопоставление дня недели и типа поста
SCHEDULE = {
    0: 'hot_news',    # понедельник вечер
    1: 'black',       # вторник вечер
    2: 'code',        # среда вечер
    3: 'hot_news',    # четверг вечер
    4: 'black',       # пятница утро (отдельно)
    5: 'code',        # суббота вечер
    6: 'rofl'         # воскресенье вечер
}

# Рефлексия — отдельно по пятницам вечером

# Маркеры тупости в ответах Голема
dumb_markers = [
    'ты серьёзно',
    'тупой вопрос',
    'Ты о чём вообще?',
    'дебил',
    'очевидно же',
    'я не телепат',
    'откуда я знаю',
    'блядь',
    'гавно'
    'ёбаный',
    'ебать',
    'пиздец',
    'да ну нахер',
    'нахуя',
    'головой подумай',
    'включи мозг',
    'не позорься',
    'я ж тебе объяснил',
    'ты вообще читал',
    'не тупи',
    'хватит',
    'заебал',
    'достал',
    'еблан'
    'дебильные вопросы',
    'сам подумай',
    'найди в гугле',
    'Иди нахуй',
    'идиот',
    'кретин'
  
]

drafts = {}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

llm = LLMClient()
blogger = Blogger(llm)
import builtins
builtins.llm = llm

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = db.get_token_balance(user_id)
    
    # Обработка реферальной ссылки
    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            if referrer_id != user_id:
                if db.get_referrals_today(referrer_id) >= 5:
                    await update.message.reply_text("❌ Пригласивший сегодня уже привёл 5 человек.")
                    return
                db.add_referral(referrer_id, user_id)
                db.add_tokens(referrer_id, 10000)
                db.increase_memory_bonus(referrer_id)
        except:
            pass
    
    if balance == 0:
        db.add_tokens(user_id, 20000)
        await update.message.reply_text(
            "🎁 Ты получил 20 000 токенов в подарок!\n"
            "💰 Баланс: 20 000 токенов\n"
            f"🔗 Твоя реферальная ссылка: https://t.me/{context.bot.username}?start=ref_{user_id}"
        )
    else:
        await update.message.reply_text(
            f"💰 Твой баланс: {balance} токенов\n"
            f"🔗 Твоя реферальная ссылка: https://t.me/{context.bot.username}?start=ref_{user_id}"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """<b>📚 Команды Голема</b>

<b>🔧 Основное</b>
/start — приветствие и баланс
/help — эта справка
/balance — баланс токенов
/referrals — реферальная программа

<b>📊 Анализ кода</b>
/analyze — анализ проекта (ZIP или ссылка на GitHub)
/fix — автофикс Ruff (Python)
/download — скачать исправленные файлы

<b>🐙 GitHub</b>
/set_github_token — добавить GitHub токен
/github_push — залить проект в новый репозиторий

<b>🧠 Память</b>
/remember — сохранить заметку
/recall — показать заметки
/forget — удалить заметку

<b>💎 Токены</b>
/buy — купить токены
/balance — проверить баланс

Подробнее: @golem666channel"""
    await update.message.reply_text(text, parse_mode='HTML')

async def ban_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ /ban_id user_id [минуты]")
        return
    
    user_id = int(context.args[0])
    minutes = int(context.args[1]) if len(context.args) > 1 else 5256000  # 10 лет
    
    db.ban_user(user_id, user_id, minutes)
    await update.message.reply_text(f"✅ Пользователь {user_id} забанен на {minutes} минут")    

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bal = db.get_token_balance(user_id)
    await update.message.reply_text(f"💰 Твой баланс: {bal} токенов")    


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Получено сообщение от {update.effective_user.id}: {update.message.text if update.message else 'no text'}")

    # === САМАЯ ПЕРВАЯ ПРОВЕРКА ===
    if update.message and update.message.text:
        text = update.message.text.strip()
        # Если это команда анализа/пуша и это НЕ личка
        if update.effective_chat.id != update.effective_user.id:
            if any(x in text for x in ['/analyze', '/analize', '/github_push', '@/analyze', '@/analize', '@/github_push']):
                await update.message.reply_text(
                    "❌ `/analyze` и `/github_push` — только в личке. Не позорься при всех.\n\n"
                    "👉 **@Golem666bot**",
                    parse_mode='Markdown'
                )
                return
            
    # ========== НОВЫЙ БЛОК: ОБРАБОТКА ССЫЛОК НА GITHUB ==========
        if 'https://github.com/' in text:
            import re
            match = re.search(r'https://github\.com/[\w\-]+/[\w\-]+', text)
            if match:
                repo_url = match.group(0)
                user_id = update.effective_user.id
                await analyze_project_from_repo(update, context, repo_url, llm, user_id)
                return
        # ===========================================================

    # === ОПРЕДЕЛЯЕМ БАЗОВЫЕ ПЕРЕМЕННЫЕ СРАЗУ ===
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # === ЗАПРЕТ КОМАНД В ЧАТЕ (НЕ В ЛС) ===
    if chat_id != user_id and update.message and update.message.text:
        text = update.message.text.strip()
        if any(x in text for x in ['/analyze', '/analize', '/github_push', '@/analyze', '@/analize', '@/github_push']):
            await update.message.reply_text(
                "❌ `/analyze` и `/github_push` — только в личке. Не позорься при всех.\n\n"
                "👉 **@Golem666bot**",
                parse_mode='Markdown'
            )
            return

        # === ОБРАБОТКА НАЗВАНИЯ РЕПОЗИТОРИЯ ===
    state = db.get_github_push_state(user_id)
    if state == "waiting_for_repo_name":
        text = update.message.text.strip()
        parts = text.split()
        
        if len(parts) < 1:
            await update.message.reply_text("❌ Напиши название репозитория")
            return
        
        repo_name = parts[0]
        description = "Uploaded by Golem"
        is_private = False
        
        if len(parts) > 1:
            if parts[-1].lower() in ['public', 'private']:
                is_private = parts[-1].lower() == 'private'
                description = " ".join(parts[1:-1]) if len(parts) > 2 else "Uploaded by Golem"
            else:
                description = " ".join(parts[1:])
        
        # Очищаем состояние
        db.clear_github_push_state(user_id)
        
        # Получаем файлы юзера за последний час
        one_hour_ago = int(time.time()) - 3600
        files = db.get_user_files_since(user_id, one_hour_ago)
        
        if not files:
            await update.message.reply_text("❌ Нет файлов. Попробуй снова: /github_push")
            return
        
        await update.message.reply_text(f"⏳ Создаю репозиторий и заливаю {len(files)} файлов...")
        
        # === ЗДЕСЬ СОЗДАНИЕ РЕПОЗИТОРИЯ И ЗАЛИВКА ===
        await create_and_push_repo(update, context, user_id, repo_name, description, is_private, files)
        return
        

     # === ОБРАБОТКА КОММЕНТАРИЕВ В КАНАЛЕ ===
    # Список всех групп обсуждения
    if (config.DISCUSSION_GROUP_ID and chat_id == config.DISCUSSION_GROUP_ID) or \
       (config.YOUR_DISCUSSION_GROUP_ID and chat_id == config.YOUR_DISCUSSION_GROUP_ID):
        if not update.effective_user:
            return
        user_id = update.effective_user.id
        text = update.message.text.strip() if update.message.text else ""
        
        # Игнорируем свои сообщения
        #if update.message.from_user.id == context.bot.id:
            #return
        
        thread_id = update.message.message_thread_id
        comment_text = text
        
        # Сохраняем комментарий юзера
        db.add_comment(thread_id, user_id, comment_text, is_bot=False)
        
        # Получаем контекст (последние 5 комментариев)
        history = db.get_comments(thread_id, limit=5)
        
        # Загружаем исходный пост
        original_post = db.get_post(thread_id)
        
        # Формируем контекст с указанием автора
        context_lines = []
        if original_post:
            context_lines.append(f"Исходный пост:\n{original_post}")
        
        if history:
            context_lines.append("История комментариев:")
            for msg, is_bot in history:
                if is_bot:
                    context_lines.append(f"Голем: {msg}")
                else:
                    context_lines.append(f"Юзер: {msg}")
        
        context_text = "\n".join(context_lines)
        
        # Генерируем ответ
        prompt = f"""Вот вся история комментариев к посту:

{context_text}

Не отвечай на старые комментарии.  
Твоя задача — ответить ТОЛЬКО на последний комментарий: {comment_text}

Ответ должен быть по существу, без пересказа истории."""
        response = llm.ask([{"role": "user", "content": prompt}])

        
        # Отправляем ответ
        await update.message.reply_text(response)
        
        # Сохраняем ответ бота в БД
        db.add_comment(thread_id, 0, response, is_bot=True)
        
        return  # Выходим, чтобы не проверять токены и не продолжать дальше
    

       # === ОБРАБОТКА ФАЙЛОВ (ZIP, анализ, пуш) ===
    if update.message and update.message.document:
        file = update.message.document
        filename = file.file_name
        ext = os.path.splitext(filename)[1].lower()
        
        state = db.get_github_push_state(user_id)
        
        if state == "waiting_for_analyze":
            db.clear_github_push_state(user_id)
            
            # Если ZIP — анализируем проект
            if ext == '.zip':
                from project_analyzer import analyze_project_from_zip
                asyncio.create_task(analyze_project_from_zip(update, context, file, llm, user_id))
                await update.message.reply_text(
                    "🔍 **Анализ запущен**\n\n"
                    "Я анализирую проект в фоне. Результат пришлю сюда через несколько минут.",
                    parse_mode='Markdown'
                )
            else:
                # Анализируем один файл (синхронно, это быстро)
                file_obj = await file.get_file()
                content = await file_obj.download_as_bytearray()
                try:
                    code = content.decode('utf-8')
                    await update.message.reply_text("🔍 Анализирую файл...")
                    prompt = f"Проанализируй код. Найди баги, уязвимости, проблемы:\n\n```\n{code[:3000]}\n```"
                    response = llm.ask([{"role": "user", "content": prompt}])
                    
                    # ЧИСТИМ MARKDOWN
                    from utils.markdown_cleaner import clean_markdown
                    response = clean_markdown(response)
                    
                    try:
                        await update.message.reply_text(response, parse_mode='Markdown')
                    except:
                        await update.message.reply_text(response)
                        
                except Exception as e:
                    await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
            return
        
        # Обычная загрузка (или пуш)
        from file_handler import FileHandler
        fh = FileHandler(context, config.STORAGE_CHANNEL_ID, user_id, db, llm)
        await fh.process(file)
        return

    

    # Игнорируем сообщения без текста (callback, etc)
    if not update.message:
        return
    
    # Игнорируем свои сообщения
    if update.message.from_user.id == context.bot.id:
        return
    
    text = update.message.text.strip()
    
    if not text:
        return
    
    if db.is_banned(user_id, chat_id):
        await update.message.reply_text("🚫 Ты в бане.")
        return
    
    # Проверка подписки (для всех, кроме хозяина и группы обсуждения)
    #if user_id != config.OWNER_ID:
        # Пропускаем проверку для группы обсуждения
        #if not (config.DISCUSSION_GROUP_ID and chat_id == config.DISCUSSION_GROUP_ID):
            #if not await is_subscribed(user_id, context):
                #from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                #keyboard = [[InlineKeyboardButton("📢 Подписаться на канал", url=config.REQUIRED_CHANNEL_LINK)]]
                #reply_markup = InlineKeyboardMarkup(keyboard)
                #await update.message.reply_text(
                    #"🔒 Чтобы пользоваться ботом, подпишись на канал:",
                    #reply_markup=reply_markup
                #)
                #return
    
    db.add_request(user_id, chat_id)

    try:
        await update.message.reply_chat_action(action="typing")
    except:
        pass

        # Проверка баланса токенов
    balance = db.get_token_balance(user_id)
    if balance < 1000:  # минимальный порог для одного запроса
        await update.message.reply_text(
            "❌ Недостаточно токенов.\n"
           f"💰 Твой баланс: {balance} токенов\n"
            "📦 Купи пакет токенов: /buy"
        )
        return
    
        # Проверяем, группа ли это
    is_group = update.effective_chat.type in ['group', 'supergroup']
    print(f"DEBUG: is_group={is_group}, chat_id={chat_id}, GROUP_CHAT_ID={config.GROUP_CHAT_ID}")
    
    if is_group:
        bot = await context.bot.get_me()
        bot_username = bot.username.lower()
        is_mention = f"@{bot_username}" in text.lower()
        is_reply_to_bot = (
            update.message.reply_to_message and
            update.message.reply_to_message.from_user and
            update.message.reply_to_message.from_user.id == bot.id
        )
        print(f"DEBUG: is_mention={is_mention}, is_reply_to_bot={is_reply_to_bot}")

        if not (is_mention or is_reply_to_bot):
            if is_technical(text):
                last_reply = db.get_last_reply_time(chat_id)
                print(f"DEBUG: is_technical=True, last_reply={last_reply}")
                if time.time() - last_reply <= 40:
                    return
            else:
                return
        
        print(f"DEBUG: запрос проходит дальше")
    
    # Формируем историю
    if is_group:
        history = db.get_chat_context(chat_id, limit=config.MAX_HISTORY_GROUP)
        print(f"Группа, история: {len(history)} сообщений")
    else:
        history = db.get_history(chat_id, limit=config.MAX_HISTORY_PRIVATE)
        print(f"ЛС, история: {len(history)} сообщений")

    # Формируем messages
    messages = []
    
    # Проверяем, нужны ли файлы для ответа
    code_keywords = ['код', 'файл', 'проект', 'баг', 'ошибку', 'исправь', 'посмотри', 'анализ', 'рефакторинг', 'найди']
    need_files = any(keyword in text.lower() for keyword in code_keywords)
    
    if need_files:
        user_files = db.get_user_files(user_id)
        if user_files:
            files_text = []
            for filename, file_id in user_files:
                try:
                    file = await context.bot.get_file(file_id)
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in ['.db', '.session', '.sqlite3', '.bin', '.exe', '.jpg', '.png']:
                        continue
                    file_content = await file.download_as_bytearray()
                    text_content = file_content.decode('utf-8')
                    files_text.append(f"Файл {filename}:\n```\n{text_content}\n```")
                except Exception as e:
                    files_text.append(f"Файл {filename}: [ошибка: {e}]")
            
            if files_text:
                total_size = sum(len(t) for t in files_text)
                if total_size > 100000:
                    await update.message.reply_text("❌ Слишком много файлов. Уменьши количество или размер.")
                    return
                messages.append({"role": "system", "content": "Загруженные файлы:\n" + "\n\n".join(files_text)})
    
    if is_group:
        # Группа: история как контекст (system), без ответов на старые вопросы
        context_limit = 3
        context_messages = history[-context_limit:] if len(history) > context_limit else history
        messages = []
        for msg, is_bot in context_messages:
            messages.append({"role": "system", "content": msg})
        messages.append({"role": "user", "content": text})
    else:
        # ЛС: передаём историю как контекст (system), а не как вопросы
        context_limit = 6
        context_messages = history[-context_limit:] if len(history) > context_limit else history
        messages = []  # <--- ЭТО ДОБАВИТЬ
        for msg, is_bot in context_messages:
            role = "assistant" if is_bot else "system"
            messages.append({"role": role, "content": msg})
    

    # Добавляем текущий вопрос
    messages.append({"role": "user", "content": text})

        # Добавляем заметки пользователя (только в ЛС)
    if chat_id == user_id:
        memories = db.get_user_memory(user_id, limit=5)
        if memories:
            memory_text = "Важные заметки пользователя:\n" + "\n".join([f"- {fact}" for _, fact in memories])
            messages.insert(0, {"role": "system", "content": memory_text})

    # Кэш
    import hashlib
    
    cache_key = hashlib.md5(text.encode()).hexdigest()
    cached = db.get_cached_response(cache_key) 
    if cached:
        response = cached
        # Отправляем кэш без стриминга
        reply_markup = None
        if config.GROUP_CHAT_ID and chat_id == config.GROUP_CHAT_ID:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton("Вызвать Голема", switch_inline_query_current_chat="")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(
                        response[i:i+4000],
                        parse_mode='Markdown'
                    )
            else:
                await update.message.reply_text(
                    response,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Ошибка отправки кэша: {e}")
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
            else:
                await update.message.reply_text(response, reply_markup=reply_markup)


                # Сохраняем тупые вопросы (для кэша)
        if chat_id == user_id: 
            if any(marker in response.lower() for marker in dumb_markers):
                db.save_dumb_question(user_id, text, response)
        db.add_to_history(chat_id, user_id, text, is_bot=False)
        db.add_to_history(chat_id, 0, response, is_bot=True)
        if is_group:
            db.set_last_reply_time(chat_id)
        return
    
            # === СТРИМИНГ ДЛЯ ВСЕХ ОСТАЛЬНЫХ ===
    
    # Стриминг только в ЛС (не в группах)
    if not is_group:
        # Отправляем черновик
        try:
            await context.bot._post(
                "sendMessageDraft",
                {
                    "chat_id": chat_id,
                    "message_id": update.message.message_id,
                    "draft_id": update.message.message_id,
                    "text": "⚙️ Генерирую..."
                }
            )
        except Exception as e:
            logger.error(f"Ошибка отправки черновика: {e}")
            await update.message.reply_text("❌ Ошибка стриминга")
            return
        
        full_response = ""
        
        try:
            stream_gen, _ = await llm.astream(messages)  # _ игнорируем total_tokens
            async for chunk in stream_gen:
                full_response += chunk
                try:
                    await context.bot._post(
                        "sendMessageDraft",
                        {
                            "chat_id": chat_id,
                            "message_id": update.message.message_id,
                            "draft_id": update.message.message_id,
                            "text": full_response[:4000]
                        }
                    )
                    await asyncio.sleep(0.3)
                except Exception as e:
                    if "Flood control" in str(e):
                        await asyncio.sleep(10)
                        try:
                            await context.bot._post(
                                "sendMessageDraft",
                                {
                                    "chat_id": chat_id,
                                    "message_id": update.message.message_id,
                                    "draft_id": update.message.message_id,
                                    "text": full_response[:4000]
                                }
                            )
                        except:
                            pass
                    else:
                        logger.error(f"Ошибка обновления черновика: {e}")
                        continue
            
            # Отправляем финальное сообщение с разбивкой
            try:
                if len(full_response) > 4000:
                    for i in range(0, len(full_response), 4000):
                        await update.message.reply_text(full_response[i:i+4000], parse_mode='Markdown')
                else:
                    await update.message.reply_text(full_response, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Ошибка финальной отправки: {e}")
                if len(full_response) > 4000:
                    for i in range(0, len(full_response), 4000):
                        await update.message.reply_text(full_response[i:i+4000])
                else:
                    await update.message.reply_text(full_response)
            
            response = full_response

            

            db.set_cached_response(cache_key, response)
            estimated_tokens = max(len(full_response) // 2, 300)
            db.deduct_tokens(user_id, estimated_tokens)
            print(f"DEBUG: списываем {estimated_tokens} токенов (оценка)")
            
        except Exception as e:
            logger.error(f"Стриминг ошибка: {e}")
            await update.message.reply_text("❌ Ошибка генерации")
            return
    else:
        # Для группы — обычный ответ (кэш или ask)
        import hashlib
        
        cache_key = hashlib.md5(text.encode()).hexdigest()
        cached = db.get_cached_response(cache_key)
        if cached:
            response = cached

        
        else:
            print(f"DEBUG: отправляем запрос в DeepSeek, messages count={len(messages)}")
            response, total_tokens = llm.ask_with_tokens(messages)

            if chat_id == user_id and user_id != config.OWNER_ID:
                if any(marker in response.lower() for marker in dumb_markers):
                    db.save_dumb_question(user_id, text, response)

            db.set_cached_response(cache_key, response)
            db.deduct_tokens(user_id, total_tokens)
            print(f"DEBUG: получили ответ, токенов={total_tokens}")
        
        # Кнопка только для твоего чата
        reply_markup = None
        if config.GROUP_CHAT_ID and chat_id == config.GROUP_CHAT_ID:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton("Вызвать Голема", switch_inline_query_current_chat="")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(
                        response[i:i+4000],
                        parse_mode='Markdown'
                    )
            else:
                await update.message.reply_text(
                    response,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
            else:
                await update.message.reply_text(response, reply_markup=reply_markup)

    
    # Сохраняем тупые вопросы
    if chat_id == user_id: 
        if any(marker in response.lower() for marker in dumb_markers):
            db.save_dumb_question(user_id, text, response)

    # Сохраняем в историю
    db.add_to_history(chat_id, user_id, text, is_bot=False)
    db.add_to_history(chat_id, 0, response, is_bot=True)
    
    # Сохраняем время последнего ответа (для группы)
    if is_group:
        db.set_last_reply_time(chat_id)
        
async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("❌ Использование: /mode demo|normal")
        return
    mode = context.args[0].lower()
    if mode not in ["demo", "normal"]:
        await update.message.reply_text("❌ Режим должен быть demo или normal")
        return
    db.set_chat_mode(config.GROUP_CHAT_ID, mode)
    await update.message.reply_text(f"✅ Режим чата: {mode}")

async def say_in_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("❌ Использование: /say текст")
        return
    text = " ".join(context.args)
    if config.GROUP_CHAT_ID:
        await context.bot.send_message(config.GROUP_CHAT_ID, text)
    else:
        await update.message.reply_text("❌ ID чата не задан")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("❌ Использование: /ban @username [минуты]")
        return
    username = context.args[0].replace("@", "")
    minutes = int(context.args[1]) if len(context.args) > 1 else 60
    
    try:
        # Ищем пользователя по username
        user = await context.bot.get_chat(username)
        user_id = user.id
        db.ban_user(user_id, config.GROUP_CHAT_ID, minutes)
        await update.message.reply_text(f"✅ {username} забанен на {minutes} минут")
    except Exception as e:
        await update.message.reply_text(f"❌ Не найден пользователь: {e}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("❌ Использование: /unban @username")
        return
    username = context.args[0].replace("@", "")
    await update.message.reply_text(f"✅ {username} разбанен")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    mode = db.get_chat_mode(config.GROUP_CHAT_ID) if config.GROUP_CHAT_ID else "не задан"
    text = f"""📊 **Статус Голема**

Режим чата: {mode}
Модель: deepseek-coder
"""
    await update.message.reply_text(text)

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"ID этого чата: `{chat_id}`", parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    conn = sqlite3.connect("golem.db")
    c = conn.cursor()
    
    c.execute("SELECT COUNT(DISTINCT user_id) FROM requests")
    users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM requests")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM analyses")
    analyses = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM github_pushes")
    pushes = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM user_memory")
    memories = c.fetchone()[0]
    
    c.execute("SELECT COUNT(DISTINCT user_id) FROM user_memory")
    memory_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM fixes")
    fixes = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM referrals")
    referrals = c.fetchone()[0]

    conn.close()
    
    text = f"""📊 **Статистика Голема**

👥 Юзеров: {users}
💬 Запросов: {total}
🔍 Анализов: {analyses}
🚀 Пушей на GitHub: {pushes}
🔧 Фиксов: {fixes}
📝 Заметок: {memories} (у {memory_users} юзеров)
👥 Рефералов: {referrals}
"""
    await update.message.reply_text(text, parse_mode='Markdown')

async def is_subscribed(user_id, context):
    try:
        member = await context.bot.get_chat_member(config.REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False


async def changelog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    try:
        with open("CHANGELOG.md", "r", encoding="utf-8") as f:
            content = f.read()
        await update.message.reply_text(f"📝 CHANGELOG:\n{content[:4000]}")
    except:
        await update.message.reply_text("❌ Файл CHANGELOG.md не найден.")      

async def clear_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    conn = sqlite3.connect("golem.db")
    c = conn.cursor()
    c.execute("DELETE FROM user_files WHERE user_id = ?", (update.effective_user.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Все файлы удалены.")        

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    conn = sqlite3.connect("golem.db")
    c = conn.cursor()
    c.execute("DELETE FROM chat_history WHERE user_id = ?", (update.effective_user.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ История очищена.")     

async def snapshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    content = blogger.get_main_content()
    db.save_main_snapshot(content)
    await update.message.reply_text("📸 Состояние main.py сохранено.")

async def post_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    post_text = blogger.generate_update_post()
    
    if post_text is None:
        await update.message.reply_text("❌ Нет снапшота. Сначала /snapshot")
        return
    
    if post_text == "✅ Изменений нет":
        await update.message.reply_text(post_text)
        return
    
    if post_text.startswith("❌"):
        await update.message.reply_text(post_text)
        return
    
    user_id = update.effective_user.id
    drafts[user_id] = {
        "type": "update",
        "topic": "обновления",
        "text": post_text
    }
    
    await update.message.reply_text(
        f"**📝 Черновик:**\n\n{post_text}\n\n"
        "✅ /publish\n"
        "🔄 /edit",
        parse_mode='Markdown'
    )

async def post_black(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    await update.message.reply_text("🔍 Ищу свежие темы для #ГолемЧёрное...")
    
    news_list = blogger.get_black_news()
    if not news_list:
        await update.message.reply_text("❌ Ничего не найдено за последние 24 часа.")
        return
    
    best_news = news_list[0]
    post_text = blogger.generate_black_post(best_news)
    user_id = update.effective_user.id
    drafts[user_id] = {
        "type": "black",
        "topic": best_news['title'],
        "text": post_text
    }
    
    try:
        await update.message.reply_text(
            f"**📝 Черновик #ГолемЧёрное:**\n\n{post_text}\n\n"
            f"**✅ Если всё ок — /publish**\n"
            f"**🔄 Если нужно исправить — /edit**",
            parse_mode='Markdown'
        )
    except:
        await update.message.reply_text(
            f"📝 Черновик #ГолемЧёрное:\n\n{post_text}\n\n"
            f"✅ Если всё ок — /publish\n"
            f"🔄 Если нужно исправить — /edit"
        )

async def post_rofl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    post_text = blogger.generate_rofl_post()
    user_id = update.effective_user.id
    drafts[user_id] = {
        "type": "rofl",
        "topic": "тупые вопросы",
        "text": post_text
    }
    
    await update.message.reply_text(
        f"**📝 Черновик #ГолемРофл:**\n\n{post_text}\n\n"
        f"✅ /publish — опубликовать\n"
        f"🔄 /edit — исправить",
        parse_mode='Markdown'
    )
    

async def edit_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != config.OWNER_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Напиши что исправить")
        return
    
    draft = drafts.get(user_id)
    if not draft:
        await update.message.reply_text("❌ Нет черновика")
        return
    
    fix_text = " ".join(context.args)
    original_post = draft["text"]
    post_type = draft["type"]
    
    prompt = f"""Отредактируй пост по правкам.

ТЕКУЩИЙ ПОСТ:
{original_post}

ПРАВКИ: {fix_text}

Сохрани структуру и смысл. Измени только то что указано в правках. Верни полный пост."""
    
    new_post = llm.ask([{"role": "user", "content": prompt}])
    drafts[user_id]["text"] = new_post
    
    await update.message.reply_text(
        f"📝 **Исправлено:**\n\n{new_post}\n\n✅ /publish\n🔄 /edit",
        parse_mode='Markdown'
    )



async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != config.OWNER_ID:
        return
    
    draft = drafts.get(user_id)
    if not draft:
        await update.message.reply_text("❌ Нет черновика.")
        return
    
    post_text = draft["text"]
    url = draft.get("topic") if draft["type"] == "news" else None
    
    if config.TEST_CHANNEL_ID:
        try:
            sent = await context.bot.send_message(
                config.TEST_CHANNEL_ID,
                post_text,
                parse_mode='Markdown',
                link_preview_options=LinkPreviewOptions(url=url, show_above_text=True) if url else None
            )
            if draft["type"] != "news":
                db.save_post(sent.message_id, post_text)

            # Комментарий в группу обсуждения
            if config.DISCUSSION_GROUP_ID:
                await context.bot.send_message(config.DISCUSSION_GROUP_ID, f"Новый пост: {draft['type']}")    
            await update.message.reply_text("✅ Пост опубликован.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    else:
        await update.message.reply_text("❌ Тестовый канал не задан.")

async def post_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    topic = " ".join(context.args)
    if not topic:
        await update.message.reply_text("❌ Напиши тему поста.")
        return
    
    post_text = blogger.generate_custom_post(topic)
    user_id = update.effective_user.id
    drafts[user_id] = {
        "type": "custom",
        "topic": topic,
        "text": post_text
    }
    
    await update.message.reply_text(
        f"<b>📝 Черновик поста на тему «{topic}»:</b>\n\n{post_text}\n\n"
        "<b>✅ Если всё ок — /publish</b>\n"
        "<b>🔄 Если нужно исправить — /edit добавь про железо</b>",
        parse_mode='HTML'
    )

async def post_hot_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    await update.message.reply_text("🔥 Ищу самую громкую новость...")
    
    hot_news = blogger.get_hot_news()
    if not hot_news:
        await update.message.reply_text("❌ Ничего громкого не найдено за последние 24 часа.")
        return
    
    post_text = blogger.generate_news_post(
        url=hot_news['link'],
        title=hot_news['title'],
        content=hot_news['summary']
    )
    
    user_id = update.effective_user.id
    drafts[user_id] = {
        "type": "news",
        "topic": hot_news['link'],
        "text": post_text
    }
    
    await update.message.reply_text(
        f"📝 **Черновик громкой новости:**\n\n{post_text}\n\n"
        f"📰 Источник: {hot_news['source']}\n\n"
        f"✅ /publish — опубликовать\n"
        f"🔄 /edit — исправить",
        parse_mode='Markdown'
    )

async def post_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    post_text = blogger.generate_code_post()
    user_id = update.effective_user.id
    drafts[user_id] = {
        "type": "code",
        "topic": "полезный код",
        "text": post_text
    }
    
    await update.message.reply_text(
        f"<b>📝 Черновик поста с полезным кодом:</b>\n\n{post_text}\n\n"
        "<b>✅ Если всё ок — /publish</b>\n"
        "<b>🔄 Если нужно исправить — /edit</b>",
        parse_mode='Markdown'
    )

async def post_reflect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    await update.message.reply_text("🤔 Думаю...")
    post_text = blogger.generate_reflect_post()
    
    user_id = update.effective_user.id
    drafts[user_id] = {
        "type": "reflect",
        "topic": "рефлексия",
        "text": post_text
    }
    
    await update.message.reply_text(
        f"**📝 Черновик #ГолемРефлексия:**\n\n{post_text}\n\n"
        f"✅ /publish — опубликовать\n"
        f"🔄 /edit — исправить",
        parse_mode='Markdown'
    )    

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /broadcast текст сообщения")
        return
    
    text = " ".join(context.args)
    users = db.get_all_users()
    
    success = 0
    fail = 0
    
    for user_id in users:
        try:
            await context.bot.send_message(user_id, text)
            success += 1
            await asyncio.sleep(0.05)  # чтобы не спамить
        except Exception as e:
            fail += 1
            logger.error(f"Не удалось отправить {user_id}: {e}")
    
    await update.message.reply_text(f"✅ Рассылка завершена.\n📨 Отправлено: {success}\n❌ Не доставлено: {fail}")     

async def admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    text = """
<b>🔧 Команды для хозяина:</b>

<b>📢 Рассылка</b>
/broadcast текст — отправить сообщение всем юзерам

<b>📝 Посты в канал</b>
/post_update — черновик поста об обновлениях
/post_about тема — черновик на любую тему
/post_code - код-сниппет гитхаб трендинг
/post_black - големблэк
/post_rofl — подборка тупых вопросов
/post_hot_news
/post_reflect
/edit текст — исправить черновик
/publish — опубликовать черновик в канал

<b>👥 Управление чатом</b>
/mode demo|normal — режим чата
/say текст — написать в чат
/ban @username [минуты] — заблокировать
/unban @username — разблокировать

<b>📊 Статистика</b>
/stats — юзеры и запросы
/stats_remember
/limits — лимиты
/changelog — показать CHANGELOG.md
/clear_files — удалить все файлы юзера
/clear_history — очистить историю

<b>🆔 Утилиты</b>
/get_chat_id — ID текущего чата
/status — статус бота
/help — публичная справка
/add_tokens user_id токены
"""
    await update.message.reply_text(text, parse_mode='HTML')             



async def referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("golem.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"👥 Ты привёл {count} друзей.")    


# ========== ЮMONEY ОПЛАТА ==========

import uuid
import time
import asyncio
import aiohttp
from urllib.parse import urlencode

# Хранилище ожидаемых платежей
pending_payments = {}  # {payment_id: {"user_id": int, "tokens": int, "amount_rub": int, "created_at": float}}
pending_approvals = {}  # {user_id: tokens}

async def create_yoomoney_payment(amount_rub: int, tokens: int, user_id: int, bot_username: str) -> tuple:
    """Создаёт платёжную ссылку с правильным label"""
    payment_id = f"golem_{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    params = {
        "receiver": config.YUMONEY_WALLET,
        "quickpay-form": "shop",
        "targets": f"Покупка {tokens:,} токенов для Голема",
        "paymentType": "AC",           # оплата картой
        "sum": amount_rub,
        "label": payment_id,           # Главный идентификатор
        "comment": payment_id,         # Дублируем для надёжности
        "successURL": f"https://t.me/{bot_username}"
    }
    
    url = f"https://yoomoney.ru/quickpay/confirm.xml?{urlencode(params)}"
    
    pending_payments[payment_id] = {
        "user_id": user_id,
        "tokens": tokens,
        "amount_rub": amount_rub,
        "created_at": time.time(),
        "status": "pending"
    }
    
    return url, payment_id


async def check_payment(payment_id: str, expected_amount: int) -> bool:
    """Проверяет наличие успешного платежа по label/comment"""
    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "records": 20,
                "type": "incoming"
            }
            
            async with session.post(
                "https://api.yoomoney.ru/api/operation-history",
                data=params,
                headers={"Authorization": f"Bearer {config.YUMONEY_ACCESS_TOKEN}"},
                timeout=15
            ) as resp:
                if resp.status != 200:
                    return False
                
                data = await resp.json()
                
                for op in data.get("operations", []):
                    op_label = op.get("label")
                    op_comment = op.get("comment")
                    op_amount = float(op.get("amount", 0))
                    
                    # Проверяем и по label, и по comment
                    if (op_label == payment_id or op_comment == payment_id) and op.get("status") == "success":
                        if abs(op_amount - expected_amount) < 1:   # допускаем разницу в 1 рубль
                            return True
    except Exception as e:
        logger.error(f"Ошибка проверки платежа {payment_id}: {e}")
    
    return False


async def auto_check_payment(payment_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Автоматическая проверка платежа (5 минут)"""
    data = pending_payments.get(payment_id)
    if not data:
        return
    
    user_id = data["user_id"]
    tokens = data["tokens"]
    amount_rub = data["amount_rub"]
    chat_id = None  # будем брать из сообщения, если нужно
    
    for _ in range(30):  # 30 попыток × 10 сек = 5 минут
        await asyncio.sleep(10)
        
        if await check_payment(payment_id, amount_rub):
            db.add_tokens(user_id, tokens)
            
            await context.bot.send_message(
                user_id,
                f"✅ **Оплата успешно получена!**\n\n"
                f"Начислено: **{tokens:,} токенов**\n"
                f"💰 Текущий баланс: **{db.get_token_balance(user_id):,} токенов**",
                parse_mode='Markdown'
            )
            
            if payment_id in pending_payments:
                del pending_payments[payment_id]
            return
    
    # Время вышло
    await context.bot.send_message(
        user_id,
        f"⏰ Время автоматической проверки истекло (5 минут).\n\n"
        f"Если ты уже оплатил — напиши:\n"
        f"`/check {payment_id[:12]}`",
        parse_mode='Markdown'
    )


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    packages = {
        "1": {"tokens": 50000,  "price": 50},
        "2": {"tokens": 200000, "price": 150},
        "3": {"tokens": 500000, "price": 350},
        "4": {"tokens": 1500000,"price": 900},
        "5": {"tokens": 5000000,"price": 2500}
    }
    
    if context.args and context.args[0].isdigit():
        choice = context.args[0]
        if choice not in packages:
            await update.message.reply_text("❌ Неверный номер пакета. Используй /buy 1–5")
            return
        
        pkg = packages[choice]
        tokens = pkg["tokens"]
        price = pkg["price"]

        pending_approvals[user_id] = tokens
        
        bot = await context.bot.get_me()
        
        payment_url, payment_id = await create_yoomoney_payment(
            amount_rub=price,
            tokens=tokens,
            user_id=user_id,
            bot_username=bot.username
        )
        
        await update.message.reply_text(
            f"💳 <b>Покупка токенов</b>\n\n"
            f"Пакет: <b>{tokens:,} токенов</b>\n"
            f"Сумма: <b>{price} ₽</b>\n\n"
            f"🔗 <b>Ссылка для оплаты:</b>\n{payment_url}\n\n"
            f"После оплаты:\n"
            f"1️⃣ Оплати по ссылке\n"
            f"2️⃣ Сделай скриншот чека\n"
            f"3️⃣ Отправь скриншот сюда, в этот чат\n\n"
            f"Токены будут зачислены после проверки.",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        
        # Запускаем автопроверку
        #asyncio.create_task(auto_check_payment(payment_id, context))
        
    else:
        # Показываем меню пакетов
        text = "💎 **Доступные пакеты токенов:**\n\n"
        for k, p in packages.items():
            text += f"{k}. {p['tokens']:,} токенов — **{p['price']} ₽**\n"
        
        text += f"\n💰 Твой баланс: **{db.get_token_balance(user_id):,} токенов**\n\n"
        text += "Чтобы купить — напиши `/buy номер`\nПример: `/buy 3`"
        
        await update.message.reply_text(text, parse_mode='Markdown')


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручная проверка платежа"""
    if not context.args:
        await update.message.reply_text("❌ Использование: `/check XXXXXXXX`")
        return
    
    short_id = context.args[0]
    
    for pid, data in list(pending_payments.items()):
        if pid.startswith(short_id):
            if await check_payment(pid, data["amount_rub"]):
                db.add_tokens(data["user_id"], data["tokens"])
                await update.message.reply_text(
                    f"✅ Платёж найден и подтверждён!\nНачислено **{data['tokens']:,} токенов**",
                    parse_mode='Markdown'
                )
                del pending_payments[pid]
                return
            else:
                await update.message.reply_text("❌ Платёж пока не найден. Подожди ещё или проверь сумму и комментарий.")
                return
    
    await update.message.reply_text("❌ Платёж с таким ID не найден.")

async def github_push(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    token = db.get_github_token(user_id)
    if not token:
        await update.message.reply_text(
            "❌ GitHub токен не найден!\n\n"
            "Используй команду /set_github_token чтобы добавить токен.\n\n"
            "Как получить токен:\n"
            "1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)\n"
            "2. Generate new token\n"
            "3. Поставь галочку repo\n"
            "4. Скопируй токен и отправь: /set_github_token ТОКЕН"
        )
        return
    
    db.set_github_push_state(user_id, "waiting_for_zip")
    await update.message.reply_text(
        "📦 Отправь ZIP-архив с проектом.\n\n"
    )
    

async def create_and_push_repo(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, repo_name, description, is_private, files):
    chat_id = update.effective_chat.id
    
    await update.message.reply_text(
        "⏳ Начинаю обработку. Процесс может занять 2-3 минуты.\n"
        "Как закончу — пришлю ссылку на GitHub."
    )
    
    try:
        asyncio.create_task(
            _do_push_repo(
                context=context,
                user_id=user_id,
                repo_name=repo_name,
                description=description,
                is_private=is_private,
                files=files,
                chat_id=chat_id
            )
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при запуске пуша: {str(e)[:200]}")

async def _do_push_repo(context, user_id, repo_name, description, is_private, files, chat_id):
    import aiohttp
    import base64
    import tempfile
    import shutil
    import os
    import zipfile
    import io
    import asyncio
    
    token = db.get_github_token(user_id)
    if not token:
        await context.bot.send_message(chat_id, "❌ GitHub токен не найден")
        return
    
    temp_dir = tempfile.mkdtemp(prefix=f"golem_{user_id}_")
    status_msg = await context.bot.send_message(chat_id, "⏳ Начинаю обработку...")
    
    try:
        await status_msg.edit_text("📦 Распаковываю ZIP...")
        
        # Находим ZIP файл
        zip_file_id = None
        for filename, file_id in files:
            if filename.endswith('.zip'):
                zip_file_id = file_id
                break
        
        if not zip_file_id:
            await status_msg.edit_text("❌ ZIP не найден")
            return
        
        file = await context.bot.get_file(zip_file_id)
        zip_bytes = await file.download_as_bytearray()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(temp_dir)
        
                # Создаём .gitignore если нет
        gitignore_path = os.path.join(temp_dir, ".gitignore")
        if not os.path.exists(gitignore_path):
            gitignore_content = """# Python
__pycache__/
*.py[cod]
*.so
.Python
env/
venv/
ENV/
.venv
*.db
*.sqlite3
*.sqlite
*.session

# IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store

# Environment
.env
.env.local
.env.*.local

# Distribution
dist/
build/
*.egg-info/
*.egg

# Testing
.pytest_cache/
.coverage
htmlcov/

# Node
node_modules/
npm-debug.log
yarn-error.log

# Logs
*.log
*.pid
"""

            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write(gitignore_content)
            print("✅ Создан .gitignore")

        # Создание репозитория
        await status_msg.edit_text("🔧 Создаю репозиторий...")
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            repo_name_fixed = repo_name.lower().replace(" ", "-")
            
            repo_data = {
                "name": repo_name_fixed,
                "description": description[:100],
                "private": is_private,
                "auto_init": True
            }
            
            async with session.post("https://api.github.com/user/repos", headers=headers, json=repo_data) as resp:
                if resp.status != 201:
                    error = await resp.json()
                    await status_msg.edit_text(f"❌ {error.get('message', 'Ошибка')}")
                    return
                repo = await resp.json()
                repo_url = repo["html_url"]
                owner = repo["owner"]["login"]
            
            # Собираем файлы
            await status_msg.edit_text("📤 Подготавливаю файлы...")

                        # Игнорируемые файлы и папки
            ignore_patterns = [
                '__pycache__', '.git', '.env', '.venv', 'venv', 'ENV',
                '*.pyc', '*.pyo', '*.so', '*.dll', '*.exe',
                '*.log', '*.pid', '*.lock', '*.tmp', '*.bak', '*.swp', '*.swo',
                '.DS_Store', 'Thumbs.db', 'desktop.ini',
                '*.db', '*db*', '*.sqlite', '*.sqlite3', '*.db3', '*.ldb',
                '.vscode', '.idea', '.eclipse', '.settings',
                'dist', 'build', 'target', 'out', 'bin', 'obj',
                '*.egg-info', '*.egg', '.eggs', '*.whl',
                'node_modules', 'bower_components',
                '.pytest_cache', '.tox', '.coverage', 'htmlcov', '.mypy_cache',
                '*.jpg', '*.jpeg', '*.png', '*.gif', '*.ico',
                '*.mp4', '*.mp3', '*.wav',
                '*.zip', '*.tar', '*.gz', '*.rar', '*.7z',
                '*.bak', '*.old', '*.orig', '*.rej', '*.temp', '*.cache','*.session',
            ]
            
            import fnmatch
            
            all_files = []
            for root, dirs, filenames in os.walk(temp_dir):
                for filename in filenames:
                    # Пропускаем игнорируемые файлы
                    skip = False
                    for pattern in ignore_patterns:
                        if fnmatch.fnmatch(filename, pattern):
                            skip = True
                            break
                    if skip:
                        continue
                    
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, temp_dir).replace("\\", "/")
                    all_files.append((file_path, relative_path))
            
            total = len(all_files)
            if total == 0:
                await status_msg.edit_text("❌ Нет файлов для загрузки")
                return
            
            # Получаем SHA начальной ветки (от auto_init)
            async with session.get(f"https://api.github.com/repos/{owner}/{repo_name_fixed}/git/refs/heads/main", headers=headers) as resp:
                if resp.status != 200:
                    await status_msg.edit_text("❌ Не могу получить ветку")
                    return
                ref_data = await resp.json()
                base_sha = ref_data["object"]["sha"]
            
            blobs = []
            for i, (file_path, relative_path) in enumerate(all_files):
                if i % max(1, total // 10) == 0:
                    percent = int(i / total * 100)
                    await status_msg.edit_text(f"📤 Загружаю файлы... {percent}% ({i}/{total})")
                
                with open(file_path, 'rb') as f:
                    content = f.read()
                content_b64 = base64.b64encode(content).decode('utf-8')
                
                blob_data = {"content": content_b64, "encoding": "base64"}
                async with session.post(f"https://api.github.com/repos/{owner}/{repo_name_fixed}/git/blobs", headers=headers, json=blob_data) as resp:
                    if resp.status != 201:
                        await status_msg.edit_text(f"❌ Ошибка: {relative_path}")
                        return
                    blob = await resp.json()
                    blobs.append({
                        "path": relative_path,
                        "sha": blob["sha"],
                        "mode": "100644",
                        "type": "blob"
                    })
            
            # Создаём дерево
            await status_msg.edit_text(f"🌲 Создаю дерево ({total} файлов)...")
            tree_data = {"base_tree": base_sha, "tree": blobs}
            async with session.post(f"https://api.github.com/repos/{owner}/{repo_name_fixed}/git/trees", headers=headers, json=tree_data) as resp:
                if resp.status != 201:
                    await status_msg.edit_text("❌ Ошибка создания дерева")
                    return
                tree = await resp.json()
            
            # Создаём коммит
            await status_msg.edit_text("💾 Создаю коммит...")
            commit_data = {
                "message": f"Add {total} files",
                "tree": tree["sha"],
                "parents": [base_sha]
            }
            async with session.post(f"https://api.github.com/repos/{owner}/{repo_name_fixed}/git/commits", headers=headers, json=commit_data) as resp:
                if resp.status != 201:
                    await status_msg.edit_text("❌ Ошибка создания коммита")
                    return
                commit = await resp.json()
            
            # Обновляем ветку
            await status_msg.edit_text("🚀 Обновляю ветку...")
            ref_data = {"sha": commit["sha"], "force": False}
            async with session.patch(f"https://api.github.com/repos/{owner}/{repo_name_fixed}/git/refs/heads/main", headers=headers, json=ref_data) as resp:
                if resp.status != 200:
                    await status_msg.edit_text("❌ Ошибка обновления ветки")
                    return
            
            db.save_github_push(user_id, repo_name, "unknown")
            
            await status_msg.edit_text(
                f"✅ **Залито!**\n\n"
                f"📁 {owner}/{repo_name_fixed}\n"
                f"🔗 {repo_url}\n"
                f"📦 Файлов: {total}",
                parse_mode='Markdown'
            )

            # Отдельное сообщение с предложением README
            await context.bot.send_message(
                chat_id,
                "📝 А хочешь я тебе README сделаю? Напиши /readme"
            )

            # Сохраняем путь к временной папке для генерации README
            db.save_temp_project_path(user_id, temp_dir, repo_name_fixed, owner, repo_url)
            
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Ошибка при пуше: {str(e)[:300]}")
    finally:
        # НЕ удаляем папку! Она нужна для README
        # shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"📁 Временная папка сохранена: {temp_dir}")
            
        
async def set_github_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) < 1:
        await update.message.reply_text("❌ Использование: /set_github_token ТОКЕН")
        return
    
    token = context.args[0]
    db.save_github_token(user_id, token)
    await update.message.reply_text("✅ GitHub токен сохранён")

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Если есть аргумент и это ссылка на GitHub
    if context.args and context.args[0].startswith('https://github.com/'):
        repo_url = context.args[0]
        from project_analyzer import analyze_project_from_repo
        asyncio.create_task(analyze_project_from_repo(update, context, repo_url, llm, user_id))
        await update.message.reply_text(
            "🔍 **Анализ запущен**\n\n"
            "Я анализирую репозиторий в фоне. Результат пришлю сюда через несколько минут.",
            parse_mode='Markdown'
        )
        return
    
    # Если нет аргумента — ожидаем ZIP или файл
    db.set_github_push_state(user_id, "waiting_for_analyze")
    await update.message.reply_text(
        "📊 **Анализ проекта**\n\n"
        "Отправь ZIP-архив с проектом, ссылку на GitHub-репозиторий или просто файл с кодом.\n\n"
        "**Пример ссылки:**\n"
        "`https://github.com/user/repo`\n\n"
        "Анализ запустится в фоне, результат пришлю сюда.",
        parse_mode='Markdown'
    )
     

async def snapshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    content = blogger.get_main_content()
    db.save_main_snapshot(content)
    await update.message.reply_text("📸 Состояние main.py сохранено.")

MAX_FREE_MEMORY = 5  # лимит бесплатных заметок

async def remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Использование: /remember текст заметки")
        return
    
    fact = " ".join(context.args)
    count = db.count_user_memory(user_id)
    limit = db.get_memory_limit(user_id)
    
    if count >= limit:
        await update.message.reply_text(f"❌ У тебя уже {limit} заметок. Пригласи друзей для увеличения лимита (1 друг = +1 заметка).")
        return
    
    db.save_memory(user_id, fact)
    await update.message.reply_text(f"✅ Заметка сохранена. Всего: {count+1}/{limit}")

async def recall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    memories = db.get_user_memory(user_id)
    limit = db.get_memory_limit(user_id)
    if not memories:
        await update.message.reply_text("📭 Нет сохранённых заметок. Добавь через /remember")
        return
    
    text = "**📝 Твои заметки:**\n\n"
    for mid, fact in memories:
        text += f"`{mid}`. {fact}\n"
    
    text += f"\nВсего: {len(memories)}/{limit}. Пригласи друзей для увеличения лимита. Удалить: `/forget ID`"
    await update.message.reply_text(text, parse_mode='Markdown')

async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Использование: /forget ID (число из /recall)")
        return
    
    try:
        memory_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ ID должно быть числом")
        return
    
    db.delete_memory(memory_id, user_id)
    await update.message.reply_text("🗑️ Заметка удалена.")    

# ========== АВТОПОСТИНГ ПО РАСПИСАНИЮ ==========
async def auto_post(app):
    print(f"auto_post ВЫЗВАНА в {datetime.now()}")

    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute

    post_type = None

     # Суббота: код
    if weekday == 5 and hour == 19:
        post_type = 'code'
        print(f"Условие сработало! post_type = {post_type} (суббота код)")

    # Пятница день — чёрное
    elif weekday == 4 and 14 <= hour <= 17:
        post_type = 'black'
        print(f"Условие сработало! post_type = {post_type} (пятница чёрное)")

    # Пятница вечер — рефлексия
    elif weekday == 4 and 18 <= hour <= 19:
        post_type = 'reflect'
        print(f"Условие сработало! post_type = {post_type} (пятница рефлексия)")

    # Воскресенье — рофл
    elif weekday == 6 and 9 <= hour <= 10:
        post_type = 'rofl'
        print(f"Условие сработало! post_type = {post_type} (воскресенье рофл)")

    # Остальные дни вечером
    elif 13 <= hour <= 14:
        schedule = {
            0: 'hot_news',
            1: 'black',
            2: 'code',
            3: 'hot_news',
        }
        post_type = schedule.get(weekday)
        if post_type:
            print(f"Условие сработало! post_type = {post_type} (вечер по расписанию)")

    if not post_type:
        return

    # Проверка на дубли
    last = db.get_last_published(post_type, days=2)
    if last and (time.time() - last) < 2 * 86400:
        print(f"Автопостинг: {post_type} уже был недавно, пропускаем")
        #print(f"DEBUG: Пропускаем проверку last_published для {post_type}")
        return

    print(f"→ Запускаю публикацию: {post_type}")

    if post_type == 'hot_news':
        await post_hot_news_auto(app)
    elif post_type == 'black':
        await post_black_auto(app)
    elif post_type == 'code':
        await post_code_auto(app)
    elif post_type == 'reflect':
        await post_reflect_auto(app)
    elif post_type == 'rofl':
        await post_rofl_auto(app)

    db.save_auto_published(post_type)
    print(f"✅ Автопостинг завершён: {post_type}")

# ========== АВТО-ФУНКЦИИ ДЛЯ АВТОПОСТИНГА ==========

async def post_hot_news_auto(app):
    """Автоматическая публикация горячей новости"""
    print("=== post_hot_news_auto ВЫЗВАНА ===")
    
    hot_news = blogger.get_hot_news()
    if not hot_news:
        print("❌ Авто-новость: ничего не найдено")
        return
    
    post_text = blogger.generate_news_post(hot_news['link'], hot_news['title'], hot_news['summary'])
    
    try:
        sent = await app.bot.send_message(
            config.TEST_CHANNEL_ID, 
            post_text, 
            parse_mode='Markdown'
        )
        print(f"✅ Авто-новость опубликована: {hot_news['title'][:50]}, ID: {sent.message_id}")
        db.save_post(sent.message_id, post_text)
    except Exception as e:
        print(f"❌ ОШИБКА при отправке новости: {type(e).__name__} — {e}")
        import traceback
        traceback.print_exc()

async def post_black_auto(app):
    """Автоматическая публикация уязвимости"""
    print("=== post_black_auto ВЫЗВАНА ===")
    
    black_news = blogger.get_black_news()
    if not black_news:
        print("❌ Авто-уязвимость: ничего не найдено")
        return
    
    post_text = blogger.generate_black_post(black_news[0])
    
    try:
        sent = await app.bot.send_message(
            config.TEST_CHANNEL_ID, 
            post_text, 
            parse_mode='Markdown'
        )
        print(f"✅ Авто-уязвимость опубликована: {black_news[0]['title'][:50]}, ID: {sent.message_id}")
        db.save_post(sent.message_id, post_text)
    except Exception as e:
        print(f"❌ ОШИБКА при отправке уязвимости: {type(e).__name__} — {e}")
        import traceback
        traceback.print_exc()

async def post_code_auto(app):
    """Автоматическая публикация полезного кода"""
    print("=== post_code_auto ВЫЗВАНА ===")
    
    post_text = blogger.generate_code_post()
    
    from utils.markdown_cleaner import clean_markdown
    post_text = clean_markdown(post_text)
    
    try:
        sent = await app.bot.send_message(
            config.TEST_CHANNEL_ID, 
            post_text, 
            parse_mode='Markdown'
        )
        print(f"✅ Авто-код опубликован успешно! ID: {sent.message_id}")
        db.save_post(sent.message_id, post_text)
    except Exception as e:
        if "Can't parse entities" in str(e):
            # Пробуем ещё раз, но с экранированием проблемных символов
            import re
            # Экранируем одиночные спецсимволы
            fixed_text = re.sub(r'(?<!\\)([_*`])(?![_*`])', r'\\\1', post_text)
            try:
                sent = await app.bot.send_message(
                    config.TEST_CHANNEL_ID, 
                    fixed_text, 
                    parse_mode='Markdown'
                )
                print(f"✅ Авто-код опубликован (после фикса)! ID: {sent.message_id}")
                db.save_post(sent.message_id, post_text)
            except:
                # Если и это не помогло — логируем ошибку
                print(f"❌ Не удалось отправить даже после фикса: {e}")
        else:
            print(f"❌ ОШИБКА при отправке кода: {type(e).__name__} — {e}")
            import traceback
            traceback.print_exc()

async def post_reflect_auto(app):
    """Автоматическая публикация рефлексии"""
    print("=== post_reflect_auto ВЫЗВАНА ===")
    
    post_text = blogger.generate_reflect_post()
    
    try:
        sent = await app.bot.send_message(
            config.TEST_CHANNEL_ID, 
            post_text, 
            parse_mode='Markdown'
        )
        print(f"✅ Авто-рефлексия опубликована! ID: {sent.message_id}")
        db.save_post(sent.message_id, post_text)
    except Exception as e:
        print(f"❌ ОШИБКА при отправке рефлексии: {type(e).__name__} — {e}")
        import traceback
        traceback.print_exc()

async def post_rofl_auto(app):
    """Автоматическая публикация подборки тупых вопросов"""
    print("=== post_rofl_auto ВЫЗВАНА ===")
    
    post_text = blogger.generate_rofl_post()
    
    try:
        sent = await app.bot.send_message(
            chat_id=config.TEST_CHANNEL_ID, 
            text=post_text
        )
        print(f"✅ Авто-рофл опубликован! ID: {sent.message_id}")
        db.save_post(sent.message_id, post_text)
    except Exception as e:
        print(f"❌ ОШИБКА при отправке рофла: {type(e).__name__} — {e}")
        import traceback
        traceback.print_exc()


async def stats_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    total_notes, total_users, top_users = db.get_remember_stats()
    
    text = f"**📊 Статистика /remember**\n\n"
    text += f"Всего заметок: {total_notes}\n"
    text += f"Пользователей с заметками: {total_users}\n\n"
    text += "**Топ-5 по заметкам:**\n"
    for user_id, count in top_users:
        text += f"• `{user_id}` — {count} заметок\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')



async def readme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Получаем сохранённый проект
    project_data = db.get_temp_project_path(user_id)
    if not project_data:
        await update.message.reply_text("❌ Нет проекта для генерации README. Сначала сделай /github_push")
        return
    
    temp_dir, repo_name, owner, repo_url = project_data
    
    await update.message.reply_text(f"📂 Сканирую файловую структуру {repo_name}...")
    
        # Рекурсивно ищем main.py
    main_content = ""
    main_path = None
    for root, dirs, filenames in os.walk(temp_dir):
        if 'main.py' in filenames:
            main_path = os.path.join(root, 'main.py')
            break
    
    if main_path:
        with open(main_path, 'r', encoding='utf-8', errors='ignore') as f:
            main_content = f.read(1500)
        await update.message.reply_text(f"✅ Обнаружен исполняемый модуль")
    else:
        await update.message.reply_text(f"⚠️ main.py не найден, README будет базовым")
    
    # Определяем тип проекта
    project_type = "Python"
    if os.path.exists(os.path.join(temp_dir, "package.json")):
        project_type = "Node.js"
    elif os.path.exists(os.path.join(temp_dir, "go.mod")):
        project_type = "Go"
    elif os.path.exists(os.path.join(temp_dir, "Cargo.toml")):
        project_type = "Rust"
    
    await update.message.reply_text(f"⚙️Генерирую README...")
    
    prompt = f"""Напиши README.md для {project_type} проекта.

Название: {repo_name}

Код из main.py:
{main_content[:1500] if main_content else 'не найден'}

README должен содержать:
1. Название и описание (придумай на основе названия и кода)
2. Установку и запуск
3. Примеры использования

Формат: Markdown. Коротко, без воды."""
    
    readme_content = llm.ask([{"role": "user", "content": prompt}])
    
    # Отправляем на GitHub
    token = db.get_github_token(user_id)
    import aiohttp, base64
    
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"token {token}"}
        
        # Проверяем, существует ли README
        async with session.get(f"https://api.github.com/repos/{owner}/{repo_name}/contents/README.md", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                sha = data.get('sha')
            else:
                sha = None
        
        # Создаём или обновляем
        data = {
            "message": "Add README.md",
            "content": base64.b64encode(readme_content.encode()).decode('utf-8'),
            "branch": "main"
        }
        if sha:
            data["sha"] = sha
        
        async with session.put(f"https://api.github.com/repos/{owner}/{repo_name}/contents/README.md", headers=headers, json=data) as resp:
            if resp.status in [200, 201]:
                await update.message.reply_text(f"✅ README добавлен! Смотри: {repo_url}")
            else:
                error = await resp.text()
                await update.message.reply_text(f"❌ Ошибка: {error[:200]}")
    
    # Удаляем временную папку
    shutil.rmtree(temp_dir, ignore_errors=True)
    db.clear_temp_project_path(user_id)

async def fix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await handle_fix(update, context, user_id, db)

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await handle_download(update, context, user_id, db)

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /approve user_id количество")
        return
    
    user_id = int(context.args[0])
    amount = int(context.args[1])
    
    db.add_tokens(user_id, amount)
    
    # Уведомляем юзера
    try:
        await context.bot.send_message(
            user_id,
            f"✅ Платёж подтверждён!\n"
            f"💰 Начислено: {amount:,} токенов\n"
            f"💎 Баланс: {db.get_token_balance(user_id):,} токенов"
        )
    except:
        pass
    
    await update.message.reply_text(f"✅ Начислено {amount:,} токенов юзеру {user_id}")    

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("=== ФОТО ПОЛУЧЕНО (отдельный хендлер) ===")
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    caption = update.message.caption or "Без подписи"
    
    photo_file = update.message.photo[-1]
    file_id = photo_file.file_id
    
    tokens = pending_approvals.get(user_id, "КОЛИЧЕСТВО")  # ← ВОТ СЮДА
    
    await context.bot.send_photo(
        chat_id=config.OWNER_ID,
        photo=file_id,
        caption=f"🧾 Чек от @{username}\n"
                f"🆔 ID: `{user_id}`\n"
                f"📝 Подпись: {caption}\n\n"
                f"Для начисления: /approve {user_id} {tokens}"
    )
    
    await update.message.reply_text("✅ Чек отправлен. Токены будут зачислены после проверки.")

async def share_report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("share_report_"):
        session_id = data.replace("share_report_", "")
        
        # Получаем отчёт из БД по session_id
        session = db.get_session_by_id(session_id)
        if not session:
            await query.edit_message_text("❌ Отчёт не найден.")
            return
        
        full_analysis = session['analysis_text']
        
        # Публикуем в канал-хранилище
        msg = await context.bot.send_message(
            config.REPORTS_CHANNEL_ID,
            full_analysis,
            parse_mode='Markdown'
        )
        
        # Формируем ссылку
        # Для публичного канала с username
        report_link = f"https://t.me/golem_reports/{msg.message_id}"
        
        await query.edit_message_text(
            f"🔗 Ссылка на отчёт:\n{report_link}\n\n"
            "Скопируй и поделись с кем угодно.",
            reply_markup=None
        )    

def main():
    if not validate_config():
        return
    
    db.init_db()
    print(f"DEBUG: TEST_CHANNEL_ID = {config.TEST_CHANNEL_ID}")
    if not config.TEST_CHANNEL_ID:
        print("⚠️ ВНИМАНИЕ! config.TEST_CHANNEL_ID пустой! Посты никуда не уйдут!")
    logger.info("База данных инициализирована")
    
    app = Application.builder().token(config.TG_BOT_TOKEN).build()
    import builtins
    builtins.bot = app.bot
    
    
    app.add_handler(CommandHandler("start", start, block=False))
    app.add_handler(CommandHandler("help", help_command, block=False))
    app.add_handler(CommandHandler("mode", set_mode, block=False))
    app.add_handler(CommandHandler("say", say_in_chat, block=False))
    app.add_handler(CommandHandler("ban", ban_user, block=False))
    app.add_handler(CommandHandler("unban", unban_user, block=False))
    app.add_handler(CommandHandler("stats", stats, block=False))
    app.add_handler(CommandHandler("get_chat_id", get_chat_id, block=False))
    app.add_handler(CommandHandler("post_update", post_update, block=False))
    app.add_handler(CommandHandler("changelog", changelog, block=False))
    app.add_handler(CommandHandler("clear_files", clear_files, block=False))
    app.add_handler(CommandHandler("clear_history", clear_history, block=False))
    app.add_handler(CommandHandler("edit", edit_post, block=False))
    app.add_handler(CommandHandler("publish", publish, block=False))
    app.add_handler(CommandHandler("post_about", post_about, block=False))
    app.add_handler(CommandHandler("post_hot_news", post_hot_news, block=False))
    app.add_handler(CommandHandler("post_reflect", post_reflect, block=False))
    app.add_handler(CommandHandler("post_rofl", post_rofl, block=False))
    app.add_handler(CommandHandler("broadcast", broadcast, block=False))  
    app.add_handler(CommandHandler("ac", admin_commands, block=False))
    app.add_handler(CommandHandler("balance", balance, block=False)) 
    app.add_handler(CommandHandler("referrals", referrals, block=False))
    app.add_handler(CommandHandler("post_code", post_code, block=False))
    app.add_handler(CommandHandler("post_black", post_black, block=False))
    app.add_handler(CommandHandler("buy", buy, block=False))
    app.add_handler(CommandHandler("check", check, block=False))
    app.add_handler(CommandHandler("github_push", github_push, block=False))
    app.add_handler(CommandHandler("set_github_token", set_github_token, block=False))
    app.add_handler(CommandHandler("analyze", analyze, block=False))
    app.add_handler(CommandHandler("snapshot", snapshot, block=False))
    app.add_handler(CommandHandler("remember", remember, block=False))
    app.add_handler(CommandHandler("recall", recall, block=False))
    app.add_handler(CommandHandler("forget", forget, block=False))
    app.add_handler(CommandHandler("ban_id", ban_id, block=False))
    app.add_handler(CommandHandler("stats_remember", stats_remember, block=False))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post, block=False))
    app.add_handler(CommandHandler("readme", readme, block=False))
    app.add_handler(CommandHandler("fix", fix_command))
    app.add_handler(CommandHandler("download", download_command))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CallbackQueryHandler(share_report_callback, pattern="^share_report_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.Document.ALL, handle_message, block=False))

        
        # Запускаем фоновую задачу автопостинга
    async def auto_post_loop():
        print("auto_post_loop ЗАПУЩЕН") 
        while True:
            await auto_post(app)
            await asyncio.sleep(3600)

    # Запускаем бота стандартным способом
    logger.info("🚀 Голем запущен!")
    
    # Добавляем задачу в текущий event loop
    loop = asyncio.get_event_loop()
    loop.create_task(auto_post_loop())
    logger.info("⏰ Автопостинг запущен (проверка каждый час)")
    
    async def cleaner_loop():
        while True:
            db.clean_old_sessions(hours=24)
            db.clean_old_temp_projects(hours=24)
            await asyncio.sleep(86400)  # 24 часа

    loop.create_task(cleaner_loop())
    logger.info("🗑️ Очистка старых сессий и временных проектов запущена (раз в 24 часа)")

    app.run_polling()

def is_technical(text):
    keywords = [
        "код","Голем", "голем" "ошибка", "баг", "функция", "класс", "скрипт", "бот", 
        "python", "питон", "сортировка", "алгоритм", "api", "json", 
        "библиотека", "установить", "import", "def", "async", "помоги",
        "как", "почему", "не работает", "поломалось", "сделай", "напиши",
        "помнишь", "память", "контекст",
    ]
    text_lower = text.lower()
    return any(k in text_lower for k in keywords) or "```" in text

if __name__ == "__main__":
    main()
