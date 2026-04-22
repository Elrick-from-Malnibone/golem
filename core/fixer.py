# core/fixer.py
import json
import subprocess
import logging
import shutil
import os
import asyncio
import tempfile
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class Fixer:
    """
    Модуль автоисправления ошибок в коде.
    v1: только Ruff автофикс
    v2: + Bandit (через LLM), + Semgrep, + рефакторинг, + оптимизация
    """
    
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.fixed_files = []
        self.fixes_applied = {}
    
    async def run_ruff_fix(self) -> Dict[str, Any]:
        """
        Запускает ruff check --fix и возвращает результат.
        """
        logger.info(f"🔧 [Fixer] Запуск ruff --fix для {self.project_path}")
        
        # Сначала считаем сколько проблем было ДО фикса
        before_result = subprocess.run(
            ["ruff", "check", self.project_path, "--output-format", "json"],
            capture_output=True, text=True,
            encoding='utf-8', errors='ignore'
        )
        
        before_count = 0
        if before_result.stdout:
            try:
                import json
                data = json.loads(before_result.stdout)
                before_count = len(data)
            except:
                pass
        
        # Запускаем автофикс
        fix_result = subprocess.run(
            ["ruff", "check", self.project_path, "--fix", "--output-format", "json"],
            capture_output=True, text=True,
            encoding='utf-8', errors='ignore'
        )
        
        # Считаем сколько проблем осталось ПОСЛЕ фикса
        after_count = 0
        remaining_issues = []
        if fix_result.stdout:
            try:
                import json
                data = json.loads(fix_result.stdout)
                after_count = len(data)
                remaining_issues = data
            except:
                pass
        
        fixed_count = before_count - after_count
        
        # Группируем оставшиеся проблемы по типам
        remaining_by_type = {}
        for issue in remaining_issues:
            code = issue.get("code", "unknown")
            remaining_by_type[code] = remaining_by_type.get(code, 0) + 1
        
        logger.info(f"✅ [Fixer] Исправлено: {fixed_count}, осталось: {after_count}")
        
        return {
            "success": True,
            "before_count": before_count,
            "after_count": after_count,
            "fixed_count": fixed_count,
            "remaining_issues": remaining_issues,
            "remaining_by_type": remaining_by_type,
            "error": None
        }
    
    def get_diff(self) -> str:
        """
        Возвращает diff изменений, сделанных Ruff.
        """
        result = subprocess.run(
            ["ruff", "check", self.project_path, "--fix", "--diff"],
            capture_output=True, text=True,
            encoding='utf-8', errors='ignore' 
        )
        
        if result.stdout:
            return result.stdout
        else:
            return "📝 Изменений нет или Ruff не показывает diff."
    
    def _clean_paths(self, diff_text: str) -> str:
        if not diff_text or diff_text == "📝 Изменений нет или Ruff не показывает diff.":
            return diff_text
    
        # Берём имя папки проекта
        project_folder = os.path.basename(self.project_path.rstrip('/\\'))
    
        cleaned_lines = []
        for line in diff_text.split('\n'):
            if line.startswith('--- ') or line.startswith('+++ '):
                if project_folder in line:
                    idx = line.find(project_folder)
                    if idx != -1:
                        # Всё после папки проекта, плюс убираем саму папку
                        rel_path = line[idx + len(project_folder):].lstrip('/\\')
                        if rel_path:
                            line = './' + rel_path.replace('\\', '/')
                        else:
                            line = '.'
            cleaned_lines.append(line)
    
        return '\n'.join(cleaned_lines)
    
    def get_fix_summary(self, result: Dict[str, Any]) -> str:
        """
        Формирует человекочитаемую сводку по результатам фикса.
        """
        if result.get("error"):
            return f"❌ Ошибка автофикса: {result['error']}"
        
        fixed = result["fixed_count"]
        before = result["before_count"]
        after = result["after_count"]
        remaining_by_type = result.get("remaining_by_type", {})
        
        if before == 0:
            return "✅ Ruff не нашёл проблем для исправления."
        
        if fixed == 0:
            lines = [f"⚠️ **Ruff не может автоматически исправить эти проблемы**\n"]
            lines.append(f"Найдено {before} проблем, но все требуют ручного анализа:\n")
            for code, count in remaining_by_type.items():
                lines.append(f"• {code}: {count} шт.")
            return "\n".join(lines)
        
        if after == 0:
            return f"✅ **Всё исправлено!**\nRuff починил все {fixed} проблем."
        
        # Частичное исправление
        lines = [
            f"🔧 **Частичное автоисправление**\n",
            f"✅ Исправлено автоматически: {fixed}",
            f"⚠️ Требуют ручной работы: {after}\n",
            "**Что осталось:**"
        ]
        for code, count in remaining_by_type.items():
            lines.append(f"• {code}: {count} шт.")
        
        return "\n".join(lines)
    
    def create_archive(self, original_name: str = None) -> Optional[str]:
        """
        Создаёт ZIP-архив с исправленными файлами.
        Возвращает путь к архиву.
        """
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip.close()
        
        # Красивое имя архива
        if original_name:
            base_name = os.path.splitext(original_name)[0]
            archive_name = f"{base_name}_fixed"
        else:
            project_name = os.path.basename(self.project_path.rstrip('/\\'))
            archive_name = f"{project_name}_fixed"
        
        # Создаём архив
        shutil.make_archive(
            os.path.join(tempfile.gettempdir(), archive_name),
            'zip',
            self.project_path
        )
        
        archive_path = os.path.join(tempfile.gettempdir(), f"{archive_name}.zip")
        logger.info(f"📦 [Fixer] Архив создан: {archive_path}")
        
        return archive_path


