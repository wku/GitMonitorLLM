import os
import re
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

class SmartContextAnalyzer:
    """
    Класс для умного анализа кода с контекстным пониманием, который интегрируется
    в систему мониторинга коммитов GitLab для повышения точности анализа
    """
    
    def __init__(self, api_key, site_url="https://example.com", site_name="GitMonitorLLM", model="openai/gpt-4o-mini"):
        """
        Инициализация анализатора кода
        
        Args:
            api_key (str): API ключ для OpenRouter
            site_url (str): URL сайта для заголовков запросов
            site_name (str): Название сайта для заголовков запросов
            model (str): Модель LLM для использования
        """
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
        self.model = model
        self.site_url = site_url
        self.site_name = site_name
        logger.info(f"SmartContextAnalyzer инициализирован с моделью {model}")
    
    def discover_required_files(self, modified_files, available_files=None):
        """
        Определяет, какие дополнительные файлы необходимы для анализа кода
        
        Args:
            modified_files (list): Список словарей с измененными файлами
                [{path: str, diff: str, old_content: str, new_content: str}, ...]
            available_files (list): Список доступных файлов в репозитории
            
        Returns:
            list: Список информации о требуемых файлах
        """
        prompt = self._create_discovery_prompt(modified_files, available_files)
        
        try:
            logger.info("Отправка запроса для определения необходимых контекстных файлов...")
            
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": self.site_url,
                    "X-Title": self.site_name,
                },
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1500
            )
            
            response_text = completion.choices[0].message.content
            logger.debug(f"Ответ на запрос обнаружения контекста получен, длина: {len(response_text)}")
            
            # Извлекаем и парсим JSON из ответа
            result = self._extract_json_response(response_text)
            
            if "required_files" not in result:
                result["required_files"] = []
                
            if "explanation" not in result:
                result["explanation"] = "Объяснение не предоставлено"
                
            logger.info(f"Определено {len(result.get('required_files', []))} необходимых файлов")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при запросе на обнаружение контекста: {e}")
            return {"required_files": [], "explanation": f"Ошибка: {str(e)}"}
    
    def analyze_with_context(self, modified_files, context_files=None):
        """
        Анализирует измененные файлы с учетом контекстных файлов
        
        Args:
            modified_files (list): Список словарей с измененными файлами
            context_files (list): Список словарей с контекстными файлами
            
        Returns:
            dict: Результат анализа с обнаруженными проблемами
        """
        prompt = self._create_analysis_prompt(modified_files, context_files)
        
        try:
            logger.info(f"Отправка запроса для анализа кода (контекстных файлов: {len(context_files) if context_files else 0})...")
            
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": self.site_url,
                    "X-Title": self.site_name,
                },
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=2000
            )
            
            response_text = completion.choices[0].message.content
            logger.debug(f"Ответ на запрос анализа кода получен, длина: {len(response_text)}")
            
            # Извлекаем и парсим JSON из ответа
            result = self._extract_json_response(response_text)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при запросе на анализ кода: {e}")
            return {"description": "", "errors": "Нет явных ошибок"}
    
    def _create_discovery_prompt(self, modified_files, available_files=None):
        """
        Создает промпт для определения необходимых контекстных файлов
        
        Args:
            modified_files (list): Список модифицированных файлов
            available_files (list): Список доступных файлов
            
        Returns:
            str: Промпт для LLM
        """
        prompt = """
### ЗАДАЧА ОПРЕДЕЛЕНИЯ КОНТЕКСТНЫХ ФАЙЛОВ ДЛЯ АНАЛИЗА КОДА ###

# ИНСТРУКЦИИ
Ты - эксперт по анализу кода. Твоя задача - проанализировать измененные файлы и определить, какие дополнительные файлы необходимы для полного понимания контекста изменений.

Нужно найти файлы, которые:
1. Содержат классы или функции, от которых наследуются или с которыми взаимодействуют измененные файлы
2. Содержат импортируемые локальные модули и их зависимости
3. Определяют интерфейсы, константы или типы, используемые в измененном коде
4. Могут содержать определения методов, которые вызываются или переопределяются

# ИЗМЕНЕННЫЕ ФАЙЛЫ:
"""
        
        # Добавляем изменённые файлы
        for i, file in enumerate(modified_files):
            prompt += f"\n## ФАЙЛ {i+1}: {file['path']}\n"
            
            # Добавляем diff если есть
            if 'diff' in file and file['diff']:
                prompt += f"### Изменения (diff):\n```diff\n{file['diff']}\n```\n"
                
            # Добавляем старое содержимое если есть
            if 'old_content' in file and file['old_content']:
                prompt += f"### Содержимое до изменений:\n```python\n{file['old_content']}\n```\n"
                
            # Добавляем новое содержимое
            if 'new_content' in file and file['new_content']:
                prompt += f"### Содержимое после изменений:\n```python\n{file['new_content']}\n```\n"
        
        # Добавляем список доступных файлов, если есть
        if available_files:
            prompt += "\n# ДОСТУПНЫЕ ФАЙЛЫ В РЕПОЗИТОРИИ:\n"
            file_list = "\n".join([f"- {path}" for path in available_files[:100]])  # Ограничиваем 100 файлами
            prompt += file_list
            
            if len(available_files) > 100:
                prompt += f"\n... и еще {len(available_files) - 100} файлов"
        
        # Инструкции по формату ответа
        prompt += """
# ФОРМАТ ОТВЕТА
Проанализируй код и верни JSON в следующем формате:

{
  "required_files": [
    {
      "path": "путь/к/файлу.py",
      "reason": "Четкое объяснение, почему этот файл нужен для анализа",
      "priority": 1-5 (1 - критически важно, 5 - может быть полезно)
    },
    ...
  ],
  "explanation": "Краткое обоснование выбранных файлов"
}

# ВАЖНЫЕ ПРАВИЛА
1. Возвращай ТОЛЬКО файлы, которые ДЕЙСТВИТЕЛЬНО необходимы для понимания контекста
2. Если контекстные файлы не нужны, верни пустой список required_files
3. При выборе из доступных файлов, отдавай предпочтение файлам из тех же директорий
4. Указывай точный путь к файлу из списка доступных файлов, если он там есть
5. Приоритет должен отражать важность файла (1 - наиболее важно, 5 - наименее важно)

Возвращай ТОЛЬКО JSON без дополнительных комментариев.
"""
        return prompt
    
    def _create_analysis_prompt(self, modified_files, context_files):
        """
        Создает промпт для анализа кода с учетом контекста
        
        Args:
            modified_files (list): Список модифицированных файлов
            context_files (list): Список контекстных файлов
            
        Returns:
            str: Промпт для LLM
        """
        prompt = """
### ЗАДАЧА АНАЛИЗА ИЗМЕНЕНИЙ КОДА С УЧЕТОМ КОНТЕКСТА ###

# ИНСТРУКЦИИ
Ты - эксперт по анализу кода, специализирующийся на Python, Django, React и JavaScript. Твоя задача - проанализировать изменения в коде и найти потенциальные проблемы или ошибки.

Анализируй только явные проблемы, которые могут вызвать ошибки:
1. Синтаксические ошибки Python
2. Несуществующие методы или параметры (с учетом контекста фреймворков)
3. Несоответствие сигнатур функций
4. Логические ошибки или уязвимости
5. Нарушения общих паттернов и практик

# ИЗМЕНЕННЫЕ ФАЙЛЫ:
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
            if 'new_content' in file and file['new_content']:
                prompt += f"### Содержимое после изменений:\n```python\n{file['new_content']}\n```\n"
        
        # Добавляем контекстные файлы, если есть
        if context_files:
            prompt += "\n# КОНТЕКСТНЫЕ ФАЙЛЫ ДЛЯ АНАЛИЗА:\n"
            
            # Сортируем контекстные файлы по приоритету (если есть)
            sorted_context = sorted(context_files, 
                                    key=lambda x: x.get("priority", 5) 
                                    if isinstance(x.get("priority"), int) else 5)
            
            for i, file in enumerate(sorted_context):
                priority_str = f" (Приоритет: {file.get('priority', 5)})" if "priority" in file else ""
                prompt += f"\n## КОНТЕКСТНЫЙ ФАЙЛ {i+1}: {file['path']}{priority_str}\n"
                prompt += f"```python\n{file['content']}\n```\n"
        
        # Инструкции по формату ответа - адаптируем под существующий формат
        prompt += """
