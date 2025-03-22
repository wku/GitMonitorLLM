# context_discovery.py

import os
import re
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv

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
SITE_NAME = os.environ.get("SITE_NAME", "CodeContextDiscovery")


class ContextDiscovery:
    """
    Класс для определения контекстных файлов, необходимых для анализа кода
    """
    
    def __init__(self, api_key=OPENROUTER_API_KEY, model=DEFAULT_MODEL):
        """
        Инициализация класса для определения контекстных файлов
        
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
        logger.info(f"Инициализирован ContextDiscovery с моделью {model}")
    
    def discover_required_files(self, modified_files, available_files=None):
        """
        Анализирует измененные файлы и определяет, какие дополнительные файлы необходимы для контекста
        
        Args:
            modified_files (list): Список словарей с изменёнными файлами 
                                  [{path: str, content: str, diff: str}, ...]
            available_files (list): Список доступных файлов в репозитории для выбора контекста
            
        Returns:
            dict: Информация о требуемых файлах {
                required_files: [{path: str, reason: str, priority: int}, ...], 
                explanation: str
            }
        """
        prompt = self._create_discovery_prompt(modified_files, available_files)
        
        try:
            logger.info("Отправка запроса для определения необходимых контекстных файлов...")
            
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
                max_tokens=1500
            )
            
            response_text = completion.choices[0].message.content
            logger.debug(f"Ответ LLM на запрос обнаружения контекста: {response_text[:200]}...")
            
            # Извлекаем JSON из ответа
            return self._extract_json_response(response_text)
        
        except Exception as e:
            logger.error(f"Ошибка при запросе на обнаружение контекста: {e}")
            return {"required_files": [], "explanation": f"Ошибка при определении контекста: {str(e)}"}
    
    def _create_discovery_prompt(self, modified_files, available_files=None):
        """
        Создает промпт для обнаружения необходимых контекстных файлов
        
        Args:
            modified_files (list): Список словарей с измененными файлами
            available_files (list): Список доступных файлов в репозитории
            
        Returns:
            str: Промт для отправки LLM
        """
        prompt = """
### ЗАДАЧА ОПРЕДЕЛЕНИЯ КОНТЕКСТНЫХ ФАЙЛОВ ДЛЯ АНАЛИЗА КОММИТА ###

# ИНСТРУКЦИИ
Ты - эксперт по анализу кода. Твоя задача - проанализировать измененные файлы в коммите и определить, какие дополнительные файлы необходимы для полного понимания контекста изменений.

Нужно найти файлы, которые:
1. Содержат классы или функции, от которых наследуются или с которыми взаимодействуют измененные файлы
2. Содержат импортируемые локальные модули и их зависимости
3. Определяют интерфейсы, константы или типы, используемые в измененном коде
4. Могут содержать определения методов, которые вызываются или переопределяются

# ИЗМЕНЕННЫЕ ФАЙЛЫ В КОММИТЕ:
"""
        
        # Добавляем изменённые файлы
        for i, file in enumerate(modified_files):
            prompt += f"\n## ФАЙЛ {i+1}: {file['path']}\n"
            
            # Добавляем diff если есть
            if 'diff' in file and file['diff']:
                prompt += f"### Изменения (diff):\n```diff\n{file['diff']}\n```\n"
                
            # Добавляем содержимое
            if 'content' in file and file['content']:
                prompt += f"### Содержимое после изменений:\n```python\n{file['content']}\n```\n"
        
        # Добавляем список доступных файлов, если есть
        if available_files:
            prompt += "\n# ДОСТУПНЫЕ ФАЙЛЫ В РЕПОЗИТОРИИ:\n"
            for file_path in available_files:
                prompt += f"- {file_path}\n"
        
        # Инструкции по формату ответа
        prompt += """
# ФОРМАТ ОТВЕТА
Проанализируй код измененных файлов и верни JSON в следующем формате:

{
  "required_files": [
    {
      "path": "путь/к/файлу.py",
      "reason": "Четкое объяснение, почему этот файл нужен для анализа",
      "priority": 1-5 (1 - критически важно, 5 - может быть полезно)
    },
    ...
  ],
  "explanation": "Краткое обоснование выбранных файлов и их важности для анализа"
}

# ВАЖНЫЕ ПРАВИЛА
1. Возвращай ТОЛЬКО файлы, которые ДЕЙСТВИТЕЛЬНО необходимы для понимания контекста
2. Если контекстные файлы не нужны, верни пустой список required_files
3. При выборе из доступных файлов, отдавай предпочтение файлам из тех же директорий
4. Указывай точный путь к файлу из списка доступных файлов, если он там есть
5. Приоритет должен отражать важность файла:
   - 1: Без этого файла анализ невозможен
   - 2: Высокая вероятность проблем без этого файла
   - 3: Полезен для полного понимания
   - 4: Может содержать полезный контекст
   - 5: Косвенно связан с изменениями

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
            if "required_files" not in result:
                logger.warning("В ответе нет ключа 'required_files'")
                result["required_files"] = []
                
            if "explanation" not in result:
                result["explanation"] = "Объяснение не предоставлено"
                
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
                    "required_files": [],
                    "explanation": "Ошибка при анализе ответа LLM"
                }
                
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при обработке ответа: {e}")
            return {
                "required_files": [],
                "explanation": f"Ошибка при обработке ответа: {str(e)}"
            }
    

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
    discoverer = ContextDiscovery()
    
    # Пример изменённых файлов
    modified_files = [
        {
            "path": "app/views.py",
            "diff": "@@ -10,6 +10,9 @@ class UserView(ModelViewSet):\n     serializer_class = UserSerializer\n \n     def get_queryset(self):\n+        # Добавлена фильтрация по группам\n+        groups = self.request.query_params.get('groups')\n+        if groups:\n             return User.objects.filter(is_active=True)\n \n     def perform_create(self, serializer):",
            "content": "from rest_framework.viewsets import ModelViewSet\nfrom .models import User\nfrom .serializers import UserSerializer\n\nclass UserView(ModelViewSet):\n    queryset = User.objects.all()\n    serializer_class = UserSerializer\n\n    def get_queryset(self):\n        # Добавлена фильтрация по группам\n        groups = self.request.query_params.get('groups')\n        if groups:\n            return User.objects.filter(is_active=True)\n\n    def perform_create(self, serializer):\n        serializer.save()"
        }
    ]
    
    # Пример доступных файлов
    available_files = [
        "app/models.py",
        "app/serializers.py",
        "app/urls.py",
        "app/admin.py",
        "app/tests.py"
    ]
    
    # Определяем необходимые контекстные файлы
    result = discoverer.discover_required_files(modified_files, available_files)
    
    # Выводим результат
    print(json.dumps(result, indent=2))
