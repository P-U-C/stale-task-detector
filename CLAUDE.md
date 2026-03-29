# CLAUDE.md — Project Memory

> Read this at the start of every session.

## Project
Post Fiat oracle scoring and task management module

## Agent Workflow (agentify)

Loop: `/spec` → `/plan` → iterate → `/execute` → `/review` → commit → `/mistake`

| File | Purpose |
|------|---------|
| `.claude/agents/implementer.md` | sonnet — write code, follow plan exactly |
| `.claude/agents/reviewer.md` | opus — read-only, structured 🟢/🟡/🔴 |
| `.claude/commands/` | /spec /plan /execute /review /mistake |
| `MISTAKES.md` | Error corpus — append-only, weekly → CLAUDE.md |
| `specs/` | Spec history |

## Conventions
- Named exports only
- No `any` type
- No `console.log` in production code
- Tests in `tests/` mirroring `src/`
- Conventional commits

## Mistakes Log Reference
See `MISTAKES.md`. Patterns that repeat become rules here.
