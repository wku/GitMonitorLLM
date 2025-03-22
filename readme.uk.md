# GitMonitorLLM

Інтелектуальна система моніторингу комітів GitLab з аналізом коду для виявлення потенційних помилок та проблем.

## Опис

GitMonitorLLM - це інструмент, який відстежує коміти в репозиторіях GitLab, аналізує зміни за допомогою штучного інтелекту та надсилає повідомлення в Telegram про потенційні проблеми.

Ключові можливості:
- Автоматичне відстеження комітів у декількох репозиторіях
- Інтелектуальний аналіз змін коду з використанням AI
- Розумне визначення необхідних контекстних файлів для точного аналізу
- Сповіщення в Telegram з посиланнями на коміти
- Детальні звіти про знайдені проблеми та потенційні помилки

## Архітектура системи

Система складається з наступних модулів:
- `main.py` - основний модуль моніторингу комітів
- `context_discovery.py` - визначення контекстних файлів для аналізу
- `code_analyzer.py` - аналіз коду з урахуванням контексту
- `smart_context_analyzer.py` - покращений аналізатор з контекстним розумінням

## Вимоги

- Python 3.8+
- Бібліотеки: python-gitlab, aiohttp, python-telegram-bot, openai, python-dotenv
- Доступ до GitLab API
- Токен API для OpenRouter
- Telegram бот

## Встановлення

1. Клонуйте репозиторій:
```bash
git clone https://github.com/wku/GitMonitorLLM.git
cd GitMonitorLLM
```

2. Встановіть залежності:
```bash
pip install -r requirements.txt
```

3. Створіть файл `.env` на основі прикладу:
```bash
cp .env.example .env
```

## Налаштування інтеграцій

### GitLab

1. Створіть персональний токен доступу в GitLab:
   - Увійдіть у свій GitLab акаунт
   - Перейдіть до Settings -> Access Tokens
   - Створіть новий токен з правами `read_api` (або `api` для повного доступу)
   - Збережіть токен у безпечному місці

2. Запишіть URL вашого GitLab сервера, наприклад:
   - `https://gitlab.com` (для GitLab.com)
   - `https://gitlab.yourdomain.com` (для self-hosted GitLab)

3. Визначте шляхи до репозиторіїв, які хочете моніторити, наприклад:
   - `group/project`
   - `namespace/group/project`

### Telegram Bot

