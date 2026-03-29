# Write a task spec

Read CLAUDE.md for project conventions and current product state.

I'm going to describe a task in plain English. Convert it into a structured spec:

```markdown
## Task: [One-line description]

### Context
[Project state relevant to this task]

### Goal
[What "done" looks like in plain English]

### Acceptance Criteria
- [ ] [Specific, testable criterion]

### Constraints
- [Tech stack constraints from CLAUDE.md]
- [Things NOT to do — reference MISTAKES.md]

### Files to Touch
- [Files to create or modify]

### Verify By
- [How to check without reading the code]

### Model Routing
- [opus/sonnet/flash — and why]
```

Ask clarifying questions if my description is too vague. Don't fill gaps with assumptions.
