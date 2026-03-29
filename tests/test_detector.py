"""
test_detector.py — Unit tests for the Stale Task Detection module.

All tests use injectable `now` timestamps — no wall-clock dependency.
Base reference timestamp: T0 = 1_000_000.0 (arbitrary fixed epoch)
Days are expressed as offsets: T0 - (days * 86400)
"""
import json
import math
import time
import pytest
from stale_task_detector import (
    TaskRecord, StalenessResult, Tier,
    scan_tasks, ScanResult, build_notification, build_notification_batch, to_json,
    Thresholds, DEFAULT_THRESHOLDS,
)

# Fixed reference "now" — used throughout for deterministic tests
# Must be large enough that (NOW - 60*86400) > 0 for validation checks
NOW = 1_700_000_000.0  # ~ Nov 2023 unix timestamp


def make_task(
    task_id: str = "task-001",
    status: str = "in_progress",
    days_ago: float = 0.0,
    owner: str = "0xABCD",
    pft_value: float = 100.0,
    verification_submitted_at: float | None = None,
) -> TaskRecord:
    last_activity = NOW - (days_ago * 86400)
    return TaskRecord(
        task_id=task_id,
        status=status,
        created_at=last_activity - 86400,  # created 1 day before last activity
        last_activity_at=last_activity,
        owner=owner,
        pft_value=pft_value,
        verification_submitted_at=verification_submitted_at,
    )


# ---------------------------------------------------------------------------
# Tier boundary tests
# ---------------------------------------------------------------------------

def test_tier_warning_at_exactly_14_days():
    task = make_task(days_ago=14.0)
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 1
    assert result.stale[0].tier == Tier.WARNING
    assert result.stale[0].recommended_action == "nudge"


def test_tier_not_triggered_at_13_days():
    task = make_task(days_ago=13.0)
    result = scan_tasks([task], now=NOW)
    assert result.stale == []


def test_tier_warning_at_15_days():
    task = make_task(days_ago=15.0)
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 1
    assert result.stale[0].tier == Tier.WARNING


def test_tier_critical_at_30_days():
    task = make_task(days_ago=30.0)
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 1
    assert result.stale[0].tier == Tier.CRITICAL
    assert result.stale[0].recommended_action == "escalate"


def test_tier_auto_expire_at_45_days():
    task = make_task(days_ago=45.0)
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 1
    assert result.stale[0].tier == Tier.AUTO_EXPIRE
    assert result.stale[0].recommended_action == "expire"


# ---------------------------------------------------------------------------
# Verification submission exemption
# ---------------------------------------------------------------------------

def test_submitted_for_verification_at_day_13_not_flagged():
    # Recent verification submission (10 days ago) — exempt
    task = make_task(days_ago=13.0, verification_submitted_at=NOW - 86400 * 10)
    result = scan_tasks([task], now=NOW)
    assert result.stale == []


def test_submitted_for_verification_at_day_15_not_flagged():
    # Recent verification submission (10 days ago) — exempt
    task = make_task(days_ago=15.0, verification_submitted_at=NOW - 86400 * 10)
    result = scan_tasks([task], now=NOW)
    assert result.stale == []


# ---------------------------------------------------------------------------
# Unknown user handling
# ---------------------------------------------------------------------------

def test_unknown_user_owner_flagged_and_expires_immediately():
    task = make_task(days_ago=14.0, owner="unknown_user")
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 1
    assert result.stale[0].is_unknown_owner is True
    assert result.stale[0].owner_resolution_required is True
    assert any("unknown_user" in note for note in result.stale[0].notes)


def test_unknown_user_action_is_nudge_at_warning_tier():
    """unknown_user at WARNING tier → action=nudge (tier-aligned, not force-expire)."""
    task = make_task(days_ago=20.0, owner="unknown_user")
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 1
    assert result.stale[0].tier == Tier.WARNING
    assert result.stale[0].recommended_action == "nudge"
    assert result.stale[0].owner_resolution_required is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty():
    result = scan_tasks([], now=NOW)
    assert result.stale == []
    assert result.invalid == []


def test_completed_task_not_flagged():
    task = make_task(days_ago=60.0, status="complete")
    result = scan_tasks([task], now=NOW)
    assert result.stale == []


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------

def test_sort_order_descending_by_days_stale():
    tasks = [
        make_task(task_id="task-A", days_ago=20.0),
        make_task(task_id="task-B", days_ago=50.0),
        make_task(task_id="task-C", days_ago=35.0),
    ]
    result = scan_tasks(tasks, now=NOW)
    assert [r.task_id for r in result.stale] == ["task-B", "task-C", "task-A"]


def test_tied_staleness_sorted_by_task_id_ascending():
    tasks = [
        make_task(task_id="task-Z", days_ago=20.0),
        make_task(task_id="task-A", days_ago=20.0),
        make_task(task_id="task-M", days_ago=20.0),
    ]
    result = scan_tasks(tasks, now=NOW)
    assert [r.task_id for r in result.stale] == ["task-A", "task-M", "task-Z"]


# ---------------------------------------------------------------------------
# Notification payload
# ---------------------------------------------------------------------------

