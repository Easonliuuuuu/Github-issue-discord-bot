# Discord GitHub Issue Tracker Bot

A Discord bot that monitors GitHub repositories and sends notifications about new issues and pull requests with specific labels to designated channels.

[Invitation Link](https://discord.com/oauth2/authorize?client_id=1431393106523197530&permissions=19456&integration_type=0&scope=bot)

## Features

- Watch GitHub repositories for new issues, pull requests, or both
- Filter notifications by issue/PR labels
- Multiple channels/servers can independently watch the same repository with different labels or types
- Persistent, crash-safe storage of watched repositories
- Command-based interface with detailed help
- Automatic repository and label validation
- Configurable check intervals
- Rich embed notifications with highlighting
- Restricted to server managers: `!watch`/`!unwatch` require the "Manage Server" permission

## Requirements

- Python 3.9+
- discord.py==2.6.4
- aiohttp==3.13.1
- python-dotenv==1.1.1

## Setup

1. Clone this repository
2. Create a virtual environment:

   **bash / zsh (Linux/macOS):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   **PowerShell (Windows):**
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your tokens:
```env
DISCORD_BOT_TOKEN=your_discord_token
GITHUB_TOKEN=your_github_token
```

5. Run the bot:
```bash
python bot.py
```

### Running with Docker

```bash
docker build -t github-issue-bot .
docker run --env-file .env -v bot_data:/app/data -e DATA_FILE_PATH=/app/data/bot_data.json github-issue-bot
```
The volume mount keeps `bot_data.json` persistent across container restarts/rebuilds.

## Commands

- `!watch owner/repo [labels...] [--type <type>]` - Watch a repository for issues, PRs, or both **(requires Manage Server permission)**
  - Types: `issues` (default), `prs`, `all`
  - Each channel that runs `!watch` gets its own independent watch on that repo - watching the same repo from two different channels/servers (even with different labels) does not affect each other.
  - Examples:
    - `!watch microsoft/vscode "help wanted" "bug"`
    - `!watch owner/repo --type prs`
    - `!watch owner/repo "enhancement" --type all`
- `!unwatch owner/repo` - Stop watching a repository in the current channel **(requires Manage Server permission)**
- `!list` - Show all repositories being watched in the current server
- `!help [command]` - Display help information for all commands or a specific command

## Configuration

### Environment Variables

Create a `.env` file in the project root with the following variables:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
GITHUB_TOKEN=your_github_token  # Optional but recommended
DATA_FILE_PATH=bot_data.json    # Optional, defaults to bot_data.json
```

### Configuration Options

Edit `config.py` to modify:
- `CHECK_INTERVAL_MINUTES` - How often to check for new issues/PRs (default: 15 minutes)
- `DATA_FILE_PATH` - Location of the persistent data file
- GitHub API headers and version settings

### GitHub Token

While optional, providing a GitHub token is highly recommended:
- **Without token**: Rate limited to 60 requests per hour
- **With token**: Rate limited to 5000 requests per hour
- Get a token at: https://github.com/settings/tokens

The bot also watches its own rate-limit headroom during the background check loop: if a run gets close to exhausting the quota, it stops early and picks back up on the next scheduled check instead of risking a hard rate-limit block.

## Testing

Install dev dependencies and run the test suite with `pytest`:

```bash
pip install -r requirements-dev.txt
pytest
```

## Project Structure

```
├── bot.py                 # Main bot file
├── config.py               # Configuration settings
├── requirements.txt         # Runtime dependencies
├── requirements-dev.txt      # Test dependencies (pytest, pytest-asyncio)
├── Dockerfile               # Container build
├── bot_data.json            # Persistent data storage (created at runtime)
├── cogs/                    # Bot command modules
│   ├── github.py            # GitHub monitoring commands
│   └── help.py              # Help command
├── utils/                   # Utility modules
│   └── persistence.py       # Data persistence functions
└── tests/                    # Automated test suite (pytest)
```

## Usage Examples

### Basic Repository Watching
```
!watch microsoft/vscode
!watch facebook/react "help wanted" "good first issue"
```

### Pull Request Monitoring
```
!watch owner/repo --type prs
!watch microsoft/vscode "enhancement" --type all
```

### Managing Watches
```
!list                    # See all watched repositories
!unwatch microsoft/vscode # Stop watching a repository in this channel
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

MIT License

## Support

Create an issue in the repository for support requests.
