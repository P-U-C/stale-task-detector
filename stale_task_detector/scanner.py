"""
scanner.py — Staleness scanner for the Task Node adjudication pipeline.

Scanning logic:
    1. Only tasks with status == "in_progress" are scanned (case-insensitive).
    2. Tasks submitted for verification recently (within auto_expire threshold)
       are exempt — the owner acted; the network owes them a decision.
       If verification_submitted_at is itself stale, the task is flagged.
    3. Days stale is computed from last_activity_at (not created_at).
    4. Results are sorted descending by days_stale (most urgent first).
       Ties broken by task_id ascending (deterministic).
    5. unknown_user owner is flagged via owner_resolution_required=True;
       recommended_action still follows tier (not overridden).

Integration with Authorization Gate cooldown:
    AUTO_EXPIRE results should be fed into the cooldown escalation logic
    defined in the Auth Gate enforcement spec.
"""
import math
import time
from dataclasses import dataclass
from stale_task_detector.schema import TaskRecord, StalenessResult, Tier
from stale_task_detector.thresholds import Thresholds, DEFAULT_THRESHOLDS


@dataclass
class ScanResult:
    stale: list[StalenessResult]
    invalid: list[tuple[str, str]]  # (task_id, reason)


def _classify_tier(days: float, t: Thresholds) -> Tier:
    if days >= t.auto_expire_days:
        return Tier.AUTO_EXPIRE
    if days >= t.critical_days:
        return Tier.CRITICAL
    return Tier.WARNING


def _recommended_action(tier: Tier) -> str:
    return {
        Tier.WARNING: "nudge",
        Tier.CRITICAL: "escalate",
        Tier.AUTO_EXPIRE: "expire",
    }[tier]


def _validate_task(task: TaskRecord, now: float) -> list[str]:
    """Return list of validation error strings; empty means valid."""
    errors = []
    if not task.task_id or not task.task_id.strip():
        errors.append("empty task_id")
    if not math.isfinite(task.last_activity_at) or task.last_activity_at <= 0:
        errors.append("invalid timestamp")
    elif task.last_activity_at > now:
        errors.append("future last_activity_at")
    if task.created_at > task.last_activity_at:
        errors.append("created_at after last_activity_at")
    if task.pft_value < 0 or not math.isfinite(task.pft_value):
        errors.append("invalid pft_value")
    return errors


def scan_tasks(
    tasks: list[TaskRecord],
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    now: float | None = None,
) -> ScanResult:
    """
    Scan a list of TaskRecords and return stale tasks ranked by severity.

    Args:
        tasks: list of TaskRecord objects from the task pipeline
        thresholds: staleness tier thresholds (configurable)
        now: unix timestamp to use as "current time" (defaults to time.time();
             injectable for deterministic testing)

    Returns:
        ScanResult with .stale (sorted descending by days_stale) and .invalid list.
    """
    if now is None:
        now = time.time()

    results: list[StalenessResult] = []
    invalid: list[tuple[str, str]] = []

    for task in tasks:
        errors = _validate_task(task, now)
        if errors:
            invalid.append((task.task_id, "; ".join(errors)))
            continue

        if task.status.strip().lower() != "in_progress":
            continue

        # Exempt if submitted for verification AND submission is recent
        if task.verification_submitted_at is not None:
            days_since_submission = (now - task.verification_submitted_at) / 86400.0
            if days_since_submission < thresholds.auto_expire_days:
                continue  # awaiting adjudication, not abandoned
            # else: submission is itself stale — fall through and flag it

        days_stale = (now - task.last_activity_at) / 86400.0

        if days_stale < thresholds.warning_days:
            continue  # not stale yet

        tier = _classify_tier(days_stale, thresholds)
        is_unknown = task.owner in ("unknown_user", "", None)
        action = _recommended_action(tier)

        notes = []
        if is_unknown:
            notes.append("unknown_user: no owner to notify, immediate expire recommended")
        if days_stale >= 60:
            notes.append(f"severely stale: {days_stale:.1f} days — Director-flagged slot")

        results.append(StalenessResult(
            task_id=task.task_id,
            owner=task.owner,
            tier=tier,
            days_stale=round(days_stale, 2),
            recommended_action=action,
            pft_value=task.pft_value,
            last_activity_at=task.last_activity_at,
            is_unknown_owner=is_unknown,
            notes=notes,
            owner_resolution_required=is_unknown,
        ))

    # Sort descending by days_stale, ties broken by task_id ascending
    results.sort(key=lambda r: (-r.days_stale, r.task_id))
    return ScanResult(stale=results, invalid=invalid)
