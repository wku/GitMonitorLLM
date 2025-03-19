# GitLab Commit Monitoring

A system for monitoring commits in GitLab repositories with automatic analysis of changes using LLM and notification via Telegram.

## Features

- Monitoring of multiple GitLab repositories
- Analysis of code changes using LLM to identify potential errors
- Detection of code issues, including logical errors and vulnerabilities
- Sending notifications to Telegram with detailed description of changes
- Flexible configuration of monitoring parameters via command line arguments
- Support for various date formats and time zones

## Requirements

- Python 3.8+
- GitLab API access token
- OpenRouter API key (for LLM code analysis)
- Telegram bot and chat ID for sending notifications

## Installation

1. Clone the repository:
```
git clone <repository-url>
cd <repository-directory>
```

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Create a `.env` file based on the example below:
```
# GitLab settings
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxx

# Telegram settings
TELEGRAM_TOKEN=5555555555:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
CHAT_ID=123456789

# Check interval (in seconds)
CHECK_INTERVAL=300

# Path to SQLite database
DB_PATH=commits.db

# OpenRouter API settings for LLM analysis
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
YOUR_SITE_URL=https://example.com
YOUR_SITE_NAME=GitLab Monitor

# List of repositories to monitor (comma-separated)
REPOSITORIES=nordic/finance/payment-gateway,nordic/finance/transaction-service
```

## Setting up integrations

### Setting up GitLab token

1. In GitLab, go to your profile: `Preferences` → `Access Tokens`
2. Create a new token with the following permissions:
   - `read_api` (to read repository data)
   - `read_repository` (to access repository content)
3. Copy the token to the `GITLAB_TOKEN` variable in the `.env` file

### Setting up Telegram bot

1. Create a new bot via [@BotFather](https://t.me/BotFather)
2. Get the bot token and copy it to the `TELEGRAM_TOKEN` variable
3. To get the Chat ID:
   - Add the bot to the desired chat
   - Send a message to this chat
   - Get the chat ID via API: `https://api.telegram.org/bot<token>/getUpdates`
   - Copy the `chat.id` value to the `CHAT_ID` variable

### Setting up OpenRouter API

1. Register at [OpenRouter](https://openrouter.ai/)
2. Create an API key in the Settings section
3. Copy the key to the `OPENROUTER_API_KEY` variable
4. Fill in the `YOUR_SITE_URL` and `YOUR_SITE_NAME` fields for proper identification

## Usage

### Basic launch

To monitor all repositories from the list with default settings:

```
python main.py
```

### Advanced launch options

#### Monitor a specific repository

```
python main.py --repo nordic/finance/payment-gateway
```

#### Check changes from a specific time

```
python main.py --since "2025-03-19 17:22"
```

#### Check for the last N hours

```
python main.py --hours 4
```

#### Debug mode with extended logging

```
python main.py --debug
```

#### Limiting the amount of data to analyze

```
python main.py --max-files 3 --max-file-size 50000
```

#### Combination of parameters

```
python main.py --repo nordic/finance/transaction-service --hours 2 --debug
```

```
python main.py --repo nordic/finance/payment-gateway --max-file-size 128000
```

## Project Structure

- `main.py` - the main monitoring script
- `commits.db` - SQLite database for tracking processed commits
- `.env` - file with configuration parameters

## Class Description

- `DBManager` - managing SQLite database for tracking commits
- `GitLabClient` - interacting with GitLab API to get information about commits
- `LLMAnalyzer` - analyzing code changes using OpenRouter API
- `TelegramNotifier` - sending notifications via Telegram API
- `CommitMonitor` - the main class coordinating the work of all components

## Troubleshooting

### Problems with GitLab API access

Make sure that:
- The GitLab token is not expired
- The token has the necessary access rights
- The GitLab URL is specified correctly (including the https:// protocol)
- You have access to the specified repositories

### Problems with Telegram

- Make sure the bot is added to the right chat
- Check the correctness of the bot token and Chat ID
- For group chats, the ID should start with a minus (e.g., -1001234567890)

### Problems with OpenRouter API

- Check the balance and limits of your account on OpenRouter
- Make sure the `openai/gpt-4o-mini` model is available in your plan
- If you get token limit exceeded errors, reduce the `max-file-size` and `max-files` parameters

### Problems with date parsing

The system supports various GitLab date formats. In case of problems, make sure that:
- The time zone in the `--since` parameter corresponds to your local time
- By default, 'Europe/Stockholm' time zone is used

### Extended debugging

For detailed system operation analysis, use:

```
python main.py --debug --repo nordic/finance/payment-gateway
```

## Example of a Telegram notification

```
nordic/finance/payment-gateway: [a1b2c3d](https://gitlab.com/nordic/finance/payment-gateway/-/commit/a1b2c3d)
Payment processing function optimization
Author: Klaus Schmidt
Changes: Added input validation and improved error handling in API endpoints

⚠️ Errors: Possible issue with null value handling in payment_controller.py, line 127
```

## Development Plans

- GitHub integration (in development)
- Support for analyzing various programming languages
- Advanced repository filtering settings
- Interactive commands in Telegram for monitoring control

## License

MIT
