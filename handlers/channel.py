import config
from database import db

async def handle_channel_post(post, bot):
    """Обработчик новых постов в канале"""
    chat_id = post.chat_id
    post_id = post.message.id
    post_text = post.text
    
    # Сохраняем пост в БД
    db.save_post(post_id, post_text)
    
    # Отправляем приветственный комментарий в группу обсуждения
    if chat_id == config.YOUR_CHANNEL_ID:
        await bot.send_message(
            config.YOUR_DISCUSSION_GROUP_ID,
            f"Новый пост. Обсуждение здесь."
        )