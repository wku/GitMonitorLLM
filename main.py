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
from smart_context_analyzer import LLMAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Добавить в начало main.py, после других импортов
import time
import functools

# Декоратор для повторных попыток при временных ошибках GitLab API
def gitlab_retry(max_retries=3, retry_delay=5):
    def decorator(func):
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except gitlab.exceptions.GitlabError as e:
                    # Проверяем коды временных ошибок
                    if hasattr(e, 'response_code') and e.response_code in [429, 500, 502, 503, 504]:
                        retries += 1
                        if retries >= max_retries:
                            logger.error(f"Превышено максимальное число попыток ({max_retries}) для {func.__name__}: {e}")
                            break
                        logger.warning(f"Временная ошибка GitLab API в {func.__name__}: {e}. Повторная попытка {retries}/{max_retries} через {retry_delay} сек")
                        time.sleep(retry_delay)
                    else:
                        # Не повторяем при других ошибках
                        logger.error(f"Ошибка GitLab API в {func.__name__}: {e}")
                        break
                except Exception as e:
                    logger.error(f"Непредвиденная ошибка в {func.__name__}: {e}")
                    break
            return None  # Возвращаем None, если все попытки неудачны

        async def async_wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except gitlab.exceptions.GitlabError as e:
                    # Проверяем коды временных ошибок
                    if hasattr(e, 'response_code') and e.response_code in [429, 500, 502, 503, 504]:
                        retries += 1
                        if retries >= max_retries:
                            logger.error(f"Превышено максимальное число попыток ({max_retries}) для {func.__name__}: {e}")
                            break
                        logger.warning(f"Временная ошибка GitLab API в {func.__name__}: {e}. Повторная попытка {retries}/{max_retries} через {retry_delay} сек")
                        await asyncio.sleep(retry_delay)
                    else:
                        # Не повторяем при других ошибках
                        logger.error(f"Ошибка GitLab API в {func.__name__}: {e}")
                        break
                except Exception as e:
                    logger.error(f"Непредвиденная ошибка в {func.__name__}: {e}")
                    break
            return None  # Возвращаем None, если все попытки неудачны

        # Выбираем нужную обертку в зависимости от типа функции
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator



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

    @gitlab_retry (max_retries=3, retry_delay=5)
    def get_project(self, project_path):
        try:
            return self.client.projects.get(project_path)
        except gitlab.exceptions.GitlabGetError as e:
            logger.error(f"Ошибка доступа к проекту {project_path}: {e}")
            return None

    @gitlab_retry (max_retries=3, retry_delay=5)
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

    @gitlab_retry (max_retries=3, retry_delay=5)
    async def get_file_content(self, project, file_path, commit_id=None):
        try:
            if commit_id:
                file_obj = project.files.get (file_path=file_path, ref=commit_id)
            else:
                file_obj = project.files.get (file_path=file_path)

            # Правильная обработка байтового содержимого
            if hasattr (file_obj, 'content'):
                content = file_obj.content
                # Если content уже строка, используем её, иначе декодируем из base64
                if isinstance (content, str):
                    return content
                else:
                    import base64
                    return base64.b64decode (content).decode ('utf-8', errors='replace')
            elif hasattr (file_obj, 'decode'):
                # Для совместимости со старыми версиями python-gitlab
                return file_obj.decode ()
            else:
                logger.error (f"Объект файла не имеет метода decode() или атрибута content")
                return None

        except gitlab.exceptions.GitlabGetError:
            logger.debug (f"Файл {file_path} не найден")
            return None
        except Exception as e:
            logger.error (f"Ошибка получения содержимого {file_path}: {e}")
            return None

    @gitlab_retry (max_retries=3, retry_delay=5)
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

class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.bot = Bot(token)
        self.chat_id = chat_id
        logger.info("Telegram бот инициализирован")
    
    async def send_message(self, message):
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="Markdown")
            logger.debug(f"Отправлено сообщение, длина: {len(message)}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения с Markdown: {e}")
            # Попытка отправить без разметки в случае ошибки
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=message)
                return True
            except Exception as e2:
                logger.error(f"Повторная ошибка отправки сообщения: {e2}")
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
                
                # Используем новый анализатор с поддержкой контекста
                desc, errors = await self.llm_analyzer.analyze_changes(
                    modified_files,
                    gitlab_client=self.gitlab_client,  # Передаем GitLab клиент
                    project_path=project_path,        # Передаем путь к проекту
                    commit_id=commit.id,              # Передаем ID коммита
                    debug_mode=self.debug_mode
                )
                
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
                
                # Добавляем информацию об ошибках только если они есть и это не "Нет явных ошибок"
                if errors and errors != "Нет явных ошибок":
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
        "repositories": os.getenv("REPOSITORIES", "").split(",") if os.getenv("REPOSITORIES") else []
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
