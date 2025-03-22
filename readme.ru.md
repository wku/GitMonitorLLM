# GitMonitorLLM

Интеллектуальная система мониторинга коммитов GitLab с анализом кода для выявления потенциальных ошибок и проблем.

## Описание

GitMonitorLLM - это инструмент, который отслеживает коммиты в репозиториях GitLab, анализирует изменения с помощью модели искусственного интеллекта и отправляет уведомления в Telegram о потенциальных проблемах.

Ключевые возможности:
- Автоматическое отслеживание коммитов в нескольких репозиториях
- Интеллектуальный анализ изменений кода с использованием AI
- Умное определение необходимых контекстных файлов для точного анализа
- Оповещения в Telegram с ссылками на коммиты
- Подробные отчеты о найденных проблемах и потенциальных ошибках

## Архитектура системы

Система состоит из следующих модулей:
- `main.py` - основной модуль мониторинга коммитов
- `context_discovery.py` - определение контекстных файлов для анализа
- `code_analyzer.py` - анализ кода с учетом контекста
- `smart_context_analyzer.py` - улучшенный анализатор с контекстным пониманием

## Требования

- Python 3.8+
- Библиотеки: python-gitlab, aiohttp, python-telegram-bot, openai, python-dotenv
- Доступ к GitLab API
- Токен API для OpenRouter
- Telegram бот

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/wku/GitMonitorLLM.git
cd GitMonitorLLM
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` на основе примера:
```bash
cp .env.example .env
```

## Настройка интеграций

### GitLab

1. Создайте персональный токен доступа в GitLab:
   - Войдите в свой GitLab аккаунт
   - Перейдите в Settings -> Access Tokens
   - Создайте новый токен с правами `read_api` (или `api` для полного доступа)
   - Сохраните токен в безопасном месте

2. Запишите URL вашего GitLab сервера, например:
   - `https://gitlab.com` (для GitLab.com)
   - `https://gitlab.yourdomain.com` (для self-hosted GitLab)

3. Определите пути к репозиториям, которые хотите мониторить, например:
   - `group/project`
   - `namespace/group/project`

### Telegram Bot

