# GitMonitorLLM

Intelligent GitLab commit monitoring system with code analysis to identify potential errors and issues.

## Description

GitMonitorLLM is a tool that tracks commits in GitLab repositories, analyzes changes using artificial intelligence, and sends notifications to Telegram about potential problems.

Key features:
- Automatic monitoring of commits across multiple repositories
- Intelligent code change analysis using AI
- Smart identification of necessary context files for accurate analysis
- Telegram notifications with links to commits
- Detailed reports on identified issues and potential errors

## System Architecture

The system consists of the following modules:
- `main.py` - main commit monitoring module
- `context_discovery.py` - identification of context files for analysis
- `code_analyzer.py` - code analysis with context consideration
- `smart_context_analyzer.py` - enhanced analyzer with contextual understanding

## Requirements

- Python 3.8+
- Libraries: python-gitlab, aiohttp, python-telegram-bot, openai, python-dotenv
- Access to GitLab API
- API token for OpenRouter
- Telegram bot

## Installation

1. Clone the repository:
```bash
git clone https://github.com/wku/GitMonitorLLM.git
cd GitMonitorLLM
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create an `.env` file based on the example:
```bash
cp .env.example .env
```

## Integration Setup

### GitLab

1. Create a personal access token in GitLab:
   - Log in to your GitLab account
   - Go to Settings -> Access Tokens
   - Create a new token with `read_api` permissions (or `api` for full access)
   - Save the token in a secure place

2. Record your GitLab server URL, for example:
   - `https://gitlab.com` (for GitLab.com)
   - `https://gitlab.yourdomain.com` (for self-hosted GitLab)

3. Define the paths to repositories you want to monitor, such as:
   - `group/project`
   - `namespace/group/project`

### Telegram Bot

1. Create a new bot through [@BotFather](https://t.me/BotFather):
   - Send the `/newbot` command
   - Follow the instructions to create a bot
   - Get the bot's API token

2. Get the chat ID for sending notifications:
   - Add the bot to a group or start a personal conversation
   - Send a message in the chat
   - Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find `"chat":{"id":` in the response - this is the chat ID

### OpenRouter

1. Create an account on [OpenRouter](https://openrouter.ai/)
2. Get an API key in the settings section
3. Recommended models:
   - `openai/gpt-4o-mini` (used by default)
   - `anthropic/claude-3-haiku`
   - Or other models with good code analysis capabilities

## Environment Configuration

Edit the `.env` file with the following parameters:

```
# GitLab settings
GITLAB_URL=https://gitlab.yourdomain.com
GITLAB_TOKEN=your_gitlab_personal_access_token
REPOSITORIES=group/project1,group/project2

# Telegram settings
TELEGRAM_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id

# OpenRouter settings
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_MODEL=openai/gpt-4o-mini

# Additional settings
CHECK_INTERVAL=300  # check interval in seconds
DB_PATH=commits.db  # path to DB for tracking processed commits
YOUR_SITE_URL=https://example.com  # for API request headers
YOUR_SITE_NAME=GitLab Monitor  # name of your tool
```

## Running

### Basic Launch

To start monitoring with default settings:

```bash
python main.py
```

### Launch Options

1. **Monitor a specific repository**:
```bash
python main.py --repo group/specific-project
```

2. **Check commits for a certain period**:
```bash
python main.py --hours 24  # check commits for the last 24 hours
```

3. **Check commits from a specific date**:
```bash
python main.py --since "2023-10-15 08:00"
```

4. **Debug mode with extended logging**:
```bash
python main.py --debug
```

5. **Configure analysis limits**:
```bash
python main.py --max-files 10 --max-file-size 20000
```

6. **Combination of parameters**:
```bash
python main.py --repo group/project --hours 48 --debug --max-files 10
```

## How It Works

1. The system checks for new commits in the specified repositories
2. For each new commit:
   - Gets changed files
   - Uses AI to determine necessary context files
   - Retrieves context files from the repository
   - Analyzes changes with context consideration
   - Sends a report to Telegram with a description of changes and detected issues
3. Marks processed commits in a local database

## Scheduled Execution

For continuous monitoring, it's recommended to set up scheduled execution using cron or systemd:

### cron Setup Example

```bash
# Run every 5 minutes
*/5 * * * * cd /path/to/gitlab-commit-monitor && python main.py >> /var/log/commit-monitor.log 2>&1
```

### systemd Setup Example

Create a file `/etc/systemd/system/gitlab-commit-monitor.service`:

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

Then enable and start the service:

```bash
sudo systemctl enable gitlab-commit-monitor
sudo systemctl start gitlab-commit-monitor
```

## Known Issues and Solutions

### "can't concat str to bytes" Error

If you see this error in the logs when retrieving file contents, the issue is related to handling byte data from the GitLab API. Solution:

```python
# Incorrect implementation
content = project.files.get(file_path=file_path, ref=commit_id).decode()

# Correct implementation
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

### "502: GitLab is not responding" Error

Temporary GitLab API failures occur quite frequently. Recommended:

1. Implement a retry mechanism for GitLab API requests:

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
                            logger.error(f"Maximum number of attempts exceeded ({max_retries}): {e}")
                            break
                        logger.warning(f"Temporary GitLab API error: {e}. Retry {retries}/{max_retries}")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"GitLab API error: {e}")
                        break
            return None
        return wrapper
    return decorator
```

2. Increase timeouts when working with GitLab API
3. Check the stability of your connection to the GitLab server

### GitLab Authorization Errors

- Check the correctness of the token
- Make sure the token has sufficient permissions
- Verify that the GitLab URL is specified correctly

### Telegram Errors

- Make sure the bot has access to the chat
- Check the correctness of the bot token and chat ID

### OpenRouter Issues

- Check the balance and request quotas
- Make sure the API key is correct
- Check the availability of the selected model

### General Analysis Issues

- Increase `max-file-size` if files are being truncated
- Enable `--debug` mode for detailed logging
- Check the error log for analysis errors

## Notes

- The system stores information about processed commits in an SQLite database
- Large repositories may require more resources for analysis
- Analysis quality depends on the AI model used
- For best results, it's recommended to use `openai/gpt-4o-mini` or better
- When processing large projects, it's recommended to increase the `max-files` and `max-file-size` values

## Example Telegram Output

```
research/biotech/genomic-data-processor: [d3151d7](https://gitlab.com/research/biotech/genomic-data-processor/-/commit/d3151d7cbc57a64d663202ab63e4e5e4632f4efa)
[dev] Fixed retrieve method
Author: Magnus L.
Changes: Changed retrieve method call to get in the manage_sequence method of the GenomeSequenceAnalyzerViewSet class.

⚠️ Errors: In the manage_sequence method, the self.get(request) call might be incorrect, as you need to pass a pk parameter to identify the object.
```

## Contributing

Contributions to the project are welcome! Please create an issue or pull request if you have suggestions for improvement.
