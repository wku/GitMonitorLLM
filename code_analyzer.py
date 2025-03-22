# code_analyzer.py

import os
import re
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv
from context_discovery import ContextDiscovery

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-4o-mini")
SITE_URL = os.environ.get("SITE_URL", "https://example.com")
SITE_NAME = os.environ.get("SITE_NAME", "GitMonitorLLM")


class CodeAnalyzer:
    """
    Класс для анализа кода с учетом контекстных файлов
    """
    
    def __init__(self, api_key=OPENROUTER_API_KEY, model=DEFAULT_MODEL):
        """
        Инициализация класса для анализа кода
        
        Args:
            api_key (str): API ключ для OpenRouter
            model (str): Модель ИИ для использования
        """
        if not api_key:
            raise ValueError("API ключ не установлен")
            
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
        self.model = model
        self.context_discoverer = ContextDiscovery(api_key, model)
        logger.info(f"Инициализирован CodeAnalyzer с моделью {model}")
    
    def analyze_commit(self, modified_files, repository_client=None, available_files=None):
        """
        Анализирует изменения в коммите с учетом контекста
        
        Args:
            modified_files (list): Список словарей с измененными файлами
                                  [{path: str, content: str, diff: str}, ...]
            repository_client (object, optional): Клиент для получения файлов из репозитория
            available_files (list, optional): Список доступных файлов в репозитории
            
        Returns:
            dict: Результат анализа {
                status: str,
                analysis: dict,
                context_files: list (optional)
            }
        """
        try:
            # Шаг 1: Определение необходимых контекстных файлов
            logger.info("Определение необходимых контекстных файлов...")
            context_result = self.context_discoverer.discover_required_files(modified_files, available_files)
            
            required_files = context_result.get("required_files", [])
            
            if not required_files:
                logger.info("Контекстные файлы не требуются, выполняем анализ только измененных файлов")
                # Если контекстные файлы не нужны, анализируем только измененные файлы
                analysis_result = self._analyze_code_changes(modified_files, [])
                return {
                    "status": "completed",
                    "analysis": analysis_result
                }
            
            # Шаг 2: Получение контекстных файлов из репозитория
            logger.info(f"Требуется получить {len(required_files)} контекстных файлов")
            context_files = []
            
            if repository_client:
                for file_info in required_files:
                    file_path = file_info.get("path")
                    priority = file_info.get("priority", 5)
                    
                    try:
                        # Получаем содержимое файла из репозитория
                        file_content = repository_client.get_file_content(file_path)
                        
                        if file_content:
                            context_files.append({
                                "path": file_path,
                                "content": file_content,
                                "priority": priority
                            })
                            logger.info(f"Получен контекстный файл: {file_path}")
                        else:
                            logger.warning(f"Не удалось получить содержимое файла: {file_path}")
                    except Exception as e:
                        logger.error(f"Ошибка при получении файла {file_path}: {e}")
                        # Если файл с высоким приоритетом не удалось получить, это проблема
                        if priority <= 2:
                            logger.warning(f"Файл с высоким приоритетом не получен: {file_path}")
            else:
                logger.warning("Репозиторный клиент не предоставлен, анализ будет выполнен без контекстных файлов")
            
            # Шаг 3: Выполнение анализа с учетом контекста
            logger.info(f"Выполнение анализа кода с учетом {len(context_files)} контекстных файлов")
            analysis_result = self._analyze_code_changes(modified_files, context_files)
            
            return {
                "status": "completed",
                "analysis": analysis_result,
                "context_files": [f.get("path") for f in context_files]
            }
        
        except Exception as e:
            logger.error(f"Ошибка при анализе коммита: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _analyze_code_changes(self, modified_files, context_files):
        """
        Выполняет анализ измененных файлов с учетом контекстных файлов
        
        Args:
            modified_files (list): Список словарей с измененными файлами
            context_files (list): Список словарей с контекстными файлами
            
        Returns:
            dict: Результат анализа
        """
        prompt = self._create_analysis_prompt(modified_files, context_files)
        
        try:
            logger.info("Отправка запроса для анализа кода...")
            
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": SITE_URL,
                    "X-Title": SITE_NAME,
                },
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
                max_tokens=2000
            )
            
            response_text = completion.choices[0].message.content
            logger.debug(f"Ответ LLM на запрос анализа: {response_text[:200]}...")
            
            # Извлекаем JSON из ответа
            return self._extract_json_response(response_text)
        
        except Exception as e:
            logger.error(f"Ошибка при запросе на анализ кода: {e}")
            return {
                "issues": [],
                "summary": f"Ошибка при анализе кода: {str(e)}"
            }
    
    def _create_analysis_prompt(self, modified_files, context_files):
        """
        Создает промпт для анализа кода с учетом контекста
        
        Args:
            modified_files (list): Список словарей с измененными файлами
            context_files (list): Список словарей с контекстными файлами
            
        Returns:
            str: Промт для отправки LLM
        """
        prompt = """
### ЗАДАЧА АНАЛИЗА ИЗМЕНЕНИЙ КОДА С УЧЕТОМ КОНТЕКСТА ###

# ИНСТРУКЦИИ
Ты - эксперт по анализу кода, специализирующийся на Python, Django, React и JavaScript. Твоя задача - проанализировать изменения в коммите и найти потенциальные проблемы или ошибки.

Анализируй только явные проблемы, которые могут вызвать ошибки:
1. Синтаксические ошибки
2. Несуществующие методы или параметры (с учетом контекста фреймворков)
3. Несоответствие сигнатур функций
4. Логические ошибки или уязвимости
5. Нарушения общих паттернов и практик

# ИЗМЕНЕННЫЕ ФАЙЛЫ В КОММИТЕ:
"""
        
        # Добавляем изменённые файлы
        for i, file in enumerate(modified_files):
            prompt += f"\n## ИЗМЕНЁННЫЙ ФАЙЛ {i+1}: {file['path']}\n"
            
            # Добавляем diff если есть
            if 'diff' in file and file['diff']:
                prompt += f"### Изменения (diff):\n```diff\n{file['diff']}\n```\n"
            
            # Добавляем старое содержимое если есть
            if 'old_content' in file and file['old_content']:
                prompt += f"### Содержимое до изменений:\n```python\n{file['old_content']}\n```\n"
                
            # Добавляем новое содержимое
            if 'content' in file and file['content']:
                prompt += f"### Содержимое после изменений:\n```python\n{file['content']}\n```\n"
            elif 'new_content' in file and file['new_content']:
                prompt += f"### Содержимое после изменений:\n```python\n{file['new_content']}\n```\n"
        
        # Добавляем контекстные файлы, если есть
        if context_files:
            prompt += "\n# КОНТЕКСТНЫЕ ФАЙЛЫ ДЛЯ АНАЛИЗА:\n"
            
            # Сортируем контекстные файлы по приоритету
            sorted_context = sorted(context_files, key=lambda x: x.get("priority", 5))
            
            for i, file in enumerate(sorted_context):
                prompt += f"\n## КОНТЕКСТНЫЙ ФАЙЛ {i+1}: {file['path']} (Приоритет: {file.get('priority', 5)})\n"
                prompt += f"```python\n{file['content']}\n```\n"
        
        # Инструкции для формата ответа
        prompt += """
# ФОРМАТ ОТВЕТА
Верни JSON в следующем формате:

{
  "issues": [
    {
      "file": "путь/к/файлу.py",
      "line": 42,
      "severity": "critical|high|medium|low",
      "description": "Описание проблемы",
      "suggestion": "Предлагаемое решение"
    },
    ...
  ],
  "summary": "Краткое описание изменений и выявленных проблем"
}

# ВАЖНЫЕ ПРАВИЛА
1. Учитывай особенности фреймворков при анализе:
   - Django/DRF часто предоставляет методы через наследование
   - React компоненты могут получать props разных типов
   - Python позволяет динамическую типизацию

2. Указывай проблемы с разными уровнями серьезности:
   - critical: Гарантированно вызовет ошибку выполнения или уязвимость
   - high: С высокой вероятностью вызовет проблемы
   - medium: Потенциальная проблема или нарушение лучших практик
   - low: Незначительные проблемы или предложения по улучшению

3. Если проблем не обнаружено, верни пустой список issues

4. Не перечисляй стилистические проблемы или форматирование

5. ОЧЕНЬ ВАЖНО: Не сообщай о проблемах без 100% уверенности. 
   Если у тебя нет доступа к полному контексту или определению - не предполагай ошибку.
   Лучше не указать проблему, чем указать ложную.

Возвращай ТОЛЬКО JSON без дополнительных комментариев.
"""
        return prompt
    
    def _extract_json_response(self, response_text):
        """
        Извлекает JSON из ответа LLM
        
        Args:
            response_text (str): Текст ответа от LLM
            
        Returns:
            dict: Распарсенный JSON или словарь с ошибкой
        """
        try:
            # Сначала ищем JSON в блоке кода
            json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                response_json = json_match.group(1)
                logger.debug("Извлечен JSON из блока кода")
            else:
                # Если не нашли в блоке кода, ищем просто JSON-объект
                json_match = re.search(r'({[\s\S]*})', response_text)
                if json_match:
                    response_json = json_match.group(1)
                    logger.debug("Извлечен JSON из текста напрямую")
                else:
                    # Если не нашли, берем весь текст и пытаемся парсить
                    response_json = response_text
                    logger.warning("Не найден форматированный JSON в ответе")
                    
            # Пытаемся парсить JSON
            result = json.loads(response_json)
            
            # Проверяем наличие правильных ключей
            if "issues" not in result:
                logger.warning("В ответе нет ключа 'issues'")
                result["issues"] = []
                
            if "summary" not in result:
                logger.warning("В ответе нет ключа 'summary'")
                result["summary"] = "Анализ выполнен, детали не предоставлены"
                
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            
            # Пытаемся очистить строку
            try:
                cleaned_text = re.sub(r'[\n\r\t]', '', response_text)
                cleaned_text = cleaned_text.replace("'", '"')
                result = json.loads(cleaned_text)
                logger.info("JSON успешно распарсен после очистки")
                return result
            except json.JSONDecodeError:
                logger.error("Не удалось распарсить JSON даже после очистки")
                return {
                    "issues": [],
                    "summary": "Ошибка при анализе ответа LLM"
                }
                
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при обработке ответа: {e}")
            return {
                "issues": [],
                "summary": f"Ошибка при обработке ответа: {str(e)}"
            }


