# core/langs/go.py
import asyncio
import json
import logging
import os
import re
from typing import Dict, Any
from core.langs.base import BaseLanguageAnalyzer

logger = logging.getLogger(__name__)


def find_go_module_dir(project_dir: str) -> str:
    """Находит папку с go.mod. Если нет — возвращает исходную папку."""
    for root, dirs, files in os.walk(project_dir):
        if "go.mod" in files:
            return root
    return project_dir


class GoAnalyzer(BaseLanguageAnalyzer):
    name = "Go"
    
    async def analyze(self, project_dir: str) -> Dict[str, Any]:
        logger.info(f"🦦 [GoAnalyzer] Запуск анализа {project_dir}")

        # Находим папку с go.mod
        module_dir = find_go_module_dir(project_dir)

        # Сначала подготавливаем зависимости
        if os.path.exists(os.path.join(module_dir, "go.mod")):
            proc_tidy = await asyncio.create_subprocess_exec(
                "go", "mod", "tidy",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=module_dir
            )
            await proc_tidy.communicate()
            
            proc_dl = await asyncio.create_subprocess_exec(
                "go", "mod", "download",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=module_dir
            )
            await proc_dl.communicate()
        
        # Запускаем golangci-lint и gosec параллельно
        lint_task = self._run_staticcheck(module_dir)
        vuln_task = self._run_gosec(module_dir)
        
        lint_result, vuln_result = await asyncio.gather(lint_task, vuln_task)
        
        return {
            "language": self.name,
            "staticcheck": lint_result,
            "gosec": vuln_result,
            "total_issues": {
                "staticcheck": len(lint_result.get("issues", [])),
                "gosec": len(vuln_result.get("issues", []))
            }
        }
    
    async def _run_staticcheck(self, module_dir: str) -> Dict[str, Any]:
        """Запускает staticcheck с JSON выводом"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "staticcheck", "-f", "json", "./...",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=module_dir
            )
            stdout, stderr = await proc.communicate()
            logger.info(f"📤 [staticcheck] stderr: {stderr[:500].decode() if stderr else 'empty'}")
            
            issues = []
            if stdout:
                for line in stdout.decode('utf-8').strip().split('\n'):
                    if line:
                        try:
                            data = json.loads(line)
                            issues.append({
                                "file": data.get("location", {}).get("file", ""),
                                "line": data.get("location", {}).get("line", 0),
                                "message": data.get("message", ""),
                                "code": data.get("code", ""),
                                "severity": data.get("severity", "warning")
                            })
                        except json.JSONDecodeError:
                            pass
            
            logger.info(f"✅ [staticcheck] Найдено проблем: {len(issues)}")
            return {"issues": issues, "error": None}
            
        except Exception as e:
            logger.warning(f"⚠️ [staticcheck] Ошибка: {str(e)[:100]}")
            return {"issues": [], "error": str(e)}
    
    async def _run_gosec(self, module_dir: str) -> Dict[str, Any]:
        """Запускает gosec с JSON выводом"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "gosec", "-fmt=json", "./...",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=module_dir
            )
            stdout, stderr = await proc.communicate()
            logger.info(f"📤 [gosec] stderr: {stderr[:500] if stderr else 'empty'}")
            
            issues = []
            if stdout:
                try:
                    data = json.loads(stdout.decode('utf-8'))
                    for issue in data.get("Issues", []):
                        issues.append({
                            "file": issue.get("file", ""),
                            "line": issue.get("line", 0),
                            "message": issue.get("details", ""),
                            "rule": issue.get("rule_id", ""),
                            "severity": issue.get("severity", "MEDIUM")
                        })
                except json.JSONDecodeError:
                    pass
            
            logger.info(f"✅ [gosec] Найдено проблем: {len(issues)}")
            return {"issues": issues, "error": None}
            
        except Exception as e:
            logger.warning(f"⚠️ [gosec] Ошибка: {str(e)[:100]}")
            return {"issues": [], "error": str(e)}
    
    def get_context_for_llm(self, results: Dict[str, Any]) -> str:
        total = results["total_issues"]
        return f"""Go-проект.
staticcheck (статический анализ): {total['staticcheck']} проблем
gosec (безопасность): {total['gosec']} проблем"""