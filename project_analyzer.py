# project_analyzer.py
import os
import time
import tempfile
import shutil
import subprocess
import zipfile
import io
import asyncio
import logging
from database import db
from core.code_analyzer import run_full_analysis
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# Настраиваем логгер
logger = logging.getLogger(__name__)


def safe_markdown(text: str) -> str:
    """Исправляет проблемные места в Markdown для Telegram"""
    if not text:
        return text
    
    stars = text.count('*')
    underscores = text.count('_')
    backticks = text.count('`')
    
    if stars % 2 != 0:
        text = text.replace('*', '\\*')
    if underscores % 2 != 0:
        text = text.replace('_', '\\_')
    if backticks % 2 != 0:
        text = text.replace('`', '\\`')
    
    return text


async def analyze_project_from_zip(update, context, file, llm, user_id):
    """Анализирует ZIP-архив, сохраняет сессию"""
    
    logger.info(f"🚀 [user_id={user_id}] Начало анализа ZIP-архива: {file.file_name}")
    
    # Удаляем старую сессию пользователя
    old_session = db.get_user_active_session(user_id)
    if old_session:
        if len(old_session) == 5:
            session_id, old_path, source, analysis_text, _ = old_session
        else:
            session_id, old_path, source, analysis_text = old_session
        if old_path and os.path.exists(old_path):
            shutil.rmtree(old_path, ignore_errors=True)
            logger.info(f"🗑️ [user_id={user_id}] Удалена старая сессия: {old_path}")
        db.delete_user_session(user_id)
    
    temp_dir = tempfile.mkdtemp(prefix=f"golem_zip_{user_id}_")
    source = "ZIP-архив"
    original_filename = file.file_name
    logger.info(f"📁 [user_id={user_id}] Создана временная директория: {temp_dir}")
    
    try:
        file_obj = await file.get_file()
        zip_bytes = await file_obj.download_as_bytearray()
        logger.info(f"📦 [user_id={user_id}] ZIP скачан, размер: {len(zip_bytes)} байт")
        
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            file_list = zf.namelist()
            logger.info(f"📋 [user_id={user_id}] Файлов в архиве: {len(file_list)}")
            zf.extractall(temp_dir)
            logger.info(f"✅ [user_id={user_id}] Архив распакован")
        
        import subprocess
        subprocess.Popen([
            "/root/golem/venv/bin/python",
            "/root/golem/run_analysis.py",
            temp_dir, source, str(user_id), original_filename
       ])

        await bot.send_message(
            user_id,
            "🔍 **Анализ запущен**\n\n"
            "Я анализирую репозиторий в фоне. Результат пришлю сюда через несколько минут.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ [user_id={user_id}] Ошибка распаковки: {str(e)[:200]}")
        await bot.send_message(user_id, f"❌ Ошибка при распаковке: {str(e)[:200]}")
        shutil.rmtree(temp_dir, ignore_errors=True)


async def analyze_project_from_repo(update, context, repo_url, llm, user_id):
    """Анализирует GitHub-репозиторий, сохраняет сессию"""
    
    logger.info(f"🚀 [user_id={user_id}] Начало анализа репозитория: {repo_url}")
    
    # Удаляем старую сессию пользователя
    old_session = db.get_user_active_session(user_id)
    if old_session:
        if len(old_session) == 5:
            session_id, old_path, source, analysis_text, _ = old_session
        else:
            session_id, old_path, source, analysis_text = old_session
        if old_path and os.path.exists(old_path):
            shutil.rmtree(old_path, ignore_errors=True)
            logger.info(f"🗑️ [user_id={user_id}] Удалена старая сессия: {old_path}")
        db.delete_user_session(user_id)
    
    temp_dir = tempfile.mkdtemp(prefix=f"golem_repo_{user_id}_")
    source = repo_url
    original_filename = repo_url.split('/')[-1] + ".zip"
    logger.info(f"📁 [user_id={user_id}] Создана временная директория: {temp_dir}")
    
    # Сразу отвечаем юзеру
    await bot.send_message(
        user_id,
        "🔍 **Анализ запущен**\n\n"
        "Я анализирую репозиторий в фоне. Результат пришлю сюда через несколько минут.",
        parse_mode='Markdown'
    )
    
    try:
        # Клонируем репозиторий асинхронно
        logger.info(f"🔄 [user_id={user_id}] Клонирование репозитория...")
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", repo_url, temp_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, ["git", "clone"])
        
        logger.info(f"✅ [user_id={user_id}] Репозиторий склонирован")
        
        import subprocess
        subprocess.Popen([
            "/root/golem/venv/bin/python",
            "/root/golem/run_analysis.py",
            temp_dir, source, str(user_id), original_filename
        ])

        await bot.send_message(
            user_id,
            "🔍 **Анализ запущен**\n\n"
            "Я анализирую репозиторий в фоне. Результат пришлю сюда через несколько минут.",
            parse_mode='Markdown'
         )
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ [user_id={user_id}] Ошибка клонирования")
        await bot.send_message(user_id, f"❌ Ошибка клонирования репозитория")
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as e:
        logger.error(f"❌ [user_id={user_id}] Ошибка: {str(e)[:200]}")
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)[:200]}")
        shutil.rmtree(temp_dir, ignore_errors=True)

