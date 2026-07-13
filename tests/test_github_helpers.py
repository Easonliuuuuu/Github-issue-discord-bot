from datetime import datetime, timezone

import pytest

from cogs.github import WatchArgsError, matches_labels, parse_watch_args, should_notify_item


def test_parse_watch_args_no_args():
    labels, watch_type = parse_watch_args(())
    assert labels == []
    assert watch_type == "issues"


def test_parse_watch_args_labels_only():
    labels, watch_type = parse_watch_args(("bug", "help wanted"))
    assert labels == ["bug", "help wanted"]
    assert watch_type == "issues"


def test_parse_watch_args_type_flag():
    labels, watch_type = parse_watch_args(("bug", "--type", "prs"))
    assert labels == ["bug"]
    assert watch_type == "prs"


def test_parse_watch_args_type_flag_case_insensitive():
    labels, watch_type = parse_watch_args(("--TYPE", "ALL"))
    assert labels == []
    assert watch_type == "all"


def test_parse_watch_args_invalid_type_raises():
    with pytest.raises(WatchArgsError):
        parse_watch_args(("--type", "bogus"))


def test_parse_watch_args_type_missing_value_raises():
    with pytest.raises(WatchArgsError):
        parse_watch_args(("--type",))


def test_matches_labels_no_watched_labels_matches_anything():
    assert matches_labels(["anything"], []) is True
    assert matches_labels([], []) is True


def test_matches_labels_case_insensitive_match():
    assert matches_labels(["Bug", "enhancement"], ["bug"]) is True


def test_matches_labels_no_overlap():
    assert matches_labels(["enhancement"], ["bug"]) is False


NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)
EARLIER = datetime(2026, 1, 1, tzinfo=timezone.utc)
LATER = datetime(2026, 1, 20, tzinfo=timezone.utc)


def _notify(**overrides):
    defaults = dict(
        is_pr=False,
        watch_type="issues",
        item_labels=["bug"],
        watched_labels=["bug"],
        notified_key="123:owner/repo#1",
        notified_issues=set(),
        issue_created_at=LATER,
        watch_since_time=NOW,
    )
    defaults.update(overrides)
    return should_notify_item(**defaults)


def test_should_notify_item_happy_path():
    assert _notify() is True


def test_should_notify_item_issues_only_skips_pr():
    assert _notify(watch_type="issues", is_pr=True) is False


def test_should_notify_item_prs_only_skips_issue():
    assert _notify(watch_type="prs", is_pr=False) is False


def test_should_notify_item_all_allows_both():
    assert _notify(watch_type="all", is_pr=True) is True
    assert _notify(watch_type="all", is_pr=False) is True


def test_should_notify_item_label_mismatch():
    assert _notify(item_labels=["enhancement"], watched_labels=["bug"]) is False


def test_should_notify_item_already_notified():
    assert _notify(notified_issues={"123:owner/repo#1"}) is False


def test_should_notify_item_created_before_watch_start():
    assert _notify(issue_created_at=EARLIER, watch_since_time=NOW) is False


def test_should_notify_item_no_watch_since_time_allows_anything():
    assert _notify(issue_created_at=EARLIER, watch_since_time=None) is True


def test_should_notify_item_two_channels_independent_dedup():
    # Channel A already notified, channel B (watching the same repo) should
    # still be notified independently - this is the bug the v3 data model fixes.
    notified = {"111:owner/repo#1"}
    assert _notify(notified_key="111:owner/repo#1", notified_issues=notified) is False
    assert _notify(notified_key="222:owner/repo#1", notified_issues=notified) is True
