import asyncio
import logging
from typing import Dict, Any

from core.langs.base import BaseLanguageAnalyzer
from core.code_analyzer import run_bandit, run_ruff, run_pip_audit

logger = logging.getLogger(__name__)


class PythonAnalyzer(BaseLanguageAnalyzer):
    name = "Python"
    
    async def analyze(self, project_dir: str) -> Dict[str, Any]:
        """Запускает все Python-анализаторы параллельно"""
        logger.info(f"🐍 [PythonAnalyzer] Запуск анализа {project_dir}")
        
        bandit_task = run_bandit(project_dir)
        ruff_task = run_ruff(project_dir)
        pip_audit_task = run_pip_audit(project_dir)
        
        bandit, ruff, pip_audit = await asyncio.gather(
            bandit_task, ruff_task,pip_audit_task,
            return_exceptions=True
        )
        
        # Обработка исключений
        if isinstance(bandit, Exception):
            bandit = {"results": [], "error": str(bandit)}
        if isinstance(ruff, Exception):
            ruff = {"results": [], "error": str(ruff)}
        if isinstance(pip_audit, Exception):
            pip_audit = {"vulnerabilities": [], "error": str(pip_audit)}
        
        return {
            "language": "Python",
            "bandit": bandit,
            "ruff": ruff,
            "pip_audit": pip_audit,
            "total_issues": {
                "bandit": len(bandit.get("results", [])),
                "ruff": len(ruff.get("results", [])),
                "pip_audit": len(pip_audit.get("vulnerabilities", []))
            }
        }
    
    def get_context_for_llm(self, results: Dict[str, Any]) -> str:
        """Формирует описание результатов для LLM"""
        total = results["total_issues"]
        return f"""Python-проект.
Bandit (безопасность): {total['bandit']} проблем
Ruff (стиль/баги): {total['ruff']} проблем
pip-audit (зависимости): {total['pip_audit']} уязвимостей"""