# core/code_analyzer.py
import json
import subprocess
import asyncio
import os
import logging
from typing import Dict, List, Any

# Настраиваем логгер
logger = logging.getLogger(__name__)


async def run_command(cmd: List[str], timeout: int = 120) -> Dict[str, Any]:
    """Асинхронный запуск команды с таймаутом"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "success": proc.returncode == 0,
            "stdout": stdout.decode('utf-8', errors='ignore'),
            "stderr": stderr.decode('utf-8', errors='ignore'),
            "returncode": proc.returncode
        }
    except asyncio.TimeoutError:
        return {"error": f"Timeout after {timeout}s", "success": False, "results": []}
    except Exception as e:
        return {"error": str(e), "success": False, "results": []}


def find_requirements_files(project_dir: str) -> List[str]:
    """Находит все файлы зависимостей в проекте"""
    req_files = []
    for root, dirs, files in os.walk(project_dir):
        # Пропускаем служебные директории
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'venv', 'env', '.venv', 'node_modules']]
        for f in files:
            if f in ['requirements.txt', 'pyproject.toml', 'setup.py', 'Pipfile', 'Pipfile.lock']:
                req_files.append(os.path.join(root, f))
    return req_files


async def run_bandit(project_dir: str) -> Dict[str, Any]:
    """Запуск Bandit для поиска уязвимостей безопасности"""
    logger.info(f"🔧 [Bandit] Запуск анализа...")
    
    result = await run_command([
        "bandit", "-r", project_dir, "-f", "json", "-q", "-ll"
    ], timeout=180)
    
    if result.get("success") or result.get("stdout"):
        try:
            data = json.loads(result["stdout"])
            issues = data.get("results", [])
            logger.info(f"✅ [Bandit] Найдено проблем: {len(issues)}")
            return {
                "results": issues,
                "metrics": data.get("metrics", {}),
                "error": None
            }
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ [Bandit] Ошибка парсинга JSON: {str(e)[:50]}")
            return {"results": [], "error": "Failed to parse JSON"}
    
    # Проверяем, может bandit не установлен
    if "not found" in result.get("error", "") or "No such file" in result.get("error", ""):
        logger.warning("⚠️ [Bandit] Утилита не установлена. Установи: pip install bandit")
        return {"results": [], "error": "Bandit not installed"}
    
    logger.warning(f"⚠️ [Bandit] Ошибка: {result.get('error', 'Unknown')[:100]}")
    return {"results": [], "error": result.get("error") or result.get("stderr")}


async def run_ruff(project_dir: str) -> Dict[str, Any]:
    """Запуск Ruff для проверки стиля и багов"""
    logger.info(f"🔧 [Ruff] Запуск анализа...")
    
    # Убрал --select для полного анализа
    result = await run_command([
        "ruff", "check", project_dir, "--output-format", "json"
    ], timeout=120)
    
    # Ruff возвращает код 1 если найдены проблемы — это нормально
    if result.get("stdout"):
        try:
            data = json.loads(result["stdout"])
            issues = []
            for item in data:
                issues.append({
                    "filename": item.get("filename"),
                    "line": item.get("location", {}).get("row"),
                    "column": item.get("location", {}).get("column"),
                    "message": item.get("message"),
                    "code": item.get("code"),
                    "severity": "error" if item.get("code", "").startswith(("E", "F")) else "warning"
                })
            logger.info(f"✅ [Ruff] Найдено проблем: {len(issues)}")
            return {"results": issues, "error": None}
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ [Ruff] Ошибка парсинга JSON: {str(e)[:50]}")
            return {"results": [], "error": "Failed to parse JSON"}
    
    # Проверяем, может ruff не установлен
    if "not found" in result.get("error", "") or "No such file" in result.get("error", ""):
        logger.warning("⚠️ [Ruff] Утилита не установлена. Установи: pip install ruff")
        return {"results": [], "error": "Ruff not installed"}
    
    # Если нет stdout и нет ошибки — значит проблем не найдено
    if result.get("returncode") == 0:
        logger.info(f"✅ [Ruff] Проблем не найдено")
        return {"results": [], "error": None}
    
    logger.warning(f"⚠️ [Ruff] Ошибка: {result.get('error', 'Unknown')[:100]}")
    return {"results": [], "error": result.get("error") or result.get("stderr")}


async def run_pip_audit(project_dir: str) -> Dict[str, Any]:
    """Запуск pip-audit для проверки уязвимых зависимостей"""
    logger.info(f"🔧 [pip-audit] Поиск файлов зависимостей...")
    
    req_files = find_requirements_files(project_dir)
    
    if not req_files:
        logger.info(f"ℹ️ [pip-audit] Файлы зависимостей не найдены")
        return {"vulnerabilities": [], "error": None}
    
    logger.info(f"🔧 [pip-audit] Найдено файлов: {len(req_files)}")
    
    vulnerabilities = []
    
    for req_file in req_files:
        logger.info(f"🔧 [pip-audit] Проверка {os.path.basename(req_file)}...")
        
        cmd = ["pip-audit", "-r", req_file, "-f", "json", "--no-deps"]
        result = await run_command(cmd, timeout=120)
        
        if result.get("stdout"):
            try:
                data = json.loads(result["stdout"])
                for vuln in data.get("dependencies", []):
                    for v in vuln.get("vulns", []):
                        vulnerabilities.append({
                            "name": vuln.get("name"),
                            "version": vuln.get("version"),
                            "description": v.get("description", ""),
                            "severity": v.get("severity", "UNKNOWN"),
                            "fix_versions": v.get("fix_versions", [])
                        })
            except json.JSONDecodeError:
                logger.warning(f"⚠️ [pip-audit] Ошибка парсинга JSON для {req_file}")
                continue
    
    # Убираем дубликаты
    unique_vulns = []
    seen = set()
    for v in vulnerabilities:
        key = f"{v.get('name')}_{v.get('description')}"
        if key not in seen:
            seen.add(key)
            unique_vulns.append(v)
    
    logger.info(f"✅ [pip-audit] Найдено уязвимостей: {len(unique_vulns)}")
    return {"vulnerabilities": unique_vulns, "error": None}


def extract_code_context(
    project_dir: str, 
    bandit: Dict, 
    ruff: Dict, 
    max_size: int = 6000
) -> str:
    """
    Извлекает ТОЛЬКО проблемные строки кода с контекстом.
    Не обрезает случайные куски файлов!
    """
    snippets = []
    total_size = 0
    seen_files = set()
    
    # Собираем все проблемные места с приоритетами
    problem_locations = []
    
    # Bandit — высокий приоритет
    for issue in bandit.get("results", []):
        if issue.get("issue_severity") in ["HIGH", "MEDIUM"]:
            filename = issue.get("filename", "")
            line = issue.get("line_number", 0)
            if filename and line:
                problem_locations.append({
                    "filename": filename,
                    "line": line,
                    "priority": 1,
                    "source": "Bandit",
                    "message": issue.get("issue_text", "")[:50]
                })
    
    # Ruff — ошибки E и F
    for issue in ruff.get("results", []):
        code = issue.get("code", "")
        if code.startswith(("E", "F")):
            filename = issue.get("filename", "")
            line = issue.get("line", 0)
            if filename and line:
                problem_locations.append({
                    "filename": filename,
                    "line": line,
                    "priority": 2,
                    "source": "Ruff",
                    "message": issue.get("message", "")[:50]
                })
    
    
    # Сортируем по приоритету и убираем дубликаты файлов
    problem_locations.sort(key=lambda x: x["priority"])
    
    for loc in problem_locations:
        full_path = loc["filename"]
        if not os.path.isabs(full_path):
            full_path = os.path.join(project_dir, full_path)
        
        if not os.path.exists(full_path):
            continue
        
        # Показываем каждый файл только один раз
        file_key = os.path.basename(full_path)
        if file_key in seen_files:
            continue
        seen_files.add(file_key)
        
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            line_num = loc["line"]
            start = max(0, line_num - 4)
            end = min(len(lines), line_num + 3)
            
            # Формируем сниппет с номерами строк
            snippet_lines = []
            for i in range(start, end):
                prefix = "→ " if i == line_num - 1 else "  "
                snippet_lines.append(f"{prefix}{i+1:4d} | {lines[i].rstrip()}")
            
            snippet = "\n".join(snippet_lines)
            
            # Добавляем заголовок с информацией о проблеме
            header = f"### {os.path.basename(full_path)} (строка {line_num})\n"
            header += f"*{loc['source']}: {loc['message']}*\n"
            
            snippets.append(header + f"```python\n{snippet}\n```")
            total_size += len(snippet)
            
            if total_size > max_size:
                snippets.append("\n*... (остальные проблемы пропущены из-за лимита)*")
                break
                
        except Exception as e:
            logger.warning(f"⚠️ Не удалось прочитать {full_path}: {str(e)[:50]}")
            continue
    
    if not snippets:
        return ""
    
    return "\n\n".join(snippets)


def aggregate_analysis_results(
    bandit: Dict, 
    ruff: Dict, 
    pip_audit: Dict,
    project_dir: str
) -> str:
    """
    Агрегирует результаты всех анализаторов в компактный отчёт для LLM.
    """
    report_lines = []
    
    # === ОСНОВНЫЕ ФАЙЛЫ ===
    main_files = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'venv', 'env']]
        for f in files:
            if f.endswith('.py') and ('main' in f.lower() or 'app' in f.lower() or 'bot' in f.lower()):
                main_files.append(os.path.relpath(os.path.join(root, f), project_dir))
    
    if main_files:
        report_lines.append(f"**📂 Главные файлы:** {', '.join(main_files[:5])}")
    
    # === BANDIT ===
    bandit_results = bandit.get("results", [])
    if bandit_results:
        high_severity = [r for r in bandit_results if r.get("issue_severity") in ["HIGH", "MEDIUM"]]
        medium_severity = [r for r in bandit_results if r.get("issue_severity") == "LOW"]
        
        if high_severity:
            report_lines.append(f"\n**🔴 КРИТИЧЕСКИЕ УЯЗВИМОСТИ ({len(high_severity)}):**")
            for r in high_severity[:5]:
                filename = os.path.basename(r.get("filename", "?"))
                line = r.get("line_number", "?")
                issue = r.get("issue_text", "")[:100]
                report_lines.append(f"  • {filename}:{line} — {issue}")
        
        if medium_severity and len(report_lines) < 20:
            report_lines.append(f"\n**🟡 Предупреждения Bandit ({len(medium_severity)}):**")
            for r in medium_severity[:3]:
                filename = os.path.basename(r.get("filename", "?"))
                issue = r.get("issue_text", "")[:80]
                report_lines.append(f"  • {filename}: {issue}")
    
    # === RUFF ===
    ruff_results = ruff.get("results", [])
    if ruff_results:
        # Группируем по типам ошибок
        error_types = {}
        for r in ruff_results:
            code = r.get("code", "?")
            error_types[code] = error_types.get(code, 0) + 1
        
        # Самые частые ошибки
        top_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]
        
        critical_ruff = [r for r in ruff_results if r.get("code", "").startswith(("E", "F"))]
        
        if critical_ruff:
            report_lines.append(f"\n**⚠️ ОШИБКИ RUFF ({len(critical_ruff)}):**")
            for r in critical_ruff[:7]:
                filename = os.path.basename(r.get("filename", "?"))
                line = r.get("line", "?")
                msg = r.get("message", "")[:80]
                code = r.get("code", "")
                report_lines.append(f"  • {filename}:{line} — [{code}] {msg}")
        
        if top_errors:
            report_lines.append(f"\n**📊 Частые проблемы Ruff:**")
            for code, count in top_errors:
                report_lines.append(f"  • {code}: {count} раз")
    
    
    # === PIP-AUDIT ===
    vulnerabilities = pip_audit.get("vulnerabilities", [])
    if vulnerabilities:
        report_lines.append(f"\n**📦 УЯЗВИМЫЕ ЗАВИСИМОСТИ ({len(vulnerabilities)}):**")
        seen = set()
        for v in vulnerabilities[:5]:
            name = v.get("name")
            severity = v.get("severity", "?")
            if name not in seen:
                seen.add(name)
                desc = v.get("description", "")[:80]
                report_lines.append(f"  • {name} [{severity}]: {desc}")
    
    # === ИТОГО ===
    if len(report_lines) == 0 or (len(report_lines) == 1 and main_files):
        report_lines.append("\n✅ **Статические анализаторы не нашли критических проблем.**")
    
    total_issues = len(bandit_results) + len(ruff_results) 
    report_lines.append(f"\n---\n**📊 ВСЕГО ПРОБЛЕМ:** {total_issues}")
    report_lines.append(f"Bandit: {len(bandit_results)} | Ruff: {len(ruff_results)} | pip-audit: {len(vulnerabilities)}")
    
    return "\n".join(report_lines)


async def run_full_analysis(project_dir: str) -> Dict[str, Any]:
    """
    Основная функция — запускает все анализаторы и возвращает агрегированный результат.
    """
    logger.info(f"\n{'='*50}")
    logger.info(f"🚀 ЗАПУСК ПОЛНОГО АНАЛИЗА ПРОЕКТА")
    logger.info(f"📁 Директория: {project_dir}")
    logger.info(f"{'='*50}")
    
    # Параллельный запуск всех утилит
    bandit_task = run_bandit(project_dir)
    ruff_task = run_ruff(project_dir)
    pip_audit_task = run_pip_audit(project_dir)
    
    bandit, ruff,pip_audit = await asyncio.gather(
        bandit_task, ruff_task,pip_audit_task,
        return_exceptions=True
    )
    
    # Обрабатываем возможные исключения
    if isinstance(bandit, Exception):
        logger.error(f"❌ Bandit упал: {str(bandit)}")
        bandit = {"results": [], "error": str(bandit)}
    if isinstance(ruff, Exception):
        logger.error(f"❌ Ruff упал: {str(ruff)}")
        ruff = {"results": [], "error": str(ruff)}
    if isinstance(pip_audit, Exception):
        logger.error(f"❌ pip-audit упал: {str(pip_audit)}")
        pip_audit = {"vulnerabilities": [], "error": str(pip_audit)}
    
    # Логируем итоги
    logger.info(f"\n📈 РЕЗУЛЬТАТЫ АНАЛИЗА:")
    logger.info(f"   🔴 Bandit: {len(bandit.get('results', []))} проблем")
    logger.info(f"   ⚠️ Ruff: {len(ruff.get('results', []))} проблем")
    logger.info(f"   📦 pip-audit: {len(pip_audit.get('vulnerabilities', []))} уязвимостей")
    
    # Агрегируем отчёт для LLM
    aggregated_report = aggregate_analysis_results(bandit, ruff,pip_audit, project_dir)
    
    # Извлекаем код ТОЛЬКО проблемных мест
    code_context = extract_code_context(project_dir, bandit, ruff)
    
    logger.info(f"📝 Агрегированный отчёт: {len(aggregated_report)} символов")
    logger.info(f"📝 Проблемный код: {len(code_context)} символов")
    logger.info(f"{'='*50}\n")
    
    return {
        "bandit": bandit,
        "ruff": ruff,
        "pip_audit": pip_audit,
        "aggregated_report": aggregated_report,
        "code_context": code_context,
        "affected_files": [],  # Оставляем для обратной совместимости
        "total_issues": {
            "bandit": len(bandit.get("results", [])),
            "ruff": len(ruff.get("results", [])),
            "pip_audit": len(pip_audit.get("vulnerabilities", []))
        }
    }