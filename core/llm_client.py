import requests
import json
import asyncio
import config
import logging
from typing import AsyncGenerator, Tuple

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.api_key = config.DEEPSEEK_API_KEY
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.model = "deepseek-chat"

    async def astream(self, messages: list) -> Tuple[AsyncGenerator[str, None], int]:
        messages.insert(0, {"role": "system", "content": config.SYSTEM_PROMPT})
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "max_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        try:
            loop = asyncio.get_running_loop()
            
            def make_request():
                return requests.post(
                    self.url,
                    headers=headers,
                    json=data,
                    stream=True,
                    timeout=180
                )

            response = await loop.run_in_executor(None, make_request)
            response.raise_for_status()

            total_tokens = 0
            line_buffer = ""

            async def generate():
                nonlocal line_buffer, total_tokens
                for line in response.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]
                    if line_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            line_buffer += delta
                            if '\n' in line_buffer:
                                lines = line_buffer.split('\n')
                                for l in lines[:-1]:
                                    yield l + '\n'
                                line_buffer = lines[-1]
                        
                        if chunk.get("usage"):
                            total_tokens = chunk["usage"]["total_tokens"]
                    except:
                        continue
                
                if line_buffer:
                    yield line_buffer
            
            return generate(), total_tokens

        except Exception as e:
            logger.error(f"DeepSeek streaming error: {e}")
            async def error_gen():
                yield f"\n\n❌ Ошибка: {str(e)}"
            return error_gen(), 0
        
    def ask(self, messages: list) -> str:
        """Только ответ, без токенов (для blogger, комментариев, кэша)"""
        messages.insert(0, {"role": "system", "content": config.SYSTEM_PROMPT})
        
        try:
            response = requests.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 2000,
                    "temperature": 0.7
                },
                timeout=90
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"DeepSeek ask error: {e}")
            return f"Ошибка: {str(e)}"

    def ask_with_tokens(self, messages: list) -> tuple:
        """Возвращает (ответ, total_tokens) для запросов юзеров"""
        messages.insert(0, {"role": "system", "content": config.SYSTEM_PROMPT})
        
        try:
            response = requests.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 2000,
                    "temperature": 0.7
                },
                timeout=90
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            total_tokens = result["usage"]["total_tokens"]
            return content, total_tokens
        except Exception as e:
            logger.error(f"DeepSeek ask_with_tokens error: {e}")
            return f"Ошибка: {str(e)}", 0