# Пример интеграции с GitLab клиентом
class GitLabRepositoryClient:
    """
    Пример клиента для получения файлов из GitLab репозитория
    """
    
    def __init__(self, gitlab_client, project_path, commit_id):
        self.gitlab_client = gitlab_client
        self.project_path = project_path
        self.commit_id = commit_id
        self.project = None
        self._init_project()
    
    def _init_project(self):
        try:
            self.project = self.gitlab_client.get_project(self.project_path)
        except Exception as e:
            logger.error(f"Ошибка при инициализации проекта: {e}")

    def get_file_content(self, file_path):
        """
        Получает содержимое файла из репозитория

        Args:
            file_path (str): Путь к файлу в репозитории

        Returns:
            str: Содержимое файла или None в случае ошибки
        """
        if not self.project:
            return None

        try:
            file_obj = self.project.files.get (file_path=file_path, ref=self.commit_id)

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
                logger.error (f"Объект файла {file_path} не имеет метода decode() или атрибута content")
                return None

        except Exception as e:
            logger.error (f"Ошибка при получении файла {file_path}: {e}")
            return None
    
    def get_available_files(self, directory=None):
        """
        Получает список доступных файлов в репозитории
        
        Args:
            directory (str, optional): Директория для поиска
            
        Returns:
            list: Список путей к файлам
        """
        if not self.project:
            return []
            
        try:
            items = self.project.repository_tree(path=directory, ref=self.commit_id, recursive=True)
            # Фильтруем только файлы
            files = [item['path'] for item in items if item['type'] == 'blob']
            return files
        except Exception as e:
            logger.error(f"Ошибка при получении списка файлов: {e}")
            return []