# ФОРМАТ ОТВЕТА
Верни JSON в следующем формате:

{
  "description": "Краткое описание изменений в одном предложении",
  "errors": "Подробное описание найденных проблем или 'Нет явных ошибок'"
}

# ВАЖНЫЕ ПРАВИЛА
1. Учитывай особенности фреймворков при анализе:
   - Django/DRF часто предоставляет методы через наследование
   - Python позволяет динамическую типизацию
   - Не считай проблемой отсутствие типов

2. В поле "description" пиши только суть изменений одним предложением  

3. В поле "errors" указывай только:
   - Файл и строку, где найдена проблема
   - Краткое описание проблемы
   - Предлагаемое решение (опционально)

4. Если проблем не обнаружено, в поле "errors" пиши "Нет явных ошибок"

5. ОЧЕНЬ ВАЖНО: Не сообщай о проблемах без 100% уверенности. 
   Если нет полного контекста - не предполагай ошибку.
   Лучше не указать проблему, чем указать ложную.

Возвращай ТОЛЬКО JSON без дополнительных комментариев.
"""
        return prompt
    
    def _extract_json_response(self, response_text):
        """
        Извлекает и парсит JSON из ответа LLM
        
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
                return {"error": "Ошибка при анализе ответа LLM"}
                
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при обработке ответа: {e}")
            return {"error": f"Ошибка при обработке ответа: {str(e)}"}