def test_notification_payload_fields_present():
    task = make_task(days_ago=50.0)
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 1
    payload = build_notification(result.stale[0], emitted_at=NOW)

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
    batch = build_notification_batch(result.stale, emitted_at=NOW)
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

    assert default_results.stale == []  # 7 < 14 default warning
    assert len(custom_results.stale) == 1
    assert custom_results.stale[0].tier == Tier.WARNING

    # At 21 days — should be AUTO_EXPIRE with custom, WARNING with default
    task2 = make_task(task_id="task-002", days_ago=21.0)
    default_results2 = scan_tasks([task2], now=NOW)
    custom_results2 = scan_tasks([task2], thresholds=custom, now=NOW)

    assert default_results2.stale[0].tier == Tier.WARNING
    assert custom_results2.stale[0].tier == Tier.AUTO_EXPIRE


def test_invalid_thresholds_raise():
    with pytest.raises(ValueError):
        Thresholds(warning_days=30.0, critical_days=14.0, auto_expire_days=45.0)


# ---------------------------------------------------------------------------
# Adversarial tests
# ---------------------------------------------------------------------------

def test_future_timestamp_is_invalid():
    """Task with last_activity_at in the future is rejected as invalid."""
    future = NOW + 86400 * 10
    task = TaskRecord("t-future", "in_progress", NOW - 86400*5, future, "0xabc")
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 0
    assert any("t-future" in inv[0] for inv in result.invalid)


def test_created_after_last_activity_is_invalid():
    task = TaskRecord("t-bad", "in_progress", NOW - 86400*5, NOW - 86400*20, "0xabc")
    # created_at (NOW-5d) > last_activity_at (NOW-20d)
    result = scan_tasks([task], now=NOW)
    assert any("t-bad" in inv[0] for inv in result.invalid)


def test_empty_task_id_is_invalid():
    task = TaskRecord("", "in_progress", NOW - 86400*50, NOW - 86400*50, "0xabc")
    result = scan_tasks([task], now=NOW)
    assert any(inv[0] == "" for inv in result.invalid)


def test_negative_pft_is_invalid():
    task = TaskRecord("t-neg", "in_progress", NOW - 86400*50, NOW - 86400*50, "0xabc", pft_value=-100.0)
    result = scan_tasks([task], now=NOW)
    assert any("t-neg" in inv[0] for inv in result.invalid)


def test_stale_verification_submission_is_flagged():
    """Submission older than auto_expire threshold should still be flagged."""
    old_submission = NOW - 86400 * 50  # submitted 50 days ago
    task = TaskRecord("t-stale-sub", "in_progress", NOW - 86400*60, NOW - 86400*60, "0xabc",
                      verification_submitted_at=old_submission)
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 1
    assert result.stale[0].task_id == "t-stale-sub"


def test_recent_verification_submission_is_exempt():
    """Submission within auto_expire threshold should be exempt."""
    recent_submission = NOW - 86400 * 10
    task = TaskRecord("t-recent-sub", "in_progress", NOW - 86400*60, NOW - 86400*60, "0xabc",
                      verification_submitted_at=recent_submission)
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 0


def test_unknown_user_tier_follows_days_stale():
    """unknown_user at 15 days → WARNING tier, action=nudge (NOT expire)."""
    task = TaskRecord("t-unk-warn", "in_progress", NOW - 86400*16, NOW - 86400*15, "unknown_user")
    result = scan_tasks([task], now=NOW)
    assert len(result.stale) == 1
    r = result.stale[0]
    assert r.tier == Tier.WARNING
    assert r.recommended_action == "nudge"
    assert r.owner_resolution_required is True


def test_unknown_user_auto_expire_tier():
    """unknown_user at 50 days → AUTO_EXPIRE tier, action=expire."""
    task = TaskRecord("t-unk-exp", "in_progress", NOW - 86400*51, NOW - 86400*50, "unknown_user")
    result = scan_tasks([task], now=NOW)
    assert result.stale[0].tier == Tier.AUTO_EXPIRE
    assert result.stale[0].recommended_action == "expire"


def test_status_case_insensitive():
    """'In_Progress' and 'IN_PROGRESS' should both be scanned."""
    for status in ["In_Progress", "IN_PROGRESS", " in_progress "]:
        task = TaskRecord(f"t-{status}", status, NOW - 86400*21, NOW - 86400*20, "0xabc")
        result = scan_tasks([task], now=NOW)
        assert len(result.stale) == 1, f"Expected 1 stale for status={status!r}"


def test_tier_boundary_29_999():
    """29.999 days → WARNING (just under CRITICAL threshold)."""
    task = TaskRecord("t-29999", "in_progress", NOW - 86400*31, NOW - 86400*29.999, "0xabc")
    result = scan_tasks([task], now=NOW)
    assert result.stale[0].tier == Tier.WARNING


def test_tier_boundary_44_999():
    """44.999 days → CRITICAL (just under AUTO_EXPIRE threshold)."""
    task = TaskRecord("t-44999", "in_progress", NOW - 86400*50, NOW - 86400*44.999, "0xabc")
    result = scan_tasks([task], now=NOW)
    assert result.stale[0].tier == Tier.CRITICAL


def test_notification_includes_provenance():
    """Notification payload should include scanner_version, thresholds_used, scan_id."""
    from stale_task_detector.notifier import build_notification
    from stale_task_detector.thresholds import DEFAULT_THRESHOLDS
    r = StalenessResult("t1", "0xabc", Tier.WARNING, 15.0, "nudge", 100.0, NOW - 86400*15, False)
    n = build_notification(r, thresholds=DEFAULT_THRESHOLDS, scan_id="scan-001", emitted_at=NOW)
    assert "scanner_version" in n
    assert "thresholds_used" in n
    assert n["thresholds_used"]["warning_days"] == 14.0
    assert n["scan_id"] == "scan-001"
    assert "owner_resolution_required" in n