async def _analyze_directory_async(context, project_dir, source, llm, user_id, original_filename=None):
    """Асинхронный анализ директории (фоновый режим)"""
    
    logger.info(f"🔍 [user_id={user_id}] Начало анализа директории: {project_dir}")
    
    try:
        from telegram.ext import Application
        import config
        app = Application.builder().token(config.TG_BOT_TOKEN).build()
        bot = app.bot
        # === ОПРЕДЕЛЯЕМ ЯЗЫКИ ПРОЕКТА ===
        extensions_map = {
            '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
            '.go': 'Go', '.rs': 'Rust', '.java': 'Java', '.kt': 'Kotlin',
            '.cpp': 'C++', '.c': 'C', '.cs': 'C#', '.php': 'PHP',
            '.rb': 'Ruby', '.swift': 'Swift'
        }
        
        languages_found = {}
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', 'vendor', 'target', 'build', '__pycache__']]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in extensions_map:
                    lang = extensions_map[ext]
                    languages_found[lang] = languages_found.get(lang, 0) + 1
        
        if not languages_found:
            await bot.send_message(user_id, "❌ **Не удалось определить язык проекта**\n\nВ проекте нет файлов с исходным кодом.")
            shutil.rmtree(project_dir, ignore_errors=True)
            return
        
                # Проверяем, какие из поддерживаемых языков есть
        supported_langs = ['Python', 'Go']
        found_supported = [lang for lang in supported_langs if languages_found.get(lang, 0) > 0]
        
        if not found_supported:
            other_list = "\n".join([f"• {lang}: {count} файлов" for lang, count in languages_found.items()])
            await bot.send_message(
                user_id,
                f"⚠️ **Голем пока не умеет анализировать эти языки**\n\n"
                f"Найденные файлы:\n{other_list}\n\n"
                f"🔥 **Сейчас умею:** Python, Go\n"
                f"📋 **В очереди:** JavaScript, Rust"
            )
            shutil.rmtree(project_dir, ignore_errors=True)
            return
        
        # Предупреждаем о неподдерживаемых языках
        other_langs = {k: v for k, v in languages_found.items() if k not in supported_langs}
        if other_langs:
            other_names = ", ".join(other_langs.keys())
            await bot.send_message(
                user_id,
                f"ℹ️ Найдены также: {other_names}. Они не анализируются.\n"
            )
        
        # Сообщаем, какие языки анализируем
        if len(found_supported) > 1:
            await bot.send_message(
                user_id,
                f"🔄 Найдены: {', '.join(found_supported)}. Анализирую оба языка параллельно..."
            )

        # === СБОР СТРУКТУРЫ ПРОЕКТА ===
        file_count = 0
        files_by_lang = {lang: [] for lang in found_supported}
        file_tree = []
        
        logger.info(f"📂 [user_id={user_id}] Сканирование файлов...")
        
        for root, dirs, filenames in os.walk(project_dir):
            if '.git' in dirs:
                dirs.remove('.git')
            if '__pycache__' in dirs:
                dirs.remove('__pycache__')
            
            level = root.replace(project_dir, '').count(os.sep)
            indent = '  ' * level
            folder_name = os.path.basename(root)
            if level == 0:
                file_tree.append(f"📁 {folder_name}/")
            elif folder_name and not folder_name.startswith('.'):
                file_tree.append(f"{indent}📁 {folder_name}/")
            
            for filename in filenames:
                file_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()
                
                if ext in ['.db', '.session', '.sqlite3', '.bin', '.exe', 
                          '.jpg', '.png', '.pyc', '.pyo', '.gif', '.ico']:
                    continue
                
                file_count += 1
                
                # Определяем язык файла
                lang = extensions_map.get(ext)
                if lang in found_supported:
                    rel_path = os.path.relpath(file_path, project_dir)
                    files_by_lang[lang].append(rel_path)
                    if lang == 'Python':
                        file_tree.append(f"{indent}  🐍 {filename}")
                    elif lang == 'Go':
                        file_tree.append(f"{indent}  🦦 {filename}")
                else:
                    icon = "📄"
                    if ext in ['.txt', '.md']: icon = "📝"
                    elif ext in ['.json', '.yaml', '.yml']: icon = "⚙️"
                    elif ext in ['.html', '.htm']: icon = "🌐"
                    elif ext in ['.js', '.ts']: icon = "📜"
                    elif ext == '.env': icon = "🔐"
                    file_tree.append(f"{indent}  {icon} {filename}")
        
        # Логируем найденное
        lang_stats = ", ".join([f"{lang}: {len(files)}" for lang, files in files_by_lang.items()])
        logger.info(f"📊 [user_id={user_id}] Найдено файлов: {file_count}, {lang_stats}")
        
        # === ЗАПУСК АНАЛИЗА ЧЕРЕЗ ПЛАГИНЫ (ПАРАЛЛЕЛЬНО) ===
        logger.info(f"🛠️ [user_id={user_id}] Запуск анализа через плагины: {', '.join(found_supported)}...")
        
        from core.langs import get_analyzer
        
        async def analyze_lang(lang):
            analyzer = get_analyzer(lang)
            if analyzer:
                return lang, await analyzer.analyze(project_dir)
            else:
                return lang, None
        
        tasks = [analyze_lang(lang) for lang in found_supported]
        results_list = await asyncio.gather(*tasks)
        
        # Объединяем результаты
        all_results = {}
        total_issues_combined = {}
        llm_contexts = []
        
        for lang, results in results_list:
            if results:
                all_results[lang] = results
                total_issues_combined.update(results.get("total_issues", {}))
                analyzer = get_analyzer(lang)
                llm_contexts.append(analyzer.get_context_for_llm(results))
        
        llm_context = "\n\n".join(llm_contexts)
        
        # Для совместимости со старым промптом
        if 'Python' in all_results:
            py_results = all_results['Python']
            bandit_result = py_results.get("bandit", {"results": []})
            ruff_result = py_results.get("ruff", {"results": []})
            pip_audit_result = py_results.get("pip_audit", {"vulnerabilities": []})
        else:
            bandit_result = {"results": []}
            ruff_result = {"results": []}
            pip_audit_result = {"vulnerabilities": []}

        
    
                # === ФОРМИРУЕМ КОНТЕКСТ ДЛЯ LLM ===
        project_tree_text = "\n".join(file_tree[:50])
        
        # Извлекаем код с проблемами Python
        from core.code_analyzer import extract_code_context
        code_context = extract_code_context(project_dir, bandit_result, ruff_result)

        # === ДОБАВЛЯЕМ ПРОБЛЕМЫ GO ===
        if 'Go' in all_results:
            go_results = all_results['Go']
            # Добавляем проблемы golangci-lint
            go_issues = go_results.get('staticcheck', {}).get('issues', [])
            if go_issues:
                code_context += "\n\n**Проблемы Go (staticcheck):**\n"
                for issue in go_issues[:15]:
                    code_context += f"- {issue.get('file')}:{issue.get('line')} — {issue.get('message')}\n"
            
            # Добавляем проблемы gosec
            gosec_issues = go_results.get('gosec', {}).get('issues', [])
            if gosec_issues:
                code_context += "\n\n**Проблемы безопасности Go (gosec):**\n"
                for issue in gosec_issues[:15]:
                    code_context += f"- {issue.get('file')}:{issue.get('line')} — {issue.get('message')} ({issue.get('rule')})\n"
        
                # === ПРОМПТ ===
        all_main_files = []
        for lang, files in files_by_lang.items():
            all_main_files.extend(files)
        
        # Формируем статистику для промпта
        stats_text = ""
        if 'Python' in all_results:
            py = all_results['Python']['total_issues']
            stats_text += f"• 🔴 Bandit: {py.get('bandit', 0)} | ⚠️ Ruff: {py.get('ruff', 0)} | 📦 pip-audit: {py.get('pip_audit', 0)}\n"
        if 'Go' in all_results:
            go = all_results['Go']['total_issues']
            stats_text += f"• 🔍 staticcheck: {go.get('staticcheck', 0)} | 🛡️ gosec: {go.get('gosec', 0)}\n"
        
        prompt = f"""Ты анализируешь код проекта. Вот ФАКТЫ от статических анализаторов:

СТРУКТУРА ПРОЕКТА:
{project_tree_text}

Найденные языки: {', '.join(found_supported)}
Файлы: {', '.join(all_main_files[:15])}
{('... и ещё ' + str(len(all_main_files) - 15)) if len(all_main_files) > 15 else ''}

РЕЗУЛЬТАТЫ АНАЛИЗАТОРОВ:
{llm_context}

КОД С ПРОБЛЕМАМИ:
{code_context if code_context else 'Анализаторы не нашли конкретных проблемных участков'}

Напиши краткий отчёт. ВАЖНО:
- Не додумывай проблемы, которых нет в отчётах анализаторов
- Основывайся ТОЛЬКО на данных выше

Используй Markdown для форматирования:

**📌 О ПРОЕКТЕ**
[2-3 предложения. Посмотри на структуру файлов и названия. Определи, что это: веб-приложение, телеграм-бот, библиотека, микросервис, CLI-утилита, системный инструмент. Укажи ключевые технологии, которые видны из файлов (фреймворки, базы данных). Будь конкретным.]


**📊 СТАТИСТИКА**
• Файлов: {file_count} ({', '.join([f"{lang}: {len(files)}" for lang, files in files_by_lang.items()])})
{stats_text}

**🔴 ПРОБЛЕМЫ БЕЗОПАСНОСТИ**
[если есть — перечисли в формате: `файл:строка` — описание (код ошибки). Если нет — "Критических уязвимостей не найдено"]

**⚠️ ПРОБЛЕМЫ КОДА**
[если есть — перечисли в формате: `файл:строка` — описание (код ошибки). Укажи язык]

**💡 РЕКОМЕНДАЦИИ**
[конкретные действия на основе проблем. Каждый пункт с новой строки, начинай с 1. 2. 3.]

---
*Отчёт сгенерирован [Големом](https://t.me/Golem666bot)*"""
        
        logger.info(f"🤖 [user_id={user_id}] Отправка запроса к LLM...")
        
        analysis = llm.ask([{"role": "user", "content": prompt}])
        logger.info(f"✅ [user_id={user_id}] Ответ от LLM получен, размер: {len(analysis)} символов")
        
        # Чистим Markdown
        from utils.markdown_cleaner import clean_markdown
        analysis = clean_markdown(analysis)
        analysis = safe_markdown(analysis)
        
                # Статистика
        stats_lines = [f"📊 **Статистика:**", f"• Всего файлов: {file_count}"]
        for lang, files in files_by_lang.items():
            stats_lines.append(f"• {lang}: {len(files)} файлов")
        
        # Детализация по тулзам
        if 'Python' in all_results:
            py_issues = all_results['Python'].get("total_issues", {})
            stats_lines.append(f"• 🔴 Bandit: {py_issues.get('bandit', 0)} | ⚠️ Ruff: {py_issues.get('ruff', 0)}")
            stats_lines.append(f"• 📦 pip-audit: {py_issues.get('pip_audit', 0)}")
        if 'Go' in all_results:
            go_issues = all_results['Go'].get("total_issues", {})
            stats_lines.append(f"• 🔍 staticcheck: {go_issues.get('staticcheck', 0)} | 🛡️ gosec: {go_issues.get('gosec', 0)}")
        
        stats_header = "\n".join(stats_lines) + "\n\n---\n\n"
        
                
        full_analysis = analysis
        
        # Сохраняем сессию
        session_id = f"{user_id}_{int(time.time())}"
        db.save_project_session(session_id, user_id, project_dir, source, full_analysis, original_filename)
        logger.info(f"💾 [user_id={user_id}] Сессия сохранена: {session_id}")
        
        # Отправляем результат
        header = f"🔍 **Анализ проекта**\n📁 {source}\n\n"
        
        try:
            await bot.send_message(user_id, header + full_analysis, parse_mode='Markdown')
            logger.info(f"📤 [user_id={user_id}] Отправлено")
        except Exception as e:
            if "Can't parse entities" in str(e):
                logger.warning(f"⚠️ [user_id={user_id}] Ошибка парсинга Markdown, отправка без форматирования")
                await bot.send_message(user_id, (header + full_analysis).replace('*', ''))
            else:
                full_text = header + full_analysis
                for i in range(0, len(full_text), 4000):
                    try:
                        await bot.send_message(user_id, full_text[i:i+4000], parse_mode='Markdown')
                    except:
                        await bot.send_message(user_id, full_text[i:i+4000].replace('*', ''))

                # Кнопка "Поделиться"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Поделиться отчётом", callback_data=f"share_report_{session_id}")]
        ])
        await bot.send_message(
            user_id,
            "📤 Хочешь поделиться результатом? Жми кнопку.",
            reply_markup=keyboard
        )                

        # Сохраняем анализ в статистику
        db.save_analysis(user_id)                

        if 'Python' in all_results:
            py_issues = all_results['Python'].get("total_issues", {})
            if py_issues.get('ruff', 0) > 0:
                await bot.send_message(
                    user_id,
                    "💡 Часть проблем можно исправить автоматически.\n"
                    "Жми /fix чтобы запустить автофикс Ruff."
                )            
                
              
        logger.info(f"🗑️ [user_id={user_id}] Анализ завершён")
        
    except Exception as e:
        logger.error(f"❌ [user_id={user_id}] Критическая ошибка анализа: {str(e)}")
        error_msg = f"❌ Ошибка анализа: {str(e)[:200]}"
        try:
            await bot.send_message(user_id, error_msg)
        except:
            pass
        shutil.rmtree(project_dir, ignore_errors=True)

