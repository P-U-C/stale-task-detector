"""
scanner.py — Staleness scanner for the Task Node adjudication pipeline.

Scanning logic:
    1. Only tasks with status == "in_progress" are scanned.
       Tasks submitted for verification (has_verification_submission=True)
       are exempt even if they exceed the warning threshold — the owner
       acted; the network owes them a decision.
    2. Days stale is computed from last_activity_at (not created_at),
       so a task that had recent activity is not penalized for an old
       creation date.
    3. Results are sorted descending by days_stale (most urgent first).
       Ties broken by task_id ascending (deterministic).
    4. unknown_user owner is handled gracefully — flagged in is_unknown_owner,
       recommended_action defaults to "expire" at WARNING tier (no owner to
       nudge, reclaim slot immediately).

Integration with Authorization Gate cooldown:
    AUTO_EXPIRE results should be fed into the cooldown escalation logic
    defined in the Auth Gate enforcement spec. An AUTO_EXPIRE recommendation
    translates to: set owner state to PROBATIONARY, block new task acceptance
    for cooldown_period_days, emit expiry event to chain envelope.
"""
import time
from stale_task_detector.schema import TaskRecord, StalenessResult, Tier
from stale_task_detector.thresholds import Thresholds, DEFAULT_THRESHOLDS


def _classify_tier(days: float, t: Thresholds) -> Tier:
    if days >= t.auto_expire_days:
        return Tier.AUTO_EXPIRE
    if days >= t.critical_days:
        return Tier.CRITICAL
    return Tier.WARNING


def _recommended_action(tier: Tier, is_unknown: bool) -> str:
    if is_unknown:
        # No owner to notify — escalate directly to expire
        return "expire"
    return {
        Tier.WARNING: "nudge",
        Tier.CRITICAL: "escalate",
        Tier.AUTO_EXPIRE: "expire",
    }[tier]


def scan_tasks(
    tasks: list[TaskRecord],
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    now: float | None = None,
) -> list[StalenessResult]:
    """
    Scan a list of TaskRecords and return stale tasks ranked by severity.

    Args:
        tasks: list of TaskRecord objects from the task pipeline
        thresholds: staleness tier thresholds (configurable)
        now: unix timestamp to use as "current time" (defaults to time.time();
             injectable for deterministic testing)

    Returns:
        list of StalenessResult, sorted descending by days_stale.
        Only tasks with status=="in_progress" AND has_verification_submission==False
        AND days_stale >= thresholds.warning_days are included.
    """
    if now is None:
        now = time.time()

    results: list[StalenessResult] = []

    for task in tasks:
        if task.status != "in_progress":
            continue
        if task.has_verification_submission:
            continue  # owner acted — exempt from expiry

        days_stale = (now - task.last_activity_at) / 86400.0

        if days_stale < thresholds.warning_days:
            continue  # not stale yet

        tier = _classify_tier(days_stale, thresholds)
        is_unknown = task.owner in ("unknown_user", "", None)
        action = _recommended_action(tier, is_unknown)

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
        ))

    # Sort descending by days_stale, ties broken by task_id ascending
    results.sort(key=lambda r: (-r.days_stale, r.task_id))
    return results
