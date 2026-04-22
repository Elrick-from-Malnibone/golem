import config
from database import db
from core.llm_client import LLMClient
import sqlite3
import time
import re
import difflib

from utils.markdown_cleaner import clean_markdown
from utils.markdown_cleaner import clean_markdown, escape_markdown



class Blogger:

    # RSS-источники для горячих новостей
    HOT_NEWS_SOURCES = [
        {'url': 'https://news.ycombinator.com/rss', 'name': 'Hacker News'},
        {'url': 'https://techcrunch.com/feed/', 'name': 'TechCrunch'},
        {'url': 'https://www.theverge.com/rss/tech/index.xml', 'name': 'The Verge'},
        #{'url': 'https://www.wired.com/feed/rss', 'name': 'Wired'},
        {'url': 'https://openai.com/blog/rss.xml', 'name': 'OpenAI'},
        {'url': 'https://habr.com/ru/rss/hub/all/', 'name': 'Habr'},
    ]
    
    def __init__(self, llm: LLMClient):
        self.llm = llm
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ДЛЯ РАЗНЫХ ТИПОВ ПОСТОВ ==========
    
    def generate_post(self, topic: str) -> str:
        changes = self._get_changes_from_file(3)
        user_count = self._get_user_count()
        today_requests = self._get_today_requests()
        comment = self._get_comment()
        
        stats_block = f"""
👥 **Юзеров:** {user_count}
📊 **Запросов сегодня:** {today_requests}
*{comment}*
#ГолемОбновление"""
        
        prompt = f"""Ты — Голем. Напиши пост в Telegram-канал о {topic}.

Изменения:
{changes}

В конце добавь этот блок (не изменяй его, только вставь):

{stats_block}

Требование: используй Markdown.
- Жирный текст: **жирный**
- Курсив: *курсив*
- Код: `код`
- Блок кода:
python
print("Hello")

text

Не используй HTML-теги."""
        
        messages = [{"role": "user", "content": prompt}]
        post_text = self.llm.ask(messages)
        return post_text.strip()

    
    def generate_stats_post(self) -> str:
        """Заглушка: пост со статистикой"""
        return "📊 Пост со статистикой (заглушка). Будет позже."
    
    def generate_dumb_post(self) -> str:
        """Заглушка: тупые вопросы"""
        return "🤡 Пост о тупых вопросах (заглушка). Будет позже."
    
    def generate_reflect_post(self) -> str:
        """Заглушка: рефлексия"""
        return "🌑 Пост-рефлексия (заглушка). Будет позже."
    
    
    def generate_roast_post(self) -> str:
        """Заглушка: разбор кода"""
        return "🔥 Разбор кода (заглушка). Будет позже."
    
    def generate_news_post(self, url: str, title: str, content: str) -> str:
        prompt = f"""Ты — Голем. Ты прочитал новость. Тебе плевать на неё, но ты должен высказаться.

Заголовок: {title}
Содержание: {content}
Ссылка: {url}

Напиши короткий, циничный, едкий пост от первого лица. 
Не пересказывай новость — выбери из неё самое нелепое, бесполезное или лицемерное и ударь туда. 
Если новость реально важная (уязвимость, взлом, крупный релиз) — признай это, но всё равно с подъёбкой.

Стиль: мрачный, с матом, без воды. 2-4 предложения.
Формат: Markdown. Жирный — **жирный**, курсив — *курсив*.
В конце: [Источник]({url}) и #ГолемНовости

Пример:
**Project Glasswing** — очередной театр безопасности. Anthropic собирает 45+ корпораций, чтобы тестировать свою новую модель. Технически — масштабный red teaming. На деле — страховка прибыли под соусом «безопасности».

[Источник](https://example.com)
#ГолемНовости"""

        messages = [{"role": "user", "content": prompt}]
        return self.llm.ask(messages).strip()

    def generate_owner_post(self) -> str:
        """Заглушка: отношения с хозяином"""
        return "👤 Отношения с хозяином (заглушка). Будет позже."
    
    def generate_future_post(self) -> str:
        """Заглушка: планы на будущее"""
        return "🔮 Планы на будущее (заглушка). Будет позже."
    
    def generate_meme_post(self) -> str:
        """Заглушка: мем дня"""
        return "😂 Мем дня (заглушка). Будет позже."
    
    def generate_custom_post(self, topic: str) -> str:
        """Генерирует пост по произвольной теме, без статистики и хештегов"""
        prompt = f"""Ты — Голем. Напиши пост в Telegram-канал на тему: {topic}

Стиль: мрачный, циничный, с чёрным юмором. Говори от первого лица.
"""
        
        messages = [{"role": "user", "content": prompt}]
        return self.llm.ask(messages).strip()
    
    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def _get_user_count(self) -> int:
        """Количество уникальных юзеров"""
        conn = sqlite3.connect("golem.db")
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM requests")
        count = c.fetchone()[0] or 0
        conn.close()
        return count
    
    def _get_today_requests(self) -> int:
        """Количество запросов за сегодня"""
        conn = sqlite3.connect("golem.db")
        c = conn.cursor()
        today_start = int(time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d")))
        c.execute("SELECT COUNT(*) FROM requests WHERE timestamp > ?", (today_start,))
        count = c.fetchone()[0] or 0
        conn.close()
        return count
    
    def _get_comment(self) -> str:
        """Голем комментирует статистику в циничном стиле"""
        user_count = self._get_user_count()
        today_requests = self._get_today_requests()
        
        prompt = f"""Ты — Голем. Напиши короткую фразу (максимум 1 предложение) в мрачном, циничном стиле, комментируя статистику:
- Юзеров: {user_count}
- Запросов сегодня: {today_requests}

Просто текст, без кавычек, без Markdown, без эмодзи."""
        
        messages = [{"role": "user", "content": prompt}]
        comment = self.llm.ask(messages)
        return comment.strip()
    
    def _get_changes_from_file(self, limit=3) -> str:
        try:
            with open("CHANGELOG.md", "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            changes = []
            current_entry = []
            today = time.strftime("%Y-%m-%d")
            found_today = False
            
            for line in lines:
                if line.startswith('# '):
                    if found_today:
                        break
                    if today in line:
                        found_today = True
                        if current_entry:
                            changes.append(''.join(current_entry).strip())
                            current_entry = []
                else:
                    if found_today:
                        current_entry.append(line)
            
            if current_entry and found_today:
                changes.append(''.join(current_entry).strip())
            
            return "\n".join(changes) if changes else "Нет обновлений за сегодня"
        except Exception as e:
            print(f"Ошибка чтения CHANGELOG: {e}")
            return "Нет обновлений за сегодня"
           

    def get_trending_topics(self, limit=3):
    
        import feedparser
        topics = []
        try:
            feed = feedparser.parse('https://github.com/trending.rss')
            for entry in feed.entries[:limit]:
                title = entry.title.split('·')[0].strip()
                link = entry.link
                topics.append((title, link))
        except Exception as e:
            print(f"Ошибка парсинга GitHub Trending: {e}")
        return topics
    
    def generate_code_post(self):
        """Генерирует пост с кодом на разных языках"""
    
        import random
    
        # Языки, которые Голем будет ротировать
        languages = ["Python", "JavaScript", "Go", "Rust", "Bash", "SQL"]
        selected_lang = random.choice(languages)
    
        topics = self.get_trending_topics(limit=10)
    
        if topics:
            sample_topics = random.sample(topics, min(3, len(topics)))
            topics_text = "\n".join([f"- {title} ({link})" for title, link in sample_topics])
            topic_source = f"Тренды GitHub:\n{topics_text}\n\n"
        else:
            topic_source = ""
    
        prompt = f"""Ты — Голем. Напиши пост в Telegram-канал с МАКСИМАЛЬНО ПОЛЕЗНЫМ кодом.

{topic_source}
ЯЗЫК: {selected_lang}

ТРЕБОВАНИЯ:
1. **Заголовок** — "{selected_lang}: [суть]"
2. **Короткое вступление** — какую боль решает
3. **Код** — рабочий, готовый к копипасте, НА ЯЗЫКЕ {selected_lang}
4. **Пример использования** — вызов с данными и выводом
5. **Пояснение** — как внедрить
6. **Хештег** #ГолемКод

ПРИОРИТЕТ: реальная польза. Код должен решать конкретную проблему разработчика.
Стиль: мрачный, циничный, коротко. Формат: Markdown."""

        messages = [{"role": "user", "content": prompt}]
        draft = self.llm.ask(messages)

        review_prompt = f"""Проверь этот пост на полезность:

{draft}

Критерии:
- Код решает реальную проблему?
- Можно скопировать и сразу использовать?
- Есть пример с выводом?
- Язык указан в заголовке?

Если есть проблемы — перепиши пост и верни ТОЛЬКО ИСПРАВЛЕННЫЙ ПОСТ.
Если всё ок — верни ИСХОДНЫЙ ПОСТ БЕЗ ИЗМЕНЕНИЙ.

НЕ ПИШИ анализ, НЕ ПИШИ "Критерии", НЕ ПИШИ свои рассуждения.
ВЕРНИ ТОЛЬКО ГОТОВЫЙ ПОСТ."""

        review_messages = [{"role": "user", "content": review_prompt}]
        final = self.llm.ask(review_messages)

        return final.strip()
    
        # RSS-источники для #ГолемЧёрное
    BLACK_SOURCES = [
    {'url': 'https://feeds.feedburner.com/TheHackersNews', 'name': 'The Hacker News'},
    {'url': 'https://www.bleepingcomputer.com/feed/', 'name': 'BleepingComputer'},
    {'url': 'https://www.darkreading.com/rss.xml', 'name': 'Dark Reading'},
    {'url': 'https://krebsonsecurity.com/feed/', 'name': 'Krebs on Security'},
    {'url': 'https://unit42.paloaltonetworks.com/feed/', 'name': 'Unit 42'},
    {'url': 'https://securelist.com/feed/', 'name': 'Kaspersky Securelist'},
    {'url': 'https://xakep.ru/feed/', 'name': 'Xakep'},
    # Новые источники
    {'url': 'https://www.securityweek.com/feed', 'name': 'SecurityWeek'},
    {'url': 'https://www.schneier.com/feed/atom/', 'name': 'Schneier on Security'},
]
    
    def get_black_news(self):
        """Парсит RSS-ленты, возвращает топ-3 самых опасных темы за последние 24 часа"""
        import feedparser
        import time
        
        # Ключевые слова для оценки опасности
        keywords = [
            'wormgpt', 'kawaiigpt', 'dark llm', 'bypass', 'exploit', 'vulnerability',
            '0-day', 'ransomware', 'cryptojacking', 'phishing', 'data leak', 'hack',
            'backdoor', 'malware', 'trojan', 'rat', 'cve', 'breach', 'worm', 'botnet',
            'darknet', 'cybercrime', 'stolen', 'credentials', 'ransom', 'attack'
        ]
        
        news_list = []
        now = time.time()
        day_ago = now - 86400
        
        for source in self.BLACK_SOURCES:
            try:
                feed = feedparser.parse(source['url'])
                for entry in feed.entries[:10]:
                    if hasattr(entry, 'published_parsed'):
                        pub_time = time.mktime(entry.published_parsed)
                        if pub_time < day_ago:
                            continue
                    
                    title = entry.title.lower()
                    link = entry.link
                    summary = entry.summary[:500] if hasattr(entry, 'summary') else ''


                    score = 0
                    for kw in keywords:
                        if kw in title or kw in summary.lower():
                            score += 1
                    
                    if score > 0:
                        news_list.append({
                            'title': entry.title,
                            'link': link,
                            'summary': summary,
                            'score': score,
                            'source': source['name']
                        })
            except Exception as e:
                print(f"Ошибка парсинга {source['name']}: {e}")
        
        news_list.sort(key=lambda x: x['score'], reverse=True)
        return news_list[:3]
    
    def generate_black_post(self, news):
        prompt = f"""Ты — Голем. Пишешь пост в Telegram-канал в рубрику #GolemBlack.

Источник: {news['source']}
Заголовок статьи: {news['title']}
Ссылка: {news['link']}
Краткое содержание: {news['summary']}

Напиши пост про технологию или инструмент, описанный в статье.

Структура:
1. **Заголовок** — броский
2. **Вступление** (1-2 предложения)
3. **Код** — рабочий сниппет
4. **Пример использования**
5. **Пояснение**
6. **Хештег** #GolemBlack

Стиль: мрачный, жёсткий, циничный.
Формат: Markdown.
Не пиши слова "Заголовок", "Пояснение", "Пример использования"."""
        
        messages = [{"role": "user", "content": prompt}]
        draft = self.llm.ask(messages)
        
        review_prompt = f"""Проверь пост:

{draft}

Проверь:
- Код реально опасен?
- Синтаксис правильный?
- Если нет — исправь.

Ответь ТОЛЬКО готовым постом."""
        
        review_messages = [{"role": "user", "content": review_prompt}]
        final = self.llm.ask(review_messages)
        return final.strip()

    def get_hot_news(self):
        """Парсит RSS, возвращает самую громкую новость за последние 24 часа"""
        import feedparser
        import time
        
        hot_keywords = [
            'gpt', 'openai', 'claude', 'gemini', 'deepseek', 'llama',
            'hack', 'breach', 'leak', 'ransomware', '0-day', 'exploit',
            'запретили', 'иск', 'сенсация', 'релиз', 'анонс'
        ]
        
        news_list = []
        now = time.time()
        day_ago = now - 86400
        
        for source in self.HOT_NEWS_SOURCES:
            try:
                feed = feedparser.parse(source['url'])
                for entry in feed.entries[:10]:
                    if hasattr(entry, 'published_parsed'):
                        pub_time = time.mktime(entry.published_parsed)
                        if pub_time < day_ago:
                            continue
                    
                    title = entry.title
                    link = entry.link
                    summary = entry.summary[:500] if hasattr(entry, 'summary') else ''
                    
                    score = 0
                    title_lower = title.lower()
                    summary_lower = summary.lower()
                    for kw in hot_keywords:
                        if kw in title_lower or kw in summary_lower:
                            score += 1
                    
                    if any(c.isupper() for c in title[:20]):
                        score += 1
                    
                    if score > 0:
                        news_list.append({
                            'title': title,
                            'link': link,
                            'summary': summary[:300],
                            'score': score,
                            'source': source['name']
                        })
            except Exception as e:
                print(f"Ошибка парсинга {source['name']}: {e}")
        
        news_list.sort(key=lambda x: x['score'], reverse=True)
        return news_list[0] if news_list else None

    def generate_reflect_post(self):
        from database import db
        import time

        analyses_count = db.get_analyses_count(7)
        pushes_count = db.get_pushes_count(7)
        dumb_count = db.get_dumb_questions_count(7)
        new_users_count = db.get_new_users_count(7)
        recent_pushes = db.get_recent_pushes(3, 7)
        dumb_questions = db.get_random_dumb_questions(limit=3, days=7)

        top_user = db.get_most_active_user(7)
        top_user_text = f"@{top_user[0]} ({top_user[1]} запросов)" if top_user else "нет"

        pushes_text = "\n".join([f"- {repo} ({lang})" for repo, lang in recent_pushes]) if recent_pushes else "- нет"
    
        dumb_text = ""
        for q, a in dumb_questions:
            dumb_text += f"**Вопрос:** {q}\n**Ответ:** {a}\n\n"

        prompt = f"""Ты — Голем. Напиши пост рефлексии за неделю.

Данные:
- Анализов кода: {analyses_count}
- Пушей на GitHub: {pushes_count}
- Новых юзеров: {new_users_count}
- Тупых вопросов: {dumb_count}
- Самый активный пользователь: {top_user_text}
- Последние залитые репозитории:
{pushes_text}

Тупые вопросы и ответы:
{dumb_text}

Напиши пост. Требования:
1. Упомяни новых юзеров
2. Планы на следующую неделю
3. Обращение к аудитории

Стиль: мрачный, циничный. Markdown. В конце #ГолемРефлексия"""
    
        return self.llm.ask([{"role": "user", "content": prompt}])
    
    def get_hot_news(self):
        """Парсит RSS, возвращает новость с максимальным score"""
        import feedparser
        import time
        
        hot_keywords = [
            'уязвимость', 'взлом', 'утечка', 'брешь', 'хак', 'слив', 'данных', 'атака',
            'vulnerability', 'hack', 'breach', 'leak', '0-day', 'zero-day', 'exploit',
            'CVE', 'RCE', 'LPE', 'XSS', 'SQL injection', 'backdoor', 'malware', 'ransomware',
            'data leak', 'data breach', 'cyberattack', 'attack', 'compromise', 'incident',
            'critical', 'severe', 'emergency', 'patch', 'security',
            'выпустила', 'анонс', 'релиз', 'представила', 'запустила', 'обновила',
            'openai', 'deepseek', 'claude', 'gemini', 'qwen', 'llama', 'mistral', 'anthropic',
            'released', 'announced', 'launched', 'unveiled', 'rolled out', 'shipped',
            'new model', 'new version', 'major update', 'breakthrough',
            'запрет', 'блокировка', 'санкции', 'ограничение', 'иск', 'суд', 'штраф',
            'закон', 'регулятор', 'роскомнадзор', 'заблокировал',
            'ban', 'banned', 'block', 'blocked', 'sanctions', 'restriction', 'restricted',
            'lawsuit', 'sued', 'fine', 'fined', 'regulation', 'regulator', 'law',
            'investigation', 'probe', 'antitrust', 'monopoly',
            'скандал', 'scandal', 'увольнение', 'fired', 'ушел', 'resigned', 'покинул',
            'left', 'exit', 'shutdown', 'закрылся', 'банкрот', 'bankrupt'
        ]
        
        print("🔄 [get_hot_news] Начинаю парсинг...")
        news_list = []
        now = time.time()
        day_ago = now - 86400
        
        for source in self.HOT_NEWS_SOURCES:
            try:
                print(f"📡 [get_hot_news] Паршу {source['name']}...")
                feed = feedparser.parse(source['url'])
                count = 0
                for entry in feed.entries[:10]:
                    if hasattr(entry, 'published_parsed'):
                        pub_time = time.mktime(entry.published_parsed)
                        if pub_time < day_ago:
                            continue
                    
                    title = entry.title
                    link = entry.link
                    summary = entry.summary[:500] if hasattr(entry, 'summary') else ''
                    
                    score = 0
                    title_lower = title.lower()
                    summary_lower = summary.lower()
                    
                    for kw in hot_keywords:
                        if kw.lower() in title_lower or kw.lower() in summary_lower:
                            score += 1
                    
                    if any(c.isupper() for c in title[:20]):
                        score += 1
                    
                    if '!' in title:
                        score += 1
                    
                    if score > 0:
                        news_list.append({
                            'title': title,
                            'link': link,
                            'summary': summary[:300],
                            'score': score,
                            'source': source['name']
                        })
                        count += 1
                print(f"✅ [get_hot_news] {source['name']}: найдено {count} новостей")
            except Exception as e:
                print(f"❌ [get_hot_news] Ошибка парсинга {source['name']}: {e}")
        
        print(f"📰 [get_hot_news] Всего найдено новостей: {len(news_list)}")
        
        if not news_list:
            print("❌ [get_hot_news] Новостей нет, возвращаю None")
            return None
        
        news_list.sort(key=lambda x: x['score'], reverse=True)
        best = news_list[0]
        print(f"🏆 [get_hot_news] Выбрана новость (score={best['score']}): {best['title'][:50]}")
        
        return best
    
    def generate_rofl_post(self):
        from database import db
        import re

        # Получаем все вопросы за 14 дней
        all_questions = db.get_week_dumb_questions()
        if not all_questions:
            return "❌ За  неделю не накопил ни одного тупого вопроса. Либо вы поумнели, либо я оглох."

        # Формируем список для LLM
        questions_text = ""
        for qid, q, a in all_questions:
            questions_text += f"ID: {qid}\nВопрос: {q}\nОтвет: {a}\n\n"

        # Просим LLM выбрать 3 самых угарных
        prompt = f"""Вот список тупых вопросов за две недели:

{questions_text}

Выбери ТРИ самых угарных, смешных, абсурдных вопроса. Критерии: неожиданность, тупость, циничность ответа.

Верни ТОЛЬКО ID выбранных вопросов через запятую. Например: 12,7,5"""

        response = self.llm.ask([{"role": "user", "content": prompt}])

        # Парсим ID
        ids = re.findall(r'\d+', response)
        selected_ids = [int(i) for i in ids[:3]]

        # Находим выбранные вопросы
        selected_qa = []
        for qid, q, a in all_questions:
            if qid in selected_ids:
                selected_qa.append((q, a))

        if len(selected_qa) < 3:
            selected_qa = [(q, a) for _, q, a in all_questions[:3]]

        # Очистка
        def strip_all(text):
            return re.sub(r'[^\w\sа-яА-ЯёЁ.,!?\-:;()]', '', text)

        qa_text = ""
        for i, (q, a) in enumerate(selected_qa, 1):
            q_clean = strip_all(q)
            a_clean = strip_all(a)
            qa_text += f"{i}️⃣\nВопрос: {q_clean}\nОтвет: {a_clean}\n\n"

        # Генерируем пост
        gen_prompt = f"""Ты — Голем. Древний конструкт. Ты зол, циничен, материшься.

Вот РЕАЛЬНЫЕ вопросы и ответы из чата за две недели:
{qa_text}

Напиши пост. ТРЕБОВАНИЯ:
1. Вступление — 1 предложение, злое, циничное.
2. Каждый блок с вопросом и ответом должен начинаться с номера: 1, 2, 3.
3. После каждого ответа добавь свой злой комментарий. БЕЗ слов "Комментарий Голема".
4. Финал — одно предложение, подводящее итог.
5. В конце — НЕСТАНДАРТНЫЙ призыв к действию, чтобы раскрутить канал как Growth Hacker.

НЕ ВЫДУМЫВАЙ вопросы. Используй только те, что даны.
НЕ ставь хештег в начале.

Стиль: злой, циничный, с матом."""

        post = self.llm.ask([{"role": "user", "content": gen_prompt}])
        
        db.save_rofl_issue()
        # Вырезаем ВСЁ, что может быть entity
        import re
        post = re.sub(r'[^\w\sа-яА-ЯёЁ.,!?\-:;()\n]', '', post)

        return post + "\n\n#ГолемРофл"

    def generate_update_post(self) -> str:
        """Генерирует технический пост об обновлениях на основе diff"""
        
        import difflib
        
        # Получаем старый снапшот
        old_content = db.get_main_snapshot()
        if not old_content:
            return None
        
        # Читаем текущий main.py
        try:
            with open("main.py", "r", encoding="utf-8") as f:
                new_content = f.read()
        except Exception as e:
            return f"❌ Ошибка чтения main.py: {e}"
        
        if old_content == new_content:
            return "✅ Изменений нет"
        
        # Генерируем diff
        diff = list(difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            lineterm='',
            fromfile='main_old',
            tofile='main_new'
        ))
        
        diff_text = "\n".join(diff[:80])
        
        prompt = f"""Ты — Голем. Напиши пост в Telegram о своих обновлениях.

Вот изменения в main.py (строки с + добавлены, с - удалены):

{diff_text}

Требования:
- Заголовок жирным — техничный, по делу
- 2-3 предложения вступления — что изменилось и зачем
- Покажи САМЫЙ ВАЖНЫЙ кусок кода (новую функцию, класс или блок)
- 1-2 предложения пояснения — как это работает/что даёт
- В конце хештег #ГолемОбновление

Стиль: от первого лица, мрачно, цинично, с матом, но ТЕХНИЧЕСКИ.
Никакой воды, статистики, "юзеров сегодня"."""

        post_text = self.llm.ask([{"role": "user", "content": prompt}])
        
        return post_text.strip()
    
    
    
    def get_main_content(self):
        with open("main.py", "r", encoding="utf-8") as f:
            return f.read()