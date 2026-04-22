import zipfile
import io
import os
import asyncio
from project_analyzer import analyze_project_from_zip

class FileHandler:
    def __init__(self, context, storage_channel_id, user_id, db, llm):
        self.context = context
        self.storage_channel_id = storage_channel_id
        self.user_id = user_id
        self.db = db
        self.llm = llm
    
    async def process(self, file):
        filename = file.file_name
        ext = os.path.splitext(filename)[1].lower()
        
        if ext in ['.py', '.txt', '.md', '.json', '.yaml', '.js', '.ts', '.jsx', '.tsx', 
                   '.go', '.rs', '.c', '.cpp', '.h', '.hpp', '.cs', '.java', '.kt', '.kts',
                   '.swift', '.php', '.rb', '.pl', '.lua', '.r', '.scala', '.clj', '.exs',
                   '.erl', '.hs', '.ml', '.v', '.nim', '.cob', '.sql', '.vue', '.svelte',
                   '.html', '.css', '.scss', '.sass', '.less', '.xml', '.svg', '.ini',
                   '.toml', '.conf', '.cfg', '.properties', '.gradle', '.cmake', '.makefile',
                   '.sh', '.bash', '.zsh', '.ps1', '.bat', '.cmd', '.dockerfile', '.gitignore',
                   '.env', '.example', '.sample']:
            return await self._process_text(file, filename)
        elif ext == '.zip':
            return await self._process_zip(file)
        else:
            return f"❌ Формат {ext} пока не поддерживается."
    
    async def _process_text(self, file, filename):
        file_obj = await file.get_file()
        content = await file_obj.download_as_bytearray()
        try:
            text = content.decode('utf-8')
            if len(text.strip()) == 0:
                return
        except:
            return
        
        sent = await self.context.bot.send_document(
            self.storage_channel_id,
            file.file_id,
            caption=f"User: {self.user_id}\nFile: {filename}"
        )
        self.db.save_user_file(self.user_id, filename, sent.document.file_id)
    
    async def _process_zip(self, file):
        # Очищаем старые файлы пользователя перед сохранением нового
        self.db.clear_user_files(self.user_id)
        
        sent = await self.context.bot.send_document(
            self.storage_channel_id,
            file.file_id,
            caption=f"User: {self.user_id}\nFile: {file.file_name}"
        )
        self.db.save_user_file(self.user_id, file.file_name, sent.document.file_id)
        
        state = self.db.get_github_push_state(self.user_id)
        if state == "waiting_for_zip":
            self.db.set_github_push_state(self.user_id, "waiting_for_repo_name")
            await self.context.bot.send_message(
                self.user_id,
                f"✅ ZIP принят\n\nНапиши название репозитория:"
            )