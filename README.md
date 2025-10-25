# Discord GitHub Issue Tracker Bot

A Discord bot that monitors GitHub repositories and sends notifications about new issues with specific labels to designated channels.

## Features

- Watch GitHub repositories for new issues
- Filter notifications by issue labels
- Multiple channel support
- Persistent storage of watched repositories
- Command-based interface

## Requirements

- Python 3.8+
- Discord.py library
- aiohttp
- python-dotenv

## Setup

1. Clone this repository
2. Create a virtual environment:
```powershell
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies:
```powershell
pip install discord.py aiohttp python-dotenv
```

4. Create a `.env` file with your tokens:
```env
DISCORD_BOT_TOKEN=your_discord_token
GITHUB_TOKEN=your_github_token
```

5. Run the bot:
```powershell
python bot.py
```

## Commands

- `!watch owner/repo ["label1" "label2"]` - Watch a repository (optionally with specific labels)
- `!unwatch owner/repo` - Stop watching a repository
- `!list` - Show all watched repositories
- `!help` - Display help information

## Configuration

Edit `config.py` to modify:
- Check interval for new issues
- Data file location
- API settings

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

MIT License

## Support

Create an issue in the repository for support requests.