import asyncio
import aiohttp
import sqlite3
from datetime import datetime, timedelta
import pytz
from telegram import Bot
import gitlab
import os
from dotenv import load_dotenv
import logging
import argparse
import re
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_datetime(date_str):
    """
    Универсальный парсер дат GitLab, поддерживающий различные форматы
    """
    # Предварительная обработка для формата с миллисекундами и часовым поясом с двоеточием
    if re.search(r'\.\d+\+\d+:\d+', date_str):
        # Конвертируем "+02:00" в "+0200" для совместимости со strptime
        date_str = re.sub(r'(\+\d+):(\d+)', r'\1\2', date_str)
    
    # Попытка парсинга в разных форматах
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",  # С миллисекундами и часовым поясом
        "%Y-%m-%dT%H:%M:%S%z",      # Без миллисекунд, с часовым поясом
        "%Y-%m-%dT%H:%M:%S.%fZ",    # С миллисекундами, UTC (Z)
        "%Y-%m-%dT%H:%M:%SZ"        # Без миллисекунд, UTC (Z)
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Если все форматы не подошли, пробуем удалить двоеточие в часовом поясе
    try:
        # Если в строке есть часовой пояс с двоеточием
        if "+" in date_str or "-" in date_str:
            # Находим и удаляем двоеточие в часовом поясе
            modified_str = re.sub(r'([+-])(\d{2}):(\d{2})', r'\1\2\3', date_str)
            return datetime.strptime(modified_str, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        pass
    
    # Если ничего не сработало, вызываем исключение
    raise ValueError(f"Не удалось распознать формат даты: {date_str}")

def parse_args():
    parser = argparse.ArgumentParser(description='Мониторинг коммитов GitLab')
    parser.add_argument('--repo', type=str, help='Конкретный репозиторий для проверки')
    parser.add_argument('--since', type=str, help='Время начала проверки (формат: YYYY-MM-DD HH:MM)')
    parser.add_argument('--hours', type=int, default=1, help='Количество часов назад для проверки (по умолчанию: 1)')
    parser.add_argument('--debug', action='store_true', help='Включить режим отладки с расширенным выводом')
    parser.add_argument('--max-files', type=int, default=5, help='Максимальное количество файлов для анализа (по умолчанию: 5)')
    parser.add_argument('--max-file-size', type=int, default=10000, help='Максимальный размер файла в символах (по умолчанию: 10000)')
    return parser.parse_args()

class DBManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS commits (
                    project TEXT,
                    commit_id TEXT,
                    processed INTEGER DEFAULT 0,
                    timestamp TIMESTAMP,
                    PRIMARY KEY (project, commit_id)
                 )''')
        conn.commit()
        conn.close()
        logger.info("БД инициализирована")
    
    def is_processed(self, project, commit_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT processed FROM commits WHERE project = ? AND commit_id = ?", (project, commit_id))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    
    def mark_processed(self, project, commit_id, timestamp, processed=1):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO commits (project, commit_id, processed, timestamp) VALUES (?, ?, ?, ?)",
                (project, commit_id, processed, timestamp))
        conn.commit()
        conn.close()
        logger.debug(f"Коммит {commit_id[:7]} в {project} помечен как обработанный")

class GitLabClient:
    def __init__(self, gitlab_url, token):
        self.client = gitlab.Gitlab(gitlab_url, private_token=token)
        logger.info("GitLab клиент инициализирован")
    
    def get_project(self, project_path):
        try:
            return self.client.projects.get(project_path)
        except gitlab.exceptions.GitlabGetError as e:
            logger.error(f"Ошибка доступа к проекту {project_path}: {e}")
            return None
    
    async def fetch_recent_commits(self, project_path, start_time, db_manager):
        project = self.get_project(project_path)
        if not project:
            return []
        
        try:
            commits = project.commits.list(all=False, per_page=20)  # Увеличим количество проверяемых коммитов
            new_commits = []
            
            for commit in commits:
                try:
                    commit_time = parse_datetime(commit.created_at)
                    logger.debug(f"Коммит {commit.id[:7]} в {project_path}, время: {commit_time}")
                    
                    if commit_time > start_time and db_manager.is_processed(project_path, commit.id) is None:
                        new_commits.append(commit)
                        logger.debug(f"Новый коммит {commit.id[:7]} в {project_path}")
                except ValueError as e:
                    logger.error(f"Ошибка парсинга времени для коммита {commit.id[:7]}: {e}")
                    continue
            
            logger.info(f"Найдено в {project_path}: {len(new_commits)} новых коммитов")
            return new_commits
        except Exception as e:
            logger.error(f"Ошибка получения коммитов {project_path}: {e}")
            return []
    
    async def get_file_content(self, project, file_path, commit_id=None):
        try:
            if commit_id:
                content = project.files.get(file_path=file_path, ref=commit_id).decode()
            else:
                content = project.files.get(file_path=file_path).decode()
            return content
        except gitlab.exceptions.GitlabGetError:
            logger.debug(f"Файл {file_path} не найден")
            return None
        except Exception as e:
            logger.error(f"Ошибка получения содержимого {file_path}: {e}")
            return None
    
    async def get_commit_details(self, project_path, commit_id, max_files=5, max_file_size=10000, debug_mode=False):
        project = self.get_project(project_path)
        if not project:
            return None, []
        
        try:
            commit = project.commits.get(commit_id)
            diff = commit.diff(get_all=True)
            
            if debug_mode:
                logger.info(f"[DEBUG] Найдено {len(diff)} измененных файлов в коммите {commit_id[:7]}")
            
            # Сортируем файлы по размеру диффа (предполагаем, что более важные изменения больше)
            diff.sort(key=lambda x: len(x.get('diff', '')), reverse=True)
            
            # Ограничиваем количество файлов для анализа
            diff = diff[:max_files]
            
            modified_files = []
            for d in diff:
                if d.get('new_path') and d.get('old_path'):
                    file_path = d.get('new_path')
                    
                    if debug_mode:
                        logger.info(f"[DEBUG] Получение содержимого файла: {file_path}")
                    
                    old_content = await self.get_file_content(project, d.get('old_path'), commit.parent_ids[0] if commit.parent_ids else None)
                    new_content = await self.get_file_content(project, file_path, commit_id)
                    
                    # Ограничиваем размер файлов для анализа
                    if old_content and len(old_content) > max_file_size:
                        old_content = old_content[:max_file_size] + f"\n... [обрезано, полный размер: {len(old_content)} символов]"
                    
                    if new_content and len(new_content) > max_file_size:
                        new_content = new_content[:max_file_size] + f"\n... [обрезано, полный размер: {len(new_content)} символов]"
                    
                    diff_content = d.get('diff', '')
                    if len(diff_content) > max_file_size:
                        diff_content = diff_content[:max_file_size] + f"\n... [обрезано, полный размер: {len(diff_content)} символов]"
                    
                    modified_files.append({
                        'path': file_path,
                        'diff': diff_content,
                        'old_content': old_content,
                        'new_content': new_content
                    })
                    
                    if debug_mode:
                        logger.info(f"[DEBUG] Файл {file_path} обработан")
                        logger.info(f"[DEBUG] Размеры: diff={len(diff_content)}, old={len(old_content) if old_content else 0}, new={len(new_content) if new_content else 0}")
            
            logger.info(f"Получены детали коммита {commit_id[:7]}, файлов: {len(modified_files)}")
            return commit, modified_files
        except Exception as e:
            logger.error(f"Ошибка получения деталей коммита {commit_id[:7]}: {e}")
            return None, []

class LLMAnalyzer:
    def __init__(self, api_key, site_url, site_name):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": site_url,
            "X-Title": site_name,
            "Content-Type": "application/json"
        }
        logger.info("LLM анализатор инициализирован")
    
    async def analyze_changes(self, modified_files, debug_mode=False):
        # Разбиваем анализ на несколько более мелких запросов, если необходимо
        if len(modified_files) > 3:
            # Если файлов слишком много, анализируем по частям
            batches = []
            current_batch = []
            current_size = 0
            max_batch_size = 15000  # Примерное ограничение размера пакета
            
            for file in modified_files:
                file_size = len(file['diff']) + len(file['new_content'] or '') + len(file['old_content'] or '')
                if current_size + file_size > max_batch_size and current_batch:
                    batches.append(current_batch)
                    current_batch = [file]
                    current_size = file_size
                else:
                    current_batch.append(file)
                    current_size += file_size
            
            if current_batch:
                batches.append(current_batch)
            
            if debug_mode:
                logger.info(f"[DEBUG] Разбивка на {len(batches)} пакетов для анализа")
            
            all_descriptions = []
            all_errors = []
            
            for i, batch in enumerate(batches):
                if debug_mode:
                    logger.info(f"[DEBUG] Анализ пакета {i+1}/{len(batches)}, файлов: {len(batch)}")
                
                desc, errors = await self._analyze_batch(batch, debug_mode)
                if desc:
                    all_descriptions.append(desc)
                if errors and errors != "Нет":
                    all_errors.append(errors)
            
            final_desc = " ".join(all_descriptions)
            final_errors = "Нет" if not all_errors else "\n".join(all_errors)
            
            return final_desc, final_errors
        else:
            # Если файлов немного, анализируем все сразу
            return await self._analyze_batch(modified_files, debug_mode)
    
    async def _analyze_batch(self, file_batch, debug_mode=False):
        prompt = self._create_prompt(file_batch)
        
        if debug_mode:
            logger.info(f"[DEBUG] ПРОМТ ДЛЯ LLM:\n{prompt}")
            logger.info(f"[DEBUG] Длина промта: {len(prompt)} символов")
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            # Увеличиваем лимит для более подробного анализа
            "max_tokens": 800
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    response_text = await resp.text()
                    
                    if debug_mode:
                        logger.info(f"[DEBUG] ОТВЕТ API:\n{response_text}")
                    
                    if resp.status != 200:
                        logger.error(f"Ошибка API: {resp.status} - {response_text}")
                        return None, None
                    
                    result = json.loads(response_text)
                    if "choices" not in result or not result["choices"]:
                        logger.error(f"Неверный ответ: {result}")
                        return None, None
                    
                    analysis = result["choices"][0]["message"]["content"]
                    
                    if debug_mode:
                        logger.info(f"[DEBUG] АНАЛИЗ LLM:\n{analysis}")
                    
                    parts = analysis.split("Ошибки:")
                    desc = parts[0].strip()
                    errors = parts[1].strip() if len(parts) > 1 else "Нет"
                    
                    logger.debug(f"Анализ получен, длина: {len(analysis)}")
                    return desc, errors
        except Exception as e:
            logger.error(f"Ошибка анализа: {e}")
            return None, None
    
    def _create_prompt(self, modified_files):
        # Расширенный и улучшенный промт для более глубокого анализа кода
        prompt = """
Ты опытный аудитор кода и эксперт по Python/Django и React/JavaScript с глубоким пониманием архитектуры веб-приложений. Твоя задача — проанализировать предложенные изменения в коде и выявить любые потенциальные проблемы, сосредоточившись исключительно на критичных аспектах (стилистика, форматирование и линтеры не учитываются). Обрати особое внимание на следующие ключевые моменты:

Вызовы несуществующих методов или некорректный доступ к атрибутам:
Проверь, существуют ли вызываемые методы и атрибуты в текущем контексте, включая импорты и зависимости.
Убедись, что доступ к объектам соответствует их структуре (например, нет попыток обращения к полям, которых нет в моделях или объектах).
Несоответствие интерфейсов и API:
Проверь корректность наследования классов, использования миксинов и интерфейсов, особенно в Django и React.
Убедись, что ожидаемые сигнатуры методов и API (включая сторонние библиотеки) соблюдены.
Логические ошибки и потенциальные баги:
Ищи скрытые логические проблемы, такие как неправильные условия, некорректная обработка краевых случаев или пропущенные проверки.
Обрати внимание на возможные состояния гонки или недетерминированное поведение.
Небезопасные операции и уязвимости безопасности:
Выяви потенциальные уязвимости, такие как SQL-инъекции, XSS, CSRF, утечки данных или неправильная валидация входных данных.
Проверь использование чувствительных данных (например, паролей, токенов) и их защиту.
Проблемы с производительностью и утечки ресурсов:
Оцени эффективность кода: избыточные запросы к базе данных (N+1), неоптимальные циклы, отсутствие кэширования там, где оно необходимо.
Проверь, нет ли утечек памяти, незакрытых соединений или неуправляемого роста ресурсов.
Для Django-кода дополнительно:

Убедись в правильности использования методов миксинов (например, порядок разрешения методов в MRO).
Проверь реализацию REST API endpoints: корректность сериализаторов, валидации, обработки ошибок и соответствие HTTP-методам (GET, POST, PUT, DELETE).
Оцени обработку запросов: фильтрацию, пагинацию, права доступа (permissions) и работу с Querysets.
Проверь корректность работы с моделями, миграциями и транзакциями.
Для React/JavaScript-кода дополнительно:

Проверь управление состоянием (state, props) и корректность передачи данных между компонентами.
Оцени использование хуков (например, useEffect, useState) на предмет бесконечных циклов или утечек.
Проверь асинхронные операции (fetch, Promises) на обработку ошибок и завершение.

        """
        
        for idx, file in enumerate(modified_files):
            file_summary = f"ФАЙЛ {idx+1}: {file['path']}\n\n"
            
            # Всегда добавляем содержимое файла до изменений, если оно есть
            if file['old_content']:
                file_summary += f"--- СОДЕРЖИМОЕ ДО ИЗМЕНЕНИЙ ---\n{file['old_content']}\n\n"
            
            # Добавляем дифф для наглядности изменений
            file_summary += f"--- ИЗМЕНЕНИЯ (DIFF) ---\n{file['diff']}\n\n"
            
            # Добавляем новое содержимое файла для полного контекста
            if file['new_content']:
                file_summary += f"--- СОДЕРЖИМОЕ ПОСЛЕ ИЗМЕНЕНИЙ ---\n{file['new_content']}\n\n"
            
            prompt += file_summary
        
        prompt += """
        Дай анализ в лаконичном формате:

        1. Краткое описание изменений: что именно было изменено (одно предложение)
        2. Ошибки: если найдены, укажи конкретно главную проблему или несколько ключевых проблем, минимально-необходимое объяснение, файл и строку где проблема

        Не используй многословные описания, не добавляй лишние объяснения. Формат ответа должен быть минималистичным и конкретным.

        Если ошибок нет, просто напиши "Нет".
        """
        
        logger.debug(f"Создан промт, длина: {len(prompt)}")
        return prompt

class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.bot = Bot(token)
        self.chat_id = chat_id
        logger.info("Telegram бот инициализирован")
    
    async def send_message(self, message):
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message)
            logger.debug(f"Отправлено сообщение, длина: {len(message)}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            return False

class CommitMonitor:
    def __init__(self, config, debug_mode=False, max_files=5, max_file_size=10000):
        self.config = config
        self.debug_mode = debug_mode
        self.max_files = max_files
        self.max_file_size = max_file_size
        self.db_manager = DBManager(config["db_path"])
        self.gitlab_client = GitLabClient(config["gitlab_url"], config["gitlab_token"])
        self.llm_analyzer = LLMAnalyzer(
            config["openrouter_api_key"], 
            config["site_url"], 
            config["site_name"]
        )
        self.notifier = TelegramNotifier(config["telegram_token"], config["chat_id"])
        self.start_time = datetime.now(pytz.UTC)
        self.repositories = config["repositories"]
        logger.info(f"Монитор инициализирован: {len(self.repositories)} репозиториев")
        
        if debug_mode:
            logger.info("[DEBUG] Режим отладки включен")
            logger.info(f"[DEBUG] Максимум файлов: {max_files}, максимальный размер файла: {max_file_size}")
    
    async def monitor_project(self, project_path):
        commits = await self.gitlab_client.fetch_recent_commits(
            project_path, self.start_time, self.db_manager
        )
        
        if not commits:
            return
        
        for commit in reversed(commits):
            try:
                commit_time = parse_datetime(commit.created_at)
                logger.info(f"Обработка коммита {commit.id[:7]} от {commit_time} в {project_path}")
                
                commit_obj, modified_files = await self.gitlab_client.get_commit_details(
                    project_path, commit.id, 
                    max_files=self.max_files,
                    max_file_size=self.max_file_size,
                    debug_mode=self.debug_mode
                )
                
                if not modified_files:
                    logger.debug(f"Коммит {commit.id[:7]} не содержит изменений файлов")
                    self.db_manager.mark_processed(project_path, commit.id, commit_time)
                    continue
                
                desc, errors = await self.llm_analyzer.analyze_changes(modified_files, self.debug_mode)
                
                if desc is None:
                    logger.warning(f"Не удалось проанализировать коммит {commit.id[:7]}")
                    self.db_manager.mark_processed(project_path, commit.id, commit_time)
                    continue
                
                # Получаем URL коммита для создания ссылки
                project_url = f"{self.config['gitlab_url']}/{project_path}"
                commit_url = f"{project_url}/-/commit/{commit.id}"
                
                # Формируем лаконичное сообщение с ссылкой на коммит
                msg = (
                    f"{project_path}: [{commit.id[:7]}]({commit_url})\n"
                    f"{commit.title}\n"
                    f"Автор: {commit.author_name}\n"
                    f"Изменения: {desc}\n"
                )
                
                # Добавляем информацию об ошибках только если они есть
                if errors and errors != "Нет":
                    msg += f"⚠️ Ошибки: {errors}"
                
                await self.notifier.send_message(msg)
                self.db_manager.mark_processed(project_path, commit.id, commit_time)
            
            except Exception as e:
                logger.error(f"Ошибка обработки {commit.id[:7]} в {project_path}: {str(e)}")
                await self.notifier.send_message(f"Ошибка обработки коммита {commit.id[:7]} в {project_path}: {str(e)}")
                # Помечаем как обработанный, чтобы не пытаться снова обработать
                try:
                    commit_time = parse_datetime(commit.created_at)
                    self.db_manager.mark_processed(project_path, commit.id, commit_time)
                except Exception as e2:
                    logger.error(f"Не удалось пометить коммит как обработанный: {str(e2)}")
    
    async def run(self, specific_repo=None):
        logger.info(f"Монитор запущен: {self.start_time}")
        
        # Если указан конкретный репозиторий, проверяем только его
        if specific_repo:
            if specific_repo in self.repositories:
                logger.info(f"Проверка только репозитория: {specific_repo}")
                await self.monitor_project(specific_repo)
            else:
                logger.error(f"Репозиторий не найден в списке: {specific_repo}")
            return
        
        # Иначе проверяем все репозитории в цикле
        while True:
            logger.info(f"Проверка проектов: {datetime.now(pytz.UTC)}")
            
            tasks = [self.monitor_project(project) for project in self.repositories]
            await asyncio.gather(*tasks)
            
            await asyncio.sleep(self.config["check_interval"])

def load_config():
    load_dotenv()
    
    # Проверка обязательных переменных
    required = ["GITLAB_TOKEN", "TELEGRAM_TOKEN", "CHAT_ID", "OPENROUTER_API_KEY"]
    missing = [var for var in required if not os.getenv(var)]
    
    if missing:
        raise ValueError(f"Отсутствуют переменные: {', '.join(missing)}")
    
    # Конфигурация из .env
    config = {
        "gitlab_url": os.getenv("GITLAB_URL", "https://gitlab.com"),
        "gitlab_token": os.getenv("GITLAB_TOKEN"),
        "telegram_token": os.getenv("TELEGRAM_TOKEN"),
        "chat_id": os.getenv("CHAT_ID"),
        "check_interval": int(os.getenv("CHECK_INTERVAL", "300")),
        "db_path": os.getenv("DB_PATH", "commits.db"),
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY"),
        "site_url": os.getenv("YOUR_SITE_URL", "https://example.com"),
        "site_name": os.getenv("YOUR_SITE_NAME", "GitLab Monitor"),
        "repositories": os.getenv("REPOSITORIES", "").split(",") if os.getenv("REPOSITORIES") else [

        ]
    }
    
    logger.info(f"Конфигурация загружена: {len(config['repositories'])} репозиториев")
    return config

async def main():
    try:
        args = parse_args()
        config = load_config()
        
        # Настройка уровня логирования в зависимости от режима отладки
        if args.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.info("Включен детальный режим логирования")
        
        # Устанавливаем начальное время на основе аргументов
        start_time = None
        if args.since:
            try:
                # Если указано конкретное время начала
                local_tz = pytz.timezone('Europe/Stockholm')  # Северная Европа по умолчанию
                start_time = local_tz.localize(datetime.strptime(args.since, "%Y-%m-%d %H:%M"))
                logger.info(f"Установлено время начала проверки: {start_time}")
            except ValueError as e:
                logger.error(f"Неверный формат времени: {e}")
                return
        elif args.hours:
            # Если указано количество часов
            start_time = datetime.now(pytz.UTC) - timedelta(hours=args.hours)
            logger.info(f"Установлено время начала проверки: {start_time} (за последние {args.hours} ч)")
        
        monitor = CommitMonitor(
            config,
            debug_mode=args.debug,
            max_files=args.max_files,
            max_file_size=args.max_file_size
        )
        
        # Переопределяем время начала, если оно было указано
        if start_time:
            monitor.start_time = start_time
        
        # Запускаем мониторинг
        if args.repo:
            await monitor.run(specific_repo=args.repo)
        else:
            await monitor.run()
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
