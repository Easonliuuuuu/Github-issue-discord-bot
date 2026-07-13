from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.github import GitHubCog


class FakeResponse:
    """A minimal stand-in for an aiohttp response usable as an async context manager."""

    def __init__(self, status, json_data=None, headers=None):
        self.status = status
        self._json_data = json_data if json_data is not None else {}
        self.headers = headers or {}

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Maps a URL to a fixed FakeResponse (or a callable(params) -> FakeResponse
    for endpoints that need to vary their reply, e.g. pagination)."""

    def __init__(self, responses):
        self.responses = responses

    def get(self, url, params=None):
        handler = self.responses[url]
        if callable(handler):
            return handler(params)
        return handler


def make_bot() -> MagicMock:
    bot = MagicMock()
    bot.watched_repos = {}
    bot.notified_issues = set()
    bot.get_channel = MagicMock(return_value=None)
    return bot


def make_ctx(channel_id: int, guild=None) -> MagicMock:
    ctx = MagicMock()
    ctx.channel.id = channel_id
    ctx.guild = guild
    loading_msg = MagicMock()
    loading_msg.edit = AsyncMock()
    ctx.send = AsyncMock(return_value=loading_msg)
    return ctx


@pytest.fixture
def cog() -> GitHubCog:
    # Bypass __init__ so we don't start the real background task loop.
    c = GitHubCog.__new__(GitHubCog)
    c.bot = make_bot()
    return c
