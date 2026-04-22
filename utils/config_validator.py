import os
from dotenv import load_dotenv

# Загружаем .env один раз при импорте
load_dotenv()

def validate_config():
    """Проверяет, что все обязательные переменные окружения заданы"""
    
    required_vars = [
        "TG_API_ID",
        "TG_API_HASH",
        "TG_BOT_TOKEN", 
        "DEEPSEEK_API_KEY",
        "OWNER_ID"
    ]
    
    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing.append(var)
    
    if missing:
        error_msg = f"""
❌ Ошибка конфигурации!

Отсутствуют обязательные переменные в файле .env:
{', '.join(missing)}

Пожалуйста, добавь их и перезапусти бота.
"""
        print(error_msg)
        return False
    
    # Дополнительная проверка: TG_API_ID должен быть числом
    try:
        int(os.getenv("TG_API_ID"))
    except ValueError:
        print("❌ Ошибка: TG_API_ID должен быть числом")
        return False
    
    # Проверка OWNER_ID
    try:
        int(os.getenv("OWNER_ID"))
    except ValueError:
        print("❌ Ошибка: OWNER_ID должен быть числом")
        return False
    
    print("✅ Конфигурация проверена, всё в порядке")
    return True
