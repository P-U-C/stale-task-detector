"""
notifier.py — Notification payload generator for stale task results.

Produces structured JSON messages per stale task for downstream consumers:
    - Task Node acceptance pipeline (block new task slots for expired owners)
    - Network governance (escalation notifications)
    - Chain envelope emitter (auto-expiry events)
"""
from __future__ import annotations
import json
import time
from stale_task_detector.schema import StalenessResult

SCHEMA_VERSION = "stale-task.notification.v1"


def build_notification(
    result: StalenessResult,
    thresholds: "Thresholds | None" = None,
    scan_id: str | None = None,
    scanner_version: str = "stale-task-detector.v1",
    emitted_at: float | None = None,
) -> dict:
    """
    Build a structured notification payload for a single stale task.

    Args:
        result: StalenessResult from scan_tasks()
        thresholds: Thresholds used in the scan (for provenance)
        scan_id: optional scan run identifier
        scanner_version: version string for provenance
        emitted_at: unix timestamp (defaults to time.time(); injectable for tests)

    Returns:
        dict — JSON-serializable notification payload
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "emitted_at": emitted_at if emitted_at is not None else time.time(),
        "task_id": result.task_id,
        "owner": result.owner,
        "tier": result.tier.value,
        "days_stale": result.days_stale,
        "recommended_action": result.recommended_action,
        "pft_at_risk": result.pft_value,
        "is_unknown_owner": result.is_unknown_owner,
        "notes": result.notes,
        "scanner_version": scanner_version,
        "scan_id": scan_id,
        "thresholds_used": {
            "warning_days": thresholds.warning_days if thresholds else 14.0,
            "critical_days": thresholds.critical_days if thresholds else 30.0,
            "auto_expire_days": thresholds.auto_expire_days if thresholds else 45.0,
        },
        "owner_resolution_required": result.owner_resolution_required,
    }


def build_notification_batch(
    results: list[StalenessResult],
    thresholds: "Thresholds | None" = None,
    scan_id: str | None = None,
    scanner_version: str = "stale-task-detector.v1",
    emitted_at: float | None = None,
) -> list[dict]:
    """Build notification payloads for all stale tasks in a scan result."""
    ts = emitted_at if emitted_at is not None else time.time()
    return [
        build_notification(r, thresholds=thresholds, scan_id=scan_id,
                           scanner_version=scanner_version, emitted_at=ts)
        for r in results
    ]


def to_json(notifications: list[dict]) -> str:
    """Serialize notification batch to JSON string."""
    return json.dumps(notifications, indent=2)
