from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

DISCORD_BOT_TOKEN: str | None = os.environ.get("DISCORD_BOT_TOKEN")
GITHUB_TOKEN: str | None = os.environ.get("GITHUB_TOKEN")

CHECK_INTERVAL_MINUTES = 15


DATA_FILE_PATH = os.environ.get("DATA_FILE_PATH", "bot_data.json")

def get_github_headers() -> dict[str, str]:
    """Constructs the headers for GitHub API calls."""
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
        logger.info("Using GitHub Token for API calls.")
    else:
        logger.warning("No GitHub Token provided. You will be rate-limited (60 req/hr).")
    return headers


