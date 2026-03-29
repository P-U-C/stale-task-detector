"""
thresholds.py — Configurable staleness thresholds.

Defaults match the Director brief:
    WARNING:     14 days (tasks stalled without activity)
    CRITICAL:    30 days (escalate to network governance)
    AUTO_EXPIRE: 45 days (recommend slot reclaim + cooldown trigger)

Override at runtime:
    from stale_task_detector.thresholds import Thresholds
    custom = Thresholds(warning_days=7, critical_days=21, auto_expire_days=35)
    results = scan_tasks(tasks, thresholds=custom)
"""
from dataclasses import dataclass


@dataclass
class Thresholds:
    warning_days: float = 14.0
    critical_days: float = 30.0
    auto_expire_days: float = 45.0

    def __post_init__(self):
        if not (0 < self.warning_days < self.critical_days < self.auto_expire_days):
            raise ValueError(
                f"Thresholds must be strictly increasing: "
                f"{self.warning_days} < {self.critical_days} < {self.auto_expire_days}"
            )


DEFAULT_THRESHOLDS = Thresholds()
