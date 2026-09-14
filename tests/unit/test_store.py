# Author: Sabari Iyyapan Duraipandian
"""
Unit tests for the SQLite dedupe layer in src.store. This is the piece that
makes webhook redelivery idempotent (dedupe key = (delivery_id, action)), and
previously had zero test coverage.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.store import EventStore


def make_store(tmp_path):
    # Always use a throwaway path under tmp_path, never the default
    # "events.db" - that would write into the repo working directory and
    # pollute state across test runs.
    return EventStore(db_path=str(tmp_path / "events.db"))


def test_already_processed_false_before_any_record(tmp_path):
    store = make_store(tmp_path)
    assert store.already_processed("delivery-1", "opened") is False


def test_already_processed_true_after_record(tmp_path):
    store = make_store(tmp_path)
    store.record("delivery-1", "issues", "opened", 42)
    assert store.already_processed("delivery-1", "opened") is True


def test_duplicate_delivery_and_action_is_ignored(tmp_path):
    """INSERT OR IGNORE means a redelivered (delivery_id, action) pair
    results in exactly one stored row, not two."""
    store = make_store(tmp_path)
    store.record("delivery-1", "issues", "opened", 42)
    store.record("delivery-1", "issues", "opened", 42)
    assert len(store.recent(10)) == 1


def test_same_delivery_different_action_is_two_rows(tmp_path):
    """The dedupe key is the (delivery_id, action) pair, not delivery_id
    alone - GitHub can send multiple actions under one delivery id over
    time (e.g. 'labeled' then 'closed')."""
    store = make_store(tmp_path)
    store.record("delivery-1", "issues", "opened", 42)
    store.record("delivery-1", "issues", "closed", 42)
    assert len(store.recent(10)) == 2
    assert store.already_processed("delivery-1", "opened") is True
    assert store.already_processed("delivery-1", "closed") is True


def test_recent_honors_limit(tmp_path):
    store = make_store(tmp_path)
    for i in range(5):
        store.record(f"delivery-{i}", "issues", "opened", i)
    assert len(store.recent(3)) == 3


def test_recent_returns_event_record_fields(tmp_path):
    store = make_store(tmp_path)
    store.record("delivery-1", "issue_comment", "created", 7)
    records = store.recent(10)
    assert len(records) == 1
    record = records[0]
    assert record.id == "delivery-1"
    assert record.event == "issue_comment"
    assert record.action == "created"
    assert record.issue_number == 7
    assert record.timestamp  # non-empty, ISO-ish string


def test_action_none_round_trips_to_none(tmp_path):
    """record() stores a None action as '' (since it's part of the SQLite
    primary key and NULL wouldn't dedupe the way we want), but recent()
    must map that back to None so callers don't see the storage detail."""
    store = make_store(tmp_path)
    store.record("delivery-1", "ping", None, None)
    records = store.recent(10)
    assert records[0].action is None


def test_already_processed_with_none_action(tmp_path):
    store = make_store(tmp_path)
    store.record("delivery-1", "ping", None, None)
    assert store.already_processed("delivery-1", None) is True
    assert store.already_processed("delivery-1", "opened") is False