1. Создайте нового бота через [@BotFather](https://t.me/BotFather):
   - Отправьте команду `/newbot`
   - Следуйте инструкциям для создания бота
   - Получите токен API бота

2. Получите ID чата для отправки уведомлений:
   - Добавьте бота в группу или начните личную переписку
   - Отправьте сообщение в чат
   - Посетите `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Найдите `"chat":{"id":` в ответе - это и есть ID чата

### OpenRouter

1. Создайте аккаунт на [OpenRouter](https://openrouter.ai/)
2. Получите API ключ в разделе настроек
3. Рекомендуемые модели:
   - `openai/gpt-4o-mini` (используется по умолчанию)
   - `anthropic/claude-3-haiku`
   - Или другие модели с хорошими возможностями анализа кода

## Настройка окружения

Отредактируйте файл `.env` со следующими параметрами:

```
# GitLab настройки
GITLAB_URL=https://gitlab.yourdomain.com
GITLAB_TOKEN=your_gitlab_personal_access_token
REPOSITORIES=group/project1,group/project2

# Telegram настройки
TELEGRAM_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id

# OpenRouter настройки
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_MODEL=openai/gpt-4o-mini

# Дополнительные настройки
CHECK_INTERVAL=300  # интервал проверки в секундах
DB_PATH=commits.db  # путь к БД для отслеживания обработанных коммитов
YOUR_SITE_URL=https://example.com  # для заголовков запросов к API
YOUR_SITE_NAME=GitLab Monitor  # имя вашего инструмента
```

## Запуск

### Базовый запуск

Для запуска мониторинга с настройками по умолчанию:

```bash
python main.py
```

### Варианты запуска

1. **Мониторинг конкретного репозитория**:
```bash
python main.py --repo group/specific-project
```

2. **Проверка коммитов за определенный период**:
```bash
python main.py --hours 24  # проверить коммиты за последние 24 часа
```

3. **Проверка коммитов с определенной даты**:
```bash
python main.py --since "2023-10-15 08:00"
```

4. **Режим отладки с расширенным логированием**:
```bash
python main.py --debug
```

5. **Настройка лимитов анализа**:
```bash
python main.py --max-files 10 --max-file-size 20000
```

6. **Комбинация параметров**:
```bash
python main.py --repo group/project --hours 48 --debug --max-files 10
```

## Как это работает

1. Система проверяет новые коммиты в указанных репозиториях
2. Для каждого нового коммита:
   - Получает измененные файлы
   - Использует AI для определения необходимых контекстных файлов
   - Получает контекстные файлы из репозитория
   - Анализирует изменения с учетом контекста
   - Отправляет отчет в Telegram с описанием изменений и обнаруженных проблем
3. Отмечает обработанные коммиты в локальной БД

## Планирование запусков

Для непрерывного мониторинга рекомендуется настроить запуск с помощью cron или systemd:

### Пример настройки cron

```bash
# Запуск каждые 5 минут
*/5 * * * * cd /path/to/gitlab-commit-monitor && python main.py >> /var/log/commit-monitor.log 2>&1
```

### Пример настройки systemd

Создайте файл `/etc/systemd/system/gitlab-commit-monitor.service`:

```
[Unit]
Description=GitMonitorLLM Service
After=network.target

[Service]
User=youruser
WorkingDirectory=/path/to/gitlab-commit-monitor
ExecStart=/usr/bin/python3 /path/to/gitlab-commit-monitor/main.py
Restart=always
RestartSec=300

[Install]
WantedBy=multi-user.target
```

Затем включите и запустите сервис:

```bash
sudo systemctl enable gitlab-commit-monitor
sudo systemctl start gitlab-commit-monitor
```

## Известные проблемы и решения

### Ошибка "can't concat str to bytes"

Если вы видите эту ошибку в логах при получении содержимого файлов, проблема связана с обработкой байтовых данных из GitLab API. Решение:

```python
# Неправильная реализация
content = project.files.get(file_path=file_path, ref=commit_id).decode()

# Правильная реализация
file_obj = project.files.get(file_path=file_path, ref=commit_id)
if hasattr(file_obj, 'content'):
    content = file_obj.content
    if isinstance(content, str):
        return content
    else:
        import base64
        return base64.b64decode(content).decode('utf-8', errors='replace')
elif hasattr(file_obj, 'decode'):
    return file_obj.decode()
```

### Ошибка "502: GitLab is not responding"

Временные сбои в работе GitLab API встречаются довольно часто. Рекомендуется:

1. Реализовать механизм повторных попыток (retry mechanism) для GitLab API запросов:

```python
def gitlab_retry(max_retries=3, retry_delay=5):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except gitlab.exceptions.GitlabError as e:
                    if hasattr(e, 'response_code') and e.response_code in [429, 500, 502, 503, 504]:
                        retries += 1
                        if retries >= max_retries:
                            logger.error(f"Превышено максимальное число попыток ({max_retries}): {e}")
                            break
                        logger.warning(f"Временная ошибка GitLab API: {e}. Повторная попытка {retries}/{max_retries}")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"Ошибка GitLab API: {e}")
                        break
            return None
        return wrapper
    return decorator
```

2. Увеличить таймауты при работе с GitLab API
3. Проверить стабильность вашего соединения с GitLab сервером

### Ошибки авторизации GitLab

- Проверьте правильность токена
- Убедитесь, что у токена достаточно прав
- Проверьте, что URL GitLab указан верно

### Ошибки Telegram

- Убедитесь, что бот имеет доступ к чату
- Проверьте правильность токена бота и ID чата

### Проблемы с OpenRouter

- Проверьте баланс и квоты на запросы
- Убедитесь в правильности API ключа
- Проверьте доступность выбранной модели

### Общие проблемы с анализом

- Увеличьте `max-file-size` если файлы обрезаются
- Включите режим отладки `--debug` для получения подробного лога
- Проверьте журнал ошибок на наличие ошибок анализа

## Примечания

- Система хранит информацию об обработанных коммитах в SQLite базе данных
- Большие репозитории могут требовать больше ресурсов для анализа
- Качество анализа зависит от используемой модели AI
- Для достижения наилучших результатов рекомендуется использовать `openai/gpt-4o-mini` или лучше
- При обработке больших проектов рекомендуется увеличить значения `max-files` и `max-file-size`

## Пример вывода в Telegram

```
research/biotech/genomic-data-processor: d3151d7
[разработка] Исправлен метод retrieve
Автор: Магнус Л
Изменения: Изменен вызов метода retrieve на get в методе manage_sequence класса GenomeSequenceAnalyzerViewSet
⚠️ Ошибки: В методе manage_sequence вызов self.get(request) может быть некорректным, так как необходимо передать параметр pk для идентификации объекта
```

## Контрибьютинг

Вклады в проект приветствуются! Пожалуйста, создайте issue или pull request, если у вас есть предложения по улучшению.
