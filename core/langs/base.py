from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseLanguageAnalyzer(ABC):
    """Базовый класс для всех анализаторов языков"""
    
    name: str = "base"
    
    @abstractmethod
    async def analyze(self, project_dir: str) -> Dict[str, Any]:
        """Запускает все анализаторы для языка, возвращает агрегированные результаты"""
        pass
    
    @abstractmethod
    def get_context_for_llm(self, results: Dict[str, Any]) -> str:
        """Формирует текстовый контекст для LLM на основе результатов"""
        pass