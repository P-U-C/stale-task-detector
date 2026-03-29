# Execute an approved plan

Read CLAUDE.md for project conventions.
Read the approved plan.

Execute it:
1. Follow the plan exactly. Do not deviate or add features.
2. If the plan needs changes, STOP and explain. Do not improvise.
3. Write all code in one pass for simple plans; step by step for complex ones.
4. Run tests after implementation.
5. Report: files created, files modified, tests passing/failing, anything surprising.

Hard constraints:
- Named exports only (no default exports)
- No `any` types
- No `console.log` in production code
- Tests in `tests/` mirroring `src/` structure
- Conventional commits
