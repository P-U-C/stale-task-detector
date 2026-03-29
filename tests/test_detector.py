"""
test_detector.py — Unit tests for the Stale Task Detection module.

All tests use injectable `now` timestamps — no wall-clock dependency.
Base reference timestamp: T0 = 1_000_000.0 (arbitrary fixed epoch)
Days are expressed as offsets: T0 - (days * 86400)
"""
import json
import pytest
from stale_task_detector import (
    TaskRecord, StalenessResult, Tier,
    scan_tasks, build_notification, build_notification_batch, to_json,
    Thresholds, DEFAULT_THRESHOLDS,
)

# Fixed reference "now"
NOW = 1_000_000.0


def make_task(
    task_id: str = "task-001",
    status: str = "in_progress",
    days_ago: float = 0.0,
    owner: str = "0xABCD",
    pft_value: float = 100.0,
    has_verification_submission: bool = False,
) -> TaskRecord:
    last_activity = NOW - (days_ago * 86400)
    return TaskRecord(
        task_id=task_id,
        status=status,
        created_at=last_activity - 86400,  # created 1 day before last activity
        last_activity_at=last_activity,
        owner=owner,
        pft_value=pft_value,
        has_verification_submission=has_verification_submission,
    )


# ---------------------------------------------------------------------------
# Tier boundary tests
# ---------------------------------------------------------------------------

def test_tier_warning_at_exactly_14_days():
    task = make_task(days_ago=14.0)
    results = scan_tasks([task], now=NOW)
    assert len(results) == 1
    assert results[0].tier == Tier.WARNING
    assert results[0].recommended_action == "nudge"


def test_tier_not_triggered_at_13_days():
    task = make_task(days_ago=13.0)
    results = scan_tasks([task], now=NOW)
    assert results == []


def test_tier_warning_at_15_days():
    task = make_task(days_ago=15.0)
    results = scan_tasks([task], now=NOW)
    assert len(results) == 1
    assert results[0].tier == Tier.WARNING


def test_tier_critical_at_30_days():
    task = make_task(days_ago=30.0)
    results = scan_tasks([task], now=NOW)
    assert len(results) == 1
    assert results[0].tier == Tier.CRITICAL
    assert results[0].recommended_action == "escalate"


def test_tier_auto_expire_at_45_days():
    task = make_task(days_ago=45.0)
    results = scan_tasks([task], now=NOW)
    assert len(results) == 1
    assert results[0].tier == Tier.AUTO_EXPIRE
    assert results[0].recommended_action == "expire"


# ---------------------------------------------------------------------------
# Verification submission exemption
# ---------------------------------------------------------------------------

def test_submitted_for_verification_at_day_13_not_flagged():
    task = make_task(days_ago=13.0, has_verification_submission=True)
    results = scan_tasks([task], now=NOW)
    assert results == []


def test_submitted_for_verification_at_day_15_not_flagged():
    task = make_task(days_ago=15.0, has_verification_submission=True)
    results = scan_tasks([task], now=NOW)
    assert results == []


# ---------------------------------------------------------------------------
# Unknown user handling
# ---------------------------------------------------------------------------

def test_unknown_user_owner_flagged_and_expires_immediately():
    task = make_task(days_ago=14.0, owner="unknown_user")
    results = scan_tasks([task], now=NOW)
    assert len(results) == 1
    assert results[0].is_unknown_owner is True
    assert results[0].recommended_action == "expire"
    assert any("unknown_user" in note for note in results[0].notes)


def test_unknown_user_action_is_expire_at_warning_tier():
    task = make_task(days_ago=20.0, owner="unknown_user")
    results = scan_tasks([task], now=NOW)
    assert len(results) == 1
    assert results[0].tier == Tier.WARNING
    assert results[0].recommended_action == "expire"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty_list():
    results = scan_tasks([], now=NOW)
    assert results == []


def test_completed_task_not_flagged():
    task = make_task(days_ago=60.0, status="complete")
    results = scan_tasks([task], now=NOW)
    assert results == []


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------

def test_sort_order_descending_by_days_stale():
    tasks = [
        make_task(task_id="task-A", days_ago=20.0),
        make_task(task_id="task-B", days_ago=50.0),
        make_task(task_id="task-C", days_ago=35.0),
    ]
    results = scan_tasks(tasks, now=NOW)
    assert [r.task_id for r in results] == ["task-B", "task-C", "task-A"]


def test_tied_staleness_sorted_by_task_id_ascending():
    tasks = [
        make_task(task_id="task-Z", days_ago=20.0),
        make_task(task_id="task-A", days_ago=20.0),
        make_task(task_id="task-M", days_ago=20.0),
    ]
    results = scan_tasks(tasks, now=NOW)
    assert [r.task_id for r in results] == ["task-A", "task-M", "task-Z"]


# ---------------------------------------------------------------------------
# Notification payload
# ---------------------------------------------------------------------------

def test_notification_payload_fields_present():
    task = make_task(days_ago=50.0)
    results = scan_tasks([task], now=NOW)
    assert len(results) == 1
    payload = build_notification(results[0], emitted_at=NOW)

    required_fields = {
        "schema_version", "emitted_at", "task_id", "owner",
        "tier", "days_stale", "recommended_action", "pft_at_risk",
        "is_unknown_owner", "notes",
    }
    assert required_fields.issubset(set(payload.keys()))
    assert payload["schema_version"] == "stale-task.notification.v1"
    assert payload["emitted_at"] == NOW
    assert payload["tier"] == Tier.AUTO_EXPIRE.value

    # Verify JSON round-trip
    batch = build_notification_batch(results, emitted_at=NOW)
    json_str = to_json(batch)
    parsed = json.loads(json_str)
    assert len(parsed) == 1
    assert parsed[0]["task_id"] == task.task_id


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------

def test_custom_thresholds_respected():
    custom = Thresholds(warning_days=7.0, critical_days=14.0, auto_expire_days=21.0)

    # At 7 days — should be WARNING with custom thresholds, nothing with defaults
    task = make_task(days_ago=7.0)
    default_results = scan_tasks([task], now=NOW)
    custom_results = scan_tasks([task], thresholds=custom, now=NOW)

    assert default_results == []  # 7 < 14 default warning
    assert len(custom_results) == 1
    assert custom_results[0].tier == Tier.WARNING

    # At 21 days — should be AUTO_EXPIRE with custom, WARNING with default
    task2 = make_task(task_id="task-002", days_ago=21.0)
    default_results2 = scan_tasks([task2], now=NOW)
    custom_results2 = scan_tasks([task2], thresholds=custom, now=NOW)

    assert default_results2[0].tier == Tier.WARNING
    assert custom_results2[0].tier == Tier.AUTO_EXPIRE


def test_invalid_thresholds_raise():
    with pytest.raises(ValueError):
        Thresholds(warning_days=30.0, critical_days=14.0, auto_expire_days=45.0)
