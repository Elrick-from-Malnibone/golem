from .python import PythonAnalyzer
from .go import GoAnalyzer

LANGUAGE_ANALYZERS = {
    "Python": PythonAnalyzer(),
    "Go": GoAnalyzer(),
}

def get_analyzer(language: str):
    return LANGUAGE_ANALYZERS.get(language)