# ========== Функции для вызова из main.py ==========

async def handle_fix(update, context, user_id, db) -> None:
    """
    Обработчик команды /fix.
    """
    # Получаем активную сессию
    session = db.get_user_active_session(user_id)
    if not session:
        try:
            await update.message.reply_text("❌ Нет активного анализа. Сначала /analyze")
        except:
            pass
        return
    
    # Распаковываем с учётом возможного original_filename
    if len(session) == 5:
        session_id, project_path, source, analysis_text, original_filename = session
    else:
        session_id, project_path, source, analysis_text = session
        original_filename = None
    
    # Проверяем что папка ещё существует
    if not project_path or not os.path.exists(project_path):
        try:
            await update.message.reply_text("❌ Проект не найден. Запусти анализ заново.")
        except:
            pass
        return
    
    try:
        await update.message.reply_text("🔧 Запускаю автофикс Ruff...")
    except:
        pass
    
    fixer = Fixer(project_path)
    
    # 1. Сначала получаем diff (до применения изменений)
    diff_text = fixer.get_diff()
    
    # 2. Потом применяем фикс
    result = await fixer.run_ruff_fix()
    summary = fixer.get_fix_summary(result)
    
    try:
        await update.message.reply_text(summary, parse_mode='Markdown')
    except:
        await update.message.reply_text(summary)
    
    # 3. Если есть исправления — показываем diff (который получили ДО фикса)
    if result["fixed_count"] > 0:
        db.save_fix(user_id, result["fixed_count"])
        if diff_text and diff_text != "📝 Изменений нет или Ruff не показывает diff.":
            # Очищаем пути перед показом
            diff_text = fixer._clean_paths(diff_text)
            
            if len(diff_text) > 1000:
                diff_text = diff_text[:1000] + "\n... (обрезано, слишком длинный diff)"
            
            try:
                await update.message.reply_text(
                    f"📝 **Изменения:**\n```diff\n{diff_text}\n```",
                    parse_mode='Markdown'
                )
            except:
                await update.message.reply_text(f"📝 Изменения:\n{diff_text}")
        
        try:
            await update.message.reply_text(
                "📦 Хочешь скачать исправленные файлы? Жми /download"
            )
        except:
            pass


async def handle_download(update, context, user_id, db) -> None:
    """
    Обработчик команды /download.
    """
    session = db.get_user_active_session(user_id)
    if not session:
        await update.message.reply_text("❌ Нет активного анализа. Сначала /analyze")
        return
    
    # Распаковываем с учётом возможного original_filename
    if len(session) == 5:
        session_id, project_path, source, analysis_text, original_filename = session
    else:
        session_id, project_path, source, analysis_text = session
        original_filename = None
    
    if not project_path or not os.path.exists(project_path):
        await update.message.reply_text("❌ Проект не найден.")
        return
    
    fixer = Fixer(project_path)
    archive_path = fixer.create_archive(original_filename)
    
    if archive_path:
        with open(archive_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(archive_path),
                caption="📦 Исправленные файлы проекта"
            )
        os.unlink(archive_path)  # Удаляем временный архив
    else:
        await update.message.reply_text("❌ Не удалось создать архив.")

class GoFixer:
    def __init__(self, project_path: str):
        self.project_path = project_path
    
    async def run_fix(self) -> Dict[str, Any]:
        """Запускает gopls codeaction только для проблемных файлов"""
        logger.info(f"🔧 [GoFixer] Анализ проблемных файлов...")
        
        # Находим папку с go.mod
        module_dir = self.project_path
        for root, dirs, files in os.walk(self.project_path):
            if "go.mod" in files:
                module_dir = root
                break
        
        # 1. Запускаем staticcheck для поиска проблем
        proc = await asyncio.create_subprocess_exec(
            "staticcheck", "-f", "json", "./...",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=module_dir
        )
        stdout, stderr = await proc.communicate()
        
        problem_files = set()
        if stdout:
            for line in stdout.decode('utf-8').strip().split('\n'):
                if line:
                    try:
                        data = json.loads(line)
                        file_path = data.get("location", {}).get("file", "")
                        if file_path:
                            full_path = os.path.join(module_dir, file_path)
                            problem_files.add(full_path)
                    except:
                        pass
        
        if not problem_files:
            return {"fixed": False, "output": "Проблемные файлы не найдены.", "error": "Нет проблем для исправления"}
        
        logger.info(f"🔧 [GoFixer] Найдено {len(problem_files)} проблемных файлов")
        
        # 2. Запускаем gopls только для проблемных файлов
        fixed = False
        for file_path in problem_files:
            if not os.path.exists(file_path):
                continue
            
            proc = await asyncio.create_subprocess_exec(
                "gopls", "codeaction", "-kind", "quickfix", "-exec", file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                fixed = True
                logger.info(f"✅ [gopls] Исправлен: {os.path.basename(file_path)}")
            else:
                logger.info(f"⚠️ [gopls] Нет фикса для: {os.path.basename(file_path)}")
        
        if fixed:
            return {"fixed": True, "output": "Автофикс применён к проблемным файлам.", "error": None}
        else:
            return {"fixed": False, "output": "gopls не смог исправить проблемы.", "error": "Нет доступных автофиксов"}
    
    def get_summary(self, result: Dict[str, Any]) -> str:
        if result["fixed"]:
            return "✅ Автофикс Go применён (gopls) к проблемным файлам."
        else:
            return f"⚠️ Автофикс Go не смог исправить проблемы. Нужно править вручную."
