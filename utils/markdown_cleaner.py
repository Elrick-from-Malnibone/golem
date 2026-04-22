import re

def clean_markdown(text: str) -> str:
    """
    Очищает Markdown для Telegram (обычный режим, не MarkdownV2)
    """
    if not text:
        return text
    
    # Убираем незакрытые **
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Считаем количество **
        count = line.count('**')
        if count % 2 != 0:
            # Убираем последнюю одинокую **
            line = re.sub(r'\*\*([^*]*)$', r'\1', line)
        
        # Убираем незакрытые блоки кода
        if line.count('```') % 2 != 0:
            line = line.replace('```', '')
        
        # Убираем битые ссылки [текст](url
        line = re.sub(r'\[([^\]]*)\]\([^)]*$', r'\1', line)
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Ограничиваем длину сообщения
    if len(text) > 4000:
        # Обрезаем, но стараемся не разорвать блок кода
        if '```' in text:
            # Ищем последний закрытый блок кода
            last_code = text.rfind('```')
            if last_code > 3500:
                text = text[:last_code] + '\n```\n... (обрезано)'
            else:
                text = text[:4000]
        else:
            text = text[:4000]
    
    return text

def escape_all_markdown(text: str) -> str:
    """Экранирует ВСЕ спецсимволы Markdown. Гарантированно не падает."""
    if not text:
        return text
    chars = r'_*[]()~`>#\+\-=|{}.!'
    return re.sub(f'([{re.escape(chars)}])', r'\\\1', text)

def clean_html(text: str) -> str:
    """Исправляет битые HTML-теги."""
    if not text:
        return text
    
    # Закрываем незакрытые теги
    tags = ['b', 'i', 'code', 'pre']
    for tag in tags:
        open_count = text.count(f'<{tag}>')
        close_count = text.count(f'</{tag}>')
        if open_count > close_count:
            text += f'</{tag}>' * (open_count - close_count)
    
    # Убираем запрещённые в Telegram теги
    allowed_tags = ['b', 'i', 'code', 'pre', 'a']
    text = re.sub(r'<(?!\/?(?:' + '|'.join(allowed_tags) + r'))[^>]+>', '', text)
    
    return text

def escape_markdown(text: str) -> str:
    """Экранирует спецсимволы Markdown"""
    if not text:
        return text
    chars = r'_*[]()~`>#\+\-=|{}.!'
    return re.sub(f'([{re.escape(chars)}])', r'\\\1', text)