"""
schema.py — Data types for the Stale Task Detection module.

TaskRecord: input task object the scanner consumes.
StalenessResult: output from the scanner for a single stale task.
Tier: staleness severity enum with configurable day thresholds.

Integration note:
    TaskRecord maps directly to task fields present in the Task Node
    adjudication pipeline (status, created_at, last_activity_at, owner,
    task_id, pft_value). The scanner is designed to be called as a
    pre-acceptance check before new task slots are assigned, and as a
    periodic background sweep to reclaim abandoned slots.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Tier(Enum):
    WARNING = "warning"         # 14–29 days stale — nudge owner
    CRITICAL = "critical"       # 30–44 days stale — escalate to network
    AUTO_EXPIRE = "auto-expire" # 45+ days stale — recommend slot reclaim


@dataclass
class TaskRecord:
    task_id: str
    status: str                    # "in_progress", "submitted", "complete", etc.
    created_at: float              # unix timestamp
    last_activity_at: float        # unix timestamp of last update/submission
    owner: str                     # wallet address or "unknown_user"
    pft_value: float = 0.0
    verification_submitted_at: float | None = None  # unix timestamp when submitted for verification; None = not submitted


@dataclass
class StalenessResult:
    task_id: str
    owner: str
    tier: Tier
    days_stale: float
    recommended_action: str        # "nudge" / "escalate" / "expire"
    pft_value: float
    last_activity_at: float
    is_unknown_owner: bool         # True if owner == "unknown_user" or empty
    notes: list[str] = field(default_factory=list)
    owner_resolution_required: bool = False  # True if owner is unknown/empty — requires manual reclaim regardless of tier
