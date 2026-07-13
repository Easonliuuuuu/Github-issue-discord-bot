import json
from unittest.mock import MagicMock

from utils import persistence


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    data_file = tmp_path / "bot_data.json"
    monkeypatch.setattr(persistence, "DATA_FILE_PATH", str(data_file))

    watched_repos = {
        "owner/repo": {
            "111": {"labels": ["bug"], "watch_since_time": "2026-01-01T00:00:00Z", "watch_type": "issues"},
            "222": {"labels": [], "watch_since_time": "2026-01-02T00:00:00Z", "watch_type": "all"},
        }
    }
    notified_issues = {"111:owner/repo#1", "222:owner/repo#2"}

    persistence.save_data(watched_repos, notified_issues)
    assert data_file.exists()

    loaded_repos, loaded_notified = persistence.load_data()
    assert loaded_repos == watched_repos
    assert loaded_notified == notified_issues


def test_load_data_missing_file(tmp_path, monkeypatch):
    data_file = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(persistence, "DATA_FILE_PATH", str(data_file))

    watched_repos, notified_issues = persistence.load_data()
    assert watched_repos == {}
    assert notified_issues == set()


def test_migrate_v1_to_v3(tmp_path, monkeypatch):
    data_file = tmp_path / "bot_data.json"
    monkeypatch.setattr(persistence, "DATA_FILE_PATH", str(data_file))

    v1_data = {
        "watched_repos": {"owner/repo": 12345},
        "notified_issues": ["owner/repo#1"],
    }
    data_file.write_text(json.dumps(v1_data))

    watched_repos, notified_issues = persistence.load_data()

    assert watched_repos == {
        "owner/repo": {
            "12345": {
                "labels": ["good first issue"],
                "watch_since_time": None,
                "watch_type": "issues",
            }
        }
    }
    assert notified_issues == {"12345:owner/repo#1"}

    # Migrated data should have been re-saved in v3 format.
    saved = json.loads(data_file.read_text())
    assert "12345" in saved["watched_repos"]["owner/repo"]


def test_migrate_v2_to_v3_drops_orphaned_notified_issues(tmp_path, monkeypatch):
    data_file = tmp_path / "bot_data.json"
    monkeypatch.setattr(persistence, "DATA_FILE_PATH", str(data_file))

    v2_data = {
        "watched_repos": {
            "owner/repo": {
                "channel_id": 999,
                "labels": ["bug"],
                "watch_since_time": "2026-01-01T00:00:00Z",
                "watch_type": "issues",
            }
        },
        # "owner/gone" is no longer watched - its notified entry should be dropped.
        "notified_issues": ["owner/repo#1", "owner/gone#5"],
    }
    data_file.write_text(json.dumps(v2_data))

    watched_repos, notified_issues = persistence.load_data()

    assert watched_repos == {
        "owner/repo": {
            "999": {
                "labels": ["bug"],
                "watch_since_time": "2026-01-01T00:00:00Z",
                "watch_type": "issues",
            }
        }
    }
    assert notified_issues == {"999:owner/repo#1"}


def test_load_data_already_v3_is_not_migrated(tmp_path, monkeypatch):
    data_file = tmp_path / "bot_data.json"
    monkeypatch.setattr(persistence, "DATA_FILE_PATH", str(data_file))

    v3_data = {
        "watched_repos": {
            "owner/repo": {
                "111": {"labels": [], "watch_since_time": None, "watch_type": "issues"},
            }
        },
        "notified_issues": ["111:owner/repo#1"],
    }
    data_file.write_text(json.dumps(v3_data))

    save_spy = MagicMock(wraps=persistence.save_data)
    monkeypatch.setattr(persistence, "save_data", save_spy)

    watched_repos, notified_issues = persistence.load_data()

    assert watched_repos == v3_data["watched_repos"]
    assert notified_issues == {"111:owner/repo#1"}
    save_spy.assert_not_called()


def test_save_data_is_atomic_no_leftover_tmp_file(tmp_path, monkeypatch):
    data_file = tmp_path / "bot_data.json"
    monkeypatch.setattr(persistence, "DATA_FILE_PATH", str(data_file))

    persistence.save_data({}, set())

    assert list(tmp_path.iterdir()) == [data_file]
