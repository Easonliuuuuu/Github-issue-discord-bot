from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.github as github_module
from cogs.github import GitHubCog
from tests.conftest import FakeResponse, FakeSession, make_ctx


@pytest.fixture(autouse=True)
def no_real_save(monkeypatch):
    """Every command test in this module touches watched_repos/notified_issues
    and calls save_data() - never let that hit the real filesystem."""
    monkeypatch.setattr(github_module, "save_data", MagicMock())


async def test_watch_repo_adds_channel_without_clobbering_other_channels(cog):
    cog.bot.watched_repos = {
        "owner/repo": {
            "111": {"labels": [], "watch_since_time": "2026-01-01T00:00:00Z", "watch_type": "issues"},
        }
    }
    cog.bot.http_session = FakeSession({
        "https://api.github.com/repos/owner/repo": FakeResponse(200),
    })

    ctx = make_ctx(channel_id=222)
    await GitHubCog.watch_repo.callback(cog, ctx, "owner/repo")

    channels = cog.bot.watched_repos["owner/repo"]
    assert set(channels.keys()) == {"111", "222"}
    assert channels["111"]["watch_since_time"] == "2026-01-01T00:00:00Z"  # untouched
    assert channels["222"]["watch_type"] == "issues"


async def test_watch_repo_rejects_invalid_repo_format(cog):
    ctx = make_ctx(channel_id=111)
    await GitHubCog.watch_repo.callback(cog, ctx, "not-a-valid-repo")

    assert cog.bot.watched_repos == {}
    ctx.send.assert_awaited_once()
    assert "Invalid format" in ctx.send.call_args.args[0]


async def test_watch_repo_repo_not_found(cog):
    cog.bot.http_session = FakeSession({
        "https://api.github.com/repos/owner/missing": FakeResponse(404),
    })

    ctx = make_ctx(channel_id=111)
    await GitHubCog.watch_repo.callback(cog, ctx, "owner/missing")

    assert cog.bot.watched_repos == {}
    ctx.send.return_value.edit.assert_awaited_once()
    assert "not found" in ctx.send.return_value.edit.call_args.kwargs["content"]


async def test_unwatch_repo_removes_only_this_channel(cog):
    cog.bot.watched_repos = {
        "owner/repo": {
            "111": {"labels": [], "watch_since_time": None, "watch_type": "issues"},
            "222": {"labels": [], "watch_since_time": None, "watch_type": "issues"},
        }
    }
    cog.bot.notified_issues = {"222:owner/repo#1", "111:owner/repo#5"}

    ctx = make_ctx(channel_id=222)
    await GitHubCog.unwatch_repo.callback(cog, ctx, "owner/repo")

    assert set(cog.bot.watched_repos["owner/repo"].keys()) == {"111"}
    assert cog.bot.notified_issues == {"111:owner/repo#5"}


async def test_unwatch_repo_removes_repo_key_when_last_channel_leaves(cog):
    cog.bot.watched_repos = {
        "owner/repo": {"111": {"labels": [], "watch_since_time": None, "watch_type": "issues"}}
    }

    ctx = make_ctx(channel_id=111)
    await GitHubCog.unwatch_repo.callback(cog, ctx, "owner/repo")

    assert "owner/repo" not in cog.bot.watched_repos


async def test_unwatch_repo_not_watching_in_this_channel(cog):
    cog.bot.watched_repos = {
        "owner/repo": {"111": {"labels": [], "watch_since_time": None, "watch_type": "issues"}}
    }

    ctx = make_ctx(channel_id=999)
    await GitHubCog.unwatch_repo.callback(cog, ctx, "owner/repo")

    assert "111" in cog.bot.watched_repos["owner/repo"]
    ctx.send.assert_awaited_once()
    assert "not currently watching" in ctx.send.call_args.args[0]


async def test_list_watched_filters_by_guild(cog):
    guild_a, guild_b = MagicMock(), MagicMock()

    channel_111, channel_222 = MagicMock(), MagicMock()
    channel_111.guild = guild_a
    channel_222.guild = guild_b

    cog.bot.get_channel = lambda cid: {111: channel_111, 222: channel_222}.get(cid)
    cog.bot.watched_repos = {
        "owner/repo": {
            "111": {"labels": ["bug"], "watch_since_time": None, "watch_type": "issues"},
            "222": {"labels": [], "watch_since_time": None, "watch_type": "all"},
        }
    }

    ctx = MagicMock()
    ctx.guild = guild_a
    ctx.send = AsyncMock()

    await GitHubCog.list_watched.callback(cog, ctx)

    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs["embed"]
    assert "<#111>" in embed.description
    assert "<#222>" not in embed.description
