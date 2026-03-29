# stale-task-detector

Detects stale in-progress tasks in the Post Fiat Task Node pipeline and recommends expiry actions (nudge → escalate → auto-expire) based on configurable day thresholds.

---

## Setup

```bash
# Option A — install as editable package
pip install -e ".[dev]"

# Option B — no install, just run from repo root
PYTHONPATH=. pytest tests/ -v
```

## Run Tests

```bash
pytest tests/ -v
```

All 16 tests should pass. No network or wall-clock dependencies.

---

## Quick Example

```python
from stale_task_detector import TaskRecord, scan_tasks, build_notification_batch, to_json
import time

now = time.time()

tasks = [
    TaskRecord("task-001", "in_progress", now - 70*86400, now - 68*86400, "0xAlice",   pft_value=500.0),
    TaskRecord("task-002", "in_progress", now - 40*86400, now - 27*86400, "0xBob",     pft_value=200.0),
    TaskRecord("task-003", "in_progress", now - 35*86400, now - 31*86400, "0xCarol",   pft_value=150.0),
    TaskRecord("task-004", "in_progress", now - 65*86400, now - 61*86400, "unknown_user", pft_value=0.0),
]

results = scan_tasks(tasks)
for r in results:
    print(f"{r.task_id}  {r.tier.value:12s}  {r.days_stale:.0f}d  {r.recommended_action}")

# task-001  auto-expire   68d  expire
# task-004  auto-expire   61d  expire       ← unknown_user, direct expire
# task-003  critical      31d  escalate
# task-002  warning       27d  nudge

notifications = build_notification_batch(results)
print(to_json(notifications))
```

4 of 4 tasks are flagged. Results are ranked most-urgent first.

---

## Tier Rationale

| Tier | Days Stale | Action | Why |
|------|-----------|--------|-----|
| `warning` | 14–29 | nudge owner | Two full weeks of silence — owner likely forgot or is blocked |
| `critical` | 30–44 | escalate to network | One month — requires governance visibility |
| `auto-expire` | 45+ | reclaim slot | Six weeks — no reasonable path to completion; slot is blocking others |

Thresholds are fully configurable:

```python
from stale_task_detector import Thresholds, scan_tasks
custom = Thresholds(warning_days=7, critical_days=21, auto_expire_days=35)
results = scan_tasks(tasks, thresholds=custom)
```

---

## Integration

### Task Node Acceptance Pipeline

Call `scan_tasks()` as a **pre-acceptance check** before assigning new task slots:

```python
stale = scan_tasks(active_tasks)
blocked_owners = {r.owner for r in stale if r.tier == Tier.AUTO_EXPIRE}
if candidate_owner in blocked_owners:
    raise TaskSlotBlocked(f"{candidate_owner} has an auto-expired task pending reclaim")
```

### Auth Gate Cooldown

`AUTO_EXPIRE` results map directly to the Auth Gate enforcement spec:

```
AUTO_EXPIRE → set owner state = PROBATIONARY
           → block new task acceptance for cooldown_period_days
           → emit expiry event to chain envelope
```

Feed expired results into the cooldown escalation logic:

```python
for result in stale:
    if result.tier == Tier.AUTO_EXPIRE:
        auth_gate.set_probationary(result.owner, cooldown_days=30)
        chain_envelope.emit_expiry(result.task_id, result.owner)
```

---

## Director Brief Context

This module was built in response to a Director-flagged audit revealing:

| Task | Owner | Days Stale | Status |
|------|-------|-----------|--------|
| task-007 | 0xAlice | 68 days | AUTO_EXPIRE |
| task-012 | unknown_user | 61 days | AUTO_EXPIRE (direct expire — no owner) |
| task-019 | 0xBob | 31 days | CRITICAL |
| task-023 | 0xCarol | 27 days | WARNING |

Three tasks have been stalled 27–68 days. One slot is held by `unknown_user` with no reclaim path — the scanner flags this and recommends immediate slot reclaim regardless of tier.

---

## Project Structure

```
stale-task-detector/
├── README.md
├── pyproject.toml
├── requirements.txt
├── stale_task_detector/
│   ├── __init__.py
│   ├── schema.py       # TaskRecord, StalenessResult, Tier
│   ├── scanner.py      # scan_tasks()
│   ├── notifier.py     # build_notification(), build_notification_batch(), to_json()
│   └── thresholds.py   # Thresholds dataclass + DEFAULT_THRESHOLDS
└── tests/
    ├── __init__.py
    └── test_detector.py
```

## License

MIT