1. Створіть нового бота через [@BotFather](https://t.me/BotFather):
   - Відправте команду `/newbot`
   - Дотримуйтесь інструкцій для створення бота
   - Отримайте токен API бота

2. Отримайте ID чату для надсилання сповіщень:
   - Додайте бота до групи або почніть особисте листування
   - Відправте повідомлення в чат
   - Відвідайте `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Знайдіть `"chat":{"id":` у відповіді - це і є ID чату

### OpenRouter

1. Створіть акаунт на [OpenRouter](https://openrouter.ai/)
2. Отримайте API ключ у розділі налаштувань
3. Рекомендовані моделі:
   - `openai/gpt-4o-mini` (використовується за замовчуванням)
   - `anthropic/claude-3-haiku`
   - Або інші моделі з хорошими можливостями аналізу коду

## Налаштування середовища

Відредагуйте файл `.env` з наступними параметрами:

```
# GitLab налаштування
GITLAB_URL=https://gitlab.yourdomain.com
GITLAB_TOKEN=your_gitlab_personal_access_token
REPOSITORIES=group/project1,group/project2

# Telegram налаштування
TELEGRAM_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id

# OpenRouter налаштування
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_MODEL=openai/gpt-4o-mini

# Додаткові налаштування
CHECK_INTERVAL=300  # інтервал перевірки в секундах
DB_PATH=commits.db  # шлях до БД для відстеження оброблених комітів
YOUR_SITE_URL=https://example.com  # для заголовків запитів до API
YOUR_SITE_NAME=GitLab Monitor  # назва вашого інструменту
```

## Запуск

### Базовий запуск

Для запуску моніторингу з налаштуваннями за замовчуванням:

```bash
python main.py
```

### Варіанти запуску

1. **Моніторинг конкретного репозиторію**:
```bash
python main.py --repo group/specific-project
```

2. **Перевірка комітів за певний період**:
```bash
python main.py --hours 24  # перевірити коміти за останні 24 години
```

3. **Перевірка комітів з певної дати**:
```bash
python main.py --since "2023-10-15 08:00"
```

4. **Режим відлагодження з розширеним логуванням**:
```bash
python main.py --debug
```

5. **Налаштування лімітів аналізу**:
```bash
python main.py --max-files 10 --max-file-size 20000
```

6. **Комбінація параметрів**:
```bash
python main.py --repo group/project --hours 48 --debug --max-files 10
```

## Як це працює

1. Система перевіряє нові коміти у вказаних репозиторіях
2. Для кожного нового коміту:
   - Отримує змінені файли
   - Використовує AI для визначення необхідних контекстних файлів
   - Отримує контекстні файли з репозиторію
   - Аналізує зміни з урахуванням контексту
   - Надсилає звіт у Telegram з описом змін та виявлених проблем
3. Позначає оброблені коміти в локальній БД

## Планування запусків

Для безперервного моніторингу рекомендується налаштувати запуск за допомогою cron або systemd:

### Приклад налаштування cron

```bash
# Запуск кожні 5 хвилин
*/5 * * * * cd /path/to/gitlab-commit-monitor && python main.py >> /var/log/commit-monitor.log 2>&1
```

### Приклад налаштування systemd

Створіть файл `/etc/systemd/system/gitlab-commit-monitor.service`:

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

Потім увімкніть та запустіть сервіс:

```bash
sudo systemctl enable gitlab-commit-monitor
sudo systemctl start gitlab-commit-monitor
```

## Відомі проблеми та рішення

### Помилка "can't concat str to bytes"

Якщо ви бачите цю помилку в логах при отриманні вмісту файлів, проблема пов'язана з обробкою байтових даних з GitLab API. Рішення:

```python
# Неправильна реалізація
content = project.files.get(file_path=file_path, ref=commit_id).decode()

# Правильна реалізація
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

### Помилка "502: GitLab is not responding"

Тимчасові збої в роботі GitLab API зустрічаються досить часто. Рекомендується:

1. Реалізувати механізм повторних спроб (retry mechanism) для GitLab API запитів:

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
                            logger.error(f"Перевищено максимальну кількість спроб ({max_retries}): {e}")
                            break
                        logger.warning(f"Тимчасова помилка GitLab API: {e}. Повторна спроба {retries}/{max_retries}")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"Помилка GitLab API: {e}")
                        break
            return None
        return wrapper
    return decorator
```

2. Збільшити таймаути при роботі з GitLab API
3. Перевірити стабільність вашого з'єднання з GitLab сервером

### Помилки авторизації GitLab

- Перевірте правильність токена
- Переконайтеся, що у токена достатньо прав
- Перевірте, що URL GitLab вказано вірно

### Помилки Telegram

- Переконайтеся, що бот має доступ до чату
- Перевірте правильність токена бота та ID чату

### Проблеми з OpenRouter

- Перевірте баланс та квоти на запити
- Переконайтеся у правильності API ключа
- Перевірте доступність обраної моделі

### Загальні проблеми з аналізом

- Збільште `max-file-size` якщо файли обрізаються
- Увімкніть режим відлагодження `--debug` для отримання докладного логу
- Перевірте журнал помилок на наявність помилок аналізу

## Примітки

- Система зберігає інформацію про оброблені коміти в SQLite базі даних
- Великі репозиторії можуть вимагати більше ресурсів для аналізу
- Якість аналізу залежить від використовуваної моделі AI
- Для досягнення найкращих результатів рекомендується використовувати `openai/gpt-4o-mini` або краще
- При обробці великих проектів рекомендується збільшити значення `max-files` та `max-file-size`

## Приклад виводу в Telegram

```
research/biotech/genomic-data-processor: d3151d7
[розробка] Виправлено метод retrieve
Автор: Магнус Л
Зміни: Змінено виклик методу retrieve на get у методі manage_sequence класу GenomeSequenceAnalyzerViewSet
⚠️ Помилки: У методі manage_sequence виклик self.get(request) може бути некоректним, оскільки необхідно передати параметр pk для ідентифікації об'єкта
```

## Контриб'ютинг

Внески у проект вітаються! Будь ласка, створіть issue або pull request, якщо у вас є пропозиції щодо покращення.
