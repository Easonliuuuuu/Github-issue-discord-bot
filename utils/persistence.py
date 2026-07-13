from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from config import DATA_FILE_PATH

logger = logging.getLogger(__name__)

WatchedRepos = dict[str, dict[str, dict[str, Any]]]

DEFAULT_WATCH_TYPE = "issues"
DEFAULT_V1_LABELS = ["good first issue"]


def _migrate_v1_to_v2(raw_watched_repos: dict[str, int]) -> dict[str, dict[str, Any]]:
    """Migrates the original {repo: channel_id} format to the v2 flat format
    (one channel per repo, with labels/watch_type)."""
    logger.info("Old data format detected (v1). Migrating...")
    migrated = {
        repo: {
            "channel_id": channel_id,
            "labels": list(DEFAULT_V1_LABELS),
            "watch_type": DEFAULT_WATCH_TYPE,
        }
        for repo, channel_id in raw_watched_repos.items()
    }
    logger.info("Migration v1 complete.")
    return migrated


def _migrate_v2_to_v3(
    v2_watched_repos: dict[str, dict[str, Any]],
    raw_notified_issues: list[str],
) -> tuple[WatchedRepos, set[str]]:
    """Migrates the flat one-channel-per-repo format to the nested
    multi-channel-per-repo format, so the same repo can be watched
    independently by more than one channel/server."""
    logger.info("Migrating data to v3 (multi-channel-per-repo) format...")

    watched_repos: WatchedRepos = {}
    repo_to_channel: dict[str, str] = {}

    for repo, repo_data in v2_watched_repos.items():
        channel_id = str(repo_data["channel_id"])
        repo_to_channel[repo] = channel_id
        watched_repos[repo] = {
            channel_id: {
                "labels": repo_data.get("labels", []),
                "watch_since_time": repo_data.get("watch_since_time"),
                "watch_type": repo_data.get("watch_type", DEFAULT_WATCH_TYPE),
            }
        }

    # Old notified_issues entries look like "owner/repo#123" with no channel
    # attribution. Re-key them per-channel using each repo's (single, old)
    # channel_id. Entries for repos that are no longer watched are dropped -
    # they're historical noise with no channel left to attribute them to.
    notified_issues: set[str] = set()
    dropped = 0
    for entry in raw_notified_issues:
        repo, _, _number = entry.rpartition("#")
        channel_id = repo_to_channel.get(repo)
        if channel_id is None:
            dropped += 1
            continue
        notified_issues.add(f"{channel_id}:{entry}")

    if dropped:
        logger.info(
            "Dropped %d notified-issue entries for repos no longer watched during v3 migration.",
            dropped,
        )
    logger.info("Migration v3 complete.")
    return watched_repos, notified_issues


def _is_v3_format(raw_watched_repos: dict[str, Any]) -> bool:
    """v3 entries are keyed by repo -> {channel_id: {...}}. A v2 entry is
    keyed by repo -> {"channel_id": ..., "labels": ..., ...} directly, so
    the presence of a "channel_id" field distinguishes the two."""
    first_value = next(iter(raw_watched_repos.values()))
    return "channel_id" not in first_value


def load_data() -> tuple[WatchedRepos, set[str]]:
    """Loads the watch list and notified issues from the JSON file,
    migrating older data formats as needed."""
    watched_repos: WatchedRepos = {}
    notified_issues: set[str] = set()

    if not os.path.exists(DATA_FILE_PATH):
        logger.info("%s not found. Starting with empty data.", DATA_FILE_PATH)
        return watched_repos, notified_issues

    try:
        with open(DATA_FILE_PATH, "r") as f:
            data = json.load(f)

        raw_watched_repos = data.get("watched_repos", {})
        raw_notified_issues = data.get("notified_issues", [])
        data_was_migrated = False

        if not raw_watched_repos:
            watched_repos = {}
            notified_issues = set(raw_notified_issues)
        else:
            first_value = next(iter(raw_watched_repos.values()))

            if isinstance(first_value, int):
                v2 = _migrate_v1_to_v2(raw_watched_repos)
                watched_repos, notified_issues = _migrate_v2_to_v3(v2, raw_notified_issues)
                data_was_migrated = True
            elif _is_v3_format(raw_watched_repos):
                watched_repos = raw_watched_repos
                notified_issues = set(raw_notified_issues)
            else:
                watched_repos, notified_issues = _migrate_v2_to_v3(raw_watched_repos, raw_notified_issues)
                data_was_migrated = True

        logger.info("Loaded data from %s", DATA_FILE_PATH)

        if data_was_migrated:
            save_data(watched_repos, notified_issues)

    except Exception as e:
        logger.error("Error reading or migrating %s: %s. Starting with empty data.", DATA_FILE_PATH, e)
        watched_repos = {}
        notified_issues = set()

    return watched_repos, notified_issues


def save_data(watched_repos: WatchedRepos, notified_issues: set[str]) -> None:
    """Atomically saves the current state to the JSON file. Writes to a
    temp file in the same directory and renames it into place, so a crash
    mid-write can't leave a corrupted data file."""
    data = {
        "watched_repos": watched_repos,
        "notified_issues": list(notified_issues),
    }

    directory = os.path.dirname(os.path.abspath(DATA_FILE_PATH)) or "."
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".bot_data_", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp_path, DATA_FILE_PATH)
        tmp_path = None
        logger.info("Saved data to %s", DATA_FILE_PATH)
    except IOError as e:
        logger.error("Error saving data: %s", e)
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.remove(tmp_path)