class LLMAnalyzer:
    """
    Обновленный класс LLMAnalyzer, интегрирующий SmartContextAnalyzer
    для анализа коммитов с учетом контекста
    """
    
    def __init__(self, api_key, site_url, site_name):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": site_url,
            "X-Title": site_name,
            "Content-Type": "application/json"
        }
        self.site_url = site_url
        self.site_name = site_name
        self.context_analyzer = SmartContextAnalyzer(api_key, site_url, site_name)
        logger.info("LLM анализатор инициализирован с поддержкой контекста")
    
    async def analyze_changes(self, modified_files, gitlab_client=None, project_path=None, commit_id=None, debug_mode=False):
        """
        Анализирует изменения в коммите с учетом контекста
        
        Args:
            modified_files (list): Список измененных файлов
            gitlab_client (object, optional): Клиент GitLab для получения контекстных файлов
            project_path (str, optional): Путь к проекту
            commit_id (str, optional): ID коммита
            debug_mode (bool): Режим отладки
            
        Returns:
            tuple: (описание изменений, обнаруженные ошибки)
        """
        # Шаг 1: Определяем необходимые контекстные файлы
        if gitlab_client and project_path and commit_id:
            logger.info("Запуск умного анализа с контекстом...")
            
            # Запрашиваем структуру репозитория для контекстного анализа
            try:
                # Получаем структуру доступных файлов в репозитории
                project = gitlab_client.get_project(project_path)
                if project:
                    available_files = []
                    try:
                        # Получаем список файлов в репозитории
                        items = project.repository_tree(ref=commit_id, recursive=True, per_page=500, get_all=True)
                        available_files = [item['path'] for item in items if item['type'] == 'blob']
                        logger.info(f"Получено {len(available_files)} файлов из репозитория")
                    except Exception as e:
                        logger.error(f"Ошибка при получении файлов из репозитория: {e}")
                
                    # Определяем, какие файлы нужны для контекста
                    context_result = self.context_analyzer.discover_required_files(modified_files, available_files)
                    required_files = context_result.get("required_files", [])
                    
                    if required_files:
                        logger.info(f"Требуется получить {len(required_files)} контекстных файлов")
                        context_files = []
                        
                        # Получаем контекстные файлы
                        for file_info in required_files:
                            file_path = file_info.get("path")
                            priority = file_info.get("priority", 5)
                            
                            try:
                                content = await gitlab_client.get_file_content(project, file_path, commit_id)
                                if content:
                                    context_files.append({
                                        "path": file_path,
                                        "content": content,
                                        "priority": priority
                                    })
                                    logger.info(f"Получен контекстный файл: {file_path}")
                                else:
                                    logger.warning(f"Не удалось получить содержимое файла: {file_path}")
                            except Exception as e:
                                logger.error(f"Ошибка при получении файла {file_path}: {e}")
                        
                        # Анализируем код с учетом контекста
                        if context_files:
                            logger.info(f"Запуск анализа с {len(context_files)} контекстными файлами")
                            analysis = self.context_analyzer.analyze_with_context(modified_files, context_files)
                            
                            description = analysis.get("description", "")
                            errors = analysis.get("errors", "Нет явных ошибок")
                            
                            return description, errors
            except Exception as e:
                logger.error(f"Ошибка при умном анализе с контекстом: {e}")
                # Продолжаем обычный анализ в случае ошибки
        
        # Если контекстный анализ не удался или не запрошен, используем стандартный подход
        if debug_mode:
            logger.info("[DEBUG] Выполняем стандартный анализ без контекста")
        
        # Разбиваем анализ на несколько более мелких запросов, если необходимо
        if len(modified_files) > 3:
            # Если файлов слишком много, анализируем по частям
            batches = []
            current_batch = []
            current_size = 0
            max_batch_size = 30000  # Увеличенное ограничение размера пакета
            
            for file in modified_files:
                file_size = len(file['diff']) + len(file.get('new_content') or '') + len(file.get('old_content') or '')
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
                if errors and errors != "Нет явных ошибок":
                    all_errors.append(errors)
            
            final_desc = " ".join(all_descriptions)
            final_errors = "Нет явных ошибок" if not all_errors else "\n".join(all_errors)
            
            return final_desc, final_errors
        else:
            # Если файлов немного, анализируем все сразу
            return await self._analyze_batch(modified_files, debug_mode)
    
    async def _analyze_batch(self, file_batch, debug_mode=False):
        """
        Анализирует пакет файлов (стандартный подход)
        """
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
            # Увеличиваем лимит токенов и снижаем температуру для более точного анализа
            "max_tokens": 1200,
            "temperature": 0.2
        }
        
        try:
            import aiohttp
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
                    errors = parts[1].strip() if len(parts) > 1 else "Нет явных ошибок"
                    
                    logger.debug(f"Анализ получен, длина: {len(analysis)}")
                    return desc, errors
        except Exception as e:
            logger.error(f"Ошибка анализа: {e}")
            return None, None
    
    def _create_prompt(self, modified_files):
        """
        Стандартный промт для LLM анализа (без контекста)
        """
        # Сохраняем ваш текущий промт без изменений
        prompt = """
Ты эксперт по код-ревью для Python/Django с глубоким пониманием Django Rest Framework, Django ORM и React/JavaScript

Твоя задача - найти только реальные проблемы в предоставленном коде, избегая ложных предположений

ВАЖНО! Специфика Django Rest Framework (DRF):
- ViewSet классы автоматически получают методы list, create, retrieve, update, partial_update, destroy
- GenericAPIView и миксины предоставляют методы get_queryset, get_object, get_serializer и т.д.
- APIView имеет методы get, post, put, patch, delete, которые обрабатывают соответствующие HTTP-запросы
- Переопределение методов (как retrieve на get или наоборот) - это нормальная практика в DRF
- Методы как retrieve и get могут быть кастомизированы и принимать различные аргументы
- self.request доступен во ViewSet и APIView, для доступа к параметрам запроса

ОСНОВНЫЕ ПРАВИЛА АНАЛИЗА:
1. Ищи только 100% подтвержденные ошибки:
   - Синтаксические ошибки в Python коде
   - Нарушения сигнатуры методов, где полностью видно определение
   - Явные несоответствия между вызовами функций и их определениями в представленном коде
   - Реальные проблемы безопасности (SQL-инъекции, XSS, отсутствие проверки прав)
   - Критичные проблемы производительности (например, N+1 запросы)

2. НЕ считай ошибкой:
   - Вызовы методов, которые могут существовать в базовых классах, даже если их определение не показано
   - Изменения в вызовах методов (например, с retrieve на get) - это может быть правильным рефакторингом
   - Разные сигнатуры стандартных методов DRF - они могут быть переопределены
   - Отсутствующие импорты или модули - они могут существовать в проекте
   - Стилистические или форматные несоответствия

3. Учитывай контекст Django/DRF:
   - Сигнатуры методов часто переопределяются в наследниках
   - В Django/DRF много магических методов через наследование и метаклассы
   - Многие методы доступны через миксины и базовые классы без явного определения
   - queryset, serializer_class, permission_classes - это нормальные атрибуты класса в DRF

ФОРМАТ ОТВЕТА:
1. Краткое описание изменений: одно предложение о сути изменений
2. Ошибки: ТОЛЬКО если 100% уверен, опиши:
   - Точную проблему
   - Файл и строку
   - Краткое объяснение

Если нет 100% уверенности в наличии ошибок, напиши: "Нет явных ошибок"
"""
        
        # Добавляем измененные файлы
        for idx, file in enumerate(modified_files):
            file_summary = f"\nИЗМЕНЕННЫЙ ФАЙЛ {idx+1}: {file['path']}\n\n"
            
            # Добавляем содержимое файла до изменений, если оно есть
            if file.get('old_content'):
                file_summary += f"СОДЕРЖИМОЕ ДО ИЗМЕНЕНИЙ:\n```python\n{file['old_content']}\n```\n\n"
            
            # Добавляем дифф для наглядности изменений
            file_summary += f"ИЗМЕНЕНИЯ (DIFF):\n```diff\n{file['diff']}\n```\n\n"
            
            # Добавляем новое содержимое файла для полного контекста
            if file.get('new_content'):
                file_summary += f"СОДЕРЖИМОЕ ПОСЛЕ ИЗМЕНЕНИЙ:\n```python\n{file['new_content']}\n```\n\n"
            
            prompt += file_summary
        
        # Заключительная инструкция
        prompt += """
Проанализируй только представленный код и его контекст. Не делай предположений без явных доказательств.
Помни: лучше не указать ошибку, чем указать ложную. Укажи ошибку только если ты 100% уверен.

Формат ответа:
1. Краткое описание изменений: [суть изменений в одном предложении]
2. Ошибки: [если 100% уверен, опиши точную проблему, файл, строку и краткое объяснение]
"""
        
        logger.debug(f"Создан промт, длина: {len(prompt)}")
        return prompt