# Интеграция в основной код мониторинга
def analyze_commit_with_context(gitlab_client, project_path, commit_id, modified_files):
    """
    Анализирует коммит с учетом контекста из репозитория
    
    Args:
        gitlab_client: Клиент GitLab
        project_path (str): Путь к проекту
        commit_id (str): ID коммита
        modified_files (list): Список измененных файлов с содержимым
        
    Returns:
        dict: Результат анализа
    """
    # Инициализация репозиторного клиента для получения контекстных файлов
    repo_client = GitLabRepositoryClient(gitlab_client, project_path, commit_id)
    
    # Получение списка доступных файлов в репозитории
    available_files = repo_client.get_available_files()
    
    # Инициализация анализатора кода
    analyzer = CodeAnalyzer()
    
    # Анализ коммита с учетом контекста
    result = analyzer.analyze_commit(
        modified_files=modified_files,
        repository_client=repo_client,
        available_files=available_files
    )
    
    return result


# Пример использования
if __name__ == "__main__":
    # Пример использования класса
    import sys
    
    if not OPENROUTER_API_KEY:
        print("Ошибка: Не задан API ключ в переменной окружения OPENROUTER_API_KEY")
        sys.exit(1)
    
    # Включаем отладочное логирование
    logger.setLevel(logging.DEBUG)
    
    # Создаем экземпляр класса
    analyzer = CodeAnalyzer()
    
    # Пример изменённых файлов
    modified_files = [
        {
            "path": "app/views.py",
            "diff": "@@ -10,6 +10,9 @@ class UserView(ModelViewSet):\n     serializer_class = UserSerializer\n \n     def get_queryset(self):\n+        # Добавлена фильтрация по группам\n+        groups = self.request.query_params.get('groups')\n+        if groups:\n             return User.objects.filter(is_active=True)\n \n     def perform_create(self, serializer):",
            "old_content": "from rest_framework.viewsets import ModelViewSet\nfrom .models import User\nfrom .serializers import UserSerializer\n\nclass UserView(ModelViewSet):\n    queryset = User.objects.all()\n    serializer_class = UserSerializer\n\n    def get_queryset(self):\n        return User.objects.filter(is_active=True)\n\n    def perform_create(self, serializer):\n        serializer.save()",
            "new_content": "from rest_framework.viewsets import ModelViewSet\nfrom .models import User\nfrom .serializers import UserSerializer\n\nclass UserView(ModelViewSet):\n    queryset = User.objects.all()\n    serializer_class = UserSerializer\n\n    def get_queryset(self):\n        # Добавлена фильтрация по группам\n        groups = self.request.query_params.get('groups')\n        if groups:\n            return User.objects.filter(is_active=True)\n\n    def perform_create(self, serializer):\n        serializer.save()"
        }
    ]
    
    # Пример контекстных файлов
    context_files = [
        {
            "path": "app/models.py",
            "content": "from django.db import models\n\nclass User(models.Model):\n    username = models.CharField(max_length=100)\n    email = models.EmailField(unique=True)\n    is_active = models.BooleanField(default=True)\n    groups = models.ManyToManyField('Group', related_name='users')\n\nclass Group(models.Model):\n    name = models.CharField(max_length=100)",
            "priority": 1
        },
        {
            "path": "app/serializers.py",
            "content": "from rest_framework import serializers\nfrom .models import User\n\nclass UserSerializer(serializers.ModelSerializer):\n    class Meta:\n        model = User\n        fields = ['id', 'username', 'email', 'is_active', 'groups']",
            "priority": 2
        }
    ]
    
    # Анализ кода с контекстом
    result = analyzer._analyze_code_changes(modified_files, context_files)
    
    # Выводим результат
    print(json.dumps(result, indent=2))
